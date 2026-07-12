"""Pydantic schemas for the projects module."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import Methodology, ProjectStatus

_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")


class ProjectCreate(BaseModel):
    """Payload to create a project."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    methodology: Methodology
    # Optional explicit code (2-10 uppercase alphanumeric). Auto-generated from
    # the project name when omitted.
    code: str | None = Field(default=None, max_length=10)

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

    @field_validator("code")
    @classmethod
    def _validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.strip().upper()
        if not _CODE_RE.match(upper):
            raise ValueError(
                "El código debe tener entre 2 y 10 caracteres alfanuméricos "
                "en mayúsculas (ej. 'SDM', 'PLT2')."
            )
        return upper


class ProjectRead(BaseModel):
    """Project representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    methodology: Methodology
    status: ProjectStatus
    organization_id: uuid.UUID
    code: str | None = None
    created_at: datetime
    # Populated by the service from the methodology Strategy before serialization.
    methodology_info: dict = Field(default_factory=dict)
    # Audit trail (R4/R5): who created/last-updated the row. NULL for rows
    # written before the audit migration or outside a request context.
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
