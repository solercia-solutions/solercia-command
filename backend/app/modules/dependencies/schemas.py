"""Pydantic schemas for the dependencies (areas) admin module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DependencyCreate(BaseModel):
    """Payload to create a dependency."""

    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=40)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio.")
        return cleaned

    @field_validator("code")
    @classmethod
    def _clean_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DependencyUpdate(BaseModel):
    """Partial payload to update a dependency."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre no puede estar vacío.")
        return cleaned

    @field_validator("code")
    @classmethod
    def _clean_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DependencyRead(BaseModel):
    """Dependency representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str | None = None
    is_active: bool
    created_at: datetime
