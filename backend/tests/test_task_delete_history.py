"""Soft-delete audit orchestration; recording fakes do not prove DB atomicity."""
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

# Register existing relationships without sessions or local credential sources.
with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}), patch(
    "pydantic_settings.sources.SecretsSettingsSource.__call__", return_value={}
):
    import app.db_init  # noqa: F401
    from app.modules.activity.models import TaskHistory
    from app.modules.activity.service import ActivityService
    from app.modules.tasks.service import TaskService
    from app.shared.exceptions import AppException


class RecordingDB:
    def __init__(self):
        self.rows = []
        self.events = []
        self.failure = None

    def add_all(self, rows):
        self.events.append("add_all")
        if self.failure:
            raise self.failure
        self.rows.extend(rows)


class Tasks:
    def __init__(self, db, org, task):
        self.db, self.org, self.task = db, org, task
        self.failure = None

    async def get(self, org, task_id):
        if org == self.org and task_id == self.task.id and self.task.is_active:
            return self.task

    async def save(self, task):
        assert task is self.task
        self.db.events.append("save")
        if self.failure:
            raise self.failure
        return task


@pytest.fixture
def case():
    org, actor = uuid4(), uuid4()
    task = SimpleNamespace(id=uuid4(), is_active=True, deleted_at=None,
                           created_by=uuid4(), updated_by=uuid4())
    db = RecordingDB()
    service = TaskService(db)
    service.repo = Tasks(db, org, task)
    return SimpleNamespace(org=org, actor=actor, task=task, db=db, service=service)


def changes(c, actor):
    assert all(isinstance(row, TaskHistory) for row in c.db.rows)
    assert len({row.field for row in c.db.rows}) == len(c.db.rows)
    for row in c.db.rows:
        assert (row.organization_id, row.task_id, row.actor_id, row.actor_type) == (
            c.org, c.task.id, actor, "user")
    return {row.field: (row.old_value, row.new_value) for row in c.db.rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_mode", ["user", "explicit_none", "omitted"])
async def test_delete_records_exact_values_before_single_save(case, actor_mode):
    creator = case.task.created_by
    kwargs = {} if actor_mode == "omitted" else {
        "actor_id": case.actor if actor_mode == "user" else None}
    before = datetime.now(UTC)
    result = await case.service.delete_task(case.org, case.task.id, **kwargs)
    deleted = case.task.deleted_at
    assert result is None
    assert deleted.tzinfo == UTC
    assert before <= deleted <= datetime.now(UTC)
    actor = case.actor if actor_mode == "user" else None
    assert changes(case, actor) == {
        "is_active": ("True", "False"), "deleted_at": (None, deleted.isoformat())}
    assert case.task.is_active is False
    assert case.task.created_by == creator
    assert case.task.updated_by == actor
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
async def test_snapshot_uses_actual_previous_deletion_timestamp(case):
    previous = datetime(2026, 1, 1, 5, tzinfo=timezone(timedelta(hours=5)))
    case.task.deleted_at = previous  # Legacy active row with a previous timestamp.
    await case.service.delete_task(case.org, case.task.id, actor_id=case.actor)
    assert changes(case, case.actor) == {
        "is_active": ("True", "False"),
        "deleted_at": ("2026-01-01T00:00:00+00:00", case.task.deleted_at.isoformat()),
    }
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["tenant", "task", "inactive"])
async def test_unavailable_task_never_mutates_records_or_saves(case, missing):
    org = uuid4() if missing == "tenant" else case.org
    task_id = uuid4() if missing == "task" else case.task.id
    if missing == "inactive":
        case.task.is_active = False
    before = vars(case.task).copy()
    with pytest.raises(AppException) as error:
        await case.service.delete_task(org, task_id, actor_id=case.actor)
    assert (error.value.code, error.value.status_code) == ("task_not_found", 404)
    assert vars(case.task) == before
    assert case.db.events == [] and case.db.rows == []


@pytest.mark.asyncio
async def test_repeat_delete_returns_404_without_more_events(case):
    await case.service.delete_task(case.org, case.task.id, actor_id=case.actor)
    before = vars(case.task).copy()
    rows = list(case.db.rows)
    with pytest.raises(AppException) as error:
        await case.service.delete_task(case.org, case.task.id, actor_id=uuid4())
    assert (error.value.code, error.value.status_code) == ("task_not_found", 404)
    assert vars(case.task) == before and case.db.rows == rows
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["recorder", "save"])
async def test_failure_propagates_without_extra_save(case, operation):
    failure = RuntimeError("synthetic failure")
    if operation == "recorder":
        case.db.failure = failure
    else:
        case.service.repo.failure = failure
    with pytest.raises(RuntimeError) as error:
        await case.service.delete_task(case.org, case.task.id, actor_id=case.actor)
    assert error.value is failure
    assert case.db.events == (["add_all"] if operation == "recorder" else ["add_all", "save"])
    assert len(case.db.rows) == (0 if operation == "recorder" else 2)


class History:
    def __init__(self, db):
        self.db = db
        self.task_calls = []

    async def list_for_task(self, org, task_id, pagination):
        self.task_calls.append((org, task_id, pagination))
        rows = [r for r in self.db.rows if r.organization_id == org and r.task_id == task_id]
        return rows, len(rows)

    async def list_for_actor(self, org, actor_id, **kwargs):
        rows = [r for r in self.db.rows if r.organization_id == org and r.actor_id == actor_id]
        return rows, len(rows)


@pytest.mark.asyncio
async def test_history_read_gate_preserved_and_actor_activity_still_eligible(case):
    activity = ActivityService(case.db)
    activity.tasks = case.service.repo
    activity.repo = History(case.db)
    assert await activity.list_for_task(case.org, case.task.id) == ([], 0)
    assert activity.repo.task_calls == [(case.org, case.task.id, None)]
    await case.service.delete_task(case.org, case.task.id, actor_id=case.actor)
    # Fake insert-generated metadata only; no flush/session/database is used.
    for row in case.db.rows:
        row.id, row.created_at = uuid4(), datetime.now(UTC)
    with pytest.raises(AppException) as error:
        await activity.list_for_task(case.org, case.task.id)
    assert (error.value.code, error.value.status_code) == ("task_not_found", 404)
    assert activity.repo.task_calls == [(case.org, case.task.id, None)]
    rows, total = await activity.list_for_actor(case.org, case.actor)
    assert total == 2 and {r.field for r in rows} == {"is_active", "deleted_at"}
    assert all(r.actor_id == case.actor and r.task_id == case.task.id for r in rows)
    assert await activity.list_for_actor(uuid4(), case.actor) == ([], 0)
    assert await activity.list_for_actor(case.org, uuid4()) == ([], 0)
