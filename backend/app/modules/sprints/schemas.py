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
    created_at: datetime
