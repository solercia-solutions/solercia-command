"""Immutable Generales definition and pure guards; no provisioning or I/O.

The shape constraint is not historical immutability: direct SQL can unmark or
hard-delete rows. Bootstrap, repair and maintenance protections are separate.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.shared.exceptions import AppException


@dataclass(frozen=True, slots=True)
class SystemProjectDefinition:
    code: str
    methodology: str
    statuses: tuple[str, ...]


GENERALES = SystemProjectDefinition(
    code="GENERALES",
    methodology="custom",
    statuses=(
        "PENDIENTE", "EN CURSO", "DIFERIDA", "RECURRENTE",
        "GESTIONADA APARTE", "REMOVIDA", "COMPLETADA",
    ),
)

_PROTECTED_FIELDS = frozenset({
    "code", "methodology", "status", "is_active", "deleted_at", "is_system",
})


def reject_reserved_project_code(code: str | None) -> None:
    if code is not None and code.strip().upper() == GENERALES.code:
        raise AppException(
            "El código GENERALES está reservado para el proyecto del sistema.",
            code="reserved_project_code",
            status_code=422,
        )


def guard_system_project_update(is_system: bool, changes: Mapping[str, object]) -> None:
    """Reject protected fields, including redundant submissions, before writes."""
    if is_system and _PROTECTED_FIELDS.intersection(changes):
        guard_system_board_configuration(True)


def guard_system_board_configuration(is_system: bool) -> None:
    if is_system:
        raise AppException(
            "La configuración del proyecto del sistema no se puede modificar.",
            code="system_project_protected",
            status_code=422,
        )
