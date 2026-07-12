"""add_time_logs_and_task_history

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-11 23:50:00.000000

Creates ``task_time_logs`` (Pk, Timestamp, SoftDelete, Audit, Tenant — same
mixin set as ``TaskChecklist``/``TaskComment``) and ``task_history`` (Pk,
Timestamp, Tenant — append-only, no soft delete, no audit; same precedent as
``Notification``). Both tables land in a single migration because they are
delivered together in change 05 (T01): ``task_time_logs`` backs the
``time_logs`` module (Batch A) and ``task_history`` backs the ``activity``
module (Batch B), but nothing downstream in either batch depends on the
other table, so one additive migration covers both. Purely additive, chains
onto ``0006`` (task dependencies).

``downgrade()`` drops both tables (task_history first, no FK between them so
order does not matter functionally; kept as the reverse of creation order).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_time_logs",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(5, 2), nullable=False),
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
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_time_logs_task_id"), "task_time_logs", ["task_id"], unique=False
    )
    op.create_index(
        "ix_task_time_logs_user_id_work_date",
        "task_time_logs",
        ["user_id", "work_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_time_logs_organization_id"),
        "task_time_logs",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "task_history",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=20), nullable=False),
        sa.Column("field", sa.String(length=60), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_history_task_id_created_at",
        "task_history",
        ["task_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_task_history_actor_id_created_at",
        "task_history",
        ["actor_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_history_organization_id"),
        "task_history",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_task_history_organization_id"), table_name="task_history"
    )
    op.drop_index("ix_task_history_actor_id_created_at", table_name="task_history")
    op.drop_index("ix_task_history_task_id_created_at", table_name="task_history")
    op.drop_table("task_history")

    op.drop_index(
        op.f("ix_task_time_logs_organization_id"), table_name="task_time_logs"
    )
    op.drop_index("ix_task_time_logs_user_id_work_date", table_name="task_time_logs")
    op.drop_index(op.f("ix_task_time_logs_task_id"), table_name="task_time_logs")
    op.drop_table("task_time_logs")
