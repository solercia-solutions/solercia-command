"""In-process WebSocket connection registry, scoped by (organization_id, user_id)."""
import logging
import uuid

from fastapi import WebSocket

logger = logging.getLogger("solercia.realtime")

ConnectionKey = tuple[uuid.UUID, uuid.UUID]


class ConnectionManager:
    """Tracks open WebSocket connections per ``(organization_id, user_id)``.

    No ``asyncio.Lock``: the event loop is single-threaded and
    ``register``/``unregister`` mutate the in-memory dict/set synchronously
    with no ``await`` in between, so each call is already atomic. ``publish``
    iterates a snapshot (``list(sockets)``) so a socket disconnecting mid-loop
    never breaks delivery to the others (design.md D3).
    """

    def __init__(self) -> None:
        self._connections: dict[ConnectionKey, set[WebSocket]] = {}

    def register(self, org_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket) -> None:
        """Associate ``ws`` with ``(org_id, user_id)``. Supports multiple tabs."""

        key = (org_id, user_id)
        self._connections.setdefault(key, set()).add(ws)

    def unregister(self, org_id: uuid.UUID, user_id: uuid.UUID, ws: WebSocket) -> None:
        """Drop ``ws`` and purge the key entirely once its socket set is empty."""

        key = (org_id, user_id)
        sockets = self._connections.get(key)
        if sockets is None:
            return
        sockets.discard(ws)
        if not sockets:
            self._connections.pop(key, None)

    async def publish(self, org_id: uuid.UUID, user_id: uuid.UUID, envelope: dict) -> None:
        """Push ``envelope`` to every socket of ``(org_id, user_id)``, best-effort.

        A socket whose ``send_json`` raises is logged and skipped — it never
        blocks or drops delivery to the other sockets in the snapshot.
        """

        sockets = self._connections.get((org_id, user_id))
        if not sockets:
            return
        for ws in list(sockets):
            try:
                await ws.send_json(envelope)
            except Exception:  # noqa: BLE001 - best-effort push, never break the caller
                logger.exception("Failed to push a realtime envelope to a socket.")


#: Process-wide singleton — one registry for the whole uvicorn worker.
manager = ConnectionManager()
