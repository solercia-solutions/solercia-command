"""Project ORM model."""

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Integer, String, Text, UniqueConstraint
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
    __table_args__ = (
        # Each organization uses unique project codes (e.g. "SDM", "PLT").
        UniqueConstraint("organization_id", "code", name="uq_project_code_per_org"),
    )

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
    # Short human-readable key (2-10 uppercase alphanumeric chars).
    # Auto-generated from the project name on create; unique per organization.
    # Nullable to allow schema addition on an existing DB without migration.
    code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # Monotonically increasing counter used to assign task_number values
    # atomically via UPDATE ... RETURNING, avoiding race conditions.
    task_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
