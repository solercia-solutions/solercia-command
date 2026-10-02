"""add_organization_theme_versions

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-02 00:00:00.000000

Adds ``organization_theme_versions``: the INSERT-ONLY history of the ThemeFile
applied to each organization (``organizations.theme``, migration 0020). The
application only ever inserts into it — there is no update nor delete path —
so the table has no soft-delete flags and no ``updated_*`` columns.

Strictly additive: ONE brand-new table, ZERO pre-existing tables touched and
no backfill. An organization that already has a theme gets it recorded as the
initial capture the first time the theme is applied or reset afterwards, not
here.

Key and constraints (mirrored in ``app/modules/organizations/models.py`` so
``Base.metadata.create_all`` — the test suite's schema path — builds the same
schema):

- ``id`` is a ``BIGINT`` identity, ``GENERATED ALWAYS``: applies are serialized
  per organization, so the id grows in apply order and doubles as the
  pagination cursor (``id < before``, newest first).
- ``uq_organization_theme_versions_org_id`` (``organization_id``, ``id``)
  serves that cursor and is the target of the composite self-reference
  ``fk_organization_theme_versions_source_same_org``, which guarantees that
  ``source_version_id`` points to a version of the SAME organization.
- ``uq_organization_theme_versions_initial_capture`` (partial, unique) allows
  a single initial capture per organization.

``downgrade()`` drops the index and the table. The history lives only in this
table, so a downgrade discards it; ``organizations.theme`` (the theme in use)
is not touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_theme_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "theme", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_name", sa.String(length=255), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("initial_capture", sa.Boolean(), nullable=False),
        sa.Column("source_version_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_version_id"],
            [
                "organization_theme_versions.organization_id",
                "organization_theme_versions.id",
            ],
            name="fk_organization_theme_versions_source_same_org",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_organization_theme_versions_org_id"
        ),
    )
    op.create_index(
        "uq_organization_theme_versions_initial_capture",
        "organization_theme_versions",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("initial_capture"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_organization_theme_versions_initial_capture",
        table_name="organization_theme_versions",
        postgresql_where=sa.text("initial_capture"),
    )
    op.drop_table("organization_theme_versions")
