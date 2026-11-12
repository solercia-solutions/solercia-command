"""Pydantic schemas for the org-role-templates module."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import Methodology, ProjectKind


class OrgRoleTemplateRead(BaseModel):
    """Template list-item representation (no tree) — ``GET /org-role-templates``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    is_system: bool


class OrgRoleTemplateNodeRead(BaseModel):
    """A node of the template's tree, nested with its children."""

    id: uuid.UUID
    name: str
    default_methodology: Methodology
    children: list["OrgRoleTemplateNodeRead"] = Field(default_factory=list)


class OrgRoleTemplateDetailRead(OrgRoleTemplateRead):
    """Template detail — ``GET /org-role-templates/{id}``, includes the tree."""

    tree: OrgRoleTemplateNodeRead


class InstantiateRequest(BaseModel):
    """Payload for ``POST /org-role-templates/{id}/instantiate``."""

    lead_user_id: uuid.UUID


class InstantiatedProjectRead(BaseModel):
    """One project returned by a successful (or reconciled) instantiation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    methodology: Methodology
    parent_project_id: uuid.UUID | None
    lead_user_id: uuid.UUID | None
    # Topological kind (change 27-plantillas-idempotentes): container node
    # -> "area", leaf -> "proyecto".
    project_kind: ProjectKind
