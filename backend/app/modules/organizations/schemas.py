"""Pydantic schemas for organizations-admin (CRUD, membership, "mis empresas")."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.shared.enums import MemberRole


class OrganizationCreate(BaseModel):
    """Payload to bootstrap a new organization (any authenticated user)."""

    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre es obligatorio.")
        return cleaned

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("El identificador (slug) es obligatorio.")
        return cleaned


class OrganizationUpdate(BaseModel):
    """Partial payload to update an organization."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre no puede estar vacío.")
        return cleaned

    @field_validator("slug")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("El identificador (slug) no puede estar vacío.")
        return cleaned


class OrganizationRead(BaseModel):
    """Organization representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class OrganizationMembership(BaseModel):
    """One organization the caller belongs to, with their role in it."""

    organization: OrganizationRead
    role: MemberRole


class MemberCreate(BaseModel):
    """Payload to add an EXISTING user (found by email) as a member."""

    email: EmailStr
    role: MemberRole = MemberRole.member


class MemberUpdateRole(BaseModel):
    """Payload to change a member's role."""

    role: MemberRole


class MemberRead(BaseModel):
    """A membership row enriched with the user's identity, for listings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: MemberRole
    created_at: datetime


class ThemeVersionRead(BaseModel):
    """Metadata of one entry of the organization's theme history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_name: str | None
    user_id: uuid.UUID | None
    applied_at: datetime
    initial_capture: bool
    source_version_id: int | None


class ThemeVersionDetail(ThemeVersionRead):
    """A history entry with the ThemeFile that was applied."""

    theme: dict


class ThemeVersionPage(BaseModel):
    """One page of the history, newest first; ``next`` is the next cursor."""

    versions: list[ThemeVersionRead]
    next: int | None


class ThemeApplied(BaseModel):
    """Outcome of applying a theme: the stored ThemeFile and its new version."""

    theme: dict
    version: ThemeVersionRead
