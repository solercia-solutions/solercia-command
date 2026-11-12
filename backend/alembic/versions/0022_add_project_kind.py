"""add_project_kind

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-20 00:00:00.000000

Change 27-plantillas-idempotentes (design.md "Migration / Rollout"). Head
verified live (``alembic heads`` -> single ``0021``, no fork) immediately
before authoring this file (Fase 0 gate, tasks.md).

Adds ``projects.project_kind`` (enum ``area|proyecto``, ``NOT NULL``, default
``'proyecto'``): every project created via the plain ``POST /projects`` flow
is always ``proyecto``; org-role-template instantiation (this same change)
assigns it per node topology (container -> ``area``, leaf -> ``proyecto``).

Same additive pattern as ``0020_add_theme_to_organizations.py``: add the
column with a ``server_default`` so every pre-existing row is backfilled to
``'proyecto'`` for free, then drop the server default so future inserts must
go through the ORM/service default instead of relying on Postgres.

``downgrade()`` drops the column — purely presentational/topological
metadata, never referenced by a foreign key, so dropping it never loses
task/project business data.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "project_kind",
            sa.Enum("area", "proyecto", name="project_kind", native_enum=False, length=20),
            nullable=False,
            server_default="proyecto",
        ),
    )
    op.alter_column("projects", "project_kind", server_default=None)


def downgrade() -> None:
    op.drop_column("projects", "project_kind")
