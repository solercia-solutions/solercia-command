"""add_checklists

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-11 23:00:00.000000

Creates ``task_checklists`` and ``checklist_items`` (both Pk, Timestamp,
SoftDelete, Audit, Tenant). Purely additive, chains onto ``0004`` (labels).

``downgrade()`` drops ``checklist_items`` first (dependent FK to
``task_checklists``), then ``task_checklists`` — the reverse of creation
order.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_checklists",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("checklist_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_task_checklists_task_id"), "task_checklists", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_checklists_organization_id"),
        "task_checklists",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "checklist_items",
        sa.Column("checklist_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["checklist_id"], ["task_checklists.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checklist_items_checklist_id"),
        "checklist_items",
        ["checklist_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_checklist_items_organization_id"),
        "checklist_items",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_checklist_items_organization_id"), table_name="checklist_items"
    )
    op.drop_index(op.f("ix_checklist_items_checklist_id"), table_name="checklist_items")
    op.drop_table("checklist_items")

    op.drop_index(
        op.f("ix_task_checklists_organization_id"), table_name="task_checklists"
    )
    op.drop_index(op.f("ix_task_checklists_task_id"), table_name="task_checklists")
    op.drop_table("task_checklists")
