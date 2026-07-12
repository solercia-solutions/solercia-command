"""Dependency ("dependencia"/área) ORM model.

An organization-scoped area or department a user can belong to.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Dependency(PkMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """An org-scoped area/department ("dependencia")."""

    __tablename__ = "dependencies"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # Optional short code (e.g. "DIR", "TEC"); not unique on purpose.
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
