"""Pydantic schemas for the menus (activities) admin module."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MenuCreate(BaseModel):
    """Payload to create a menu (activity)."""

    name: str = Field(min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=80)
    path: str | None = Field(default=None, max_length=200)
    parent_id: uuid.UUID | None = None
    order: int = Field(default=0, ge=0)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio.")
        return cleaned

    @field_validator("icon", "path")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MenuUpdate(BaseModel):
    """Partial payload to update a menu."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    icon: str | None = Field(default=None, max_length=80)
    path: str | None = Field(default=None, max_length=200)
    parent_id: uuid.UUID | None = None
    order: int | None = Field(default=None, ge=0)
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

    @field_validator("icon", "path")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MenuRead(BaseModel):
    """Flat menu representation, including its ``parent_id``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    icon: str | None = None
    path: str | None = None
    parent_id: uuid.UUID | None = None
    order: int = 0
    is_active: bool
    created_at: datetime


class MenuNode(BaseModel):
    """A menu nested with its children, for hierarchical navigation."""

    id: uuid.UUID
    name: str
    icon: str | None = None
    path: str | None = None
    order: int = 0
    children: list[MenuNode] = Field(default_factory=list)


MenuNode.model_rebuild()
