"""Pydantic schemas for the projects module."""

import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.enums import Methodology, ProjectKind, ProjectStatus

_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")


class ProjectCreate(BaseModel):
    """Payload to create a project."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    methodology: Methodology
    # Optional explicit code (2-10 uppercase alphanumeric). Auto-generated from
    # the project name when omitted.
    code: str | None = Field(default=None, max_length=10)
    # Optional parent in the hierarchy (change 21-project-hierarchy). When
    # omitted the project is created as a root, unchanged from before.
    parent_project_id: uuid.UUID | None = None
    # Optional responsible/head of the project (change 23-org-role-templates).
    # Omitted -> null, unchanged from before (specs/projects/spec.md delta).
    lead_user_id: uuid.UUID | None = None
    # Optional topological kind (change 27-plantillas-idempotentes). Omitted
    # -> "proyecto". Only org-role-template instantiation may set "area";
    # the plain POST /projects flow always forces "proyecto" regardless of
    # what the client sends (specs/projects/spec.md delta).
    project_kind: ProjectKind | None = None

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


class ProjectUpdate(BaseModel):
    """Partial payload for ``PATCH /projects/{id}``. Every field is optional.

    Only fields explicitly present in the request are applied
    (``model_dump(exclude_unset=True)`` in the service). ``methodology`` is
    declared ONLY so the service can reject it with a distinct 422
    ``methodology_not_editable`` — the seeded board and the task statuses
    derive from the methodology Strategy, so it is never editable.
    """

    name: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    code: str | None = Field(default=None, max_length=10)
    methodology: Methodology | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("El nombre no puede ser nulo.")
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
            raise ValueError("El código no puede ser nulo.")
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
    # Parent in the hierarchy (change 21-project-hierarchy); null = root.
    parent_project_id: uuid.UUID | None = None
    # Responsible/head of the project (change 23-org-role-templates); null for
    # projects created outside a template instantiation.
    lead_user_id: uuid.UUID | None = None
    # Topological kind (change 27-plantillas-idempotentes): "area"|"proyecto".
    project_kind: ProjectKind = ProjectKind.proyecto
    # Override de calendario laboral del equipo (change 28-calendario-
    # laboral): refleja las columnas ORM tal cual (``from_attributes=True``).
    # ``null`` para todo proyecto no-raíz, o para una raíz sin override
    # configurado — el invariante "solo la raíz persiste valores" lo
    # garantiza ``WorkCalendarService.set_project_override``
    # (``override_requires_root``), nunca este schema.
    working_hours_per_day: Decimal | None = None
    working_days: list[int] | None = None
    # Only ``GET /projects`` fills these (ODD S05): active top-level tasks and
    # open ones (not done — completed_at or last board column — nor
    # cancelled) for the requested ``year`` or for every year. ``null`` on
    # endpoints that do not compute them.
    task_count: int | None = None
    open_task_count: int | None = None


class ProjectTreeNode(BaseModel):
    """A node of ``GET /{id}/tree``: the project nested with its descendants."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None = None
    methodology: Methodology
    status: ProjectStatus
    children: list["ProjectTreeNode"] = Field(default_factory=list)


class ReparentRequest(BaseModel):
    """Payload for ``PATCH /{id}/parent``. ``null`` unlinks the project to root."""

    parent_project_id: uuid.UUID | None


class ProjectProgressCounts(BaseModel):
    """``{done, total, percent_done}`` — shared shape for ``self``/``rollup``."""

    done: int
    total: int
    percent_done: int


class ProjectProgressNode(BaseModel):
    """A node of ``GET /{id}/progress``: own vs. consolidated subtree counts."""

    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    name: str
    # Own tasks only (this project, excluding its subtree).
    self: ProjectProgressCounts
    # This project's own counts PLUS every active descendant's (design.md,
    # "el valor consolidado ... DEBE sumar done y total de él mismo más
    # todos los proyectos activos de su subárbol").
    rollup: ProjectProgressCounts
    children: list["ProjectProgressNode"] = Field(default_factory=list)
