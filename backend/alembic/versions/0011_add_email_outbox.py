"""add_email_outbox

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-12 00:00:00.000000

Creates ``email_outbox`` (Pk, Timestamp, Tenant — no SoftDelete/Audit, it is a
transactional delivery queue, not an entity a user manages) plus the
additive ``notifications.emailed_at`` column, the pair backing change 08
(email-notifications) Fase B: the outbox is populated in the SAME
transaction that creates an urgent ``Notification`` (D2) and drained
exclusively by the ``email_dispatch`` job (D3). Purely additive, chains onto
``0010`` (assets/SDMujer).

``downgrade()`` drops ``email_outbox`` and the ``emailed_at`` column
(reverse of creation order).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("notification_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sending",
                "sent",
                "failed",
                name="email_outbox_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_outbox_dedup_key"), "email_outbox", ["dedup_key"], unique=True
    )
    op.create_index(
        op.f("ix_email_outbox_organization_id"),
        "email_outbox",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_outbox_status"), "email_outbox", ["status"], unique=False
    )
    op.add_column(
        "notifications", sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("notifications", "emailed_at")
    op.drop_index(op.f("ix_email_outbox_status"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_organization_id"), table_name="email_outbox")
    op.drop_index(op.f("ix_email_outbox_dedup_key"), table_name="email_outbox")
    op.drop_table("email_outbox")
