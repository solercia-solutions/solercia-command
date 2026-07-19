"""raw -> ``NormalizedJiraIssue`` (change 18-adapter-jira, design.md
"Normalizador"). The ONE homologation boundary both vias converge on:
``normalize_api_issue``/``normalize_file_row`` each build a CANONICAL flat
dict from their own raw shape (nested Jira API JSON vs. a parsed file row)
and hand it to the SAME private ``_build_issue`` — the single place that
resolves type/status/priority and constructs the DTO (specs/jira-import/
spec.md "Convergencia entre vías": the same issue via either route produces
an equivalent ``NormalizedJiraIssue``).

Never descarta un issue por falta de homologación — every fallback is
tracked via ``_UnmappedFlags`` and aggregated into a ``NormalizationReport``
by the ``*_batch`` functions (specs/jira-import/spec.md "Homologación ...
con fallback y reporte").
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.integrations.adapters.jira.mappings import (
    JiraMappings,
    resolve_priority,
    resolve_status,
    resolve_type,
)

_UNKNOWN_LABEL = "desconocido"

# Matches a trailing timezone offset WITHOUT a colon (e.g. "+0000") so it
# can be normalized to "+00:00" before `datetime.fromisoformat` — Jira's
# `created`/`updated` timestamps use the colon-less form.
_TZ_NO_COLON_RE = re.compile(r"([+-]\d{2})(\d{2})$")

# Sub-task type names Jira/locale variants use — resolved from the FILE
# vía's plain "Issue Type" text column (the API vía uses `issuetype.subtask`
# instead, a real boolean, never a name guess).
_FILE_SUBTASK_NAMES = frozenset({"sub-task", "subtask"})


@dataclass(frozen=True)
class _UnmappedFlags:
    """Per-issue fallback tracking — ``None`` means that field mapped
    exactly; a non-``None`` value is the raw Jira value the caller's batch
    function should count into the matching ``NormalizationReport`` bucket.
    """

    type_raw: str | None = None
    status_raw: str | None = None
    priority_raw: str | None = None


def _adf_to_text(node: Any) -> str:
    """Flatten an Atlassian Document Format node tree to plain text."""

    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    node_type = node.get("type")
    if node_type == "text":
        return str(node.get("text", ""))
    parts = "".join(_adf_to_text(child) for child in node.get("content") or [])
    if node_type in ("paragraph", "heading", "blockquote", "codeBlock"):
        return f"{parts}\n"
    return parts


def _normalize_description(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _adf_to_text(value).strip() or None
    return None


def _parse_jira_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = _TZ_NO_COLON_RE.sub(r"\1:\2", value)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_assignee_from_api(assignee: Mapping[str, Any] | None) -> str | None:
    if not assignee:
        return None
    return assignee.get("accountId") or assignee.get("emailAddress") or assignee.get(
        "displayName"
    )


def _extract_sprint_from_api(value: Any) -> tuple[str | None, str | None]:
    """A Jira Cloud sprint custom field is a list — either plain sprint
    NAME strings (older/simpler instances) or richer ``{id, name, state}``
    objects. The LAST entry is the most recently assigned sprint."""

    if not value or not isinstance(value, Sequence):
        return None, None
    last = value[-1]
    if isinstance(last, str):
        return last, None
    if isinstance(last, Mapping):
        return last.get("name"), last.get("state")
    return None, None


def _canonical_from_api_issue(
    raw_issue: Mapping[str, Any],
    *,
    story_points_field: str | None,
    sprint_field: str | None,
) -> dict[str, Any]:
    fields = raw_issue.get("fields") or {}
    issuetype = fields.get("issuetype") or {}
    status = fields.get("status") or {}
    status_category = (status.get("statusCategory") or {}).get("key")
    priority = fields.get("priority") or {}
    story_points = fields.get(story_points_field) if story_points_field else None
    sprint_name, sprint_state = _extract_sprint_from_api(
        fields.get(sprint_field) if sprint_field else None
    )

    return {
        "key": raw_issue.get("key", ""),
        "summary": fields.get("summary") or "",
        "description": fields.get("description"),
        "issue_type_name": issuetype.get("name") or "",
        "is_subtask": bool(issuetype.get("subtask", False)),
        "status_name": status.get("name") or "",
        "status_category": status_category,
        "priority_name": priority.get("name") or "",
        "assignee_raw": _extract_assignee_from_api(fields.get("assignee")),
        "sprint_name": sprint_name,
        "sprint_state": sprint_state,
        "story_points": float(story_points) if isinstance(story_points, int | float) else None,
        "labels": list(fields.get("labels") or []),
        "created_at": _parse_jira_datetime(fields.get("created")),
        "source": "api",
    }


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _canonical_from_file_row(row: Mapping[str, Any]) -> dict[str, Any]:
    labels = _as_list(row.get("Labels"))
    sprint_values = _as_list(row.get("Sprint"))
    story_points_raw = row.get("Story Points")
    story_points: float | None
    try:
        story_points = (
            float(story_points_raw) if story_points_raw not in (None, "") else None
        )
    except (TypeError, ValueError):
        story_points = None

    issue_type_name = str(row.get("Issue Type") or "")

    return {
        "key": row.get("Issue key") or "",
        "summary": row.get("Summary") or "",
        "description": row.get("Description"),
        "issue_type_name": issue_type_name,
        "is_subtask": issue_type_name.strip().lower() in _FILE_SUBTASK_NAMES,
        "status_name": row.get("Status") or "",
        "status_category": None,
        "priority_name": row.get("Priority") or "",
        "assignee_raw": row.get("Assignee") or None,
        "sprint_name": sprint_values[-1] if sprint_values else None,
        "sprint_state": None,
        "story_points": story_points,
        "labels": labels,
        "created_at": _parse_jira_datetime(row.get("Created")),
        "source": "file",
    }


def _build_issue(
    canonical: Mapping[str, Any], *, mappings: JiraMappings
) -> tuple[NormalizedJiraIssue, _UnmappedFlags]:
    type_name = canonical["issue_type_name"] or _UNKNOWN_LABEL
    status_name = canonical["status_name"] or _UNKNOWN_LABEL
    priority_name = canonical["priority_name"] or _UNKNOWN_LABEL

    issue_type, type_mapped = resolve_type(
        type_name, is_subtask=canonical["is_subtask"], mappings=mappings
    )
    status_bucket, status_mapped = resolve_status(
        status_name, status_category_key=canonical["status_category"], mappings=mappings
    )
    priority, priority_mapped = resolve_priority(priority_name, mappings=mappings)

    issue = NormalizedJiraIssue(
        key=canonical["key"],
        title=canonical["summary"],
        description=_normalize_description(canonical["description"]),
        issue_type=issue_type,
        status_raw=canonical["status_name"],
        status_bucket=status_bucket,
        priority=priority,
        assignee_raw=canonical["assignee_raw"],
        sprint_name=canonical["sprint_name"],
        sprint_state=canonical["sprint_state"],
        story_points=canonical["story_points"],
        labels=tuple(canonical["labels"] or ()),
        created_at=canonical["created_at"],
        source=canonical["source"],
    )
    flags = _UnmappedFlags(
        type_raw=None if type_mapped else type_name,
        status_raw=None if status_mapped else status_name,
        priority_raw=None if priority_mapped else priority_name,
    )
    return issue, flags


def normalize_api_issue(
    raw_issue: Mapping[str, Any],
    *,
    mappings: JiraMappings,
    story_points_field: str | None,
    sprint_field: str | None,
) -> tuple[NormalizedJiraIssue, _UnmappedFlags]:
    """Normalize ONE raw Jira API issue (``GET /search/jql``'s ``issues[]``
    shape)."""

    canonical = _canonical_from_api_issue(
        raw_issue, story_points_field=story_points_field, sprint_field=sprint_field
    )
    return _build_issue(canonical, mappings=mappings)


def normalize_file_row(
    row: Mapping[str, Any], *, mappings: JiraMappings
) -> tuple[NormalizedJiraIssue, _UnmappedFlags]:
    """Normalize ONE parsed CSV/XLSX row (``file_parser.parse_file``'s
    per-row dict shape) — same homologation boundary as
    :func:`normalize_api_issue`."""

    canonical = _canonical_from_file_row(row)
    return _build_issue(canonical, mappings=mappings)


def _accumulate(counter: dict[str, int], key: str | None) -> None:
    if key is not None:
        counter[key] = counter.get(key, 0) + 1


def normalize_api_batch(
    raw_issues: Sequence[Mapping[str, Any]],
    *,
    mappings: JiraMappings,
    story_points_field: str | None,
    sprint_field: str | None,
) -> tuple[list[NormalizedJiraIssue], NormalizationReport]:
    """Normalize a full page/batch of raw API issues into
    ``(issues, report)``."""

    issues: list[NormalizedJiraIssue] = []
    unmapped_types: dict[str, int] = {}
    unmapped_statuses: dict[str, int] = {}
    unmapped_priorities: dict[str, int] = {}

    for raw_issue in raw_issues:
        issue, flags = normalize_api_issue(
            raw_issue,
            mappings=mappings,
            story_points_field=story_points_field,
            sprint_field=sprint_field,
        )
        issues.append(issue)
        _accumulate(unmapped_types, flags.type_raw)
        _accumulate(unmapped_statuses, flags.status_raw)
        _accumulate(unmapped_priorities, flags.priority_raw)

    report = NormalizationReport(
        total=len(raw_issues),
        normalized=len(issues),
        unmapped_types=unmapped_types,
        unmapped_statuses=unmapped_statuses,
        unmapped_priorities=unmapped_priorities,
        story_points_field=story_points_field,
        sprint_field=sprint_field,
        source="api",
    )
    return issues, report


def normalize_file_batch(
    rows: Sequence[Mapping[str, Any]], *, mappings: JiraMappings
) -> tuple[list[NormalizedJiraIssue], NormalizationReport]:
    """Normalize every parsed file row into ``(issues, report)`` — a file
    import never resolves custom field ids (``story_points_field``/
    ``sprint_field`` stay ``None`` in the report, design.md Data Flow)."""

    issues: list[NormalizedJiraIssue] = []
    unmapped_types: dict[str, int] = {}
    unmapped_statuses: dict[str, int] = {}
    unmapped_priorities: dict[str, int] = {}

    for row in rows:
        issue, flags = normalize_file_row(row, mappings=mappings)
        issues.append(issue)
        _accumulate(unmapped_types, flags.type_raw)
        _accumulate(unmapped_statuses, flags.status_raw)
        _accumulate(unmapped_priorities, flags.priority_raw)

    report = NormalizationReport(
        total=len(rows),
        normalized=len(issues),
        unmapped_types=unmapped_types,
        unmapped_statuses=unmapped_statuses,
        unmapped_priorities=unmapped_priorities,
        story_points_field=None,
        sprint_field=None,
        source="file",
    )
    return issues, report
