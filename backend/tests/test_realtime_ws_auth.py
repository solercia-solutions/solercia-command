"""Integration tests for the realtime WS handshake — auth only, no push.

R: Handshake autenticado — token válido acepta la conexión y envía
``connection.ack`` como primer mensaje; token ausente/inválido/expirado o
usuario inactivo cierra la conexión ANTES de aceptar, sin enviar
``connection.ack``. R: Heartbeat y cierre por inactividad.
(openspec/changes/09-websocket-realtime/specs/realtime-notifications/spec.md)

Gotcha (design.md): Starlette's ``TestClient`` drives the ASGI app on its OWN
portal/event loop — never the pytest-asyncio loop the SAVEPOINT ``session``
fixture is bound to. Real data is committed for real via the
``real_org_user`` fixture (tests/conftest.py) and ``get_db`` is overridden
with a session bound to the shared NullPool ``engine`` fixture — the real
``get_db`` (bound to ``settings.DATABASE_URL``) is never used, per the gate
correction (PROHIBIDO el ``get_db`` real).

``ws_client`` is deliberately NOT entered as ``with TestClient(app) as c:``:
each test here makes a single, self-contained WS call with no REST call
interleaved on the same connection, so the app's lifespan (DB wait, seed,
scheduler) never needs to run — see test_realtime_push.py (Fase C) for the
persistent-portal variant these tests do not need.
"""

import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import skip_no_db

WS_PATH = "/api/v1/ws/notifications"


def _ensure_realtime_router_mounted(app) -> None:
    """Mount the realtime WS router on ``app`` if it is not there yet.

    ``app/main.py`` only mounts it conditionally on ``WS_ENABLED`` (task C5,
    Fase C) — idempotent so this is safe to call whether or not that mount
    already ran (production import order, or a later test in the same
    session that already triggered this fixture).
    """

    from app.realtime.router import router as realtime_router

    already_mounted = any(
        getattr(route, "path", None) == WS_PATH for route in app.routes
    )
    if not already_mounted:
        app.include_router(realtime_router, prefix="/api/v1")


@pytest.fixture
def ws_client(engine: AsyncEngine):
    """A ``TestClient`` wired to ``get_db`` overridden onto the test engine."""

    from app.database import get_db
    from app.main import app

    _ensure_realtime_router_mounted(app)

    async def _override_get_db():
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Handshake autenticado
# ---------------------------------------------------------------------------


@skip_no_db
class TestHandshakeAuth:
    def test_valid_token_accepts_and_sends_connection_ack_first(
        self, ws_client: TestClient, real_org_user
    ) -> None:
        _, _, token = real_org_user

        with ws_client.websocket_connect(WS_PATH, subprotocols=["bearer", token]) as ws:
            message = ws.receive_json()

        assert message["v"] == 1
        assert message["type"] == "connection.ack"

    def test_missing_token_closes_before_accept(self, ws_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(WS_PATH):
                pass

        # 1008 (policy violation) proves an INTENTIONAL auth reject, not a
        # generic default close (would be a trivial pass if the route were
        # simply missing — see design.md D4, "cierra ANTES de accept").
        assert exc_info.value.code == 1008

    def test_invalid_token_closes_before_accept(self, ws_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(
                WS_PATH, subprotocols=["bearer", "not-a-real-jwt"]
            ):
                pass

        assert exc_info.value.code == 1008

    def test_expired_token_closes_before_accept(
        self, ws_client: TestClient, real_org_user
    ) -> None:
        from app.shared.security import create_access_token

        _, user, _ = real_org_user
        expired_token = create_access_token(str(user.id), expires_minutes=-1)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with ws_client.websocket_connect(
                WS_PATH, subprotocols=["bearer", expired_token]
            ):
                pass

        assert exc_info.value.code == 1008

    @pytest.mark.asyncio(loop_scope="session")
    async def test_inactive_user_closes_before_accept(
        self, ws_client: TestClient, engine: AsyncEngine
    ) -> None:
        from app.modules.organizations.models import Organization, OrganizationMember
        from app.modules.users.models import User
        from app.shared.enums import MemberRole
        from app.shared.security import create_access_token, hash_password

        async with AsyncSession(engine, expire_on_commit=False) as db:
            organization = Organization(
                name="Inactive Org", slug=f"inactive-org-{uuid.uuid4().hex[:12]}"
            )
            db.add(organization)
            await db.flush()

            inactive_user = User(
                email=f"inactive-{uuid.uuid4().hex[:12]}@example.com",
                primer_nombre="Inactive",
                primer_apellido="User",
                hashed_password=hash_password("Test123*"),
                is_active=False,
            )
            db.add(inactive_user)
            await db.flush()

            db.add(
                OrganizationMember(
                    organization_id=organization.id,
                    user_id=inactive_user.id,
                    role=MemberRole.member,
                )
            )
            await db.commit()
            token = create_access_token(str(inactive_user.id))

            try:
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with ws_client.websocket_connect(
                        WS_PATH, subprotocols=["bearer", token]
                    ):
                        pass
                assert exc_info.value.code == 1008
            finally:
                await db.execute(delete(User).where(User.id == inactive_user.id))
                await db.execute(
                    delete(Organization).where(Organization.id == organization.id)
                )
                await db.commit()

    def test_query_param_fallback_authenticates_when_no_subprotocol(
        self, ws_client: TestClient, real_org_user
    ) -> None:
        """Documented fallback: ``?token=`` works when no subprotocol is sent."""

        _, _, token = real_org_user

        with ws_client.websocket_connect(f"{WS_PATH}?token={token}") as ws:
            message = ws.receive_json()

        assert message["type"] == "connection.ack"


# ---------------------------------------------------------------------------
# Heartbeat y cierre por inactividad
# ---------------------------------------------------------------------------


@skip_no_db
class TestHeartbeat:
    def test_client_responding_in_time_keeps_the_connection_open(
        self, ws_client: TestClient, real_org_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "WS_HEARTBEAT_SECONDS", 0.05)
        monkeypatch.setattr(settings, "WS_IDLE_TIMEOUT_SECONDS", 0.5)
        _, _, token = real_org_user

        with ws_client.websocket_connect(WS_PATH, subprotocols=["bearer", token]) as ws:
            ack = ws.receive_json()
            assert ack["type"] == "connection.ack"

            ping = ws.receive_json()
            assert ping["type"] == "ping"
            ws.send_text("pong")

            # A second ping proves the server kept looping (never closed).
            second_ping = ws.receive_json()
            assert second_ping["type"] == "ping"

    def test_client_inactive_beyond_idle_timeout_is_closed(
        self, ws_client: TestClient, real_org_user, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "WS_HEARTBEAT_SECONDS", 0.05)
        monkeypatch.setattr(settings, "WS_IDLE_TIMEOUT_SECONDS", 0.1)
        _, _, token = real_org_user

        with ws_client.websocket_connect(WS_PATH, subprotocols=["bearer", token]) as ws:
            ack = ws.receive_json()
            assert ack["type"] == "connection.ack"

            # Never respond — the server must close once idle time is exceeded.
            with pytest.raises(WebSocketDisconnect):
                while True:
                    ws.receive_json()
