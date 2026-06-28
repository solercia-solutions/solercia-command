"""Pydantic schemas for the user-management (admin) module.

The public read shape is shared with the auth module via ``UserRead`` so a user
is represented identically everywhere (split name parts + composed
``full_name`` + roles, never the password hash).
"""

import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


def _clean_required(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Este campo es obligatorio.")
    return cleaned


class AdminUserCreate(BaseModel):
    """Payload to create a user from the admin area."""

    primer_nombre: str = Field(min_length=1, max_length=120)
    segundo_nombre: str | None = Field(default=None, max_length=120)
    primer_apellido: str = Field(min_length=1, max_length=120)
    segundo_apellido: str | None = Field(default=None, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    dependency_id: uuid.UUID | None = None
    is_active: bool = True
    role_ids: list[uuid.UUID] = Field(default_factory=list)

    @field_validator("primer_nombre", "primer_apellido")
    @classmethod
    def _validate_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("segundo_nombre", "segundo_apellido")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class AdminUserUpdate(BaseModel):
    """Partial payload to update a user from the admin area."""

    primer_nombre: str | None = Field(default=None, min_length=1, max_length=120)
    segundo_nombre: str | None = Field(default=None, max_length=120)
    primer_apellido: str | None = Field(default=None, min_length=1, max_length=120)
    segundo_apellido: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    dependency_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("primer_nombre", "primer_apellido")
    @classmethod
    def _validate_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required(value)

    @field_validator("segundo_nombre", "segundo_apellido")
    @classmethod
    def _clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UserRolesUpdate(BaseModel):
    """Payload to replace the set of roles assigned to a user."""

    role_ids: list[uuid.UUID] = Field(default_factory=list)
