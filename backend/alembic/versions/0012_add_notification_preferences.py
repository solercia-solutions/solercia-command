"""add_notification_preferences

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-12 00:00:00.000000

Creates ``notification_preferences`` (Pk, Timestamp, Tenant, Audit — no
SoftDelete: a singleton row per ``(organization_id, user_id)``, upserted in
place, never soft-deleted), the table backing change 08 (email-notifications)
Fase C digest cadence (`none/daily/weekly`, default `none`). Purely additive,
chains onto ``0011`` (email outbox).

``downgrade()`` drops the table.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "digest_frequency",
            sa.Enum(
                "none",
                "daily",
                "weekly",
                name="digest_frequency",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("digest_hour", sa.Integer(), nullable=False),
        sa.Column("digest_weekday", sa.Integer(), nullable=True),
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_notification_preferences_org_user"
        ),
    )
    op.create_index(
        op.f("ix_notification_preferences_organization_id"),
        "notification_preferences",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_preferences_user_id"),
        "notification_preferences",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notification_preferences_user_id"), table_name="notification_preferences"
    )
    op.drop_index(
        op.f("ix_notification_preferences_organization_id"),
        table_name="notification_preferences",
    )
    op.drop_table("notification_preferences")
