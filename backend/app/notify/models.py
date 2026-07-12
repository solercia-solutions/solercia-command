"""``NotificationDelivery`` ORM model — channel-agnostic delivery outbox
(rename of ``EmailOutbox``, change 12-notification-hub, design.md D3).

Frontera de imports (design.md, "Fronteras de extracción futura"): this
module — and every other module under ``app/notify/`` — may import
``app.modules.notifications.models`` to type ``notification_id``/the
``notification`` relationship, but NEVER ``app.modules.notifications.
repository``. Importing the repository here would close the cycle
``notifications.repository -> app.notify -> notifications.repository`` (the
repository is the one that iterates the channel registry that lives in this
package). Mirrors ``app/email/models.py`` (change 08) before it.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.modules.notifications.models import Notification
from app.shared.base_model import PkMixin, TenantMixin, TimestampMixin
from app.shared.enums import DeliveryStatus


class NotificationDelivery(PkMixin, TimestampMixin, TenantMixin, Base):
    """A single delivery attempt for one channel, claimed and dispatched by
    the ``delivery_dispatch`` job (design.md D3 — the ONLY dispatcher)."""

    __tablename__ = "notification_deliveries"

    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True
    )
    notification: Mapped[Notification | None] = relationship(
        Notification, lazy="noload", viewonly=True
    )
    # Name of the channel that generated this delivery (e.g. "email"). Plain
    # unbounded VARCHAR + server_default 'email' mirrors migration 0013's
    # ``ADD COLUMN`` exactly, so ``alembic check`` reports zero diff.
    channel: Mapped[str] = mapped_column(String, nullable=False, server_default="email")
    # Unique key preventing double-enqueue: e.g. "immediate:{notification_id}"
    # or "digest:{user_id}:{period}" — see D2/D4.
    dedup_key: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        SAEnum(DeliveryStatus, name="email_outbox_status", native_enum=False, length=20),
        default=DeliveryStatus.pending,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Channel-specific data (e.g. recipient/subject/bodies for email). D3:
    # replaces the 4 typed columns EmailOutbox used to have.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
