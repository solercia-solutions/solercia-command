"""Jira-specific DTOs (change 18-adapter-jira, design.md "Interfaces /
Contracts"). Deliberately NOT the core's thin ``Ticket`` (``app/
integrations/dtos.py``) — the import needs type/assignee/sprint/points/
labels the generic ticketing port never models (design.md Architecture
Decisions, "DTO propio NormalizedJiraIssue, no el Ticket del puerto").

Frozen dataclasses: a normalized issue is a pure snapshot of one Jira
issue/row, never mutated after construction — same discipline as
``app/integrations/dtos.py``'s ``Ticket``/``OAuthTokens``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NormalizedJiraIssue:
    """One Jira issue normalized to the platform's vocabulary, regardless
    of which via (API or file) produced it — ``source`` is the only field
    that tells them apart (specs/jira-import/spec.md "Convergencia entre
    vías").

    ``assignee_raw``/``labels`` are preserved exactly as Jira sent them —
    homologating them against platform users/labels is out of scope for
    this change (specs/jira-import/spec.md "Asignado y labels se
    conservan crudos").
    """

    key: str
    title: str
    description: str | None
    issue_type: str
    status_raw: str
    status_bucket: str
    priority: str
    assignee_raw: str | None
    sprint_name: str | None
    sprint_state: str | None
    story_points: float | None
    labels: tuple[str, ...]
    created_at: datetime | None
    source: str
    # Import fields (user-driven project import): all optional so every
    # existing construction keeps working. ``original_estimate_seconds`` is
    # Jira's ``timeoriginalestimate``; ``assignee_email`` keeps
    # ``assignee.emailAddress`` (``assignee_raw`` prefers the accountId);
    # ``parent_key`` is ``parent.key`` (epic -> story -> subtask hierarchy).
    original_estimate_seconds: int | None = None
    assignee_email: str | None = None
    parent_key: str | None = None
    sprint_start_date: datetime | None = None
    sprint_end_date: datetime | None = None


@dataclass(frozen=True)
class NormalizationReport:
    """Summary of one normalization run — never descarta un issue por
    falta de homologación; cada fallback suma aquí (specs/jira-import/
    spec.md "Homologación de tipo/estado/prioridad con fallback y
    reporte").

    ``story_points_field``/``sprint_field`` carry the RESOLVED custom
    field id, or ``None`` when the Jira instance has no field matching
    that name and no override was configured (specs/jira-import/spec.md
    "Resolución configurable de custom fields").

    ``skipped_malformed`` tracks per-item normalization failures (e.g. a
    malformed ``assignee``) — isolated here instead of aborting the batch.
    """

    total: int
    normalized: int
    unmapped_types: dict[str, int]
    unmapped_statuses: dict[str, int]
    unmapped_priorities: dict[str, int]
    story_points_field: str | None
    sprint_field: str | None
    source: str
    skipped_malformed: tuple[dict[str, Any], ...] = ()
