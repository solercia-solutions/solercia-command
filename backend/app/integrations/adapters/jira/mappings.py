"""Jira -> platform homologation tables (change 18-adapter-jira, design.md
"Vocabulario de normalización anclado al código real"). Anchored to the
REAL enums the platform already has (``app/shared/enums.py``'s ``Priority``
and ``TaskType``) rather than an invented one — ``Task.status``/
``Task.task_type`` are free-text columns validated per-methodology, so this
module derives a stable, small vocabulary instead of forcing a global enum
that does not exist (design.md Architecture Decisions).

Every resolver returns ``(value, mapped)`` — ``mapped=False`` tells the
caller (``normalizer.py``) the value came from a FALLBACK, which the caller
then feeds into the ``NormalizationReport`` (specs/jira-import/spec.md
"Homologación ... con fallback y reporte").
"""

from collections.abc import Mapping
from dataclasses import dataclass

# Jira Cloud's own type names, lowercased. `subtask` is resolved separately
# via the `issuetype.subtask` boolean (never by name — Jira instances name
# it "Sub-task"/"Subtarea"/etc. depending on locale).
DEFAULT_TYPE_MAP: dict[str, str] = {
    "epic": "epic",
    "story": "story",
    "task": "task",
    "bug": "bug",
    "sub-task": "subtask",
    "subtask": "subtask",
}
_TYPE_FALLBACK = "task"

# Common Jira Cloud default workflow status names, lowercased -> platform
# bucket. A CUSTOM workflow status (renamed/added by the organization) that
# is not in this table falls back to `statusCategory` (`resolve_status`).
DEFAULT_STATUS_MAP: dict[str, str] = {
    "to do": "todo",
    "open": "todo",
    "backlog": "todo",
    "in progress": "in_progress",
    "in review": "in_progress",
    "done": "done",
    "closed": "done",
}
# Jira's own `statusCategory.key` -> platform bucket (design.md, "deriva un
# bucket estable de statusCategory: new→todo, indeterminate→in_progress,
# done→done").
STATUS_CATEGORY_BUCKET: dict[str, str] = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
}
_STATUS_FALLBACK = "todo"

# Jira Cloud's default priority scheme, lowercased -> the platform's real
# `Priority` enum (`app/shared/enums.py`).
DEFAULT_PRIORITY_MAP: dict[str, str] = {
    "highest": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "lowest": "low",
}
_PRIORITY_FALLBACK = "medium"


@dataclass(frozen=True)
class JiraMappings:
    """Fully-merged (defaults + connector overrides) homologation tables
    for ONE import run — built once by :func:`build_mappings`, never
    mutated afterwards."""

    type_map: Mapping[str, str]
    status_map: Mapping[str, str]
    priority_map: Mapping[str, str]


def _merged(default: Mapping[str, str], override: object) -> dict[str, str]:
    """Lowercase-key merge: `override` entries win, every default entry
    NOT overridden survives untouched (specs/jira-import/spec.md
    'Override cuando el nombre no calza' never means "replace the whole
    table")."""

    merged = {key.lower(): value for key, value in default.items()}
    if isinstance(override, Mapping):
        merged.update({str(key).lower(): str(value) for key, value in override.items()})
    return merged


def build_mappings(jira_settings: Mapping[str, object] | None) -> JiraMappings:
    """Build the effective homologation tables for a connector's
    ``settings.jira`` payload (``None``/absent keys -> pure defaults)."""

    settings = jira_settings or {}
    return JiraMappings(
        type_map=_merged(DEFAULT_TYPE_MAP, settings.get("type_map")),
        status_map=_merged(DEFAULT_STATUS_MAP, settings.get("status_map")),
        priority_map=_merged(DEFAULT_PRIORITY_MAP, settings.get("priority_map")),
    )


def resolve_type(
    type_name: str, *, is_subtask: bool, mappings: JiraMappings
) -> tuple[str, bool]:
    """Resolve a Jira issue type to the platform's ``issue_type`` vocabulary.

    ``is_subtask`` (Jira's own ``issuetype.subtask`` boolean) wins over the
    display name — a subtask is ALWAYS ``subtask`` regardless of how the
    Jira instance/locale labels it.
    """

    if is_subtask:
        return "subtask", True
    resolved = mappings.type_map.get(type_name.strip().lower())
    if resolved is not None:
        return resolved, True
    return _TYPE_FALLBACK, False


def resolve_status(
    status_name: str, *, status_category_key: str | None, mappings: JiraMappings
) -> tuple[str, bool]:
    """Resolve a Jira status to the platform's status bucket.

    An EXACT name match (default or connector override) wins first; when
    the name does not calzar, ``statusCategory`` decides (design.md); a
    file-vía row with no category at all falls back to ``todo``.
    """

    resolved = mappings.status_map.get(status_name.strip().lower())
    if resolved is not None:
        return resolved, True
    if status_category_key is not None:
        return STATUS_CATEGORY_BUCKET.get(status_category_key, _STATUS_FALLBACK), False
    return _STATUS_FALLBACK, False


def resolve_priority(priority_name: str, *, mappings: JiraMappings) -> tuple[str, bool]:
    """Resolve a Jira priority to the platform's real ``Priority`` enum."""

    resolved = mappings.priority_map.get(priority_name.strip().lower())
    if resolved is not None:
        return resolved, True
    return _PRIORITY_FALLBACK, False
