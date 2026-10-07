"""add_scheduled_sync_runs

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-07 00:00:00.000000

Adds ``scheduled_sync_runs``: the INSERT-ONLY log of the daily_sync job (C02),
one row per (run, organization) with the ordered steps (checklist, intake,
classification) as JSONB. No update nor delete path, so no soft-delete flags
and no ``updated_*`` columns (same convention as 0028).

Strictly additive: ONE brand-new table, ZERO pre-existing tables touched, no
backfill. ``downgrade()`` drops the index and the table, discarding the log.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduled_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "trigger IN ('scheduled', 'manual')", name="ck_scheduled_sync_runs_trigger"
        ),
        sa.CheckConstraint(
            "status IN ('success', 'partial', 'failed')", name="ck_scheduled_sync_runs_status"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_sync_runs_org_started",
        "scheduled_sync_runs",
        ["organization_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_sync_runs_org_started", table_name="scheduled_sync_runs")
    op.drop_table("scheduled_sync_runs")
