"""Project ORM model."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    false,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

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
        # Current shape only, not protection against unmarking or hard DELETE.
        CheckConstraint(
            "NOT is_system OR (code IS NOT NULL AND code = 'GENERALES' AND methodology = 'custom' AND status = 'active' AND is_active AND deleted_at IS NULL)",
            name="ck_projects_system_shape",
        ),
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
        # External origin anchor (Jira import): one project per
        # (organization, source, external_key); rows without a key never collide.
        Index(
            "uq_projects_org_source_external_key",
            "organization_id",
            "source",
            "external_key",
            unique=True,
            postgresql_where=text("external_key IS NOT NULL"),
        ),
    )

    is_system: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
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
    # Override de calendario laboral del equipo (change 28-calendario-
    # laboral): SOLO el proyecto raíz (``parent_project_id is None``) puede
    # tener valores no nulos aquí — la validación vive en
    # ``WorkCalendarService.set_project_override`` (regla ``override_
    # requires_root``), nunca en este modelo. ``NULL`` = hereda el
    # calendario de la organización (o el default global). Ambas columnas
    # nullable, sin default: ``POST /projects`` nunca las rellena.
    working_hours_per_day: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2), nullable=True
    )
    working_days: Mapped[list[int] | None] = mapped_column(
        ARRAY(Integer), nullable=True
    )
    # Origin system and opaque key of an imported project (e.g. "jira" +
    # the Jira project key). NULL on every project created in Command.
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    if TYPE_CHECKING:
        # Transient attribute attached by ProjectService for response
        # serialization only; never persisted (no mapped_column/column).
        methodology_info: dict[str, Any]
