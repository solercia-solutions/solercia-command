"""add_project_parent_id

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-18 00:00:00.000000

Adds a nullable self-FK ``projects.parent_project_id`` (``ON DELETE
SET NULL``), the structural backbone of the project hierarchy (change
21-project-hierarchy, design.md "Migration / Rollout"). Same additive
pattern as ``Task.parent_task_id`` and ``projects.code`` (ADR 0003): chains
onto ``0013`` (head), purely additive, no data migration/backfill needed —
every existing project simply becomes a root (``parent_project_id = NULL``).

The model declares the same index via ``index=True`` (``models.py``) so
``create_all`` (conftest) and this migration produce an identical schema —
``alembic check`` reports no diff (same parity contract as migration 0008).

``downgrade()`` drops the index then the column — the reverse of creation
order. No data is lost: the column being dropped only ever held hierarchy
metadata, never task/project business data.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("parent_project_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "projects_parent_project_id_fkey",
        "projects",
        "projects",
        ["parent_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_projects_parent_project_id"),
        "projects",
        ["parent_project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_parent_project_id"), table_name="projects")
    op.drop_constraint(
        "projects_parent_project_id_fkey", "projects", type_="foreignkey"
    )
    op.drop_column("projects", "parent_project_id")
