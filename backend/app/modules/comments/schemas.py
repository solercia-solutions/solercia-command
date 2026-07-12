"""Pydantic schemas for the comments module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommentCreate(BaseModel):
    """Payload to create a comment on a task."""

    body: str = Field(min_length=1, max_length=100_000)

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El comentario no puede estar vacío.")
        return cleaned


class CommentUpdate(BaseModel):
    """Partial payload to edit a comment body."""

    body: str = Field(min_length=1, max_length=100_000)

    @field_validator("body")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El comentario no puede estar vacío.")
        return cleaned


class CommentRead(BaseModel):
    """Comment representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    mentioned_user_ids: list[Any] = Field(default_factory=list)
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Audit trail (R4/R5): who created/last-updated the row. NULL for rows
    # written before the audit migration or outside a request context.
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
