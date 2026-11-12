"""add_org_role_templates

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-19 00:00:00.000000

Change 23-org-role-templates (design.md "Migration / Rollout"). ``down_revision``
anchored to ``0017`` (add_glpi_homologation) — the real head verified live via
``alembic current`` immediately before authoring this file (Lote 0 gate).

Four additive pieces, all in this ONE migration:

1. ``org_role_templates`` — template header. ``organization_id`` nullable
   (NULL = system template, seeded via ``db_init.seed_default`` ->
   ``ensure_system_templates``, design.md Decision 1). Backed by two partial
   unique indexes on the seeder's natural key: ``name`` alone when NULL
   (system templates), ``(organization_id, name)`` otherwise — judgment-day
   fix, "sin UNIQUE natural key".
2. ``org_role_template_nodes`` — the tree (umbrella/branch/team) of a
   template, self-referencing ``parent_node_id``.
3. ``org_role_template_instantiations`` — the idempotency ledger
   ``(organization, template, node, lead) -> project``, ``UNIQUE`` on that
   4-tuple (design.md Decision 2).
4. ``projects.lead_user_id`` — nullable self-contained FK to ``users``,
   ``SET NULL`` on delete, populated by instantiation on every generated
   project (specs/projects/spec.md delta).

``downgrade()`` reverses in strict dependency order: instantiations ->
nodes -> templates -> ``projects.lead_user_id``. Safe as a clean round-trip
with zero pre-existing template rows (purely additive; no data
transformation on the way up or down).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- 1. org_role_templates (header) --------------------------------------
    op.create_table(
        "org_role_templates",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_org_role_templates_organization_id"),
        "org_role_templates",
        ["organization_id"],
    )
    # PARTIAL unique indexes backing the seeder's check-then-insert natural
    # key (same idempotency pattern as ``uq_users_numero_documento``,
    # migration 0017): a plain ``UNIQUE(organization_id, name)`` would NOT
    # catch a duplicate SYSTEM template name — Postgres treats every NULL
    # as distinct in a regular unique constraint.
    op.create_index(
        "uq_org_role_templates_system_name",
        "org_role_templates",
        ["name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        "uq_org_role_templates_org_name",
        "org_role_templates",
        ["organization_id", "name"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )

    # -- 2. org_role_template_nodes (tree) ------------------------------------
    op.create_table(
        "org_role_template_nodes",
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("parent_node_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "default_methodology",
            sa.Enum(
                "planner",
                "kanban",
                "scrum",
                "custom",
                name="methodology",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("node_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["org_role_templates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_node_id"], ["org_role_template_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_org_role_template_nodes_template_id"),
        "org_role_template_nodes",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_org_role_template_nodes_parent_node_id"),
        "org_role_template_nodes",
        ["parent_node_id"],
    )

    # -- 3. org_role_template_instantiations (idempotency ledger) ------------
    op.create_table(
        "org_role_template_instantiations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("lead_user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["org_role_templates.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id"], ["org_role_template_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["lead_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "template_id",
            "node_id",
            "lead_user_id",
            name="uq_org_role_template_instantiation",
        ),
    )
    op.create_index(
        op.f("ix_org_role_template_instantiations_organization_id"),
        "org_role_template_instantiations",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_org_role_template_instantiations_template_id"),
        "org_role_template_instantiations",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_org_role_template_instantiations_node_id"),
        "org_role_template_instantiations",
        ["node_id"],
    )
    op.create_index(
        op.f("ix_org_role_template_instantiations_lead_user_id"),
        "org_role_template_instantiations",
        ["lead_user_id"],
    )

    # -- 4. projects.lead_user_id ----------------------------------------------
    op.add_column(
        "projects",
        sa.Column("lead_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "projects_lead_user_id_fkey",
        "projects",
        "users",
        ["lead_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_projects_lead_user_id"),
        "projects",
        ["lead_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_lead_user_id"), table_name="projects")
    op.drop_constraint("projects_lead_user_id_fkey", "projects", type_="foreignkey")
    op.drop_column("projects", "lead_user_id")

    op.drop_index(
        op.f("ix_org_role_template_instantiations_lead_user_id"),
        table_name="org_role_template_instantiations",
    )
    op.drop_index(
        op.f("ix_org_role_template_instantiations_node_id"),
        table_name="org_role_template_instantiations",
    )
    op.drop_index(
        op.f("ix_org_role_template_instantiations_template_id"),
        table_name="org_role_template_instantiations",
    )
    op.drop_index(
        op.f("ix_org_role_template_instantiations_organization_id"),
        table_name="org_role_template_instantiations",
    )
    op.drop_table("org_role_template_instantiations")

    op.drop_index(
        op.f("ix_org_role_template_nodes_parent_node_id"),
        table_name="org_role_template_nodes",
    )
    op.drop_index(
        op.f("ix_org_role_template_nodes_template_id"),
        table_name="org_role_template_nodes",
    )
    op.drop_table("org_role_template_nodes")

    op.drop_index("uq_org_role_templates_org_name", table_name="org_role_templates")
    op.drop_index("uq_org_role_templates_system_name", table_name="org_role_templates")
    op.drop_index(
        op.f("ix_org_role_templates_organization_id"), table_name="org_role_templates"
    )
    op.drop_table("org_role_templates")
