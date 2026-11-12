"""Update audit control flow with the real recorder; no database guarantees."""
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

# Never consult local credentials/dotenv during offline model imports.
with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}), patch(
    "pydantic_settings.sources.SecretsSettingsSource.__call__", return_value={}
):
    from app.modules.tasks.schemas import TaskUpdate
    from app.modules.tasks.service import TaskService
    from app.modules.activity.models import TaskHistory
    from app.shared.enums import Priority
    from app.shared.exceptions import AppException
    import app.db_init  # noqa: F401 -- register relationships, no sessions


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
        self.member = True

    async def get(self, org, task_id):
        return self.task if org == self.org and task_id == self.task.id else None

    async def is_org_member(self, org, user):
        assert org == self.org
        return self.member

    async def save(self, task):
        assert task is self.task
        self.db.events.append("save")
        if self.failure:
            raise self.failure
        return task

    async def reassign_order_for_container(self, org, project, ids):
        assert org == self.org and project == self.task.project_id
        assert ids == [self.task.id]
        self.task.order = 0


class Projects:
    def __init__(self, org, project):
        self.org, self.project = org, project

    async def get(self, org, project_id):
        if org == self.org and project_id == self.project.id:
            return self.project


@pytest.fixture
def case(monkeypatch):
    org, actor, project_id = uuid4(), uuid4(), uuid4()
    columns = [SimpleNamespace(id=uuid4(), status_key=s) for s in ("PENDIENTE", "COMPLETADA")]
    task = SimpleNamespace(
        id=uuid4(), project_id=project_id, parent_task_id=None, title="Before",
        description="Old description", task_type="task", status="PENDIENTE",
        assignee_id=uuid4(), sprint_id=uuid4(), priority=Priority.medium,
        estimation_points=3, estimation_hours=2.5,
        due_date=datetime(2026, 9, 1, tzinfo=UTC), start_date=datetime(2026, 8, 1, tzinfo=UTC),
        board_column_id=columns[0].id, completed_at=None, order=4,
        risk_flag=True, risk_reason="Old risk", updated_by=None,
    )
    db = RecordingDB()
    service = TaskService(db)
    service.repo = Tasks(db, org, task)
    service.projects = Projects(org, SimpleNamespace(id=project_id, code="SYN"))
    strategy = SimpleNamespace(estimation_mode="both", allowed_statuses=lambda: [c.status_key for c in columns])
    monkeypatch.setattr("app.modules.tasks.service.resolve_board_strategy", AsyncMock(return_value=strategy))
    monkeypatch.setattr(service, "_assignee_name_map", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_to_read", lambda task, *args, **kwargs: task)
    monkeypatch.setattr("app.modules.boards.repository.BoardRepository.get_board_with_columns",
                        AsyncMock(return_value=SimpleNamespace(columns=columns)))

    async def move(_self, target_task, target, **kwargs):
        assert kwargs == {"actor_id": actor, "enforce_wip": True, "commit": False}
        target_task.status, target_task.board_column_id = target.status_key, target.id
        return target_task

    monkeypatch.setattr("app.modules.boards.service.BoardService.move_to_column", move)
    monkeypatch.setattr("app.modules.sprints.repository.SprintRepository.get_for_project",
                        AsyncMock(return_value=SimpleNamespace(status="active")))
    return SimpleNamespace(service=service, task=task, db=db, org=org, actor=actor, columns=columns)


async def update(c, payload, **kwargs):
    return await c.service.update_task(c.org, c.task.id, TaskUpdate(**payload),
                                       **({"actor_id": c.actor} | kwargs))


def changes(c):
    assert all(isinstance(row, TaskHistory) for row in c.db.rows)
    assert len({row.field for row in c.db.rows}) == len(c.db.rows)
    for row in c.db.rows:
        assert (row.organization_id, row.task_id, row.actor_type) == (c.org, c.task.id, "user")
    return {row.field: (row.old_value, row.new_value) for row in c.db.rows}


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,expected", [
    ("title", "After", "After"), ("description", "New description", "New description"),
    ("task_type", "bug", "bug"), ("order", 0, "0"), ("risk_flag", False, "False"),
    ("risk_reason", "New risk", "New risk"),
    ("due_date", datetime(2026, 10, 1, 5, tzinfo=timezone(timedelta(hours=5))), "2026-10-01T00:00:00+00:00"),
    ("start_date", datetime(2026, 9, 2, tzinfo=UTC), "2026-09-02T00:00:00+00:00"),
    ("priority", Priority.high, "high"), ("assignee_id", uuid4(), None),
    ("sprint_id", uuid4(), None), ("estimation_points", 0, "0"), ("estimation_hours", 0.0, "0.0"),
])
async def test_each_effective_field_stages_one_row_before_single_save(case, field, value, expected):
    before = getattr(case.task, field)
    result = await update(case, {field: value})
    old = before.isoformat() if isinstance(before, datetime) else str(getattr(before, "value", before))
    assert changes(case) == {field: (old, expected if expected is not None else str(value))}
    assert result is case.task
    assert case.db.events == ["add_all", "save"]
    assert case.db.rows[0].actor_id == case.actor
    assert case.task.updated_by == case.actor
    assert getattr(case.task, field) == value
    if isinstance(value, datetime):
        assert getattr(case.task, field).tzinfo == value.tzinfo


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["description", "assignee_id", "sprint_id", "estimation_points",
                                      "estimation_hours", "due_date", "start_date", "risk_reason"])
async def test_nullable_clearing(case, field):
    await update(case, {field: None})
    assert set(changes(case)) == {field}
    assert case.db.rows[0].old_value is not None
    assert case.db.rows[0].new_value is None
    assert getattr(case.task, field) is None
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
async def test_all_fields_noop_and_omitted_payload(case):
    payload = {field: getattr(case.task, field) for field in TaskUpdate.model_fields}
    await update(case, payload)
    await update(case, {})
    assert changes(case) == {}
    assert case.db.events == ["save", "save"]


@pytest.mark.asyncio
async def test_equivalent_instants_do_not_create_history(case):
    other_zone = timezone(timedelta(hours=-5))
    await update(case, {"due_date": case.task.due_date.astimezone(other_zone),
                        "start_date": case.task.start_date.astimezone(other_zone)})
    assert changes(case) == {}
    assert case.task.due_date.tzinfo == other_zone


@pytest.mark.asyncio
async def test_naive_datetime_is_not_assigned_an_invented_timezone(case):
    case.task.due_date = datetime(2026, 1, 1)
    await update(case, {"due_date": datetime(2026, 1, 2)})
    assert changes(case) == {"due_date": ("2026-01-01T00:00:00", "2026-01-02T00:00:00")}
    assert case.task.due_date.tzinfo is None


@pytest.mark.asyncio
async def test_derived_completion_and_column_then_reopen(case):
    await update(case, {"status": "COMPLETADA", "title": "Finished"})
    completed = case.task.completed_at
    assert completed.tzinfo == UTC
    assert changes(case) == {
        "status": ("PENDIENTE", "COMPLETADA"), "title": ("Before", "Finished"),
        "board_column_id": (str(case.columns[0].id), str(case.columns[1].id)),
        "completed_at": (None, completed.isoformat()),
    }
    assert case.db.events == ["add_all", "save"]
    case.db.rows.clear()
    case.db.events.clear()
    await update(case, {"status": "COMPLETADA"})
    assert changes(case) == {}
    assert case.task.completed_at is completed
    await update(case, {"status": "PENDIENTE"})
    assert changes(case) == {
        "status": ("COMPLETADA", "PENDIENTE"),
        "board_column_id": (str(case.columns[1].id), str(case.columns[0].id)),
        "completed_at": (completed.isoformat(), None),
    }
    assert case.db.events == ["save", "add_all", "save"]


@pytest.mark.asyncio
async def test_missing_actor_preserves_existing_user_none_contract(case):
    await update(case, {"title": "Changed"}, actor_id=None)
    assert changes(case) == {"title": ("Before", "Changed")}
    assert case.db.rows[0].actor_id is None
    assert case.task.updated_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,code", [
    ({"status": "unknown"}, "invalid_status"),
    ({"task_type": "subtask"}, "subtask_points_not_allowed"),
    ({"assignee_id": uuid4()}, "invalid_assignee"),
])
async def test_validation_errors_never_stage_or_save(case, payload, code):
    case.service.repo.member = False
    with pytest.raises(AppException) as error:
        await update(case, payload)
    assert error.value.code == code
    assert case.db.events == []


@pytest.mark.asyncio
async def test_tenant_not_found_never_stages_or_saves(case):
    with pytest.raises(AppException) as error:
        await case.service.update_task(uuid4(), case.task.id, TaskUpdate(title="No"))
    assert error.value.code == "task_not_found"
    assert case.db.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["recorder", "save"])
async def test_failures_propagate_without_extra_save_or_transaction_calls(case, operation):
    failure = RuntimeError("synthetic failure")
    if operation == "recorder":
        case.db.failure = failure
    else:
        case.service.repo.failure = failure
    with pytest.raises(RuntimeError) as error:
        await update(case, {"priority": Priority.high})
    assert error.value is failure
    assert case.db.events == (["add_all"] if operation == "recorder" else ["add_all", "save"])


@pytest.mark.asyncio
async def test_reorder_retains_six_field_contract_without_order_events(case):
    assert set(TaskService._HISTORY_TRACKED_FIELDS) == {
        "status", "assignee_id", "estimation_points", "estimation_hours", "sprint_id", "priority"
    }
    before = case.task.sprint_id
    await case.service.reorder_tasks(case.org, case.task.id, None, [case.task.id], actor_id=case.actor)
    assert changes(case) == {"sprint_id": (str(before), None)}
    assert case.task.order == 0
    assert case.db.events == ["add_all", "save"]


@pytest.mark.asyncio
async def test_bounded_text_is_intentional_history_not_a_task_dump(case, caplog):
    await update(case, {"description": "d" * 4000, "risk_reason": "r" * 2000})
    assert changes(case) == {"description": ("Old description", "d" * 4000),
                             "risk_reason": ("Old risk", "r" * 2000)}
    assert not caplog.records


def test_update_allowlist_is_exact_schema_plus_derived_fields():
    fields = TaskService._UPDATE_HISTORY_TRACKED_FIELDS
    assert len(fields) == 16
    assert set(fields) == set(TaskUpdate.model_fields) | {"board_column_id", "completed_at"}


@pytest.mark.asyncio
async def test_combined_legacy_fields_and_status_are_each_recorded_once(case):
    before = {field: getattr(case.task, field) for field in TaskService._HISTORY_TRACKED_FIELDS}
    await update(case, {"status": "COMPLETADA", "assignee_id": None, "sprint_id": None,
                        "estimation_points": 0, "estimation_hours": 0, "priority": "high"})
    result = changes(case)
    assert len(result) == 8  # six explicit fields and two derived
    assert result["status"] == (before["status"], "COMPLETADA")
    assert result["assignee_id"] == (str(before["assignee_id"]), None)
    assert result["sprint_id"] == (str(before["sprint_id"]), None)
    assert result["estimation_points"] == ("3", "0")
    assert result["estimation_hours"] == ("2.5", "0.0")
    assert result["priority"] == ("medium", "high")
    assert all(row.actor_id == case.actor for row in case.db.rows)
    assert case.db.events == ["add_all", "save"]
