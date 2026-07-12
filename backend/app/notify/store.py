"""Delivery store port — persistence for ``notification_deliveries`` (D3).

Frontera de imports (design.md, "Fronteras de extracción futura"): this
module — like every module under ``app/notify/`` — may import
``app.modules.notifications.models`` to type ``notification_id``, but NEVER
``app.modules.notifications.repository`` (the repository calls INTO the hub
via the channel registry; importing it back here would close the cycle
``notifications.repository -> app.notify -> notifications.repository``).
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.notify.models import NotificationDelivery
from app.shared.enums import DeliveryStatus


async def enqueue_delivery(
    db: AsyncSession,
    *,
    channel: str,
    notification_id: uuid.UUID | None,
    organization_id: uuid.UUID,
    dedup_key: str,
    payload: dict[str, Any],
) -> None:
    """Insert a ``pending`` delivery row in the SAME transaction as the caller.

    No ``commit()`` of its own — same transactional contract as the
    ``EmailOutbox`` insert it replaces (change 08 D2): the caller controls
    the transaction boundary, and a rollback by the caller reverts this
    insert too.
    """

    db.add(
        NotificationDelivery(
            organization_id=organization_id,
            notification_id=notification_id,
            channel=channel,
            status=DeliveryStatus.pending,
            dedup_key=dedup_key,
            payload=payload,
        )
    )
