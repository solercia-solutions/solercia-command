"""add_federated_identities

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-18 00:00:00.000000

Creates ``federated_identities`` (Pk, Timestamp, SoftDelete, Audit —
NO Tenant mixin: the row is anchored to a ``user``, which is itself
org-scoped via ``organization_members``) and relaxes ``users.hashed_password``
to nullable, so a user created/linked only via SSO never carries a local
password (change 20-sso-keycloak, design.md D1). Purely additive, chains
onto ``0015`` (add_connectors, head at the time this migration was authored
— verified live via ``alembic heads``, T01).

``downgrade()`` reverts both changes but GUARDS the ``hashed_password``
restore: if any user row still has ``hashed_password IS NULL`` (an
SSO-only account with no local credential ever set), restoring the
``NOT NULL`` constraint would either fail outright or silently corrupt that
row — so the guard raises BEFORE touching the schema, leaving both the
table and the column untouched until the operator resolves those accounts
(design.md "Migration / Rollout").
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class SsoOnlyUsersExistError(RuntimeError):
    """Raised when downgrade() would corrupt SSO-only (password-less) users."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"Cannot downgrade 0016: {count} user(s) have hashed_password "
            "IS NULL (SSO-only accounts). Assign a local password to each "
            "one first, or accept losing those accounts, before "
            "downgrading."
        )


def upgrade() -> None:
    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.create_table(
        "federated_identities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("issuer", sa.String(length=500), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuer", "subject", name="uq_federated_identities_issuer_subject"
        ),
    )
    op.create_index(
        op.f("ix_federated_identities_user_id"),
        "federated_identities",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    orphan_count = bind.execute(
        sa.text("SELECT count(*) FROM users WHERE hashed_password IS NULL")
    ).scalar_one()
    if orphan_count:
        raise SsoOnlyUsersExistError(orphan_count)

    op.drop_index(
        op.f("ix_federated_identities_user_id"), table_name="federated_identities"
    )
    op.drop_table("federated_identities")

    op.alter_column(
        "users",
        "hashed_password",
        existing_type=sa.String(length=255),
        nullable=False,
    )
