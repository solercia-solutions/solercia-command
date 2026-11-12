"""add_reconciliation_proposals

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-07 12:00:00.000000

Adds the two tables of the mail classification channel (C05):

- ``task_embeddings``: cached vector per (task, embedding model) as
  ``REAL[]`` plus the hash of the embedded text. No pgvector.
- ``intake_proposals``: what the classifier proposes per mail thread, with
  ONE open proposal per (organization, thread) through a partial unique
  index (``status = 'propuesta'``).

Strictly additive: two brand-new tables, no pre-existing table touched, no
backfill. ``downgrade()`` drops both tables, discarding cached vectors and
every proposal (accepted ones already left their comment on the task).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "task_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("vector", postgresql.ARRAY(sa.REAL()), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "model", name="uq_task_embeddings_task_model"),
    )
    op.create_index(
        op.f("ix_task_embeddings_organization_id"), "task_embeddings", ["organization_id"]
    )

    op.create_table(
        "intake_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_key", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("item_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("thread_state", sa.String(length=24), nullable=False),
        sa.Column("relation", sa.String(length=24), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("classification_error", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="propuesta", nullable=False),
        sa.Column("created_task_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "status IN ('propuesta', 'aceptada', 'descartada')", name="ck_intake_proposals_status"
        ),
        sa.CheckConstraint(
            "thread_state IN ('respondido', 'pendiente_respuesta', 'solo_saliente')",
            name="ck_intake_proposals_thread_state",
        ),
        sa.CheckConstraint(
            "relation IS NULL OR relation IN ('tarea_existente', 'tarea_nueva', 'irrelevante')",
            name="ck_intake_proposals_relation",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intake_proposals_organization_id"), "intake_proposals", ["organization_id"]
    )
    op.create_index(
        "ix_intake_proposals_org_status", "intake_proposals", ["organization_id", "status"]
    )
    op.create_index(
        "ix_intake_proposals_org_task", "intake_proposals", ["organization_id", "task_id"]
    )
    op.create_index(
        "uq_intake_proposals_open_thread",
        "intake_proposals",
        ["organization_id", "conversation_key"],
        unique=True,
        postgresql_where=sa.text("status = 'propuesta'"),
    )


def downgrade() -> None:
    op.drop_index("uq_intake_proposals_open_thread", table_name="intake_proposals")
    op.drop_index("ix_intake_proposals_org_task", table_name="intake_proposals")
    op.drop_index("ix_intake_proposals_org_status", table_name="intake_proposals")
    op.drop_index(op.f("ix_intake_proposals_organization_id"), table_name="intake_proposals")
    op.drop_table("intake_proposals")
    op.drop_index(op.f("ix_task_embeddings_organization_id"), table_name="task_embeddings")
    op.drop_table("task_embeddings")
