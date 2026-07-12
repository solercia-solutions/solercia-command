"""add_assets

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-12 00:00:00.000000

Creates ``assets`` (Pk, Timestamp, SoftDelete, Audit, Tenant), ``asset_licenses``
(same mixin set, composition child — ``asset_id`` FK is ``CASCADE``: a licence
never survives its parent asset) and ``asset_tasks`` (Pk, Timestamp, Tenant —
M:N link to EXISTING tasks, ``UNIQUE(asset_id, task_id)``, hard-deleted on
unlink, same association convention as ``task_labels``). Backs change 07
(inventario de activos de información SDMujer). Purely additive, chains onto
``0009`` (reminders).

``downgrade()`` drops the three tables in reverse creation order (children
before parent: ``asset_tasks``, ``asset_licenses``, then ``assets``).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "asset_type",
            sa.Enum(
                "hardware",
                "software",
                "saas_subscription",
                "information",
                "service",
                "certificate",
                name="asset_type",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "inactive",
                "retired",
                "under_review",
                name="asset_status",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "criticality",
            sa.Enum(
                "critical",
                "high",
                "medium",
                "low",
                name="asset_criticality",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("responsible_id", sa.Uuid(), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("vendor", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_asset_type"), "assets", ["asset_type"], unique=False)
    op.create_index(op.f("ix_assets_status"), "assets", ["status"], unique=False)
    op.create_index(
        op.f("ix_assets_criticality"), "assets", ["criticality"], unique=False
    )
    op.create_index(
        op.f("ix_assets_responsible_id"), "assets", ["responsible_id"], unique=False
    )
    op.create_index(
        op.f("ix_assets_organization_id"), "assets", ["organization_id"], unique=False
    )

    op.create_table(
        "asset_licenses",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column(
            "license_type",
            sa.Enum(
                "perpetual",
                "subscription",
                "trial",
                name="license_type",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("license_key", sa.String(length=200), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_asset_licenses_asset_id"), "asset_licenses", ["asset_id"], unique=False
    )
    op.create_index(
        op.f("ix_asset_licenses_expiration_date"),
        "asset_licenses",
        ["expiration_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_asset_licenses_organization_id"),
        "asset_licenses",
        ["organization_id"],
        unique=False,
    )

    op.create_table(
        "asset_tasks",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "task_id", name="uq_asset_tasks_asset_task"),
    )
    op.create_index(
        op.f("ix_asset_tasks_asset_id"), "asset_tasks", ["asset_id"], unique=False
    )
    op.create_index(
        op.f("ix_asset_tasks_task_id"), "asset_tasks", ["task_id"], unique=False
    )
    op.create_index(
        op.f("ix_asset_tasks_organization_id"),
        "asset_tasks",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_asset_tasks_organization_id"), table_name="asset_tasks")
    op.drop_index(op.f("ix_asset_tasks_task_id"), table_name="asset_tasks")
    op.drop_index(op.f("ix_asset_tasks_asset_id"), table_name="asset_tasks")
    op.drop_table("asset_tasks")

    op.drop_index(
        op.f("ix_asset_licenses_organization_id"), table_name="asset_licenses"
    )
    op.drop_index(
        op.f("ix_asset_licenses_expiration_date"), table_name="asset_licenses"
    )
    op.drop_index(op.f("ix_asset_licenses_asset_id"), table_name="asset_licenses")
    op.drop_table("asset_licenses")

    op.drop_index(op.f("ix_assets_organization_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_responsible_id"), table_name="assets")
    op.drop_index(op.f("ix_assets_criticality"), table_name="assets")
    op.drop_index(op.f("ix_assets_status"), table_name="assets")
    op.drop_index(op.f("ix_assets_asset_type"), table_name="assets")
    op.drop_table("assets")
