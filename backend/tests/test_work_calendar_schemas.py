"""Unit tests (no DB) for ``app.modules.work_calendar.schemas`` (change
28-calendario-laboral, tasks.md T2.1/T2.3).

``WorkCalendarConfig`` is the validation contract shared by the company
calendar (PUT/GET) and the raw values of a root project's override once
present. ``ResolvedCalendar`` proves the reconciliation the orchestrator
closed before this phase (tasks.md, "Reconciliación aplicada" #3): the
internal ``CalendarSource`` enum literals never change, only their JSON
wire representation does.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError


def test_work_calendar_config_accepts_a_half_day() -> None:
    """7.5 hours (a half-day) is a valid working_hours_per_day."""

    from app.modules.work_calendar.schemas import WorkCalendarConfig

    config = WorkCalendarConfig(working_hours_per_day=Decimal("7.5"), working_days=[1, 2, 3])

    assert config.working_hours_per_day == Decimal("7.5")


@pytest.mark.parametrize("hours", [0, 25])
def test_work_calendar_config_rejects_hours_out_of_range(hours: int) -> None:
    """0 and 25 are both outside the valid 1-24 range."""

    from app.modules.work_calendar.schemas import WorkCalendarConfig

    with pytest.raises(ValidationError):
        WorkCalendarConfig(working_hours_per_day=hours, working_days=[1, 2, 3])


@pytest.mark.parametrize("days", [[], [1, 1, 2], [0], [8]])
def test_work_calendar_config_rejects_invalid_working_days(days: list[int]) -> None:
    """Empty, duplicate, or out-of-ISO-range (not 1-7) days are all rejected."""

    from app.modules.work_calendar.schemas import WorkCalendarConfig

    with pytest.raises(ValidationError):
        WorkCalendarConfig(working_hours_per_day=8, working_days=days)


def test_work_calendar_config_normalizes_working_days_to_ascending_order() -> None:
    """[3, 1, 2] is accepted and normalized to the canonical [1, 2, 3]."""

    from app.modules.work_calendar.schemas import WorkCalendarConfig

    config = WorkCalendarConfig(working_hours_per_day=8, working_days=[3, 1, 2])

    assert config.working_days == [1, 2, 3]


def test_resolved_calendar_serializes_internal_source_to_the_public_wire_value() -> None:
    """``.model_dump()["source"]`` uses the PUBLIC wire value, not the internal literal."""

    from app.modules.work_calendar.schemas import CalendarSource, ResolvedCalendar

    team = ResolvedCalendar(
        working_hours_per_day=8,
        working_days=[1, 2, 3, 4, 5],
        source=CalendarSource.project_root_override,
    )
    organization = ResolvedCalendar(
        working_hours_per_day=8,
        working_days=[1, 2, 3, 4, 5],
        source=CalendarSource.organization_default,
    )
    default = ResolvedCalendar(
        working_hours_per_day=8,
        working_days=[1, 2, 3, 4, 5],
        source=CalendarSource.global_default,
    )

    assert team.model_dump()["source"] == "team"
    assert organization.model_dump()["source"] == "organization"
    assert default.model_dump()["source"] == "default"
    # The Python-side enum stays the internal literal — only the JSON
    # representation is translated at the serialization boundary.
    assert team.source is CalendarSource.project_root_override
