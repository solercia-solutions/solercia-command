"""Offline orchestration checks; not PostgreSQL locking/isolation evidence."""

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.sql.elements import BindParameter, BinaryExpression, BooleanClauseList
from sqlalchemy.sql.dml import Update

from app.notify import dispatcher
from app.notify.ports import DeliveryPolicy
from app.shared.enums import DeliveryStatus


def delivery(channel="email", attempts=2, status=DeliveryStatus.pending):
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(), organization_id=uuid4(), notification_id=uuid4(),
        channel=channel, status=status, attempts=attempts,
        payload={"recipient": "synthetic@example.invalid", "body": "private-marker"},
        dedup_key="synthetic-key", last_error="previous-marker",
        created_at=timestamp, updated_at=timestamp, sent_at=None,
    )


def evaluate(expression, row):
    """Evaluate only the actual dispatcher's small SQL expression subset."""
    if isinstance(expression, BindParameter):
        return expression.value
    if isinstance(expression, BooleanClauseList):
        return all(evaluate(clause, row) for clause in expression.clauses)
    if isinstance(expression, BinaryExpression):
        return expression.operator(evaluate(expression.left, row), evaluate(expression.right, row))
    return getattr(row, expression.name)


class FakeSession:
    def __init__(self, rows, lost_claims=()):
        self.rows = rows
        self.lost_claims = lost_claims
        self.events = []

    async def execute(self, statement):
        matches = [row for row in self.rows if evaluate(statement.whereclause, row)]
        if isinstance(statement, Update):
            assert len(matches) <= 1
            row = matches[0] if matches else None
            self.events.append(("claim", row.id if row else None))
            if row is None or row.id in self.lost_claims:
                return SimpleNamespace(first=lambda: None)
            values = {column: evaluate(value, row) for column, value in statement._values.items()}
            for column, value in values.items():
                setattr(row, column.key, value)
            return SimpleNamespace(first=lambda: (row.id,))
        if statement._limit_clause is not None:
            matches = matches[:statement._limit_clause.value]
        if len(statement.selected_columns) == 1:
            return SimpleNamespace(all=lambda: [(row.id,) for row in matches])
        return SimpleNamespace(scalar_one=lambda: matches[0])

    async def commit(self):
        self.events.append(("commit",))

    def add(self, row):
        self.events.append(("add", row.id))


def register(monkeypatch, db, *, email=True, error=False):
    async def deliver(payload):
        db.events.append(("deliver", deepcopy(payload)))
        if error:
            raise RuntimeError("synthetic failure")

    names = ["other"] + (["email"] if email else [])
    monkeypatch.setattr(dispatcher, "get_channels", lambda: [
        SimpleNamespace(name=name, policy=DeliveryPolicy.durable, deliver=deliver)
        for name in names
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["console", "smtp"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("registered", [False, True])
async def test_email_is_untouched_before_claim(monkeypatch, caplog, backend, enabled, registered):
    rows = [delivery(attempts=attempts, status=status)
            for attempts in (0, 2, 9) for status in DeliveryStatus]
    before = deepcopy([vars(row) for row in rows])
    db = FakeSession(rows)
    register(monkeypatch, db, email=registered)
    monkeypatch.setattr(dispatcher.settings, "EMAIL_BACKEND", backend)
    monkeypatch.setattr(dispatcher.settings, "EMAIL_ENABLED", enabled)

    assert await dispatcher.dispatch_deliveries(db) == 0
    assert [vars(row) for row in rows] == before
    assert db.events == []
    assert caplog.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "retryable", "terminal", "lost_claim", "unknown"])
async def test_mixed_queue_preserves_other_channel_semantics(monkeypatch, outcome):
    emails = [delivery() for _ in range(100)]
    other = delivery("missing" if outcome == "unknown" else "other")
    before = deepcopy([vars(row) for row in emails])
    db = FakeSession(emails + [other], [other.id] if outcome == "lost_claim" else [])
    register(monkeypatch, db, error=outcome in ("retryable", "terminal"))
    monkeypatch.setattr(dispatcher.settings, "EMAIL_MAX_ATTEMPTS", 3 if outcome == "terminal" else 5)

    assert await dispatcher.dispatch_deliveries(db) == (0 if outcome == "lost_claim" else 1)
    assert [vars(row) for row in emails] == before
    if outcome == "lost_claim":
        assert db.events == [("claim", other.id)]
        assert other.attempts == 2
        assert other.status == DeliveryStatus.pending
        return
    assert db.events[:2] == [("claim", other.id), ("commit",)]
    expected = ["claim", "commit"] + ([] if outcome == "unknown" else ["deliver"]) + ["add", "commit"]
    assert [event[0] for event in db.events] == expected
    assert other.attempts == 3
    assert other.status == {"success": DeliveryStatus.sent, "terminal": DeliveryStatus.failed}.get(outcome, DeliveryStatus.pending)
    assert (other.sent_at is not None) == (outcome == "success")
    if outcome != "success":
        assert other.last_error


@pytest.mark.asyncio
async def test_empty_queue_has_no_transaction_effects(monkeypatch):
    db = FakeSession([])
    register(monkeypatch, db)
    assert await dispatcher.dispatch_deliveries(db) == 0
    assert db.events == []
