"""Realtime notification publisher — buffer on create(), drain after commit.

``NotificationRepository.create()`` fans out to every channel registered in
the hub (change 12-notification-hub, design.md D2/D5): :class:`WebSocketChannel`
is the ``best_effort`` adapter whose ``buffer`` calls :func:`buffer_notification`
to serialize the envelope onto ``db.info`` right after ``flush``/``refresh``,
before the ORM instance can expire post-commit — ZERO behavior change from
before the hub existed. The owner of the transaction (alert evaluator,
comment mentions) then calls :func:`flush_pending` once, right after
``db.commit()``, to actually push to connected sockets.
"""
import logging
import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import NotificationRead
from app.notify.ports import DeliveryPolicy
from app.notify.registry import register_channel
from app.realtime.manager import manager
from app.realtime.schemas import make_envelope

logger = logging.getLogger("solercia.realtime")

#: Key on ``AsyncSession.info`` where serialized (org_id, user_id, envelope)
#: tuples wait between ``create()`` and the next ``flush_pending`` drain.
_PENDING_KEY = "realtime_pending"


class NotificationPublisher(Protocol):
    """Port implemented by :data:`app.realtime.manager.manager`."""

    async def publish(self, org_id: uuid.UUID, user_id: uuid.UUID, envelope: dict) -> None: ...


def buffer_notification(db: AsyncSession, notification: Notification) -> None:
    """Serialize ``notification`` and queue it for the next drain on ``db``.

    Serializing now (not deferring to publish time) avoids depending on the
    ORM instance staying attached/unexpired after a later ``commit()``.
    """

    envelope = make_envelope(
        "notification.created",
        NotificationRead.model_validate(notification).model_dump(mode="json"),
    )
    pending: list[tuple[uuid.UUID, uuid.UUID, dict]] = db.info.setdefault(_PENDING_KEY, [])
    pending.append((notification.organization_id, notification.recipient_user_id, envelope))


async def flush_pending(db: AsyncSession) -> None:
    """Pop and publish everything buffered on ``db``, best-effort.

    The pop MUST happen before publishing (design.md D2, gate correction):
    ``evaluate_all_organizations`` reuses ONE session across N organizations
    with a commit+drain cycle per organization. Without an atomic pop here,
    the first organization's payloads would be re-published on every
    subsequent drain of the same session.
    """

    pending: list[tuple[uuid.UUID, uuid.UUID, dict]] = db.info.pop(_PENDING_KEY, [])
    for org_id, user_id, envelope in pending:
        try:
            await manager.publish(org_id, user_id, envelope)
        except Exception:  # noqa: BLE001 - best-effort, must never break the caller
            logger.exception("Failed to flush a pending realtime notification.")


class WebSocketChannel:
    """The hub's ``best_effort`` adapter for realtime push (design.md D5).

    ``buffer`` is a thin wrapper around :func:`buffer_notification` — ZERO
    behavior change (specs/realtime-notifications/spec.md, "Comportamiento
    idéntico tras el refactor"): no ``notification_deliveries`` row is ever
    written for this channel, by definition of ``best_effort``.
    """

    name = "websocket"
    policy = DeliveryPolicy.best_effort

    def buffer(self, db: AsyncSession, notification: Notification) -> None:
        buffer_notification(db, notification)


# Registered at import time (design.md D1/D6, "sin tocar el núcleo"): the
# hub's core never imports this module — this module registers ITSELF.
register_channel(WebSocketChannel())
