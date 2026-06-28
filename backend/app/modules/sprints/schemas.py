"""Pydantic schemas for the sprints module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SprintCreate(BaseModel):
    """Payload to create a sprint."""

    name: str = Field(min_length=1, max_length=160)
    goal: str | None = Field(default=None, max_length=2000)
    start_date: datetime | None = None
    end_date: datetime | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre del sprint es obligatorio.")
        return cleaned

    @field_validator("goal")
    @classmethod
    def _clean_goal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SprintUpdate(BaseModel):
    """Partial payload to update a sprint. Every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    goal: str | None = Field(default=None, max_length=2000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str | None = Field(default=None, max_length=20)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre del sprint no puede estar vacío.")
        return cleaned


class SprintRead(BaseModel):
    """Sprint representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    goal: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: str
    completed_points: int = 0
    closed_at: datetime | None = None
    created_at: datetime


class SprintCloseBody(BaseModel):
    """Optional body for the close-sprint endpoint.

    When ``target_sprint_id`` is provided, incomplete tasks are moved to that
    sprint instead of the backlog (``sprint_id = null``).
    """

    target_sprint_id: uuid.UUID | None = None


class SprintCloseResponse(BaseModel):
    """Response returned after closing a sprint."""

    model_config = ConfigDict(from_attributes=True)

    sprint: SprintRead
    tasks_moved: int


class VelocitySprintEntry(BaseModel):
    """A single data point in the velocity series."""

    model_config = ConfigDict(from_attributes=True)

    sprint_id: uuid.UUID
    name: str
    completed_points: int
    closed_at: datetime | None


class VelocityRead(BaseModel):
    """Velocity report for a project."""

    # Closed sprints ordered by closed_at ascending.
    series: list[VelocitySprintEntry]
    # Average completed_points across all closed sprints (0 when no closed sprints).
    average_velocity: float
    # Sum of estimation_points for backlog tasks (no sprint, not done).
    backlog_points: int
    # Estimated sprints needed to finish the backlog (null when average_velocity == 0).
    projected_sprints: int | None
