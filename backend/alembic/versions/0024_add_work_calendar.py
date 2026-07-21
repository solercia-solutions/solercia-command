"""add_work_calendar

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-20 00:00:00.000000

Change 28-calendario-laboral (design.md "Migration / Rollout"). Head verified
live (``alembic heads`` -> single ``0023``, no fork) immediately before
authoring this file (Fase 0 gate, tasks.md).

Adds ``working_hours_per_day``/``working_days`` to ``organizations`` (``NOT
NULL`` with a ``server_default`` — backfills existing rows to the global
default 8h/Lun-Vie) and the SAME two columns to ``projects`` (``nullable``,
NO default — only the root project of a hierarchy stores an override, and
only via ``PUT /projects/{id}/work-calendar``, never on create). Same
additive "server_default then drop it" pattern as ``0020_add_theme_to_
organizations.py``/``0022_add_project_kind.py``.

``working_days`` is the first ``ARRAY`` column of the repository
(design.md D2): valid in Postgres real (test DB) and in
``Base.metadata.create_all`` (conftest), no extension needed (unlike
``gin_trgm_ops``/JSONB). ``working_hours_per_day`` uses ``Numeric(4, 2)``
(design.md D3) so half-days (7.5, 8.5) never drift like a float would —
same type family as ``TimeLog.hours`` (``Numeric(5, 2)``).

``downgrade()`` drops the four columns in reverse order — purely additive
metadata, never referenced by a foreign key, so dropping it never loses
task/project business data.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "working_hours_per_day",
            sa.Numeric(4, 2),
            nullable=False,
            server_default="8",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "working_days",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{1,2,3,4,5}",
        ),
    )
    op.alter_column("organizations", "working_hours_per_day", server_default=None)
    op.alter_column("organizations", "working_days", server_default=None)

    op.add_column(
        "projects",
        sa.Column("working_hours_per_day", sa.Numeric(4, 2), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("working_days", postgresql.ARRAY(sa.Integer()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "working_days")
    op.drop_column("projects", "working_hours_per_day")
    op.drop_column("organizations", "working_days")
    op.drop_column("organizations", "working_hours_per_day")
