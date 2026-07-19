"""add_intake

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-19 00:00:00.000000

Change 22-intake-classifier (design.md "Migration / Rollout"). ``down_revision``
anchored to ``0018`` (add_org_role_templates) — the real head verified live via
``alembic heads`` immediately before authoring this file (Fase 0 gate, tasks.md
T0.1). Este cambio es el ÚLTIMO apply de la serie: encadena sobre el head
resultante de 14 (connectors) y 21/23 (project hierarchy + org role templates).

Four additive tables, all in this ONE migration:

1. ``intake_items`` — insumos leídos vía los puertos del 14, idempotentes por
   ``UNIQUE(organization_id, connector_id, external_id)`` (design.md
   Architecture Decisions, "Idempotencia").
2. ``intake_rules`` — reglas tema→respondiente, ordenadas por ``rule_order``.
3. ``intake_runs`` — bitácora por cuenta de cada ``POST /intake/pull``, SIN
   soft delete (un log se consulta, nunca se "des-borra").
4. ``intake_settings`` — configuración por organización (proyecto por
   defecto), ``UNIQUE(organization_id)``.

``downgrade()`` reverses in strict dependency order: ``intake_settings`` ->
``intake_runs`` -> ``intake_rules`` -> ``intake_items`` (design.md "Tablas").
Purely additive; no data transformation on the way up or down.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- 1. intake_items -------------------------------------------------------
    op.create_table(
        "intake_items",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_provider", sa.String(length=50), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("connected_account_id", sa.Uuid(), nullable=True),
        sa.Column(
            "item_type",
            sa.Enum(
                "email",
                "calendar_event",
                "external_task",
                "meeting_note",
                "ticket",
                name="intake_item_type",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("origin_actor", sa.String(length=320), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "converted",
                "ignored",
                "error",
                name="intake_item_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("matched_rule_id", sa.Uuid(), nullable=True),
        sa.Column("created_task_id", sa.Uuid(), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connected_account_id"], ["connected_accounts.id"], ondelete="SET NULL"
        ),
        # matched_rule_id -> intake_rules.id added below (Fase 2, "created
        # AFTER intake_rules exists in this SAME upgrade").
        sa.ForeignKeyConstraint(["created_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "connector_id",
            "external_id",
            name="uq_intake_items_org_connector_external",
        ),
    )
    op.create_index(
        op.f("ix_intake_items_organization_id"), "intake_items", ["organization_id"]
    )
    op.create_index(op.f("ix_intake_items_source_provider"), "intake_items", ["source_provider"])
    op.create_index(op.f("ix_intake_items_connector_id"), "intake_items", ["connector_id"])
    op.create_index(op.f("ix_intake_items_item_type"), "intake_items", ["item_type"])
    op.create_index(op.f("ix_intake_items_external_id"), "intake_items", ["external_id"])
    op.create_index(op.f("ix_intake_items_origin_actor"), "intake_items", ["origin_actor"])
    op.create_index(op.f("ix_intake_items_status"), "intake_items", ["status"])

    # -- 2. intake_rules ---------------------------------------------------------
    op.create_table(
        "intake_rules",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("convert_to_task", sa.Boolean(), nullable=False),
        sa.Column("target_project_id", sa.Uuid(), nullable=True),
        sa.Column(
            "task_priority",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="priority",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("rule_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["target_project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intake_rules_organization_id"), "intake_rules", ["organization_id"]
    )
    op.create_index(op.f("ix_intake_rules_rule_order"), "intake_rules", ["rule_order"])

    # Now that intake_rules exists, wire intake_items.matched_rule_id -> it
    # (created in the SAME upgrade — no cross-migration dependency).
    op.create_foreign_key(
        "intake_items_matched_rule_id_fkey",
        "intake_items",
        "intake_rules",
        ["matched_rule_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- 3. intake_runs (Pk+Timestamp+Audit+Tenant, SIN soft delete) -----------
    op.create_table(
        "intake_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("connected_account_id", sa.Uuid(), nullable=True),
        sa.Column("items_fetched", sa.Integer(), nullable=False),
        sa.Column("items_new", sa.Integer(), nullable=False),
        sa.Column("items_duplicated", sa.Integer(), nullable=False),
        sa.Column("items_converted", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "error",
                name="intake_run_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connected_account_id"], ["connected_accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intake_runs_organization_id"), "intake_runs", ["organization_id"]
    )
    op.create_index(op.f("ix_intake_runs_connector_id"), "intake_runs", ["connector_id"])
    op.create_index(op.f("ix_intake_runs_status"), "intake_runs", ["status"])

    # -- 4. intake_settings (Pk+Timestamp+Tenant, UNIQUE por organización) -----
    op.create_table(
        "intake_settings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("default_project_id", sa.Uuid(), nullable=True),
        sa.Column("default_project_name", sa.String(length=160), nullable=True),
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
            ["default_project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_intake_settings_organization"),
    )
    op.create_index(
        op.f("ix_intake_settings_organization_id"), "intake_settings", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_intake_settings_organization_id"), table_name="intake_settings"
    )
    op.drop_table("intake_settings")

    op.drop_index(op.f("ix_intake_runs_status"), table_name="intake_runs")
    op.drop_index(op.f("ix_intake_runs_connector_id"), table_name="intake_runs")
    op.drop_index(op.f("ix_intake_runs_organization_id"), table_name="intake_runs")
    op.drop_table("intake_runs")

    op.drop_constraint(
        "intake_items_matched_rule_id_fkey", "intake_items", type_="foreignkey"
    )

    op.drop_index(op.f("ix_intake_rules_rule_order"), table_name="intake_rules")
    op.drop_index(op.f("ix_intake_rules_organization_id"), table_name="intake_rules")
    op.drop_table("intake_rules")

    op.drop_index(op.f("ix_intake_items_status"), table_name="intake_items")
    op.drop_index(op.f("ix_intake_items_origin_actor"), table_name="intake_items")
    op.drop_index(op.f("ix_intake_items_external_id"), table_name="intake_items")
    op.drop_index(op.f("ix_intake_items_item_type"), table_name="intake_items")
    op.drop_index(op.f("ix_intake_items_connector_id"), table_name="intake_items")
    op.drop_index(op.f("ix_intake_items_source_provider"), table_name="intake_items")
    op.drop_index(
        op.f("ix_intake_items_organization_id"), table_name="intake_items"
    )
    op.drop_table("intake_items")
