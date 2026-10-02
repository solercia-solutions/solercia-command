"""Offline projection/SQL-shape checks; these do not prove PostgreSQL behavior."""
from datetime import UTC, datetime
from uuid import UUID
from unittest.mock import patch

import pytest
from pydantic_settings import BaseSettings
from sqlalchemy.dialects import postgresql

# No dotenv or secret-directory reads during application model imports.
_original_init = BaseSettings.__init__
def _without_files(self, *args, **kwargs):
    kwargs.update(_env_file=None, _secrets_dir=None)
    _original_init(self, *args, **kwargs)

with patch.object(BaseSettings, '__init__', _without_files):
    from app.modules.dashboard.daily_repository import DailyRepository
from app.modules.dashboard.daily_contracts import DailyContext
from app.modules.dashboard.daily_service import DailySummaryError, DailySummaryService

ORG, USER, PROJECT, BOARD = (UUID(int=i) for i in range(1, 5))
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def task(n=10, **changes):
    return dict(id=str(UUID(int=n)), organization_id=str(ORG), project_id=str(PROJECT),
                assignee_id=str(USER), title='Synthetic task', status='open',
                due_date=NOW.isoformat(), updated_at=NOW.isoformat(), completed_at=None,
                is_active=True, project_code='CODE', task_number=n, **changes)


def board():
    return dict(id=str(BOARD), project_id=str(PROJECT), organization_id=str(ORG))


def column(status, order, created=NOW):
    return dict(board_id=str(BOARD), status_key=status, column_order=order,
                created_at=created.isoformat())


class Result:
    def __init__(self, rows): self.rows = rows
    def mappings(self): return self
    def all(self): return self.rows


class Session:
    """Only execute exists: accidental session ownership/writes fail immediately."""
    def __init__(self, **streams):
        self.rows = [dict(kind=k, payload=v) for k, values in streams.items() for v in values]
        self.calls = []
    async def execute(self, statement):
        self.calls.append(statement)
        return Result(self.rows)


async def load(session, **limits):
    return await DailyRepository(session).assigned_daily_snapshot(
        DailyContext(ORG, USER), task_limit=limits.get('task_limit', 2),
        edge_limit=limits.get('edge_limit', 2))


@pytest.mark.asyncio
async def test_single_read_only_bounded_core_statement_and_empty_snapshot():
    session = Session()
    result = await load(session)
    assert result.tasks == result.boards == result.edges == ()
    assert len(session.calls) == 1
    statement = session.calls[0]
    assert statement.get_execution_options()['autoflush'] is False
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert sql.count('UNION ALL') == 3
    assert sql.count('LIMIT') == 4
    assert 'assigned_tasks' in sql and 'incoming_edges' in sql
    assert 'blocked_task_id = assigned_tasks.id' in sql
    assert 'blocker_task_id = blocker.id' in sql
    assert 'projects.organization_id' in sql and 'blocker_project.organization_id' in sql
    for name in ('tasks', 'projects', 'blocker', 'blocker_project', 'boards', 'board_columns', 'task_dependencies'):
        assert f'{name}.is_active IS true' in sql
        assert f'{name}.deleted_at IS NULL' in sql
    assert 'projects.code AS project_code' in sql and 'tasks.task_number' in sql
    assert 'tasks.assignee_id =' in sql
    assert 'blocker.assignee_id =' not in sql
    assert 'task_dependencies.organization_id =' in sql
    assert 'tasks.board_id' not in sql
    assert not any(word in sql.upper() for word in ('FOR UPDATE', 'INSERT INTO', 'DELETE FROM', 'UPDATE '))


@pytest.mark.asyncio
async def test_mapping_canonical_order_blocker_other_assignee_and_conflicting_completion():
    blocker = task(11)
    blocker['assignee_id'] = str(UUID(int=999))
    target = task()
    target['completed_at'] = NOW.isoformat()
    session = Session(task=[target], board=[board()], column=[column('closed', 9), column('open', 1)],
                      edge=[dict(target_id=target['id'], **blocker)])
    snapshot = await load(session)
    assert snapshot.boards[0].statuses == ('open', 'closed')
    assert snapshot.tasks[0].board_id == BOARD
    assert snapshot.tasks[0].task_key == 'CODE-10'
    assert snapshot.tasks[0].completed_at == NOW  # domain owns conflict classification
    assert snapshot.edges[0].target_id == UUID(int=10)
    assert snapshot.edges[0].blocker.assignee_id == UUID(int=999)
    assert snapshot.edges[0].blocker.board_id == BOARD
    class Clock:
        def now(self): return NOW
    summary = await DailySummaryService(DailyRepository(session), Clock()).summarize(
        DailyContext(ORG, USER), timezone='UTC', date_policy='instant')
    assert 'completion_conflict' in summary.coverage_warnings


@pytest.mark.asyncio
async def test_missing_or_inactive_board_remains_unknown_not_methodology_fallback():
    snapshot = await load(Session(task=[task()]))
    assert snapshot.tasks[0].board_id is None
    assert snapshot.boards == ()
    snapshot = await load(Session(task=[task()], board=[board()]))
    assert snapshot.boards[0].statuses == ()


@pytest.mark.asyncio
async def test_created_at_breaks_order_tie_but_exact_tie_fails():
    earlier = NOW.replace(hour=11)
    snapshot = await load(Session(board=[board()], column=[column('closed', 1), column('open', 1, earlier)]))
    assert snapshot.boards[0].statuses == ('open', 'closed')
    with pytest.raises(DailySummaryError, match='ambiguous_board_order'):
        await load(Session(board=[board()], column=[column('open', 1), column('closed', 1)]))


@pytest.mark.asyncio
async def test_conflicting_canonical_boards_fail_without_inventing_choice():
    other = board()
    other['id'] = str(UUID(int=99))
    with pytest.raises(DailySummaryError, match='ambiguous_board'):
        await load(Session(board=[board(), other]))


@pytest.mark.asyncio
@pytest.mark.parametrize('stream,rows,limits', [
    ('task', [task()] * 3, {}),
    ('edge', [dict(target_id=str(UUID(int=10)), **task(11))] * 3, {}),
    ('board', [board()] * 5, {}),
    ('column', [column('open', 1)] * 20001, {}),
])
async def test_overflow_fails_before_any_partial_mapping(stream, rows, limits):
    with pytest.raises(DailySummaryError, match='input_limit'):
        await load(Session(**{stream: rows}), **limits)


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [-1, 0, True, 1001])
async def test_invalid_admission_limit_never_executes(value):
    session = Session()
    with pytest.raises(DailySummaryError, match='input_limit'):
        await load(session, task_limit=value)
    assert session.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('code,number,expected', [
    ('ABC', 7, 'ABC-7'), ('Mixed-Code', 0, 'Mixed-Code-0'),
    (None, 7, None), ('', 7, None), ('ABC', None, None),
])
async def test_key_matches_existing_task_read_and_reaches_domain_item(code, number, expected):
    row = task()
    row.update(project_code=code, task_number=number)
    session = Session(task=[row], board=[board()], column=[column('open', 1), column('closed', 2)])
    snapshot = await load(session)
    assert snapshot.tasks[0].task_key == expected
    class Clock:
        def now(self): return NOW
    result = await DailySummaryService(DailyRepository(session), Clock()).summarize(
        DailyContext(ORG, USER), timezone='UTC', date_policy='instant')
    assert result.today.items[0].task_key == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('found', [True, False])
async def test_local_organization_gate_scoped_live_read_without_transaction_ownership(found):
    class GateSession:
        async def execute(self, statement):
            self.statement = statement
            class GateResult:
                def scalar_one_or_none(self): return ORG if found else None
            return GateResult()
    session = GateSession()
    assert await DailyRepository(session).organization_available(DailyContext(ORG, USER)) is found
    assert session.statement.get_execution_options()['autoflush'] is False
    sql = str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'organizations.id =' in sql and str(ORG) in sql
    assert 'organizations.is_active IS true' in sql and 'organizations.deleted_at IS NULL' in sql
    assert 'tasks' not in sql and 'projects' not in sql
