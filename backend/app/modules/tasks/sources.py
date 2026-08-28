"""Vocabulary for externally originated tasks.

The value is deliberately application-validated rather than a PostgreSQL
enum: registering a new provider must not require a schema migration.
"""

from typing import Final

from app.shared.exceptions import AppException

KNOWN_TASK_SOURCES: Final[frozenset[str]] = frozenset(
    {
        "checklist_xlsx",
        "microsoft365",
        "google",
        "jira",
        "glpi",
        "mcp",
        "fake",
        "solercia_connect",
    }
)


def validate_task_source(value: str) -> str:
    """Return a known task source or raise the public validation error."""

    if value not in KNOWN_TASK_SOURCES:
        raise AppException(
            "El sistema de origen indicado no es válido para una tarea.",
            code="invalid_task_source",
            status_code=422,
        )
    return value
