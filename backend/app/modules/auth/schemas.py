"""Pydantic schemas for the auth module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials submitted to obtain an access token."""

    email: EmailStr
    password: str


class RoleBrief(BaseModel):
    """Compact role descriptor embedded in the authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str


class UserRead(BaseModel):
    """Public representation of a user.

    ``full_name`` is the short composed name (``primer_nombre`` +
    ``primer_apellido``); the split parts are exposed individually too. The
    password hash is never serialized. ``roles`` lists the user's RBAC roles in
    the current organization.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    primer_nombre: str
    segundo_nombre: str | None = None
    primer_apellido: str
    segundo_apellido: str | None = None
    full_name: str
    dependency_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    roles: list[RoleBrief] = Field(default_factory=list)


class TokenResponse(BaseModel):
    """Bearer access token returned after login or refresh."""

    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Login payload: an access token plus the authenticated user."""

    access_token: str
    token_type: str = "bearer"
    user: UserRead
