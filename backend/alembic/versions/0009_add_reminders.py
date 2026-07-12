"""add_reminders

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-12 00:00:00.000000

Creates ``reminders`` and ``reminder_rules`` (both Pk, Timestamp, SoftDelete,
Audit, Tenant — same mixin set as ``AlertRule``/``TaskTimeLog``), the two
tables backing change 06 (reminders): manual one-shot reminders and per-user
automatic rules (e.g. ``task_due_soon``). Both are strictly personal
resources scoped by ``user_id`` in addition to ``organization_id`` — no admin
exemption (specs/reminders/spec.md). Purely additive, chains onto ``0008``
(search trigram indexes).

``downgrade()`` drops both tables (reverse of creation order; no FK between
them so order does not matter functionally).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "scheduled",
                "fired",
                "skipped",
                "cancelled",
                name="reminder_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reminders_user_id"), "reminders", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_reminders_status"), "reminders", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_reminders_organization_id"),
        "reminders",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "reminder_rules",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(length=60), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reminder_rules_user_id"), "reminder_rules", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_reminder_rules_rule_type"),
        "reminder_rules",
        ["rule_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reminder_rules_organization_id"),
        "reminder_rules",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_reminder_rules_organization_id"), table_name="reminder_rules"
    )
    op.drop_index(op.f("ix_reminder_rules_rule_type"), table_name="reminder_rules")
    op.drop_index(op.f("ix_reminder_rules_user_id"), table_name="reminder_rules")
    op.drop_table("reminder_rules")

    op.drop_index(op.f("ix_reminders_organization_id"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_status"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_user_id"), table_name="reminders")
    op.drop_table("reminders")
