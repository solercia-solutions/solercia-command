"""Pydantic schemas for the work-calendar module.

``CalendarSource`` uses internal literals matching design.md's Architecture
Decisions verbatim (``project_root_override``/``organization_default``/
``global_default``); the public API contract (specs/work-calendar/spec.md)
requires the wire values ``team``/``organization``/``default`` instead. Both
documents are satisfied by keeping the enum internal and translating ONLY at
the ``ResolvedCalendar`` serialization boundary via ``field_serializer`` —
see the orchestrator's reconciliation note in tasks.md ("Reconciliación
aplicada" #3).
"""

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

# Default global explícito (specs/work-calendar/spec.md): 8-hour day,
# Monday(1)-Friday(5) in ISO 8601 weekday numbering. Applied only when
# NEITHER the root project override NOR the organization default resolve
# (design.md, "Data Flow" — theoretically unreachable once organizations
# is NOT NULL, kept as an explicit defensive floor).
DEFAULT_HOURS_PER_DAY = Decimal("8")
DEFAULT_WORKING_DAYS = [1, 2, 3, 4, 5]


class CalendarSource(str, Enum):
    """Where a resolved calendar came from (INTERNAL literals — design.md)."""

    project_root_override = "project_root_override"
    organization_default = "organization_default"
    global_default = "global_default"


# Translation table applied ONLY at the ResolvedCalendar JSON boundary
# (never changes the enum itself) — the public wire values required by
# specs/work-calendar/spec.md.
_WIRE_SOURCE: dict[CalendarSource, str] = {
    CalendarSource.project_root_override: "team",
    CalendarSource.organization_default: "organization",
    CalendarSource.global_default: "default",
}


def _normalize_working_days(value: list[int]) -> list[int]:
    """Shared rule: each day is ISO 1-7, no duplicates, canonical ascending order."""

    if len(value) != len(set(value)):
        raise ValueError("Los días laborables no pueden repetirse.")
    if any(day < 1 or day > 7 for day in value):
        raise ValueError(
            "Cada día laborable debe estar entre 1 (lunes) y 7 (domingo)."
        )
    return sorted(value)


class WorkCalendarConfig(BaseModel):
    """Company-wide calendar: ``PUT``/``GET`` body. Both fields are required."""

    working_hours_per_day: Decimal = Field(ge=1, le=24)
    working_days: list[int] = Field(min_length=1, max_length=7)

    @field_validator("working_days")
    @classmethod
    def _validate_working_days(cls, value: list[int]) -> list[int]:
        return _normalize_working_days(value)


class WorkCalendarOverride(BaseModel):
    """Root-project override: ``PUT``/``GET`` body. ``null`` = heredar (inherit)."""

    working_hours_per_day: Decimal | None = Field(default=None, ge=1, le=24)
    working_days: list[int] | None = Field(default=None, min_length=1, max_length=7)

    @field_validator("working_days")
    @classmethod
    def _validate_working_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        return _normalize_working_days(value)

    @model_validator(mode="after")
    def _validate_pair(self) -> "WorkCalendarOverride":
        has_hours = self.working_hours_per_day is not None
        has_days = self.working_days is not None
        if has_hours != has_days:
            raise ValueError(
                "Los dos campos deben enviarse juntos: ambos con valor para "
                "fijar el override, o ambos null para volver a heredar."
            )
        return self


class ResolvedCalendar(BaseModel):
    """Effective calendar of a project at any depth, plus its source."""

    working_hours_per_day: Decimal
    working_days: list[int]
    source: CalendarSource

    @field_serializer("source")
    def _serialize_source(self, source: CalendarSource) -> str:
        return _WIRE_SOURCE[source]
