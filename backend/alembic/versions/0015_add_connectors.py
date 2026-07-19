"""add_connectors

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-18 00:00:00.000000

Creates ``connectors`` (Pk, Timestamp, SoftDelete, Audit, Tenant —
``UNIQUE(organization_id, provider)``), ``connected_accounts`` (same mixin
set — ``UNIQUE(connector_id, external_account_id)``, NEVER
``(connector_id, user_id)``: a user may connect several accounts of the
same provider, decisión ratificada #1) and ``connection_credentials``
(Pk, Timestamp, Tenant — ``UNIQUE(connected_account_id)``, an isolated 1:1
table so encrypted tokens never live alongside API-exposed account fields,
decisión ratificada #4). Backs change 14-integration-ports. Purely
additive, chains onto ``0014`` (add_project_parent_id, head at the time
this migration was authored — verified live via ``alembic heads``, T2.1).

``downgrade()`` drops the three tables in reverse creation order (children
before parents: ``connection_credentials``, ``connected_accounts``, then
``connectors``).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "inactive",
                "error",
                name="connector_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
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
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "provider", name="uq_connectors_organization_provider"
        ),
    )
    op.create_index(op.f("ix_connectors_provider"), "connectors", ["provider"], unique=False)
    op.create_index(op.f("ix_connectors_status"), "connectors", ["status"], unique=False)
    op.create_index(
        op.f("ix_connectors_organization_id"), "connectors", ["organization_id"], unique=False
    )

    op.create_table(
        "connected_accounts",
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "expired",
                "revoked",
                "error",
                name="account_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
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
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_id",
            "external_account_id",
            name="uq_connected_accounts_connector_external",
        ),
    )
    op.create_index(
        op.f("ix_connected_accounts_connector_id"),
        "connected_accounts",
        ["connector_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connected_accounts_user_id"),
        "connected_accounts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connected_accounts_external_account_id"),
        "connected_accounts",
        ["external_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connected_accounts_status"), "connected_accounts", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_connected_accounts_organization_id"),
        "connected_accounts",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "connection_credentials",
        sa.Column("connected_account_id", sa.Uuid(), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_type", sa.String(length=50), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["connected_account_id"], ["connected_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connected_account_id", name="uq_connection_credentials_connected_account"
        ),
    )
    op.create_index(
        op.f("ix_connection_credentials_connected_account_id"),
        "connection_credentials",
        ["connected_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connection_credentials_organization_id"),
        "connection_credentials",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_connection_credentials_organization_id"),
        table_name="connection_credentials",
    )
    op.drop_index(
        op.f("ix_connection_credentials_connected_account_id"),
        table_name="connection_credentials",
    )
    op.drop_table("connection_credentials")

    op.drop_index(
        op.f("ix_connected_accounts_organization_id"), table_name="connected_accounts"
    )
    op.drop_index(op.f("ix_connected_accounts_status"), table_name="connected_accounts")
    op.drop_index(
        op.f("ix_connected_accounts_external_account_id"),
        table_name="connected_accounts",
    )
    op.drop_index(op.f("ix_connected_accounts_user_id"), table_name="connected_accounts")
    op.drop_index(
        op.f("ix_connected_accounts_connector_id"), table_name="connected_accounts"
    )
    op.drop_table("connected_accounts")

    op.drop_index(op.f("ix_connectors_organization_id"), table_name="connectors")
    op.drop_index(op.f("ix_connectors_status"), table_name="connectors")
    op.drop_index(op.f("ix_connectors_provider"), table_name="connectors")
    op.drop_table("connectors")
