"""connectors_unique_only_active

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-13 15:00:00.000000

Replaces the unique constraint ``uq_connectors_organization_provider`` on
``connectors (organization_id, provider)`` with a partial unique index of the
same name limited to active rows (``WHERE is_active``).

Deleting a connector is a soft delete, so the old constraint kept counting the
deleted row and connecting the same provider again failed with an
``IntegrityError``. No row changes. ``downgrade()`` restores the full
constraint and fails if an organization has both a deleted and an active
connector for the same provider.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "uq_connectors_organization_provider"


def upgrade() -> None:
    op.drop_constraint(_NAME, "connectors", type_="unique")
    op.create_index(
        _NAME,
        "connectors",
        ["organization_id", "provider"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index(_NAME, table_name="connectors")
    op.create_unique_constraint(_NAME, "connectors", ["organization_id", "provider"])
