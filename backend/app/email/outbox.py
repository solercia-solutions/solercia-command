"""Email outbox — transactional queue + the single dispatcher (D2/D3).

Frontera de imports (design.md D2, gate correction): this module — like every
other module under ``app/email/`` — may import ``app.modules.notifications.
models`` but NEVER ``app.modules.notifications.repository``; the repository
is the caller that imports THIS module (``enqueue_immediate_email``), so
importing it back here would close the cycle
``notifications.repository -> app.email -> notifications.repository``.

``dispatch_outbox`` is the ONLY dispatcher in the system (D3, gate
correction): no other module drains the outbox inline. It always runs with
its OWN transactional discipline on whatever session it is given — claim
(``pending -> sending``, ``attempts += 1``) + ``db.commit()`` BEFORE touching
the ``EmailSender`` (the state authorizing an irreversible external effect
must be durable first), then a final ``db.commit()`` marking ``sent`` /
``pending`` (retryable) / ``failed`` (terminal, ``EMAIL_MAX_ATTEMPTS``
exhausted).
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.email.models import EmailOutbox
from app.email.policy import EmailClass, email_class
from app.email.sender import get_email_sender
from app.email.templates import render_immediate
from app.modules.notifications.models import Notification
from app.modules.users.models import User
from app.shared.enums import EmailOutboxStatus

logger = logging.getLogger("solercia.email.outbox")


async def enqueue_immediate_email(db: AsyncSession, notification: Notification) -> None:
    """Enqueue ``notification`` for immediate delivery, in the SAME transaction
    that creates it (D2). No-op if the master switch is off or the
    notification's ``rule_type`` is not urgent (D5) — the caller
    (``NotificationRepository.create()``) never needs to know either reason.
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
            "No se pudo resolver el correo del destinatario %s; correo inmediato omitido.",
            notification.recipient_user_id,
        )
        return

    subject, text_body, html_body = render_immediate(notification)

    db.add(
        EmailOutbox(
            organization_id=notification.organization_id,
            notification_id=notification.id,
            recipient_email=recipient_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            dedup_key=f"immediate:{notification.id}",
            status=EmailOutboxStatus.pending,
        )
    )
    notification.emailed_at = datetime.now(UTC)
    db.add(notification)


async def _claim_outbox_row(db: AsyncSession, outbox_id: uuid.UUID) -> bool:
    """Atomically transition an outbox row FROM ``pending`` to ``sending``.

    Mirrors ``app.reminders.dispatcher._claim_reminder``: only a row still
    ``pending`` at the moment of the UPDATE is claimed (``RETURNING`` empty
    otherwise) — never overwrites a row a concurrent worker already picked up
    or that failed terminally.
    """

    stmt = (
        update(EmailOutbox)
        .where(EmailOutbox.id == outbox_id, EmailOutbox.status == EmailOutboxStatus.pending)
        .values(status=EmailOutboxStatus.sending, attempts=EmailOutbox.attempts + 1)
        .returning(EmailOutbox.id)
    )
    result = await db.execute(stmt)
    return result.first() is not None


async def dispatch_outbox(db: AsyncSession) -> int:
    """Claim and send every currently ``pending`` outbox row.

    Returns the number of rows processed (sent, left pending for retry, or
    terminally failed — every claimed row counts once).
    """

    sender = get_email_sender()

    result = await db.execute(
        select(EmailOutbox.id).where(EmailOutbox.status == EmailOutboxStatus.pending)
    )
    pending_ids = [row[0] for row in result.all()]

    processed = 0
    for outbox_id in pending_ids:
        claimed = await _claim_outbox_row(db, outbox_id)
        if not claimed:
            continue  # concurrently claimed/reclaimed — never overwrite it
        await db.commit()  # claim durable BEFORE the irreversible send

        row_result = await db.execute(
            select(EmailOutbox).where(EmailOutbox.id == outbox_id)
        )
        row = row_result.scalar_one()

        try:
            await sender.send(
                to=row.recipient_email,
                subject=row.subject,
                text_body=row.text_body,
                html_body=row.html_body,
            )
        except Exception as exc:  # noqa: BLE001 - any send failure is retryable/terminal, never raised
            row.last_error = str(exc)
            if row.attempts >= settings.EMAIL_MAX_ATTEMPTS:
                row.status = EmailOutboxStatus.failed
                logger.error(
                    "Correo agotó reintentos (dedup_key=%s, attempts=%d); no se reintentará más.",
                    row.dedup_key,
                    row.attempts,
                )
            else:
                row.status = EmailOutboxStatus.pending
            db.add(row)
            await db.commit()
            processed += 1
            continue

        row.status = EmailOutboxStatus.sent
        row.sent_at = datetime.now(UTC)
        db.add(row)
        await db.commit()
        processed += 1

    return processed


async def drain_outbox_best_effort(db: AsyncSession) -> None:
    """Best-effort wrapper around :func:`dispatch_outbox` — never raises.

    Exposed for a future request-time immediate drain (D3/interfaces); NOT
    wired into the alert evaluator or any other request path in this change
    (gate correction — ``email_dispatch`` is the only dispatcher).
    """

    try:
        await dispatch_outbox(db)
    except Exception:  # noqa: BLE001
        logger.exception("Drenaje best-effort del outbox de correo falló.")
