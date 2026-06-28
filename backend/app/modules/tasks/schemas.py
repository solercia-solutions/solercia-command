"""Pydantic schemas for the tasks module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import Priority


class TaskCreate(BaseModel):
    """Payload to create a task.

    ``status`` is optional; the service defaults it to the first allowed status
    of the project methodology and validates any provided value.
    """

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=60)
    priority: Priority = Priority.medium
    task_type: str | None = Field(default=None, max_length=40)
    assignee_id: uuid.UUID | None = None
    estimation_points: int | None = Field(default=None, ge=0, le=1000)
    estimation_hours: float | None = Field(default=None, ge=0, le=10000)
    due_date: datetime | None = None
    start_date: datetime | None = None
    sprint_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El título es obligatorio.")
        return cleaned

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class TaskUpdate(BaseModel):
    """Partial payload to update a task. Every field is optional.

    Only fields explicitly present in the request are applied, so ``None`` is a
    deliberate clear (e.g. unassign) rather than "leave unchanged".
    """

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=60)
    priority: Priority | None = None
    task_type: str | None = Field(default=None, max_length=40)
    assignee_id: uuid.UUID | None = None
    estimation_points: int | None = Field(default=None, ge=0, le=1000)
    estimation_hours: float | None = Field(default=None, ge=0, le=10000)
    due_date: datetime | None = None
    start_date: datetime | None = None
    sprint_id: uuid.UUID | None = None
    order: int | None = Field(default=None, ge=0)
    risk_flag: bool | None = None
    risk_reason: str | None = Field(default=None, max_length=2000)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El título no puede estar vacío.")
        return cleaned


class TaskRead(BaseModel):
    """Task representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    sprint_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    task_type: str
    status: str
    priority: Priority
    assignee_id: uuid.UUID | None = None
    # Resolved by the service from the assignee User; transient on the ORM row.
    assignee_name: str | None = None
    estimation_points: int | None = None
    estimation_hours: float | None = None
    due_date: datetime | None = None
    start_date: datetime | None = None
    completed_at: datetime | None = None
    order: int = 0
    risk_flag: bool = False
    risk_reason: str | None = None
    created_at: datetime


class MemberRead(BaseModel):
    """An organization member that can be assigned to tasks."""

    user_id: uuid.UUID
    full_name: str
    email: str
    role: str
