"""Add system project marker and current-shape constraint.

Single on-disk head 0025 checked before authoring; never executed here.
Existing rows remain ordinary. This CHECK does not prevent unmarking or hard
DELETE; no backfill, Generales creation, hierarchy or intake changes occur.
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_projects_system_shape",
        "projects",
        "NOT is_system OR (code IS NOT NULL AND code = 'GENERALES' AND methodology = 'custom' AND status = 'active' AND is_active AND deleted_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_projects_system_shape", "projects", type_="check")
    op.drop_column("projects", "is_system")
