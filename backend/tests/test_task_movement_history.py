"""Real movement and recorder orchestration; fakes do not prove DB rollback."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

# Offline imports must not consult local dotenv or credential sources.
with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}), patch(
    "pydantic_settings.sources.SecretsSettingsSource.__call__", return_value={}
):
    import app.db_init  # noqa: F401 -- register ORM relationships without sessions
    from app.modules.activity.models import TaskHistory
    from app.modules.tasks.schemas import TaskUpdate
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

    async def commit(self):
        pytest.fail("Board movement must not commit")

    async def refresh(self, task):
        pytest.fail("Board movement must not refresh")


class Tasks:
    def __init__(self, db, org, task):
        self.db, self.org, self.task = db, org, task
        self.failure = None

    async def get(self, org, task_id):
        if org == self.org and task_id == self.task.id:
            return self.task

    async def save(self, task):
        assert task is self.task
        self.db.events.append("save")
        if self.failure:
            raise self.failure
        return task


class Projects:
    def __init__(self, org, project):
        self.org, self.project = org, project

    async def get(self, org, project_id):
        if org == self.org and project_id == self.project.id:
            return self.project


@pytest.fixture
def case(monkeypatch):
    org, actor, project_id = uuid4(), uuid4(), uuid4()
    columns = [SimpleNamespace(id=uuid4(), status_key=s, name=s, wip_limit=1)
               for s in ("PENDIENTE", "COMPLETADA")]
    task = SimpleNamespace(
        id=uuid4(), project_id=project_id, status="PENDIENTE",
        board_column_id=columns[0].id, completed_at=None, updated_by=None,
        title="Before", description=None, task_type="task", parent_task_id=None,
        assignee_id=None, sprint_id=None, priority="medium", estimation_points=None,
        estimation_hours=None, due_date=None, start_date=None, order=4,
        risk_flag=False, risk_reason=None,
    )
    db = RecordingDB()
    service = TaskService(db)
    service.repo = Tasks(db, org, task)
    service.projects = Projects(org, SimpleNamespace(id=project_id, code="SYN"))
    strategy = SimpleNamespace(allowed_statuses=lambda: [c.status_key for c in columns])
    monkeypatch.setattr("app.modules.tasks.service.resolve_board_strategy",
                        AsyncMock(return_value=strategy))
    monkeypatch.setattr(service, "_assignee_name_map", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_to_read", lambda task, *args, **kwargs: task)
    c = SimpleNamespace(service=service, task=task, db=db, org=org, actor=actor,
                        columns=columns, count=0, missing_lock=False, locks=[], counts=[])

    async def board(_repo, requested_project):
        assert requested_project == project_id
        return SimpleNamespace(columns=columns)

    async def lock(_repo, column_id):
        c.locks.append(column_id)
        return None if c.missing_lock else next(col for col in columns if col.id == column_id)

    async def count(_repo, column_id):
        c.counts.append(column_id)
        return c.count

    monkeypatch.setattr("app.modules.boards.repository.BoardRepository.get_board_with_columns", board)
    monkeypatch.setattr("app.modules.boards.repository.BoardRepository.lock_column", lock)
    monkeypatch.setattr("app.modules.boards.repository.BoardRepository.count_active_tasks_in_column", count)
    return c


async def move(c, column=1):
    return await c.service.move_task_column(c.org, c.task.id, c.columns[column].id,
                                            actor_id=c.actor)


def changes(c):
    assert all(isinstance(row, TaskHistory) for row in c.db.rows)
    assert len({row.field for row in c.db.rows}) == len(c.db.rows)
    for row in c.db.rows:
        assert (row.organization_id, row.task_id, row.actor_id, row.actor_type) == (
            c.org, c.task.id, c.actor, "user")
    return {row.field: (row.old_value, row.new_value) for row in c.db.rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("null_actor", [False, True])
async def test_completion_records_exact_derived_values_before_single_save(case, null_actor):
    if null_actor:
        case.actor = None
    before = datetime.now(UTC)
    assert await move(case) is case.task
    completed = case.task.completed_at
    assert before <= completed <= datetime.now(UTC)
    assert changes(case) == {
        "status": ("PENDIENTE", "COMPLETADA"),
        "board_column_id": (str(case.columns[0].id), str(case.columns[1].id)),
        "completed_at": (None, completed.isoformat()),
    }
    assert case.task.updated_by == case.actor
    assert case.db.events == ["add_all", "save"]
    assert case.locks == case.counts == [case.columns[1].id]


@pytest.mark.asyncio
async def test_reopen_clears_completion(case):
    completed = datetime(2026, 9, 1, tzinfo=UTC)
    case.task.status = "COMPLETADA"
    case.task.board_column_id = case.columns[1].id
    case.task.completed_at = completed
    await move(case, 0)
    assert changes(case) == {
        "status": ("COMPLETADA", "PENDIENTE"),
        "board_column_id": (str(case.columns[1].id), str(case.columns[0].id)),
        "completed_at": (completed.isoformat(), None),
    }
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
@pytest.mark.parametrize("column", [0, 1])
async def test_same_column_noop_preserves_completion_and_wip_capacity(case, column):
    completed = datetime(2026, 9, 1, tzinfo=UTC) if column else None
    case.task.status = case.columns[column].status_key
    case.task.board_column_id = case.columns[column].id
    case.task.completed_at = completed
    case.count = 1  # The task itself fills the limit; moving within it must succeed.
    await move(case, column)
    assert changes(case) == {}
    assert case.task.completed_at is completed
    assert case.db.events == ["save"]
    assert case.locks == case.counts == [case.columns[column].id]


@pytest.mark.asyncio
async def test_update_status_and_title_records_each_field_once(case):
    await case.service.update_task(case.org, case.task.id,
                                  TaskUpdate(status="COMPLETADA", title="Finished"),
                                  actor_id=case.actor)
    assert changes(case) == {
        "status": ("PENDIENTE", "COMPLETADA"), "title": ("Before", "Finished"),
        "board_column_id": (str(case.columns[0].id), str(case.columns[1].id)),
        "completed_at": (None, case.task.completed_at.isoformat()),
    }
    assert case.db.events == ["add_all", "save"]
    assert case.locks == case.counts == [case.columns[1].id]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,code", [
    ("wip", "wip_limit_exceeded"), ("unknown", "invalid_board_column"),
    ("missing_lock", "invalid_board_column"), ("tenant", "task_not_found"),
])
async def test_rejections_never_record_or_save(case, failure, code):
    org = uuid4() if failure == "tenant" else case.org
    target = uuid4() if failure == "unknown" else case.columns[1].id
    case.count = 1 if failure == "wip" else 0
    case.missing_lock = failure == "missing_lock"
    with pytest.raises(AppException) as error:
        await case.service.move_task_column(org, case.task.id, target, actor_id=case.actor)
    assert error.value.code == code
    assert changes(case) == {}
    assert case.db.events == []
    assert (case.task.status, case.task.board_column_id, case.task.completed_at) == (
        "PENDIENTE", case.columns[0].id, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["recorder", "save"])
async def test_failure_propagates_without_extra_save_or_board_commit(case, operation):
    failure = RuntimeError("synthetic failure")
    if operation == "recorder":
        case.db.failure = failure
    else:
        case.service.repo.failure = failure
    with pytest.raises(RuntimeError) as error:
        await move(case)
    assert error.value is failure
    assert case.db.events == (["add_all"] if operation == "recorder" else ["add_all", "save"])
    # Only control flow is proven: fake staged rows do not demonstrate rollback.
