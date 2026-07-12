"""Pydantic schemas for the reminders module (``Reminder`` + ``ReminderRule``).

``ReminderRuleCreate``/``ReminderRuleUpdate`` expose ``lead_days`` as a
convenience top-level field even though the ORM stores it inside the
``params`` JSON column (models.py docstring) — the service maps it in/out of
``params`` so the API contract stays stable while future ``rule_type``s can
carry different ``params`` shapes with zero schema break.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import ReminderStatus


def _require_future(value: datetime) -> datetime:
    reference = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if reference <= datetime.now(UTC):
        raise ValueError("remind_at debe ser una fecha futura.")
    return value


class ReminderCreate(BaseModel):
    """Payload to create a manual reminder. Always for the caller themself."""

    task_id: uuid.UUID | None = None
    remind_at: datetime
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("remind_at")
    @classmethod
    def _remind_at_must_be_future(cls, value: datetime) -> datetime:
        return _require_future(value)


class ReminderUpdate(BaseModel):
    """Partial payload to edit a reminder. Only allowed while ``status=scheduled``."""

    remind_at: datetime | None = None
    message: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("remind_at")
    @classmethod
    def _remind_at_must_be_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _require_future(value)


class ReminderResponse(BaseModel):
    """A reminder as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID | None = None
    remind_at: datetime
    message: str
    status: ReminderStatus
    fired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class ReminderRuleCreate(BaseModel):
    """Payload to create a personal reminder rule (e.g. ``task_due_soon``)."""

    rule_type: str = Field(min_length=1, max_length=60)
    lead_days: int = Field(gt=0)


class ReminderRuleUpdate(BaseModel):
    """Partial payload to edit a reminder rule's ``enabled``/``lead_days``."""

    enabled: bool | None = None
    lead_days: int | None = Field(default=None, gt=0)


class ReminderRuleResponse(BaseModel):
    """A reminder rule as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_type: str
    enabled: bool
    params: dict
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
