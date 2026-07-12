"""add_boards_and_board_column_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11 21:00:00.000000

Creates ``boards`` (one row per project, ``project_id`` UNIQUE) and
``board_columns`` (``UNIQUE(board_id, status_key)``, ``status_key``
immutable), plus a nullable ``tasks.board_column_id`` FK
(``ON DELETE SET NULL``) — then backfills BOTH for every project/task that
already existed before this migration (design.md D4, tasks.md delta
"Backfill de tareas existentes a columnas por status").

The methodology -> columns map below is an inline VERBATIM snapshot of each
strategy's ``default_columns()`` (design.md C6) — this migration NEVER
imports ``app.methodology`` so its behavior stays fixed and reproducible even
if the strategies change later. Per project: a ``boards`` row is always
created; its columns come from the snapshot (``custom`` -> zero columns).
Per task: ``board_column_id`` is set to the column whose ``status_key``
equals the task's current ``status``; when no column matches (e.g. a stale
"archived" status), it falls back to the FIRST column by ``order`` and logs a
warning for manual review. A project with zero columns (``custom``) leaves
every one of its tasks' ``board_column_id`` as ``NULL`` — there is no column
to fall back to, and `status` itself is left untouched either way.

``downgrade()`` drops ``tasks.board_column_id`` first (dependent FK), then
``board_columns``, then ``boards`` — the reverse of creation order. The
backfill is NOT reversible (there was no ``board_column_id`` to restore), so
``downgrade()`` simply un-creates the schema; original ``status`` values were
never modified, so no data is lost.
"""
import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration.0003_boards_backfill")

# VERBATIM snapshot of `strategy.default_columns()` at the time this change
# was authored (design.md C6) — any transcription drift (accents, spacing,
# casing) would silently route tasks to the fallback column.
_METHODOLOGY_COLUMNS: dict[str, list[str]] = {
    "planner": ["Sin iniciar", "En curso", "Completada"],
    "kanban": ["Backlog", "Doing", "Done"],
    "scrum": ["To Do", "In Progress", "In Review", "Done"],
    "custom": [],
}


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

    _backfill_boards_and_tasks()


def _backfill_boards_and_tasks() -> None:
    """Seed a board (+ columns) for every existing project and backfill tasks.

    Uses ad-hoc ``sa.table()``/``sa.column()`` definitions (never the ORM
    models, which can change shape over time) so this migration's behavior
    stays fixed regardless of future model edits — the standard Alembic
    data-migration pattern.
    """

    bind = op.get_bind()

    projects_t = sa.table(
        "projects",
        sa.column("id", sa.Uuid()),
        sa.column("methodology", sa.String()),
    )
    boards_t = sa.table(
        "boards",
        sa.column("id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("is_active", sa.Boolean()),
    )
    board_columns_t = sa.table(
        "board_columns",
        sa.column("id", sa.Uuid()),
        sa.column("board_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("status_key", sa.String()),
        sa.column("column_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    tasks_t = sa.table(
        "tasks",
        sa.column("id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("status", sa.String()),
        sa.column("board_column_id", sa.Uuid()),
    )

    projects = bind.execute(
        sa.select(projects_t.c.id, projects_t.c.methodology)
    ).fetchall()

    for project_id, methodology in projects:
        column_names = _METHODOLOGY_COLUMNS.get(methodology, [])

        board_id = uuid.uuid4()
        bind.execute(
            boards_t.insert().values(
                id=board_id, project_id=project_id, is_active=True
            )
        )

        # (column_id, status_key), in seed order — first entry is the
        # fallback target for tasks whose status matches no column.
        columns: list[tuple[uuid.UUID, str]] = []
        for order, name in enumerate(column_names):
            column_id = uuid.uuid4()
            bind.execute(
                board_columns_t.insert().values(
                    id=column_id,
                    board_id=board_id,
                    name=name,
                    status_key=name,
                    column_order=order,
                    is_active=True,
                )
            )
            columns.append((column_id, name))

        if not columns:
            # custom, zero columns: every task of this project keeps
            # board_column_id = NULL (nothing to assign it to).
            continue

        status_to_column = {status_key: column_id for column_id, status_key in columns}
        fallback_column_id = columns[0][0]

        tasks = bind.execute(
            sa.select(tasks_t.c.id, tasks_t.c.status).where(
                tasks_t.c.project_id == project_id
            )
        ).fetchall()

        for task_id, task_status in tasks:
            target_column_id = status_to_column.get(task_status)
            if target_column_id is None:
                target_column_id = fallback_column_id
                logger.warning(
                    "[0003 backfill] task %s (project %s): status %r no coincide "
                    "con ninguna columna sembrada; asignada a la primera columna "
                    "por order — revisar manualmente.",
                    task_id,
                    project_id,
                    task_status,
                )
            bind.execute(
                tasks_t.update()
                .where(tasks_t.c.id == task_id)
                .values(board_column_id=target_column_id)
            )


def downgrade() -> None:
    op.drop_index(op.f("ix_tasks_board_column_id"), table_name="tasks")
    op.drop_constraint("tasks_board_column_id_fkey", "tasks", type_="foreignkey")
    op.drop_column("tasks", "board_column_id")

    op.drop_index(op.f("ix_board_columns_board_id"), table_name="board_columns")
    op.drop_table("board_columns")

    op.drop_table("boards")
