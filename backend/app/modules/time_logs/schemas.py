"""Pydantic schemas for the time_logs module.

The API contract uses ``date`` (time-logs.md alcance propuesto); the ORM
column is ``work_date`` (``TaskTimeLog.work_date``, see models.py docstring
for why the column name differs). ``TimeLogResponse.date`` reads that column
via ``validation_alias`` (design.md, "Correcciones de gate (2026-07-11)" #4)
while ``TimeLogCreate``/``TimeLogUpdate`` simply name the field ``date``
directly — the service maps it onto ``work_date`` when building the ORM row.
"""

import uuid
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TimeLogCreate(BaseModel):
    """Payload to register time worked on a task. Always for the caller themself."""

    date: date_
    hours: Decimal = Field(gt=0, le=24)
    note: str | None = Field(default=None, max_length=2000)


class TimeLogUpdate(BaseModel):
    """Partial payload to edit a time-log entry. Only the owner may submit this."""

    date: date_ | None = None
    hours: Decimal | None = Field(default=None, gt=0, le=24)
    note: str | None = Field(default=None, max_length=2000)


class TimeLogResponse(BaseModel):
    """A time-log entry as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    user_id: uuid.UUID
    date: date_ = Field(validation_alias="work_date")
    hours: Decimal
    note: str | None = None
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class DailyHoursEntry(BaseModel):
    """Total hours logged by a user on a single calendar day."""

    date: date_
    hours: Decimal


class WeeklyHoursEntry(BaseModel):
    """Total hours logged by a user within an ISO week, keyed by the Monday it starts on."""

    week_start: date_
    hours: Decimal


class TimeLogSummary(BaseModel):
    """Daily and weekly aggregation of a user's logged hours."""

    daily: list[DailyHoursEntry]
    weekly: list[WeeklyHoursEntry]
