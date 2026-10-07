"""add_intake_thread_signals

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-07 00:00:00.000000

C03: ``intake_items`` gains the mail thread signals Solercia Connect already
emits — ``conversation_id``, ``internet_message_id`` and ``direction``
(``inbound``/``outbound``) — all nullable and indexed (the first two together
with ``organization_id``, since every thread lookup is tenant-scoped).

Data step (non-destructive, idempotent): fills a NULL column ONLY from the
same key already present in the row's own ``raw_payload`` and only for
``email`` items; ``direction`` is copied only when it is one of the two known
values. ``raw_payload`` is never rewritten, no row is deleted, no value is
guessed. Rows ingested before C03 do not carry these keys, so they stay NULL
until a re-ingest of their window refreshes them (``upsert_item``).

``downgrade()`` drops the indexes and the three columns; the payload keys that
fed them remain in ``raw_payload``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL = """
UPDATE intake_items
SET
    conversation_id = COALESCE(conversation_id, NULLIF(btrim(raw_payload->>'conversation_id'), '')),
    internet_message_id = COALESCE(
        internet_message_id, NULLIF(btrim(raw_payload->>'internet_message_id'), '')
    ),
    direction = COALESCE(
        direction,
        CASE WHEN raw_payload->>'direction' IN ('inbound', 'outbound')
             THEN raw_payload->>'direction' END
    )
WHERE item_type = 'email'
  AND (
        (conversation_id IS NULL AND raw_payload ? 'conversation_id')
     OR (internet_message_id IS NULL AND raw_payload ? 'internet_message_id')
     OR (direction IS NULL AND raw_payload ? 'direction')
  )
"""


def upgrade() -> None:
    op.add_column("intake_items", sa.Column("conversation_id", sa.Text(), nullable=True))
    op.add_column("intake_items", sa.Column("internet_message_id", sa.Text(), nullable=True))
    op.add_column("intake_items", sa.Column("direction", sa.String(length=10), nullable=True))
    op.create_index(
        "ix_intake_items_org_conversation",
        "intake_items",
        ["organization_id", "conversation_id"],
    )
    op.create_index(
        "ix_intake_items_org_internet_message",
        "intake_items",
        ["organization_id", "internet_message_id"],
    )
    op.create_index(op.f("ix_intake_items_direction"), "intake_items", ["direction"])
    op.execute(_BACKFILL)


def downgrade() -> None:
    op.drop_index(op.f("ix_intake_items_direction"), table_name="intake_items")
    op.drop_index("ix_intake_items_org_internet_message", table_name="intake_items")
    op.drop_index("ix_intake_items_org_conversation", table_name="intake_items")
    op.drop_column("intake_items", "direction")
    op.drop_column("intake_items", "internet_message_id")
    op.drop_column("intake_items", "conversation_id")
