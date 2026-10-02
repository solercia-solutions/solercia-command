"""add_institutional_plans

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-30 00:00:00.000000

Change 45a-planes-modelo-api (design.md "Migración 0028", re-anchored). The
design reserved ``0028``/``0027`` assuming change 44 (two revisions) landed
first. Fase 0 gate, verified live before authoring this file: a single
on-disk head ``0026`` (``alembic heads``), inventory ends at
``0026_add_project_is_system.py``, and change 44 is NOT implemented, so it has
not claimed ``0026``/``0027`` in this tree. THIS revision therefore takes the
next free consecutive number: ``0027`` with ``down_revision="0026"`` (only two
literals and this docstring changed; no design decision was renegotiated).

Strictly additive: FIVE brand-new tables, ZERO pre-existing tables touched, so
no row of the current schema changes on upgrade OR on downgrade. Same additive
pattern as ``0019_add_intake.py`` (``op.create_table`` with the constraints
declared INSIDE, then ``op.create_index(op.f(...))``), without
``batch_alter_table`` — the project is PostgreSQL-only.

``plan_activities`` deliberately has NO ``organization_id``: tenant scope is
transitive through ``plan_id -> plans.organization_id``, exactly like ``tasks``
reaches it through ``project_id`` (design.md D-D / P7).

The ``ck_plan_activity_links_no_self`` CHECK and every UNIQUE below are mirrored
BYTE-IDENTICALLY in ``app/modules/plans/models.py`` ``__table_args__`` because
the test harness builds the schema with ``Base.metadata.create_all``
(tests/conftest.py), NOT with Alembic. ``alembic check`` does NOT compare
CheckConstraints, so the equality is enforced by
``test_migration_institutional_plans.py`` comparing ``pg_get_indexdef`` /
``pg_get_constraintdef`` between the two schemas (design.md D-B).

``downgrade()`` drops indexes and tables in strict reverse creation order. The
five tables are new and no pre-existing table references them, so dropping them
loses no business data of any other aggregate.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- 1. plans (TenantMixin + Pk + Timestamp + SoftDelete + Audit) --------
    op.create_table(
        "plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column("source_document", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_plans_org_code"),
    )
    op.create_index(op.f("ix_plans_organization_id"), "plans", ["organization_id"])
    op.create_index(
        "ix_plans_org_type_year",
        "plans",
        ["organization_id", "plan_type", "period_year"],
    )

    # -- 2. plan_activities (NO organization_id — D-D / P7) -----------------
    op.create_table(
        "plan_activities",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("group_code", sa.String(length=20), nullable=True),
        sa.Column("group_name", sa.String(length=255), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("deliverable", sa.Text(), nullable=True),
        sa.Column("evidence_expected", sa.Text(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("is_mine", sa.Boolean(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("target_from", sa.Numeric(5, 2), nullable=True),
        sa.Column("target_to", sa.Numeric(5, 2), nullable=True),
        sa.Column("iso_controls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # PLURAL: PSPI 2.4 carries OM-05 AND OM-08 (D2, spec scenario 2).
        sa.Column("external_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scheduled_periods", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "code", name="uq_plan_activities_plan_code"),
    )
    op.create_index(op.f("ix_plan_activities_plan_id"), "plan_activities", ["plan_id"])
    op.create_index("ix_plan_activities_plan_is_mine", "plan_activities", ["plan_id", "is_mine"])

    # -- 3. plan_activity_reports (NO SoftDeleteMixin — D-C) ----------------
    op.create_table(
        "plan_activity_reports",
        sa.Column("plan_activity_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("reported_progress", sa.Numeric(5, 2), nullable=True),
        sa.Column("qualitative_summary", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_met", sa.Boolean(), nullable=True),
        sa.Column("met_on_time", sa.Boolean(), nullable=True),
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
        sa.ForeignKeyConstraint(["plan_activity_id"], ["plan_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_activity_id",
            "period",
            name="uq_plan_activity_reports_activity_period",
        ),
    )
    op.create_index(
        op.f("ix_plan_activity_reports_plan_activity_id"),
        "plan_activity_reports",
        ["plan_activity_id"],
    )

    # -- 4. plan_activity_links (the only CHECK of this change) -------------
    op.create_table(
        "plan_activity_links",
        sa.Column("from_activity_id", sa.Uuid(), nullable=False),
        sa.Column("to_activity_id", sa.Uuid(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("source_reference", sa.String(length=50), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["from_activity_id"], ["plan_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_activity_id"], ["plan_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_activity_id",
            "to_activity_id",
            "link_type",
            name="uq_plan_activity_links_from_to_type",
        ),
        sa.CheckConstraint(
            "from_activity_id <> to_activity_id",
            name="ck_plan_activity_links_no_self",
        ),
    )
    op.create_index(
        op.f("ix_plan_activity_links_from_activity_id"),
        "plan_activity_links",
        ["from_activity_id"],
    )
    op.create_index(
        op.f("ix_plan_activity_links_to_activity_id"),
        "plan_activity_links",
        ["to_activity_id"],
    )

    # -- 5. task_plan_activities (the ONLY touch point with `tasks`) --------
    op.create_table(
        "task_plan_activities",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("plan_activity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_activity_id"], ["plan_activities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "plan_activity_id",
            name="uq_task_plan_activities_task_activity",
        ),
    )
    op.create_index(op.f("ix_task_plan_activities_task_id"), "task_plan_activities", ["task_id"])
    op.create_index(
        op.f("ix_task_plan_activities_plan_activity_id"),
        "task_plan_activities",
        ["plan_activity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_task_plan_activities_plan_activity_id"),
        table_name="task_plan_activities",
    )
    op.drop_index(op.f("ix_task_plan_activities_task_id"), table_name="task_plan_activities")
    op.drop_table("task_plan_activities")

    op.drop_index(op.f("ix_plan_activity_links_to_activity_id"), table_name="plan_activity_links")
    op.drop_index(
        op.f("ix_plan_activity_links_from_activity_id"),
        table_name="plan_activity_links",
    )
    op.drop_table("plan_activity_links")

    op.drop_index(
        op.f("ix_plan_activity_reports_plan_activity_id"),
        table_name="plan_activity_reports",
    )
    op.drop_table("plan_activity_reports")

    op.drop_index("ix_plan_activities_plan_is_mine", table_name="plan_activities")
    op.drop_index(op.f("ix_plan_activities_plan_id"), table_name="plan_activities")
    op.drop_table("plan_activities")

    op.drop_index("ix_plans_org_type_year", table_name="plans")
    op.drop_index(op.f("ix_plans_organization_id"), table_name="plans")
    op.drop_table("plans")
