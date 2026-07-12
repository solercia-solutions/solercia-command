"""Asset, AssetLicense and AssetTask ORM models.

``Asset`` is the inventory root (Pk+Timestamp+SoftDelete+Audit+Tenant, same
mixin set as ``Reminder``/``AlertRule``). ``AssetLicense`` is a composition
child (1:N, ``ondelete="CASCADE"``): a licence never survives its parent
asset, unlike ``Reminder.task_id`` which is ``SET NULL`` (design.md, "FK y
borrado de las entidades hijas"). ``AssetTask`` is the M:N link to existing
tasks.

``AssetTask`` deliberately DIVERGES from the ``TaskLabel`` precedent
(``Pk+Timestamp`` only, no ``TenantMixin``, scoped only via its joined
``Task``/``Label``): it adds ``TenantMixin`` directly so the link can be
scoped by ``organization_id`` without an extra join (design.md, "FK y
borrado de las entidades hijas"). It keeps the rest of the convention: no
``SoftDeleteMixin`` — unlinking a task from an asset hard-deletes the row.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from app.shared.enums import AssetCriticality, AssetStatus, AssetType, LicenseType


class Asset(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """An information asset owned by the organization (hardware, software, etc.)."""

    __tablename__ = "assets"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, name="asset_type", native_enum=False, length=30),
        nullable=False,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[AssetStatus] = mapped_column(
        SAEnum(AssetStatus, name="asset_status", native_enum=False, length=20),
        default=AssetStatus.active,
        nullable=False,
        index=True,
    )
    criticality: Mapped[AssetCriticality] = mapped_column(
        SAEnum(AssetCriticality, name="asset_criticality", native_enum=False, length=20),
        default=AssetCriticality.medium,
        nullable=False,
        index=True,
    )
    responsible_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AssetLicense(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A licence attached to an ``Asset`` (composition — CASCADE on asset delete)."""

    __tablename__ = "asset_licenses"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    license_type: Mapped[LicenseType] = mapped_column(
        SAEnum(LicenseType, name="license_type", native_enum=False, length=20),
        nullable=False,
    )
    license_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AssetTask(PkMixin, TimestampMixin, TenantMixin, Base):
    """M:N link between an ``Asset`` and an EXISTING ``Task``.

    Follows the ``Role``/``UserRole``/``TaskLabel`` association convention: a
    surrogate ``PkMixin`` id + a ``UniqueConstraint``, no ``SoftDeleteMixin``
    — unlinking removes the row outright (hard delete). DIVERGES from
    ``TaskLabel`` by keeping ``TenantMixin`` directly on the join row (see
    module docstring).
    """

    __tablename__ = "asset_tasks"
    __table_args__ = (
        UniqueConstraint("asset_id", "task_id", name="uq_asset_tasks_asset_task"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
