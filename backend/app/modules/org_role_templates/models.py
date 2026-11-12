"""ORM models for org role templates (change 23-org-role-templates).

Three tables: ``org_role_templates`` (header), ``org_role_template_nodes``
(the tree: umbrella/branch/team), and ``org_role_template_instantiations``
(the idempotency ledger — design.md Decision 2). See
``specs/org-role-templates/spec.md``.
"""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, SoftDeleteMixin, TimestampMixin
from app.shared.enums import Methodology


class OrgRoleTemplate(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A high-role organizational template header.

    ``organization_id`` is ``NULL`` for the 5 seeded system templates
    (``is_system=True``, read-only, visible to every organization — design.md
    Decision 1). A non-``NULL`` value would scope a template to a single
    organization; not seeded today, but the column allows it without another
    migration.
    """

    __tablename__ = "org_role_templates"
    __table_args__ = (
        # Partial unique indexes backing the seeder's check-then-insert
        # natural key (same idempotency pattern as
        # ``uq_users_numero_documento``, migration 0017): a plain
        # ``UNIQUE(organization_id, name)`` would NOT catch a duplicate
        # SYSTEM template name — Postgres treats every NULL as distinct.
        # Declared here too so ``Base.metadata.create_all`` (tests) enforces it.
        Index(
            "uq_org_role_templates_system_name",
            "name",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
        ),
        Index(
            "uq_org_role_templates_org_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("organization_id IS NOT NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)


class OrgRoleTemplateNode(PkMixin, TimestampMixin, Base):
    """One node (umbrella, branch or team) of a template's project tree.

    ``parent_node_id`` is ``None`` for the umbrella (root) node. Instantiation
    walks this tree parent -> child, mirroring ``parent_project_id`` on the
    generated ``Project`` rows (change 21-project-hierarchy).
    """

    __tablename__ = "org_role_template_nodes"

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("org_role_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("org_role_template_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    default_methodology: Mapped[Methodology] = mapped_column(
        SAEnum(Methodology, name="methodology", native_enum=False, length=20),
        default=Methodology.planner,
        nullable=False,
    )
    # Sibling display order. Mapped to a non-reserved column name, same
    # pattern as BoardColumn.order -> "column_order"/Menu.order -> "menu_order".
    order: Mapped[int] = mapped_column(
        "node_order", Integer, default=0, nullable=False
    )


class OrgRoleTemplateInstantiation(PkMixin, TimestampMixin, Base):
    """Idempotency ledger: ``(organization, template, node)`` -> the
    generated ``Project`` (change 27-plantillas-idempotentes, design.md
    Decisión 1 — the key deliberately EXCLUDES ``lead_user_id``: a node is
    the SAME node regardless of who its responsible is).

    Reconciliation reads this row: if the referenced ``Project`` is still
    ``is_active=True`` the node is REUSED (and its ``lead_user_id``, on both
    the ``Project`` and this row, is reconciled to the CURRENT instantiation
    call — never a new tree); otherwise it is treated as missing and this
    row's ``project_id`` is UPDATED (never re-inserted, preserving the
    unique constraint) — design.md Decision 2/1, "Reconciliación con
    is_active" / "match por ledger, lead reconciliado".
    """

    __tablename__ = "org_role_template_instantiations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "template_id",
            "node_id",
            name="uq_org_role_template_instantiation",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("org_role_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("org_role_template_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
