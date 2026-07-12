"""add_task_dependencies

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-11 23:30:00.000000

Creates ``task_dependencies`` (Pk, Timestamp, SoftDelete, Tenant — NO Audit,
design.md's "Decisión: Modelo de datos" deliberately excludes it for this
entity). ``UNIQUE(blocker_task_id, blocked_task_id)`` — one directed row per
ordered pair; ``is_blocked_by`` is read as the inverse view, never a second
row. Purely additive, chains onto ``0005`` (checklists).

``downgrade()`` drops ``task_dependencies``.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("blocker_task_id", sa.Uuid(), nullable=False),
        sa.Column("blocked_task_id", sa.Uuid(), nullable=False),
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["blocker_task_id"], ["tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["blocked_task_id"], ["tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "blocker_task_id", "blocked_task_id", name="uq_task_dependencies_edge"
        ),
    )
    op.create_index(
        op.f("ix_task_dependencies_blocker_task_id"),
        "task_dependencies",
        ["blocker_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_dependencies_blocked_task_id"),
        "task_dependencies",
        ["blocked_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_task_dependencies_organization_id"),
        "task_dependencies",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_task_dependencies_organization_id"), table_name="task_dependencies"
    )
    op.drop_index(
        op.f("ix_task_dependencies_blocked_task_id"), table_name="task_dependencies"
    )
    op.drop_index(
        op.f("ix_task_dependencies_blocker_task_id"), table_name="task_dependencies"
    )
    op.drop_table("task_dependencies")
