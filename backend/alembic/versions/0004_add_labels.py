"""add_labels

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11 22:00:00.000000

Creates ``labels`` (Pk, Timestamp, SoftDelete, Audit, Tenant —
``UNIQUE(project_id, name)``) and ``task_labels`` (Pk, Timestamp only, no
SoftDelete — ``UNIQUE(task_id, label_id)``, association hard-deleted on
unlink, same convention as ``UserRole``/``RoleMenu``). Purely additive, chains
onto the current head (``0003``, boards).

``downgrade()`` drops ``task_labels`` first (dependent FK to ``labels``), then
``labels`` — the reverse of creation order.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "labels",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_labels_project_name"),
    )
    op.create_index(op.f("ix_labels_project_id"), "labels", ["project_id"], unique=False)
    op.create_index(
        op.f("ix_labels_organization_id"), "labels", ["organization_id"], unique=False
    )

    op.create_table(
        "task_labels",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("label_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["label_id"], ["labels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "label_id", name="uq_task_labels_task_label"),
    )
    op.create_index(
        op.f("ix_task_labels_task_id"), "task_labels", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_task_labels_label_id"), "task_labels", ["label_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_labels_label_id"), table_name="task_labels")
    op.drop_index(op.f("ix_task_labels_task_id"), table_name="task_labels")
    op.drop_table("task_labels")

    op.drop_index(op.f("ix_labels_organization_id"), table_name="labels")
    op.drop_index(op.f("ix_labels_project_id"), table_name="labels")
    op.drop_table("labels")
