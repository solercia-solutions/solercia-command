"""unique_org_member

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-20 00:00:00.000000

Adds a unique constraint on ``organization_members (organization_id,
user_id)`` (multi-tenancy spec, "Unicidad de membresía por empresa y
usuario") so a user can never end up with two membership rows in the same
organization — a precondition the "sin admin" protection (organizations-admin
R3) relies on to count admins reliably.

``OrganizationMember`` has no child rows, so deleting the duplicates is safe
(design.md, Decision 3): ``upgrade()`` first removes every duplicate row,
keeping only the one with the earliest ``created_at`` per pair, THEN creates
the constraint — without the dedup step, any pre-existing duplicate would
make ``create_unique_constraint`` fail outright.

``downgrade()`` only drops the constraint; no data is touched, so reverting
never loses rows created after this migration.
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "uq_organization_members_org_user"


def upgrade() -> None:
    # Keep only the earliest row (by created_at) per (organization_id,
    # user_id); delete every other duplicate before the constraint can be
    # created.
    op.execute(
        """
        DELETE FROM organization_members om
        USING organization_members newer
        WHERE om.organization_id = newer.organization_id
          AND om.user_id = newer.user_id
          AND (
                om.created_at > newer.created_at
                OR (om.created_at = newer.created_at AND om.id > newer.id)
              )
        """
    )
    op.create_unique_constraint(
        _CONSTRAINT_NAME,
        "organization_members",
        ["organization_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT_NAME, "organization_members", type_="unique"
    )
