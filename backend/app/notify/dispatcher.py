"""Generic delivery dispatcher — drains ``pending`` rows across EVERY
registered ``durable`` channel (change 12-notification-hub, design.md D3).

Byte-for-byte refactor of ``app.email.outbox.dispatch_outbox`` (change 08):
the SAME transactional discipline — claim (``pending -> sending``,
``attempts += 1``) + ``db.commit()`` BEFORE touching the channel's
``deliver`` (the state authorizing an irreversible external effect must be
durable first), then a final ``db.commit()`` marking ``sent`` / ``pending``
(retryable) / ``failed`` (terminal, ``EMAIL_MAX_ATTEMPTS`` exhausted) — but
generic: resolves the concrete channel by ``row.channel`` via the registry
instead of hard-coding the email sender.

Threat matrix (design.md): the exhaustion ERROR log NEVER includes
``row.payload`` — only ``dedup_key`` — to avoid leaking recipient/credential
data into logs.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.notify.models import NotificationDelivery
from app.notify.ports import DeliveryPolicy, DurableChannel
from app.notify.registry import get_channels
from app.shared.enums import DeliveryStatus

logger = logging.getLogger("solercia.notify.dispatcher")


def has_active_durable_channel() -> bool:
    """Whether the scheduled dispatch job should be registered at startup.

    Today identical to ``settings.EMAIL_ENABLED`` (design.md D4, "sin flag
    nuevo") — email is the only durable channel that exists yet.
    """

    return settings.EMAIL_ENABLED


def _resolve_channel(name: str) -> DurableChannel | None:
    """Return the registered ``durable`` channel named ``name``, if any."""

    for channel in get_channels():
        if channel.policy == DeliveryPolicy.durable and channel.name == name:
            return channel  # type: ignore[return-value]
    return None


async def _claim_delivery_row(db: AsyncSession, delivery_id: uuid.UUID) -> bool:
    """Atomically transition a delivery row FROM ``pending`` to ``sending``.

    Mirrors ``app.email.outbox._claim_outbox_row``: only a row still
    ``pending`` at the moment of the UPDATE is claimed (``RETURNING`` empty
    otherwise) — never overwrites a row a concurrent worker already claimed
    or that failed terminally.
    """

    stmt = (
        update(NotificationDelivery)
        .where(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.status == DeliveryStatus.pending,
        )
        .values(
            status=DeliveryStatus.sending,
            attempts=NotificationDelivery.attempts + 1,
        )
        .returning(NotificationDelivery.id)
    )
    result = await db.execute(stmt)
    return result.first() is not None


async def dispatch_deliveries(db: AsyncSession) -> int:
    """Claim and send every currently ``pending`` delivery row, across ALL
    registered ``durable`` channels.

    Returns the number of rows processed (sent, left pending for retry, or
    terminally failed — every claimed row counts once).
    """

    result = await db.execute(
        select(NotificationDelivery.id).where(
            NotificationDelivery.status == DeliveryStatus.pending
        )
    )
    pending_ids = [row[0] for row in result.all()]

    processed = 0
    for delivery_id in pending_ids:
        claimed = await _claim_delivery_row(db, delivery_id)
        if not claimed:
            continue  # concurrently claimed/reclaimed — never overwrite it
        await db.commit()  # claim durable BEFORE the irreversible send

        row_result = await db.execute(
            select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
        )
        row = row_result.scalar_one()

        try:
            channel = _resolve_channel(row.channel)
            if channel is None:
                raise RuntimeError(f"Canal de entrega desconocido: {row.channel!r}")
            await channel.deliver(row.payload)
        except Exception as exc:  # noqa: BLE001 - any send failure is retryable/terminal, never raised
            row.last_error = str(exc)
            if row.attempts >= settings.EMAIL_MAX_ATTEMPTS:
                row.status = DeliveryStatus.failed
                logger.error(
                    "Entrega agotó reintentos (dedup_key=%s, attempts=%d); "
                    "no se reintentará más.",
                    row.dedup_key,
                    row.attempts,
                )
            else:
                row.status = DeliveryStatus.pending
            db.add(row)
            await db.commit()
            processed += 1
            continue

        row.status = DeliveryStatus.sent
        row.sent_at = datetime.now(UTC)
        db.add(row)
        await db.commit()
        processed += 1

    return processed
