"""Pydantic schemas for the checklists module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskChecklistCreate(BaseModel):
    """Payload to create a checklist on a task."""

    title: str = Field(min_length=1, max_length=160)
    order: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El título del checklist es obligatorio.")
        return cleaned


class TaskChecklistUpdate(BaseModel):
    """Partial payload to rename or reorder a checklist."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    order: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El título del checklist no puede estar vacío.")
        return cleaned


class TaskChecklistRead(BaseModel):
    """A checklist as returned by the API, with its progress embedded.

    ``done``/``total`` are computed by the service (not persisted columns) —
    same transient-field pattern as ``Task.assignee_name``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    order: int
    created_at: datetime
    done: int = 0
    total: int = 0


class ChecklistItemCreate(BaseModel):
    """Payload to create an item within a checklist."""

    text: str = Field(min_length=1, max_length=500)
    order: int = Field(default=0, ge=0)

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El texto del ítem es obligatorio.")
        return cleaned


class ChecklistItemUpdate(BaseModel):
    """Partial payload to edit or reorder an item. ``is_done`` uses the toggle endpoint."""

    text: str | None = Field(default=None, min_length=1, max_length=500)
    order: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def _validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El texto del ítem no puede estar vacío.")
        return cleaned


class ChecklistItemRead(BaseModel):
    """A checklist item as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    checklist_id: uuid.UUID
    text: str
    is_done: bool
    order: int
    created_at: datetime
