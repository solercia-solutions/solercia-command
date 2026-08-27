"""add_task_external_origin

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-26 00:00:00.000000

Change 43-tareas-origen-externo (design.md "Migración 0025"). Head verified
live (``alembic heads`` -> single ``0024``, no fork) immediately before
authoring this file.

Purely additive, NO backfill: both columns are NULLABLE, so every existing
row keeps its values and simply gains two NULLs. Same additive pattern as
``0022_add_project_kind.py``, WITHOUT the ``server_default``/``alter_column``
pair — that pair exists only to backfill a ``NOT NULL`` column, and neither of
these is ``NOT NULL``.

``downgrade()`` reverses in strict creation order (unique index -> check ->
external_key -> source): additive metadata never referenced by a foreign key,
so dropping it loses no task business data.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept BYTE-IDENTICAL to app/modules/tasks/models.py `__table_args__`
# (design.md D-B). `alembic check` does NOT compare these predicates, so the
# equality is enforced by test_migration_task_external_origin.py.
#
# `AND is_active` (design.md D-I): a soft-deleted task RELEASES its anchor, so
# the index covers exactly the same rows `get_by_external_key` considers to
# exist. Column order is `(source, external_key, project_id)` (design.md D-A):
# same per-project uniqueness, and its leading `(source, external_key)` prefix
# also serves the org-wide lookup, which is why there is no second index.
_ANCHOR_UNIQUE_WHERE = "source IS NOT NULL AND external_key IS NOT NULL AND is_active"
_ANCHOR_CHECK = "external_key IS NULL OR source IS NOT NULL"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("source", sa.String(length=50), nullable=True))
    op.add_column("tasks", sa.Column("external_key", sa.String(length=255), nullable=True))
    op.create_check_constraint("ck_tasks_external_key_requires_source", "tasks", _ANCHOR_CHECK)
    op.create_index(
        "uq_tasks_source_external_key_project",
        "tasks",
        ["source", "external_key", "project_id"],
        unique=True,
        postgresql_where=sa.text(_ANCHOR_UNIQUE_WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_tasks_source_external_key_project", table_name="tasks")
    op.drop_constraint("ck_tasks_external_key_requires_source", "tasks", type_="check")
    op.drop_column("tasks", "external_key")
    op.drop_column("tasks", "source")
