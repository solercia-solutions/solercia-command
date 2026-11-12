"""Closed vocabularies of the plans module (change 45a, design.md D-J).

Plain ``frozenset[str]`` constants plus pure validators. Deliberately NOT
PostgreSQL enums or ``SAEnum`` (D12): a new value is a one-line change here and
zero migrations. The importer of a later change reads these without importing
the service (and with it a session and its dependencies).
"""

from decimal import Decimal

from app.shared.exceptions import AppException

PLAN_TYPES: frozenset[str] = frozenset({"pspi", "ptr", "pai", "ptep"})
PLAN_STATUSES: frozenset[str] = frozenset({"active", "archived"})
REPORT_PERIODS: frozenset[str] = frozenset({"I", "II", "III", "ANUAL"})
TASK_LINK_ROLES: frozenset[str] = frozenset({"primary", "contributes"})
ACTIVITY_LINK_TYPES: frozenset[str] = frozenset({"contributes_to", "derives_from", "duplicates"})
# Assertions about READING A SOURCE: only the importer seam may emit the
# non-`manual` ones; the HTTP API always forces `manual` (design.md D14).
LINK_RESOLUTIONS: frozenset[str] = frozenset({"exact", "by_external_code", "conflict", "manual"})

#: Resolution that does NOT count as a confirmed link (design.md D-I/H3).
CONFLICT_RESOLUTION = "conflict"


def _validate(value: str, allowed: frozenset[str], *, code: str, label: str) -> str:
    if value not in allowed:
        options = ", ".join(sorted(allowed))
        raise AppException(
            f"El valor '{value}' no es válido para {label}. Valores permitidos: {options}.",
            code=code,
            status_code=422,
        )
    return value


def validate_plan_type(value: str) -> str:
    return _validate(value, PLAN_TYPES, code="plan_type_invalid", label="el tipo de plan")


def validate_plan_status(value: str) -> str:
    return _validate(value, PLAN_STATUSES, code="plan_status_invalid", label="el estado del plan")


def validate_period(value: str) -> str:
    return _validate(value, REPORT_PERIODS, code="plan_period_invalid", label="el periodo")


def validate_task_link_role(value: str) -> str:
    return _validate(
        value,
        TASK_LINK_ROLES,
        code="plan_task_link_role_invalid",
        label="el rol del enlace con la tarea",
    )


def validate_activity_link_type(value: str) -> str:
    return _validate(
        value,
        ACTIVITY_LINK_TYPES,
        code="plan_activity_link_type_invalid",
        label="el tipo de enlace entre actividades",
    )


def validate_resolution(value: str) -> str:
    return _validate(
        value,
        LINK_RESOLUTIONS,
        code="plan_resolution_invalid",
        label="la resolución del enlace",
    )


def validate_reported_progress(value: Decimal | float | int | None) -> None:
    """Require ``0 <= value <= 100`` (``None`` means "not reported" and passes).

    Raises ``plan_progress_out_of_range`` (422). A dedicated validator instead
    of ``ge/le`` in the schema so the code is stable and the importer seam,
    which does not go through the HTTP schema, can defend the range too.
    """

    if value is None:
        return
    if value < 0 or value > 100:
        raise AppException(
            "El avance reportado debe estar entre 0 y 100.",
            code="plan_progress_out_of_range",
            status_code=422,
        )
