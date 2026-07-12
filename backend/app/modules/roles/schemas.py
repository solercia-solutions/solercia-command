"""Pydantic schemas for the roles (RBAC) admin module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoleCreate(BaseModel):
    """Payload to create a role."""

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("El código es obligatorio.")
        return cleaned

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio.")
        return cleaned


class RoleUpdate(BaseModel):
    """Partial payload to update a role."""

    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("El código no puede estar vacío.")
        return cleaned

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre no puede estar vacío.")
        return cleaned


class RoleMenusUpdate(BaseModel):
    """Payload to replace the set of menus a role grants access to."""

    menu_ids: list[uuid.UUID] = Field(default_factory=list)


class RoleRead(BaseModel):
    """Role representation returned by the API, including its menu ids."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime
    menu_ids: list[uuid.UUID] = Field(default_factory=list)
    # Audit trail (R4/R5): who created/last-updated the row. NULL for rows
    # written before the audit migration or outside a request context.
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
