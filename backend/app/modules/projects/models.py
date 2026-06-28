"""Project ORM model."""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from app.shared.enums import Methodology, ProjectStatus


class Project(PkMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """A project scoped to an organization and configured by a methodology."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology: Mapped[Methodology] = mapped_column(
        SAEnum(Methodology, name="methodology", native_enum=False, length=20),
        nullable=False,
    )
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status", native_enum=False, length=20),
        default=ProjectStatus.active,
        nullable=False,
    )
