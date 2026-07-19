"""add_glpi_homologation

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-19 00:00:00.000000

Change 17-adapter-glpi (design.md "Migration / Rollout"). ``down_revision``
anchored to ``0016`` (add_federated_identities) — the real head verified
live via ``alembic heads`` immediately before authoring this file (T2.1).

Five additive pieces, all in this ONE migration:

1. ``users.numero_documento`` (nullable) + a PARTIAL unique index
   (``WHERE numero_documento IS NOT NULL``) — global scope, same as
   ``email``, since ``User`` carries no ``TenantMixin`` in the real code
   (user-homologation spec, UH-R1).
2. ``connectors.credential_kind`` (``oauth``/``api_token``, default
   ``oauth`` so every pre-existing connector — microsoft365/google from
   changes 15/16 — keeps behaving exactly as before) + ``connectors.
   settings`` (JSONB, nullable, non-secret provider config). The 17 is
   DUEÑO of both columns (design.md "Deltas al 14"); changes 18/19 only
   ever CONSUME ``settings`` with their own namespace, never add a column.
3. ``glpi_user_links`` — confirmed GLPI person -> platform user mapping,
   ``UNIQUE(connector_id, glpi_user_id)``.
4. ``glpi_unmatched_assignees`` — the unmatched-queue HEADER, one row per
   unmatched GLPI person, same unique anchor as the link table.
5. ``glpi_unmatched_cases`` — the unmatched-queue DETAIL, 1:N off the
   header, ``UNIQUE(unmatched_assignee_id, glpi_ticket_id)`` (idempotent
   re-sync: a second case for the same person is appended, never
   duplicated).

``downgrade()`` reverses in strict dependency order: cases -> unmatched
headers -> links -> connectors columns -> numero_documento. Safe as a clean
round-trip with zero pre-existing GLPI rows (this is a purely additive
migration; no data transformation happens on the way up or down).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- 1. users.numero_documento + partial unique index -------------------
    op.add_column(
        "users", sa.Column("numero_documento", sa.String(length=32), nullable=True)
    )
    op.create_index(
        "uq_users_numero_documento",
        "users",
        ["numero_documento"],
        unique=True,
        postgresql_where=sa.text("numero_documento IS NOT NULL"),
    )

    # -- 2. connectors.credential_kind + connectors.settings ----------------
    op.add_column(
        "connectors",
        sa.Column(
            "credential_kind",
            sa.Enum(
                "oauth",
                "api_token",
                name="connector_credential_kind",
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default="oauth",
        ),
    )
    op.add_column(
        "connectors",
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # -- 3. glpi_user_links ---------------------------------------------------
    op.create_table(
        "glpi_user_links",
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("glpi_user_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "match_method",
            sa.Enum(
                "email",
                "document",
                "name",
                "manual",
                name="glpi_match_method",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("glpi_username", sa.String(length=255), nullable=True),
        sa.Column("glpi_email", sa.String(length=255), nullable=True),
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
            "connector_id", "glpi_user_id", name="uq_glpi_user_links_connector_glpi_user"
        ),
    )
    op.create_index(
        op.f("ix_glpi_user_links_connector_id"), "glpi_user_links", ["connector_id"]
    )
    op.create_index(
        op.f("ix_glpi_user_links_glpi_user_id"), "glpi_user_links", ["glpi_user_id"]
    )
    op.create_index(op.f("ix_glpi_user_links_user_id"), "glpi_user_links", ["user_id"])
    op.create_index(
        op.f("ix_glpi_user_links_organization_id"), "glpi_user_links", ["organization_id"]
    )

    # -- 4. glpi_unmatched_assignees (header) ---------------------------------
    op.create_table(
        "glpi_unmatched_assignees",
        sa.Column("connector_id", sa.Uuid(), nullable=False),
        sa.Column("glpi_user_id", sa.String(length=64), nullable=False),
        sa.Column("glpi_username", sa.String(length=255), nullable=True),
        sa.Column("glpi_email", sa.String(length=255), nullable=True),
        sa.Column("glpi_document", sa.String(length=64), nullable=True),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "resolved",
                "ignored",
                name="glpi_unmatched_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("resolved_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_id",
            "glpi_user_id",
            name="uq_glpi_unmatched_assignees_connector_glpi_user",
        ),
    )
    op.create_index(
        op.f("ix_glpi_unmatched_assignees_connector_id"),
        "glpi_unmatched_assignees",
        ["connector_id"],
    )
    op.create_index(
        op.f("ix_glpi_unmatched_assignees_glpi_user_id"),
        "glpi_unmatched_assignees",
        ["glpi_user_id"],
    )
    op.create_index(
        op.f("ix_glpi_unmatched_assignees_status"),
        "glpi_unmatched_assignees",
        ["status"],
    )
    op.create_index(
        op.f("ix_glpi_unmatched_assignees_organization_id"),
        "glpi_unmatched_assignees",
        ["organization_id"],
    )

    # -- 5. glpi_unmatched_cases (detail, 1:N off the header) -----------------
    op.create_table(
        "glpi_unmatched_cases",
        sa.Column("unmatched_assignee_id", sa.Uuid(), nullable=False),
        sa.Column("glpi_ticket_id", sa.String(length=64), nullable=False),
        sa.Column("glpi_ticket_title", sa.String(length=255), nullable=True),
        sa.Column("glpi_ticket_status", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["unmatched_assignee_id"],
            ["glpi_unmatched_assignees.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "unmatched_assignee_id",
            "glpi_ticket_id",
            name="uq_glpi_unmatched_cases_assignee_ticket",
        ),
    )
    op.create_index(
        op.f("ix_glpi_unmatched_cases_unmatched_assignee_id"),
        "glpi_unmatched_cases",
        ["unmatched_assignee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_glpi_unmatched_cases_unmatched_assignee_id"),
        table_name="glpi_unmatched_cases",
    )
    op.drop_table("glpi_unmatched_cases")

    op.drop_index(
        op.f("ix_glpi_unmatched_assignees_organization_id"),
        table_name="glpi_unmatched_assignees",
    )
    op.drop_index(
        op.f("ix_glpi_unmatched_assignees_status"), table_name="glpi_unmatched_assignees"
    )
    op.drop_index(
        op.f("ix_glpi_unmatched_assignees_glpi_user_id"),
        table_name="glpi_unmatched_assignees",
    )
    op.drop_index(
        op.f("ix_glpi_unmatched_assignees_connector_id"),
        table_name="glpi_unmatched_assignees",
    )
    op.drop_table("glpi_unmatched_assignees")

    op.drop_index(
        op.f("ix_glpi_user_links_organization_id"), table_name="glpi_user_links"
    )
    op.drop_index(op.f("ix_glpi_user_links_user_id"), table_name="glpi_user_links")
    op.drop_index(
        op.f("ix_glpi_user_links_glpi_user_id"), table_name="glpi_user_links"
    )
    op.drop_index(
        op.f("ix_glpi_user_links_connector_id"), table_name="glpi_user_links"
    )
    op.drop_table("glpi_user_links")

    op.drop_column("connectors", "settings")
    op.drop_column("connectors", "credential_kind")

    op.drop_index("uq_users_numero_documento", table_name="users")
    op.drop_column("users", "numero_documento")
