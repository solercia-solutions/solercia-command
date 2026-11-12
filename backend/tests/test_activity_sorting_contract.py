"""Offline query-construction contracts, not PostgreSQL execution guarantees."""
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

# Prevent local dotenv/secret reads before any application imports.
with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}), patch(
    "pydantic_settings.sources.SecretsSettingsSource.__call__", return_value={}
):
    from app.modules.activity.repository import ActivityRepository
    from app.modules.activity.schemas import TaskHistoryResponse
    from app.shared.exceptions import AppException
    from app.shared.pagination import PaginationParams
    import app.db_init  # noqa: F401 -- register relationships without sessions


class RecordingSession:
    def __init__(self):
        self.statements = []
        self.rows = [SimpleNamespace(id=uuid4())]

    async def execute(self, stmt):
        self.statements.append(stmt)
        return SimpleNamespace(
            scalar_one=lambda: 7,
            scalars=lambda: SimpleNamespace(all=lambda: self.rows),
        )


def compiled(stmt):
    return stmt.compile(dialect=postgresql.dialect())


async def listing(repo, kind, org, subject, pagination, **kwargs):
    method = getattr(repo, f"list_for_{kind}")
    return await method(org, subject, pagination=pagination, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["task", "actor"])
@pytest.mark.parametrize("order", ["asc", "desc"])
@pytest.mark.parametrize("sort,column", [
    ("changed_at", "created_at"), ("created_at", "created_at"), ("field", "field"),
])
async def test_explicit_sort_preserves_scope_and_pagination(kind, order, sort, column):
    db = RecordingSession()
    org, subject = uuid4(), uuid4()
    rows, total = await listing(
        ActivityRepository(db), kind, org, subject,
        PaginationParams(page=2, size=3, sort=sort, order=order),
    )
    assert rows is db.rows
    assert total == 7
    assert len(db.statements) == 2
    for stmt in db.statements:
        query = compiled(stmt)
        sql = str(query)
        assert f"task_history.{kind}_id =" in sql
        assert "task_history.organization_id =" in sql
        assert subject in query.params.values()
        assert org in query.params.values()
    query = compiled(db.statements[-1])
    assert f"ORDER BY task_history.{column} {order.upper()}" in str(query)
    assert db.statements[-1]._limit_clause.value == 3
    assert db.statements[-1]._offset_clause.value == 3
    assert "ORDER BY" not in str(compiled(db.statements[0]))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["task", "actor"])
async def test_unknown_sort_rejected_before_execution(kind):
    db = RecordingSession()
    with pytest.raises(AppException) as error:
        await listing(ActivityRepository(db), kind, uuid4(), uuid4(),
                      PaginationParams(page=1, size=20, sort="unknown", order="asc"))
    assert error.value.status_code == 422
    assert error.value.code == "invalid_sort_field"
    assert db.statements == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["task", "actor"])
@pytest.mark.parametrize("pagination", [
    None,
    PaginationParams(page=None, size=20, sort=None, order="desc"),
    PaginationParams(page=1, size=20, sort=None, order="desc"),
])
async def test_default_sort_unchanged(kind, pagination):
    db = RecordingSession()
    rows, total = await listing(ActivityRepository(db), kind, uuid4(), uuid4(), pagination)
    paginated = pagination is not None and pagination.requested
    assert len(db.statements) == (2 if paginated else 1)
    assert total == (7 if paginated else 1)
    assert rows is db.rows
    assert "ORDER BY task_history.created_at DESC" in str(compiled(db.statements[-1]))
    if not paginated:
        assert db.statements[-1]._limit_clause is None
        assert db.statements[-1]._offset_clause is None


@pytest.mark.asyncio
async def test_actor_date_predicates_preserved_with_public_sort():
    db = RecordingSession()
    day = date(2026, 9, 1)
    await listing(ActivityRepository(db), "actor", uuid4(), uuid4(),
                  PaginationParams(page=1, size=20, sort="changed_at", order="desc"),
                  on_date=day, date_from=day, date_to=day)
    for stmt in db.statements:
        query = compiled(stmt)
        assert str(query).count("task_history.created_at >=") == 2
        assert str(query).count("task_history.created_at <") == 2
        values = list(query.params.values())
        assert values.count(datetime(2026, 9, 1)) == 2
        assert values.count(datetime(2026, 9, 2)) == 2


def test_response_keeps_public_changed_at_shape():
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    row = SimpleNamespace(id=uuid4(), task_id=uuid4(), actor_id=uuid4(),
                          actor_type="user", field="status", old_value="to_do",
                          new_value="done", created_at=timestamp)
    response = TaskHistoryResponse.model_validate(row).model_dump(mode="json")
    assert response == {
        "id": str(row.id), "task_id": str(row.task_id), "actor_id": str(row.actor_id),
        "actor_type": "user", "field": "status", "old_value": "to_do",
        "new_value": "done", "changed_at": "2026-09-01T00:00:00Z",
    }
