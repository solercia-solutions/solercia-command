"""Unit tests for the realtime engine's in-process pieces: no DB, no ASGI.

Covers ``ConnectionManager`` (register/unregister/publish, tenant isolation,
multi-tab fan-out, best-effort delivery) and the publisher helpers
(``buffer_notification``/``flush_pending``), including the atomic-pop
contract from design.md D2 (gate correction): ``flush_pending`` MUST pop
``db.info["realtime_pending"]`` before publishing, so a session reused across
multiple commit+drain cycles (``evaluate_all_organizations``) never
re-publishes an earlier organization's payloads.

openspec/changes/09-websocket-realtime/specs/realtime-notifications/spec.md
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.shared.enums import NotificationStatus

# ---------------------------------------------------------------------------
# Fakes — no real WebSocket, no real AsyncSession
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Duck-typed stand-in for ``fastapi.WebSocket`` — only ``send_json``."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self._fail = fail

    async def send_json(self, data: dict) -> None:
        if self._fail:
            raise RuntimeError("boom — socket write failed")
        self.sent.append(data)


class _FakeSession:
    """Stand-in for ``AsyncSession`` exposing only the ``.info`` dict."""

    def __init__(self) -> None:
        self.info: dict = {}


def _make_notification(
    *, org_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None
) -> SimpleNamespace:
    """A duck-typed ``Notification`` — enough attributes for ``NotificationRead``."""

    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=org_id or uuid.uuid4(),
        recipient_user_id=user_id or uuid.uuid4(),
        rule_type="task_overdue",
        title="Tarea vencida",
        body="La tarea X está vencida.",
        target_type="task",
        target_id=uuid.uuid4(),
        dedup_key=f"task_overdue:{uuid.uuid4()}",
        status=NotificationStatus.active,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# schemas.make_envelope
# ---------------------------------------------------------------------------


class TestMakeEnvelope:
    def test_envelope_has_versioned_shape(self):
        from app.realtime.schemas import make_envelope

        envelope = make_envelope("connection.ack", None)

        assert envelope["v"] == 1
        assert envelope["type"] == "connection.ack"
        assert envelope["data"] is None
        assert "ts" in envelope

    def test_envelope_carries_arbitrary_data_payload(self):
        from app.realtime.schemas import make_envelope

        envelope = make_envelope("notification.created", {"title": "Hola"})

        assert envelope["type"] == "notification.created"
        assert envelope["data"] == {"title": "Hola"}


# ---------------------------------------------------------------------------
# ConnectionManager
# ---------------------------------------------------------------------------


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_register_then_publish_delivers_envelope_to_socket(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_id, user_id = uuid.uuid4(), uuid.uuid4()
        ws = _FakeWebSocket()
        manager.register(org_id, user_id, ws)

        await manager.publish(org_id, user_id, {"v": 1, "type": "ping", "data": None})

        assert ws.sent == [{"v": 1, "type": "ping", "data": None}]

    @pytest.mark.asyncio
    async def test_unregister_stops_further_delivery(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_id, user_id = uuid.uuid4(), uuid.uuid4()
        ws = _FakeWebSocket()
        manager.register(org_id, user_id, ws)
        manager.unregister(org_id, user_id, ws)

        await manager.publish(org_id, user_id, {"v": 1, "type": "ping", "data": None})

        assert ws.sent == []

    @pytest.mark.asyncio
    async def test_publish_to_unregistered_key_is_a_noop(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()

        # No exception, nothing to deliver to.
        await manager.publish(uuid.uuid4(), uuid.uuid4(), {"v": 1, "type": "ping", "data": None})

    @pytest.mark.asyncio
    async def test_isolation_across_organizations(self):
        """publish a (orgA,userX) nunca llega a (orgB,userY)."""
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_a, user_x = uuid.uuid4(), uuid.uuid4()
        org_b, user_y = uuid.uuid4(), uuid.uuid4()
        ws_a = _FakeWebSocket()
        ws_b = _FakeWebSocket()
        manager.register(org_a, user_x, ws_a)
        manager.register(org_b, user_y, ws_b)

        await manager.publish(org_a, user_x, {"v": 1, "type": "ping", "data": None})

        assert ws_a.sent == [{"v": 1, "type": "ping", "data": None}]
        assert ws_b.sent == []

    @pytest.mark.asyncio
    async def test_isolation_across_users_in_the_same_organization(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_id = uuid.uuid4()
        user_x, user_y = uuid.uuid4(), uuid.uuid4()
        ws_x = _FakeWebSocket()
        ws_y = _FakeWebSocket()
        manager.register(org_id, user_x, ws_x)
        manager.register(org_id, user_y, ws_y)

        await manager.publish(org_id, user_x, {"v": 1, "type": "ping", "data": None})

        assert ws_x.sent == [{"v": 1, "type": "ping", "data": None}]
        assert ws_y.sent == []

    @pytest.mark.asyncio
    async def test_multi_tab_both_sockets_of_the_same_user_receive(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_id, user_id = uuid.uuid4(), uuid.uuid4()
        tab_1 = _FakeWebSocket()
        tab_2 = _FakeWebSocket()
        manager.register(org_id, user_id, tab_1)
        manager.register(org_id, user_id, tab_2)

        await manager.publish(org_id, user_id, {"v": 1, "type": "ping", "data": None})

        assert tab_1.sent == [{"v": 1, "type": "ping", "data": None}]
        assert tab_2.sent == [{"v": 1, "type": "ping", "data": None}]

    @pytest.mark.asyncio
    async def test_best_effort_one_failing_socket_does_not_block_the_other(self):
        from app.realtime.manager import ConnectionManager

        manager = ConnectionManager()
        org_id, user_id = uuid.uuid4(), uuid.uuid4()
        bad = _FakeWebSocket(fail=True)
        good = _FakeWebSocket()
        manager.register(org_id, user_id, bad)
        manager.register(org_id, user_id, good)

        # Must not raise even though `bad.send_json` throws.
        await manager.publish(org_id, user_id, {"v": 1, "type": "ping", "data": None})

        assert good.sent == [{"v": 1, "type": "ping", "data": None}]


# ---------------------------------------------------------------------------
# publisher: buffer_notification / flush_pending
# ---------------------------------------------------------------------------


class TestBufferNotification:
    def test_buffers_a_serialized_envelope_on_db_info(self):
        from app.realtime.publisher import buffer_notification

        db = _FakeSession()
        notification = _make_notification()

        buffer_notification(db, notification)

        pending = db.info["realtime_pending"]
        assert len(pending) == 1
        org_id, user_id, envelope = pending[0]
        assert org_id == notification.organization_id
        assert user_id == notification.recipient_user_id
        assert envelope["v"] == 1
        assert envelope["type"] == "notification.created"
        assert envelope["data"]["id"] == str(notification.id)
        assert envelope["data"]["title"] == notification.title

    def test_buffering_twice_accumulates_both_entries(self):
        from app.realtime.publisher import buffer_notification

        db = _FakeSession()
        buffer_notification(db, _make_notification())
        buffer_notification(db, _make_notification())

        assert len(db.info["realtime_pending"]) == 2


class TestFlushPending:
    @pytest.mark.asyncio
    async def test_flush_pending_pops_before_publishing(self, monkeypatch):
        """Gate correction (D2): the pop MUST happen before publish runs."""
        from app.realtime import publisher as publisher_module

        db = _FakeSession()
        publisher_module.buffer_notification(db, _make_notification())
        assert db.info["realtime_pending"]

        seen_during_publish: object = "sentinel-not-called"

        async def fake_publish(org_id, user_id, envelope):
            nonlocal seen_during_publish
            seen_during_publish = db.info.get("realtime_pending")

        monkeypatch.setattr(publisher_module.manager, "publish", fake_publish)

        await publisher_module.flush_pending(db)

        assert seen_during_publish is None
        assert "realtime_pending" not in db.info

    @pytest.mark.asyncio
    async def test_flush_pending_does_not_republish_across_multiple_drains(
        self, monkeypatch
    ):
        """evaluate_all_organizations reuses one session for N orgs — no re-send."""
        from app.realtime import publisher as publisher_module

        db = _FakeSession()
        published: list[tuple[uuid.UUID, uuid.UUID]] = []

        async def fake_publish(org_id, user_id, envelope):
            published.append((org_id, user_id))

        monkeypatch.setattr(publisher_module.manager, "publish", fake_publish)

        notif_a = _make_notification()
        publisher_module.buffer_notification(db, notif_a)
        await publisher_module.flush_pending(db)

        notif_b = _make_notification()
        publisher_module.buffer_notification(db, notif_b)
        await publisher_module.flush_pending(db)

        assert published == [
            (notif_a.organization_id, notif_a.recipient_user_id),
            (notif_b.organization_id, notif_b.recipient_user_id),
        ]

    @pytest.mark.asyncio
    async def test_flush_pending_with_empty_buffer_is_a_noop(self, monkeypatch):
        from app.realtime import publisher as publisher_module

        db = _FakeSession()
        calls: list[object] = []

        async def fake_publish(org_id, user_id, envelope):
            calls.append((org_id, user_id, envelope))

        monkeypatch.setattr(publisher_module.manager, "publish", fake_publish)

        await publisher_module.flush_pending(db)

        assert calls == []

    @pytest.mark.asyncio
    async def test_flush_pending_swallows_publish_failures(self, monkeypatch):
        """Best-effort: a broken publisher must never raise out of flush_pending."""
        from app.realtime import publisher as publisher_module

        db = _FakeSession()
        publisher_module.buffer_notification(db, _make_notification())

        async def broken_publish(org_id, user_id, envelope):
            raise RuntimeError("publisher unavailable")

        monkeypatch.setattr(publisher_module.manager, "publish", broken_publish)

        await publisher_module.flush_pending(db)  # must not raise
