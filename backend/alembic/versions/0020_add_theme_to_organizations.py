"""add_theme_to_organizations

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-20 00:00:00.000000

Adds a nullable ``organizations.theme`` JSONB column that stores the full
@solercia/ui ThemeFile of the tenant (feat/org-theme). ``NULL`` means "use
the bundled default theme" — no backfill needed, every existing organization
simply keeps the default look. Same additive pattern as migration 0014
(ADR 0003): chains onto ``0019`` (head), purely additive.

The model declares the same JSONB type (``models.py``) so ``create_all``
(conftest) and this migration produce an identical schema.

``downgrade()`` drops the column. The theme is presentation-only metadata —
dropping it never loses task/project business data.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "theme", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "theme")
