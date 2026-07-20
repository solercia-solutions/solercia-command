"""Organization and membership ORM models."""

import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, SoftDeleteMixin, TimestampMixin
from app.shared.enums import MemberRole


class Organization(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A tenant that owns projects and members."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(120),
        unique=True,
        nullable=False,
        index=True,
    )
    # ThemeFile completo de @solercia/ui almacenado opacamente (3 niveles
    # primitives → semantic → component). ``NULL`` = tema por defecto
    # empaquetado en el frontend; el backend nunca interpreta su contenido.
    theme: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class OrganizationMember(PkMixin, TimestampMixin, Base):
    """Association between a user and an organization with a role.

    ``uq_organization_members_org_user`` (migration 0021) guarantees a user
    can never hold two membership rows in the same organization — declared
    here too (not just in the migration) so ``Base.metadata.create_all``
    (the test suite's schema path) and ``alembic check`` both agree with the
    migrated schema, same pattern as ``User``'s partial unique index.
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_members_org_user"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MemberRole] = mapped_column(
        SAEnum(MemberRole, name="member_role", native_enum=False, length=20),
        default=MemberRole.member,
        nullable=False,
    )
