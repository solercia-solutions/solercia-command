"""add_external_anchor_projects_sprints

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-13 12:00:00.000000

Adds the external origin anchor ``(source, external_key)`` to ``projects``
and ``sprints`` so the Jira importer can reconcile a re-import instead of
duplicating rows:

- ``projects``: unique ``(organization_id, source, external_key)`` among rows
  with ``external_key``.
- ``sprints``: unique ``(project_id, source, external_key)`` among rows with
  ``external_key`` (``project_id`` already implies the organization).

``tasks`` already carries its own anchor (revision 0025). Strictly additive:
two nullable columns per table, two partial unique indexes, no backfill.
``downgrade()`` drops the indexes and the four columns; rows imported from
Jira stay, they only lose their anchor.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECTS_INDEX = "uq_projects_org_source_external_key"
_SPRINTS_INDEX = "uq_sprints_project_source_external_key"


def upgrade() -> None:
    for table in ("projects", "sprints"):
        op.add_column(table, sa.Column("source", sa.String(length=50), nullable=True))
        op.add_column(table, sa.Column("external_key", sa.String(length=255), nullable=True))
    op.create_index(
        _PROJECTS_INDEX,
        "projects",
        ["organization_id", "source", "external_key"],
        unique=True,
        postgresql_where=sa.text("external_key IS NOT NULL"),
    )
    op.create_index(
        _SPRINTS_INDEX,
        "sprints",
        ["project_id", "source", "external_key"],
        unique=True,
        postgresql_where=sa.text("external_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_SPRINTS_INDEX, table_name="sprints")
    op.drop_index(_PROJECTS_INDEX, table_name="projects")
    for table in ("sprints", "projects"):
        op.drop_column(table, "external_key")
        op.drop_column(table, "source")
