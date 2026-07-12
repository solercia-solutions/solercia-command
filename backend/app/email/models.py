"""``EmailOutbox`` ORM model — transactional outbox for outgoing email (D2/D3).

Frontera de imports (design.md D2, gate correction): this module — and every
other module under ``app/email/`` — may import ``app.modules.notifications.
models`` to type ``notification_id``/the ``notification`` relationship, but
NEVER ``app.modules.notifications.repository``. Importing the repository here
would close the cycle ``notifications.repository -> app.email ->
notifications.repository`` (the repository is the one that calls into
``app.email``). Mirrors ``app/realtime/publisher.py``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.modules.notifications.models import Notification
from app.shared.base_model import PkMixin, TenantMixin, TimestampMixin
from app.shared.enums import EmailOutboxStatus


class EmailOutbox(PkMixin, TimestampMixin, TenantMixin, Base):
    """A single outgoing email delivery attempt, claimed and dispatched by
    the ``email_dispatch`` job (design.md D3 — the ONLY dispatcher)."""

    __tablename__ = "email_outbox"

    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True
    )
    notification: Mapped[Notification | None] = relationship(
        Notification, lazy="noload", viewonly=True
    )
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Unique key preventing double-enqueue: e.g. "immediate:{notification_id}"
    # or "digest:{user_id}:{period}" — see D2/D4.
    dedup_key: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )
    status: Mapped[EmailOutboxStatus] = mapped_column(
        SAEnum(EmailOutboxStatus, name="email_outbox_status", native_enum=False, length=20),
        default=EmailOutboxStatus.pending,
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
