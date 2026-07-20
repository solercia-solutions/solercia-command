"""WebSocket endpoint for realtime notification push.

Handshake auth reuses :func:`app.dependencies.authenticate_access_token`
(the same code path REST's ``get_current_user`` delegates to) so a rejected
token yields the exact same ``AppException`` regardless of transport
(design.md D4). Org scope is the caller's first membership, identical to
``get_current_membership``.
"""
import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.database import get_db
from app.dependencies import authenticate_access_token
from app.modules.organizations.models import OrganizationMember
from app.realtime.manager import manager
from app.realtime.schemas import make_envelope
from app.shared.exceptions import AppException

logger = logging.getLogger("solercia.realtime")

router = APIRouter(tags=["realtime"])

#: Policy-violation close code (RFC 6455 §7.4.1) — used for every pre-accept
#: reject so tests can distinguish an intentional auth close from a default one.
_POLICY_VIOLATION = 1008


def _extract_token(websocket: WebSocket) -> str | None:
    """Read the bearer token from ``Sec-WebSocket-Protocol`` or ``?token=``.

    Primary: subprotocol ``"bearer, <token>"``. Fallback (documented risk —
    query params leak in proxy logs): ``?token=``.
    """

    subprotocols = websocket.scope.get("subprotocols") or []
    if len(subprotocols) >= 2 and subprotocols[0] == "bearer":
        return subprotocols[1]
    return websocket.query_params.get("token")


async def _resolve_organization_id(
    db: AsyncSession, user_id: uuid.UUID, org_hint: str | None = None
) -> uuid.UUID | None:
    """Resolve the org scope for this connection (organizations-admin R4
    extended to the WS handshake).

    ``org_hint`` (``?org_id=``) present -> validated as a REAL membership of
    ``user_id``; a malformed UUID or an organization the user does not
    belong to returns ``None`` — the caller closes with ``1008`` BEFORE
    accept, the same posture as an invalid token (gotcha 2 extended to the
    WS: never silently falls back to a different scope). Hint ABSENT ->
    unchanged fallback, identical to REST's ``get_current_membership``: the
    first membership by ``created_at``.
    """

    if org_hint is not None:
        try:
            organization_id = uuid.UUID(org_hint)
        except ValueError:
            return None
        result = await db.execute(
            select(OrganizationMember.organization_id).where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
        return result.scalars().first()

    result = await db.execute(
        select(OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_id)
        .order_by(OrganizationMember.created_at.asc())
    )
    return result.scalars().first()


@router.websocket("/ws/notifications")
async def notifications_ws(
    websocket: WebSocket, db: AsyncSession = Depends(get_db)
) -> None:
    """Push channel scoped to ``(organization_id, user_id)`` — best-effort.

    REST stays authoritative: this channel only ever pushes to sockets that
    are already connected; a lost/never-open connection never blocks or
    fails notification creation (design.md D5).
    """

    token = _extract_token(websocket)
    if token is None:
        await websocket.close(code=_POLICY_VIOLATION)
        return

    try:
        user = await authenticate_access_token(db, token)
    except AppException:
        await websocket.close(code=_POLICY_VIOLATION)
        return

    org_hint = websocket.query_params.get("org_id")
    org_id = await _resolve_organization_id(db, user.id, org_hint)
    if org_id is None:
        await websocket.close(code=_POLICY_VIOLATION)
        return

    await websocket.accept(subprotocol="bearer")
    await websocket.send_json(make_envelope("connection.ack"))
    manager.register(org_id, user.id, websocket)

    try:
        await _heartbeat_loop(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(org_id, user.id, websocket)


async def _heartbeat_loop(websocket: WebSocket) -> None:
    """Ping every ``WS_HEARTBEAT_SECONDS``; close after ``WS_IDLE_TIMEOUT_SECONDS``
    of silence — any client message (not just literal ``pong``) counts as
    activity and resets the idle clock.
    """

    last_activity = time.monotonic()
    while True:
        heartbeat = settings.WS_HEARTBEAT_SECONDS
        idle_timeout = settings.WS_IDLE_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat)
            last_activity = time.monotonic()
        except TimeoutError:
            if time.monotonic() - last_activity >= idle_timeout:
                await websocket.close(code=1000)
                return
            await websocket.send_json(make_envelope("ping"))
