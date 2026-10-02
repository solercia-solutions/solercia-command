"""Organization and membership ORM models."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # Calendario laboral de la empresa (change 28-calendario-laboral):
    # default global explícito 8h/Lun-Vie. NOT NULL — siempre resoluble sin
    # caer al default global salvo el caso defensivo teórico documentado en
    # ``WorkCalendarResolver`` (design.md, "Data Flow").
    working_hours_per_day: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("8"), nullable=False
    )
    working_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=[1, 2, 3, 4, 5], nullable=False
    )


class OrganizationThemeVersion(Base):
    """One ThemeFile applied to an organization — INSERT-ONLY history.

    Rows are never updated nor deleted by the application (migration 0028), so
    the table deliberately carries no soft-delete flags and no ``updated_*``
    columns: ``user_id``/``applied_at`` are its whole audit trail, and
    ``user_name`` is captured at apply time so the entry stays readable if the
    user is later renamed or removed.

    ``id`` is a ``BIGINT`` identity (not the UUID of ``PkMixin``): applies are
    serialized per organization by a row lock, so within one organization the
    id grows in apply order — a total order and a stable pagination cursor
    (``id < before``). ``uq_organization_theme_versions_org_id`` backs both
    that cursor and the composite self-reference that ties
    ``source_version_id`` to a version of the SAME organization. The partial
    unique index allows a single initial capture per organization.

    Constraints and the index are declared here too (not just in the
    migration) so ``Base.metadata.create_all`` — the test suite's schema path
    — matches the migrated schema.
    """

    __tablename__ = "organization_theme_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_organization_theme_versions_org_id"
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_version_id"],
            [
                "organization_theme_versions.organization_id",
                "organization_theme_versions.id",
            ],
            name="fk_organization_theme_versions_source_same_org",
        ),
        Index(
            "uq_organization_theme_versions_initial_capture",
            "organization_id",
            unique=True,
            postgresql_where=text("initial_capture"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # ThemeFile completo tal como se aplicó; opaco para el backend.
    theme: Mapped[dict] = mapped_column(JSONB, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # ``True`` solo para el tema que existía antes de que hubiera historial.
    initial_capture: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    source_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


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
