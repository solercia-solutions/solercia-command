"""add_boards_and_board_column_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11 21:00:00.000000

Schema-only step for change 03-boards-persistentes (design.md D2/D6): creates
``boards`` (one row per project, ``project_id`` UNIQUE) and ``board_columns``
(``UNIQUE(board_id, status_key)``, ``status_key`` immutable), plus a nullable
``tasks.board_column_id`` FK (``ON DELETE SET NULL``). No data is written or
moved here — the backfill that assigns every existing project a board and
every existing task a ``board_column_id`` is added to THIS SAME revision's
``upgrade()`` in a later commit (Batch E), per the tasks plan: one revision,
two commits.

``downgrade()`` drops ``tasks.board_column_id`` first (dependent FK), then
``board_columns``, then ``boards`` — the reverse of creation order.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "boards",
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
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", name="uq_boards_project_id"),
    )

    op.create_table(
        "board_columns",
        sa.Column("board_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status_key", sa.String(length=60), nullable=False),
        sa.Column("column_order", sa.Integer(), nullable=False),
        sa.Column("wip_limit", sa.Integer(), nullable=True),
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
            ["board_id"], ["boards.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "board_id", "status_key", name="uq_board_column_status_key"
        ),
    )
    op.create_index(
        op.f("ix_board_columns_board_id"), "board_columns", ["board_id"], unique=False
    )

    op.add_column("tasks", sa.Column("board_column_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "tasks_board_column_id_fkey",
        "tasks",
        "board_columns",
        ["board_column_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_tasks_board_column_id"), "tasks", ["board_column_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_board_column_id"), table_name="tasks")
    op.drop_constraint("tasks_board_column_id_fkey", "tasks", type_="foreignkey")
    op.drop_column("tasks", "board_column_id")

    op.drop_index(op.f("ix_board_columns_board_id"), table_name="board_columns")
    op.drop_table("board_columns")

    op.drop_table("boards")
