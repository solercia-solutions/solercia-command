"""rename_email_outbox_to_notification_deliveries

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-12 00:00:00.000000

Renames ``email_outbox`` to ``notification_deliveries`` **in place**
(preserves PK/FK/indexes/rows — change 12-notification-hub, design.md D3):
generalizes the transactional delivery outbox to be channel-agnostic instead
of email-only. Adds ``channel`` (default ``'email'``, backward-compatible
for the rows that pre-date this migration) and ``payload`` JSONB, backfilled
from the 4 typed columns (``recipient_email``/``subject``/``text_body``/
``html_body``), then drops those 4 typed columns. Purely additive+rename,
chains onto ``0012`` (notification preferences).

``ALTER TABLE ... RENAME TO`` preserves index DEFINITIONS but NOT their
NAMES in Postgres, so the 3 indexes are explicitly renamed too
(``ix_email_outbox_*`` -> ``ix_notification_deliveries_*``) to match the
naming convention SQLAlchemy derives from ``NotificationDelivery``'s
``__tablename__`` — required for ``alembic check`` to report zero diff once
``app/email/models.py`` (``EmailOutbox``) is deleted in Fase 2.

``downgrade()`` reverses the index renames, re-adds the 4 typed columns,
back-fills them from ``payload``, drops ``channel``/``payload`` and renames
the table back to ``email_outbox`` — a full round trip with zero row loss.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("email_outbox", "notification_deliveries")
    op.execute(
        "ALTER INDEX ix_email_outbox_dedup_key "
        "RENAME TO ix_notification_deliveries_dedup_key"
    )
    op.execute(
        "ALTER INDEX ix_email_outbox_organization_id "
        "RENAME TO ix_notification_deliveries_organization_id"
    )
    op.execute(
        "ALTER INDEX ix_email_outbox_status RENAME TO ix_notification_deliveries_status"
    )

    op.add_column(
        "notification_deliveries",
        sa.Column("channel", sa.String(), nullable=False, server_default="email"),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.execute(
        "UPDATE notification_deliveries SET payload = jsonb_build_object("
        "'recipient_email', recipient_email, "
        "'subject', subject, "
        "'text_body', text_body, "
        "'html_body', html_body)"
    )
    op.alter_column("notification_deliveries", "payload", nullable=False)

    op.drop_column("notification_deliveries", "recipient_email")
    op.drop_column("notification_deliveries", "subject")
    op.drop_column("notification_deliveries", "text_body")
    op.drop_column("notification_deliveries", "html_body")


def downgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("subject", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "notification_deliveries", sa.Column("text_body", sa.Text(), nullable=True)
    )
    op.add_column(
        "notification_deliveries", sa.Column("html_body", sa.Text(), nullable=True)
    )
    op.execute(
        "UPDATE notification_deliveries SET "
        "recipient_email = payload->>'recipient_email', "
        "subject = payload->>'subject', "
        "text_body = payload->>'text_body', "
        "html_body = payload->>'html_body'"
    )
    op.alter_column("notification_deliveries", "recipient_email", nullable=False)
    op.alter_column("notification_deliveries", "subject", nullable=False)
    op.alter_column("notification_deliveries", "text_body", nullable=False)
    # html_body stays nullable — same as its original EmailOutbox definition.

    op.drop_column("notification_deliveries", "payload")
    op.drop_column("notification_deliveries", "channel")

    op.execute(
        "ALTER INDEX ix_notification_deliveries_status RENAME TO ix_email_outbox_status"
    )
    op.execute(
        "ALTER INDEX ix_notification_deliveries_organization_id "
        "RENAME TO ix_email_outbox_organization_id"
    )
    op.execute(
        "ALTER INDEX ix_notification_deliveries_dedup_key "
        "RENAME TO ix_email_outbox_dedup_key"
    )
    op.rename_table("notification_deliveries", "email_outbox")
