"""Project ORM model."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from app.shared.enums import Methodology, ProjectKind, ProjectStatus


class Project(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A project scoped to an organization and configured by a methodology."""

    __tablename__ = "projects"
    __table_args__ = (
        # Each organization uses unique project codes (e.g. "SDM", "PLT").
        UniqueConstraint("organization_id", "code", name="uq_project_code_per_org"),
        # Trigram GIN indexes backing GET /search (change 10-busqueda-global,
        # design.md "Índices GIN"); accelerate ILIKE '%q%' + similarity().
        Index(
            "ix_projects_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_projects_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology: Mapped[Methodology] = mapped_column(
        SAEnum(Methodology, name="methodology", native_enum=False, length=20),
        nullable=False,
    )
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status", native_enum=False, length=20),
        default=ProjectStatus.active,
        nullable=False,
    )
    # Short human-readable key (2-10 uppercase alphanumeric chars).
    # Auto-generated from the project name on create; unique per organization.
    # Nullable to allow schema addition on an existing DB without migration.
    code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # Monotonically increasing counter used to assign task_number values
    # atomically via UPDATE ... RETURNING, avoiding race conditions.
    task_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Parent project in the hierarchy (change 21-project-hierarchy). NULL means
    # this project is a root. ``SET NULL`` on delete so a soft/hard-deleted
    # parent never cascades into its children — they simply become roots.
    # Same self-FK pattern as ``Task.parent_task_id``; indexed for ancestor
    # walks and subtree CTEs (``ix_projects_parent_project_id``).
    parent_project_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Responsible/head of the project (change 23-org-role-templates). Populated
    # by org-role-template instantiation for EVERY project it generates;
    # projects created via the plain POST /projects flow keep it NULL — see
    # specs/projects/spec.md (delta), "compatibilidad". SET NULL on delete so
    # removing the responsible user never blocks/cascades into the project.
    lead_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Topological kind (change 27-plantillas-idempotentes): "area" for a
    # container node with children in an org-role-template tree, "proyecto"
    # for a leaf node or any project created via the plain POST /projects
    # flow. Defaults to "proyecto" — see specs/projects/spec.md (delta).
    project_kind: Mapped[ProjectKind] = mapped_column(
        SAEnum(ProjectKind, name="project_kind", native_enum=False, length=20),
        default=ProjectKind.proyecto,
        nullable=False,
    )

    if TYPE_CHECKING:
        # Transient attribute attached by ProjectService for response
        # serialization only; never persisted (no mapped_column/column).
        methodology_info: dict[str, Any]
