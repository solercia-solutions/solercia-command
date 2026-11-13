"""Pure preview of a Jira project import (no database, no network).

Given the normalized issues of ONE Jira project and the target
methodology strategy, it computes what the import would create: counts per
type, the sprints found, the proposed status mapping and the estimation
totals. The importer uses the SAME helpers, so the preview never promises
something the import would do differently.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.methodology.base import MethodologyStrategy
from app.modules.jira_import.mapper import SPRINT_STATUS_BY_JIRA_STATE
from app.shared.exceptions import AppException

PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+$")
_CODE_MAX = 10
_DEFAULT_SPRINT_STATUS = "draft"
_HOURS_QUANTUM = Decimal("0.01")


def require_project_key(value: str) -> str:
    """Return ``value`` when it is a safe Jira project key, else 422.

    Runs BEFORE any JQL is built or any request reaches Jira, so a key can
    never smuggle JQL (``ABC" OR 1=1``) into the search.
    """

    if not isinstance(value, str) or not PROJECT_KEY_RE.fullmatch(value):
        raise AppException(
            "La clave del proyecto de Jira no es válida. Usa solo mayúsculas y "
            "números, empezando por una letra (por ejemplo, PROJ).",
            code="jira_project_key_invalid",
            status_code=422,
        )
    return value


def project_jql(project_key: str) -> str:
    """JQL of every issue of one project (key already validated)."""

    return f'project = "{require_project_key(project_key)}" ORDER BY key ASC'


def suggested_code(project_key: str) -> str:
    """Local project code derived from the Jira key (2-10 characters)."""

    return project_key[:_CODE_MAX]


def seconds_to_hours(seconds: int | None) -> Decimal | None:
    """Jira ``timeoriginalestimate`` (seconds) -> hours, ``Decimal(s) / 3600``."""

    if seconds is None:
        return None
    return (Decimal(seconds) / Decimal(3600)).quantize(_HOURS_QUANTUM)


def story_points_to_int(points: float | None) -> int | None:
    """Story points as the integer ``estimation_points`` (rounded up)."""

    return None if points is None else int(math.ceil(points))


def status_for_bucket(bucket: str, allowed: Sequence[str]) -> str:
    """Project a Jira status bucket onto the strategy's allowed statuses.

    ``todo`` -> first, ``done`` -> last, ``in_progress`` -> the first
    interior status (or the first one when there is no interior status).
    Reads only the strategy's ordered list; never a methodology name.
    """

    if not allowed:
        raise AppException(
            "La metodología del proyecto destino no define estados para las tareas.",
            code="jira_import_no_statuses",
            status_code=422,
        )
    if bucket == "done":
        return allowed[-1]
    if bucket == "in_progress":
        return allowed[1] if len(allowed) > 2 else allowed[0]
    return allowed[0]


def resolve_status(
    issue: NormalizedJiraIssue,
    allowed: Sequence[str],
    overrides: Mapping[str, str] | None = None,
) -> str:
    """Target status of one issue: an explicit override wins over the bucket."""

    override = (overrides or {}).get(issue.status_raw)
    if override is not None:
        return override
    return status_for_bucket(issue.status_bucket, allowed)


def validate_overrides(overrides: Mapping[str, str] | None, allowed: Sequence[str]) -> None:
    """Every override target must be one of the strategy's statuses."""

    invalid = sorted(target for target in (overrides or {}).values() if target not in allowed)
    if invalid:
        raise AppException(
            f"Estos estados no existen en el proyecto destino: {', '.join(invalid)}.",
            code="jira_import_status_override_invalid",
            status_code=422,
        )


def sprint_status(jira_state: str | None) -> str:
    """Jira sprint state -> Command sprint status (``future`` -> ``draft``)."""

    return SPRINT_STATUS_BY_JIRA_STATE.get((jira_state or "").lower(), _DEFAULT_SPRINT_STATUS)


@dataclass(frozen=True)
class SprintPreview:
    name: str
    jira_state: str | None
    status: str
    start_date: datetime | None
    end_date: datetime | None
    issues: int


@dataclass(frozen=True)
class StatusMappingPreview:
    jira_status: str
    bucket: str
    target_status: str
    issues: int


@dataclass(frozen=True)
class PreviewResult:
    total: int
    counts_by_type: dict[str, int]
    sprints: list[SprintPreview]
    status_mapping: list[StatusMappingPreview]
    target_statuses: list[str]
    estimated_hours: Decimal
    issues_with_estimate: int
    story_points: int
    issues_with_points: int
    unmapped_types: dict[str, int]
    unmapped_statuses: dict[str, int]
    unmapped_priorities: dict[str, int]
    skipped_malformed: int
    sample_keys: list[str] = field(default_factory=list)


def build_preview(
    issues: Sequence[NormalizedJiraIssue],
    report: NormalizationReport,
    *,
    strategy: MethodologyStrategy,
) -> PreviewResult:
    """Counts and proposed mapping for ``issues`` — pure, persists nothing."""

    allowed = strategy.allowed_statuses()
    counts: dict[str, int] = {}
    statuses: dict[str, StatusMappingPreview] = {}
    sprints: dict[str, SprintPreview] = {}
    hours = Decimal(0)
    with_estimate = points = with_points = 0

    for issue in issues:
        counts[issue.issue_type] = counts.get(issue.issue_type, 0) + 1

        current = statuses.get(issue.status_raw)
        statuses[issue.status_raw] = StatusMappingPreview(
            jira_status=issue.status_raw,
            bucket=issue.status_bucket,
            target_status=status_for_bucket(issue.status_bucket, allowed),
            issues=(current.issues if current else 0) + 1,
        )

        if issue.sprint_name:
            seen = sprints.get(issue.sprint_name)
            sprints[issue.sprint_name] = SprintPreview(
                name=issue.sprint_name,
                jira_state=issue.sprint_state or (seen.jira_state if seen else None),
                status=sprint_status(issue.sprint_state or (seen.jira_state if seen else None)),
                start_date=issue.sprint_start_date or (seen.start_date if seen else None),
                end_date=issue.sprint_end_date or (seen.end_date if seen else None),
                issues=(seen.issues if seen else 0) + 1,
            )

        issue_hours = seconds_to_hours(issue.original_estimate_seconds)
        if issue_hours is not None:
            hours += issue_hours
            with_estimate += 1
        issue_points = story_points_to_int(issue.story_points)
        if issue_points is not None:
            points += issue_points
            with_points += 1

    return PreviewResult(
        total=len(issues),
        counts_by_type=counts,
        sprints=list(sprints.values()),
        status_mapping=sorted(statuses.values(), key=lambda item: item.jira_status.lower()),
        target_statuses=list(allowed),
        estimated_hours=hours,
        issues_with_estimate=with_estimate,
        story_points=points,
        issues_with_points=with_points,
        unmapped_types=dict(report.unmapped_types),
        unmapped_statuses=dict(report.unmapped_statuses),
        unmapped_priorities=dict(report.unmapped_priorities),
        skipped_malformed=len(report.skipped_malformed),
        sample_keys=[issue.key for issue in issues[:5]],
    )
