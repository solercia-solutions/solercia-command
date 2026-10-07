"""add_ai_provider_settings

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-07 00:00:00.000000

Adds ``ai_provider_settings`` (C04): the AI provider each organization
chose — ONE row per organization (UNIQUE), edited in place, no history. The
API key is stored only as a Fernet token plus its last four characters.
Presets live in code, so ``preset`` has no CHECK; ``reasoning_effort`` does.

Strictly additive: ONE brand-new table, ZERO pre-existing tables touched, no
backfill. An organization without a row keeps the default behaviour
(global ``LLM_*`` or the local Ollama preset). ``downgrade()`` drops the
table, discarding saved provider settings and their encrypted keys.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("preset", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("chat_model", sa.String(length=200), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("api_key_last4", sa.String(length=4), nullable=True),
        sa.Column("timeout_seconds", sa.Float(), server_default="60", nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="1024", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0", nullable=False),
        sa.Column("reasoning_effort", sa.String(length=16), server_default="none", nullable=True),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint(
            "reasoning_effort IS NULL OR reasoning_effort IN ('none', 'low', 'medium', 'high')",
            name="ck_ai_provider_settings_reasoning_effort",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_ai_provider_settings_organization"),
    )
    op.create_index(
        op.f("ix_ai_provider_settings_organization_id"),
        "ai_provider_settings",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_ai_provider_settings_organization_id"), table_name="ai_provider_settings"
    )
    op.drop_table("ai_provider_settings")
