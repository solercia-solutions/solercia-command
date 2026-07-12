"""add_search_trgm_indexes

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12 00:00:00.000000

Enables ``pg_trgm`` and creates the 5 GIN trigram indexes backing
``GET /search`` (change 10-busqueda-global, design.md Decision 2 and
"Índices GIN"): ``tasks.title``, ``tasks.description``, ``projects.name``,
``projects.description``, ``task_comments.body``. Purely additive, chains
onto ``0007`` (time logs + task history).

``downgrade()`` drops the 5 indexes first, then the extension itself
(``DROP EXTENSION IF EXISTS pg_trgm``) — symmetric rollback, safe because no
later object in the linear Alembic history depends on the extension by the
time this migration is reverted (design.md "Migration / Rollout").
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index_name, table_name, column_name) — single source of truth for both
# upgrade() and downgrade(), mirrored by the ``__table_args__`` GIN indexes
# declared on Task/Project/TaskComment (design.md Decision 2: model and
# migration must produce the identical schema so `alembic check` reports no
# diff).
_GIN_INDEXES: tuple[tuple[str, str, str], ...] = (
    ("ix_tasks_title_trgm", "tasks", "title"),
    ("ix_tasks_description_trgm", "tasks", "description"),
    ("ix_projects_name_trgm", "projects", "name"),
    ("ix_projects_description_trgm", "projects", "description"),
    ("ix_task_comments_body_trgm", "task_comments", "body"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for index_name, table_name, column_name in _GIN_INDEXES:
        op.create_index(
            index_name,
            table_name,
            [column_name],
            unique=False,
            postgresql_using="gin",
            postgresql_ops={column_name: "gin_trgm_ops"},
        )


def downgrade() -> None:
    for index_name, table_name, _column_name in reversed(_GIN_INDEXES):
        op.drop_index(index_name, table_name=table_name)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
