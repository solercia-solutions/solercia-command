"""Pydantic schemas for the labels module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LabelCreate(BaseModel):
    """Payload to create a project-scoped label."""

    name: str = Field(min_length=1, max_length=80)
    color: str = Field(min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre de la etiqueta es obligatorio.")
        return cleaned


class LabelUpdate(BaseModel):
    """Partial payload to rename or recolor a label."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre de la etiqueta no puede estar vacío.")
        return cleaned


class LabelRead(BaseModel):
    """A label as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str
    created_at: datetime


class TaskLabelLink(BaseModel):
    """Payload to assign a label to a task."""

    label_id: uuid.UUID
