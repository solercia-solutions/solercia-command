"""E2E: notification creation (mention / alert evaluator) pushes over WS.

R: Push en creación de notificación · R: Aislamiento estricto por
organización · R: Best-effort ante desconexión/fallo de publish
(openspec/changes/09-websocket-realtime/specs/realtime-notifications/spec.md,
specs/notifications-inapp/spec.md — "REST sigue siendo autoritativo").

Gate correction (design.md D2/Testing Strategy, "corrección de gate — BD"):
PROHIBIDO usar el ``get_db`` real ligado a ``settings.DATABASE_URL`` (BD de
desarrollo o DNS inalcanzable fuera de compose). REST and WS calls must share
ONE Starlette ``TestClient`` portal/event loop (never mixed with the
SAVEPOINT ``session`` fixture), so ``get_db`` is overridden with sessions
bound to a DEDICATED ``NullPool`` engine over ``TEST_DATABASE_URL``, created
INSIDE that portal via ``client.portal.call(...)``, with explicit row
cleanup and ``engine.dispose()`` in teardown. The real app lifespan (DB
wait/seed/scheduler against ``settings.DATABASE_URL``) is bypassed — the
persistent portal is still required for REST+WS interleaving.
"""

import contextlib
import json
import queue
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import NamedTuple

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

from tests.conftest import TEST_DATABASE_URL, skip_no_db

WS_PATH = "/api/v1/ws/notifications"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@contextlib.asynccontextmanager
async def _noop_lifespan(app):
    """Skip the real app lifespan for this test — see module docstring."""
    yield


def _receive_json_with_timeout(ws, timeout: float = 2.0) -> dict:
    """Bounded ``receive_json`` — never hangs the suite.

    ``WebSocketTestSession.receive()`` blocks indefinitely with no public
    timeout parameter; its delivery queue is a plain thread-safe
    ``queue.Queue``, so a bounded ``get(timeout=)`` on it is the only safe
    way to wait for a push without risking an indefinite hang if the
    production hook is missing/broken — fails the test cleanly instead.
    """

    try:
        message = ws._send_queue.get(timeout=timeout)
    except queue.Empty:
        pytest.fail(f"No se recibió ningún mensaje WS en {timeout}s.")
    if isinstance(message, BaseException):
        raise message
    ws._raise_on_close(message)
    return json.loads(message["text"])


def _assert_no_message_received(ws, timeout: float = 0.3) -> None:
    """Assert nothing arrives on ``ws`` within ``timeout`` seconds.

    Isolation itself is already proven at the unit level
    (test_realtime_manager.py::TestConnectionManager) — this only guards the
    E2E wiring end to end.
    """

    with pytest.raises(queue.Empty):
        ws._send_queue.get(timeout=timeout)


async def _run_evaluate_organization(engine: AsyncEngine, org_id: uuid.UUID) -> int:
    from app.alerts.evaluator import evaluate_organization

    async with AsyncSession(engine, expire_on_commit=False) as db:
        return await evaluate_organization(db, org_id)


async def _seed_e2e_data(engine: AsyncEngine) -> SimpleNamespace:
    """A REALLY committed two-org fixture: mention flow + an overdue task."""

    from app.modules.alert_rules.models import AlertRule
    from app.modules.organizations.models import Organization, OrganizationMember
    from app.modules.projects.models import Project
    from app.modules.tasks.models import Task
    from app.modules.users.models import User
    from app.shared.enums import MemberRole, Methodology
    from app.shared.security import create_access_token, hash_password

    async with AsyncSession(engine, expire_on_commit=False) as db:
        org_a = Organization(name="E2E Org A", slug=f"e2e-a-{uuid.uuid4().hex[:12]}")
        org_b = Organization(name="E2E Org B", slug=f"e2e-b-{uuid.uuid4().hex[:12]}")
        db.add_all([org_a, org_b])
        await db.flush()

        author = User(
            email=f"e2e-author-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Autor",
            primer_apellido="E2E",
            hashed_password=hash_password("Test123*"),
        )
        recipient = User(
            email=f"e2e-recipient-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Destinatario",
            primer_apellido="E2E",
            hashed_password=hash_password("Test123*"),
        )
        other_user = User(
            email=f"e2e-other-{uuid.uuid4().hex[:12]}@example.com",
            primer_nombre="Otra",
            primer_apellido="Org",
            hashed_password=hash_password("Test123*"),
        )
        db.add_all([author, recipient, other_user])
        await db.flush()

        db.add_all(
            [
                OrganizationMember(
                    organization_id=org_a.id, user_id=author.id, role=MemberRole.member
                ),
                OrganizationMember(
                    organization_id=org_a.id, user_id=recipient.id, role=MemberRole.member
                ),
                OrganizationMember(
                    organization_id=org_b.id, user_id=other_user.id, role=MemberRole.member
                ),
            ]
        )
        await db.flush()

        project_a = Project(
            organization_id=org_a.id,
            name="E2E Project",
            methodology=Methodology.kanban,
            code=f"E2E{uuid.uuid4().hex[:6].upper()}",
            task_counter=0,
        )
        db.add(project_a)
        await db.flush()

        task_a = Task(project_id=project_a.id, title="Tarea para mención", status="Backlog")
        overdue_task = Task(
            project_id=project_a.id,
            title="Tarea vencida",
            status="Backlog",
            assignee_id=recipient.id,
            due_date=datetime.now(UTC) - timedelta(days=1),
        )
        db.add_all([task_a, overdue_task])
        await db.flush()

        alert_rule = AlertRule(
            organization_id=org_a.id,
            rule_type="task_overdue",
            enabled=True,
            threshold_params={},
        )
        db.add(alert_rule)
        await db.commit()

        return SimpleNamespace(
            org_a=org_a,
            org_b=org_b,
            author=author,
            recipient=recipient,
            other_user=other_user,
            task_a=task_a,
            overdue_task=overdue_task,
            author_token=create_access_token(str(author.id)),
            recipient_token=create_access_token(str(recipient.id)),
            other_user_token=create_access_token(str(other_user.id)),
        )


async def _cleanup_e2e_data(engine: AsyncEngine, data: SimpleNamespace) -> None:
    from app.modules.organizations.models import Organization
    from app.modules.users.models import User

    async with AsyncSession(engine, expire_on_commit=False) as db:
        # ondelete=CASCADE (TenantMixin) removes OrganizationMember, Project,
        # Task and AlertRule/Notification rows scoped to each organization.
        await db.execute(
            delete(Organization).where(
                Organization.id.in_([data.org_a.id, data.org_b.id])
            )
        )
        await db.execute(
            delete(User).where(
                User.id.in_([data.author.id, data.recipient.id, data.other_user.id])
            )
        )
        await db.commit()


@pytest_asyncio.fixture
async def e2e_data(engine: AsyncEngine):
    data = await _seed_e2e_data(engine)
    try:
        yield data
    finally:
        await _cleanup_e2e_data(engine, data)


class E2EClient(NamedTuple):
    client: TestClient
    engine: AsyncEngine


@pytest.fixture
def e2e_client(engine: AsyncEngine):
    """A ``TestClient`` with REST+WS sharing ONE portal, wired to its OWN engine.

    ``engine`` (the shared session-scoped fixture) only orders this fixture
    AFTER schema creation (``Base.metadata.create_all`` + ``pg_trgm``) — it
    is never reused for requests; a DEDICATED engine is built instead, per
    the gate correction.
    """

    from app.database import get_db
    from app.main import app
    from app.realtime.router import router as realtime_router

    already_mounted = any(getattr(route, "path", None) == WS_PATH for route in app.routes)
    if not already_mounted:
        app.include_router(realtime_router, prefix="/api/v1")

    original_lifespan_context = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan

    try:
        with TestClient(app) as client:

            async def _make_engine() -> AsyncEngine:
                return create_async_engine(
                    TEST_DATABASE_URL, poolclass=NullPool, future=True
                )

            request_engine = client.portal.call(_make_engine)

            async def _override_get_db():
                async with AsyncSession(request_engine, expire_on_commit=False) as session:
                    yield session

            app.dependency_overrides[get_db] = _override_get_db

            try:
                yield E2EClient(client=client, engine=request_engine)
            finally:
                app.dependency_overrides.pop(get_db, None)
                client.portal.call(request_engine.dispose)
    finally:
        app.router.lifespan_context = original_lifespan_context


# ---------------------------------------------------------------------------
# Push en creación (mención) + aislamiento por organización
# ---------------------------------------------------------------------------


@skip_no_db
class TestMentionPush:
    def test_mention_via_rest_pushes_notification_created_to_the_recipient_socket(
        self, e2e_client: E2EClient, e2e_data: SimpleNamespace
    ) -> None:
        client = e2e_client.client

        with client.websocket_connect(
            WS_PATH, subprotocols=["bearer", e2e_data.recipient_token]
        ) as ws:
            assert _receive_json_with_timeout(ws)["type"] == "connection.ack"

            response = client.post(
                f"/api/v1/tasks/{e2e_data.task_a.id}/comments",
                json={"body": f"Hola @{e2e_data.recipient.id}, revisa esto"},
                headers=_auth(e2e_data.author_token),
            )
            assert response.status_code == 201, response.text

            push = _receive_json_with_timeout(ws)

        assert push["v"] == 1
        assert push["type"] == "notification.created"
        assert push["data"]["rule_type"] == "mention"
        assert push["data"]["recipient_user_id"] == str(e2e_data.recipient.id)

    def test_mention_push_never_reaches_a_different_organization_socket(
        self, e2e_client: E2EClient, e2e_data: SimpleNamespace
    ) -> None:
        client = e2e_client.client

        with client.websocket_connect(
            WS_PATH, subprotocols=["bearer", e2e_data.other_user_token]
        ) as ws:
            assert _receive_json_with_timeout(ws)["type"] == "connection.ack"

            response = client.post(
                f"/api/v1/tasks/{e2e_data.task_a.id}/comments",
                json={"body": f"Hola @{e2e_data.recipient.id}, revisa esto"},
                headers=_auth(e2e_data.author_token),
            )
            assert response.status_code == 201, response.text

            _assert_no_message_received(ws, timeout=0.5)


# ---------------------------------------------------------------------------
# Push en creación (alerta del motor)
# ---------------------------------------------------------------------------


@skip_no_db
class TestAlertEvaluatorPush:
    def test_alert_evaluator_push_reaches_the_recipient_socket(
        self, e2e_client: E2EClient, e2e_data: SimpleNamespace
    ) -> None:
        client = e2e_client.client

        with client.websocket_connect(
            WS_PATH, subprotocols=["bearer", e2e_data.recipient_token]
        ) as ws:
            assert _receive_json_with_timeout(ws)["type"] == "connection.ack"

            created = client.portal.call(
                _run_evaluate_organization, e2e_client.engine, e2e_data.org_a.id
            )
            assert created >= 1

            push = _receive_json_with_timeout(ws)

        assert push["type"] == "notification.created"
        assert push["data"]["rule_type"] == "task_overdue"
        assert push["data"]["recipient_user_id"] == str(e2e_data.recipient.id)


# ---------------------------------------------------------------------------
# Best-effort: fallo de publish nunca rompe la persistencia; REST recupera
# ---------------------------------------------------------------------------


@skip_no_db
class TestBestEffort:
    def test_publish_failure_does_not_prevent_persistence_or_rest_recovery(
        self,
        e2e_client: E2EClient,
        e2e_data: SimpleNamespace,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.realtime import manager as manager_module

        async def _broken_publish(org_id, user_id, envelope):
            raise RuntimeError("publisher down")

        monkeypatch.setattr(manager_module.manager, "publish", _broken_publish)
        client = e2e_client.client

        # No WS connection at all — proves persistence is independent of the
        # realtime channel being reachable, not just of one send failing.
        response = client.post(
            f"/api/v1/tasks/{e2e_data.task_a.id}/comments",
            json={"body": f"Hola @{e2e_data.recipient.id}, revisa esto"},
            headers=_auth(e2e_data.author_token),
        )
        assert response.status_code == 201, response.text

        listing = client.get(
            "/api/v1/notifications", headers=_auth(e2e_data.recipient_token)
        )
        assert listing.status_code == 200, listing.text
        rule_types = [row["rule_type"] for row in listing.json()["data"]]
        assert "mention" in rule_types
