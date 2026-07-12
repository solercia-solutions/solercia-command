"""``EmailChannel`` — the hub's ``durable`` adapter for email (design.md D5).

Frontera de imports (design.md D2, gate correction): this module — like
every other module under ``app/email/`` — may import ``app.modules.
notifications.models`` but NEVER ``app.modules.notifications.repository``;
the repository is the caller that reaches THIS module through the hub's
channel registry (``app.notify.registry``), so importing it back here would
close the cycle ``notifications.repository -> app.email ->
notifications.repository``.

``EmailChannel.enqueue`` is the SAME logic ``enqueue_immediate_email`` used
to have (change 08) — applicability check (``EMAIL_ENABLED`` + urgent
``rule_type``) + recipient resolution + render + ``notification.emailed_at``
— but the row INSERT is delegated to the hub's store port
(``app.notify.store.enqueue_delivery``) instead of instantiating
``EmailOutbox`` directly (change 12, D3). ``EmailChannel.deliver`` is the
SAME send logic ``dispatch_outbox`` used to have inline, now called by the
GENERIC dispatcher (``app.notify.dispatcher.dispatch_deliveries``) instead
of a dedicated email-only loop.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.email.policy import EmailClass, email_class
from app.email.sender import get_email_sender
from app.email.templates import render_immediate
from app.modules.notifications.models import Notification
from app.modules.users.models import User
from app.notify.ports import DeliveryPolicy
from app.notify.registry import register_channel
from app.notify.store import enqueue_delivery

logger = logging.getLogger("solercia.email.outbox")


class EmailChannel:
    """The hub's ``durable`` adapter for email (design.md D5)."""

    name = "email"
    policy = DeliveryPolicy.durable

    async def enqueue(self, db: AsyncSession, notification: Notification) -> None:
        """Enqueue ``notification`` for immediate delivery, in the SAME
        transaction that creates it (D2). No-op if the master switch is off
        or the notification's ``rule_type`` is not urgent (D5) — the caller
        (the hub's fan-out in ``NotificationRepository.create()``) never
        needs to know either reason.
        """

        if not settings.EMAIL_ENABLED:
            return
        if email_class(notification.rule_type) != EmailClass.IMMEDIATE:
            return

        result = await db.execute(
            select(User.email).where(User.id == notification.recipient_user_id)
        )
        recipient_email = result.scalar_one_or_none()
        if recipient_email is None:
            logger.warning(
                "No se pudo resolver el correo del destinatario %s; correo "
                "inmediato omitido.",
                notification.recipient_user_id,
            )
            return

        subject, text_body, html_body = render_immediate(notification)

        await enqueue_delivery(
            db,
            channel=self.name,
            notification_id=notification.id,
            organization_id=notification.organization_id,
            dedup_key=f"immediate:{notification.id}",
            payload={
                "recipient_email": recipient_email,
                "subject": subject,
                "text_body": text_body,
                "html_body": html_body,
            },
        )
        notification.emailed_at = datetime.now(UTC)
        db.add(notification)

    async def deliver(self, payload: dict) -> None:
        """Send ``payload`` — called ONLY by the generic dispatcher."""

        sender = get_email_sender()
        await sender.send(
            to=payload["recipient_email"],
            subject=payload["subject"],
            text_body=payload["text_body"],
            html_body=payload.get("html_body"),
        )


# Registered at import time (design.md D1/D6, "sin tocar el núcleo"): the
# hub's core never imports this module — this module registers ITSELF.
register_channel(EmailChannel())
