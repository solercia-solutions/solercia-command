"""Pydantic schemas for the projects module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import Methodology, ProjectStatus


class ProjectCreate(BaseModel):
    """Payload to create a project."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    methodology: Methodology

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio.")
        return cleaned

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProjectRead(BaseModel):
    """Project representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    methodology: Methodology
    status: ProjectStatus
    organization_id: uuid.UUID
    created_at: datetime
    # Populated by the service from the methodology Strategy before serialization.
    methodology_info: dict = Field(default_factory=dict)
