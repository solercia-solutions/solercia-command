"""Offline domain contracts with synthetic facts and injected clock/query."""
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.dashboard.daily_contracts import (
    DailyContext, DailySnapshot, DailyTask, BlockingEdge, BoardStatuses,
)
from app.modules.dashboard.daily_service import DailySummaryService, DailySummaryError

ORG, USER, PROJECT, BOARD = (UUID(int=i) for i in range(1, 5))
NOW = datetime(2026, 9, 5, 5, tzinfo=UTC)


def task(n=10, **changes):
    return replace(DailyTask(UUID(int=n), ORG, PROJECT, BOARD, USER, 'Tarea',
                             'open', NOW, NOW, None, True), **changes)


def board(**changes):
    return replace(BoardStatuses(ORG, PROJECT, BOARD, ('open', 'REMOVIDA', 'closed')), **changes)


class Clock:
    def __init__(self, now=NOW):
        self.value = now
        self.calls = 0

    def now(self):
        self.calls += 1
        return self.value


class Query:
    def __init__(self, tasks=(), boards=None, edges=()):
        self.snapshot = DailySnapshot(ORG, USER, tuple(tasks),
                                      (board(),) if boards is None else tuple(boards), tuple(edges))
        self.calls = []

    async def assigned_daily_snapshot(self, context, *, task_limit, edge_limit):
        self.calls.append((context, task_limit, edge_limit))
        return self.snapshot


async def summary(query, policy='instant', now=NOW, zone='America/Bogota'):
    return await DailySummaryService(query, Clock(now)).summarize(
        DailyContext(ORG, USER), timezone=zone, date_policy=policy)


@pytest.mark.asyncio
async def test_explicit_policies_differ_at_bogota_midnight():
    q = Query([task(due_date=datetime(2026, 9, 5, tzinfo=UTC))])
    stored = await summary(q, 'stored_calendar_date')
    instant = await summary(q)
    assert len(stored.today.items) == stored.today.count == 1
    assert len(instant.overdue.items) == instant.overdue.count == 1
    assert stored.date_policy == 'stored_calendar_date'
    assert instant.date_policy == 'instant'
    assert stored.timezone == 'America/Bogota'
    assert stored.generated_at == NOW
    assert stored.provider_freshness == 'unknown'
    assert stored.today.items[0].updated_at == NOW
    assert q.calls[0][0] == DailyContext(ORG, USER)


@pytest.mark.asyncio
async def test_dst_calendar_tomorrow_and_disjoint_groups():
    now = datetime(2026, 3, 8, 4, 30, tzinfo=UTC)
    q = Query([task(10, due_date=datetime(2026, 3, 8, 16, tzinfo=UTC)),
               task(11, due_date=datetime(2026, 3, 9, 4, tzinfo=UTC)),
               task(12, due_date=datetime(2026, 3, 7, 6, tzinfo=UTC))])
    result = await summary(q, now=now, zone='America/New_York')
    assert result.tomorrow_date.isoformat() == '2026-03-08'
    assert [t.id.int for t in result.tomorrow.items] == [10]
    assert [t.id.int for t in result.today.items] == [12]
    assert result.overdue.count == 0


@pytest.mark.asyncio
async def test_blockers_null_naive_duplicates_and_completed():
    target = task(due_date=None)
    active = task(20, assignee_id=None)
    done = task(21, status='closed', completed_at=NOW)
    edge = BlockingEdge(ORG, target.id, True, active)
    q = Query([target, task(11, due_date=NOW.replace(tzinfo=None))],
              edges=[edge, edge, BlockingEdge(ORG, target.id, True, done)])
    result = await summary(q)
    assert result.today.count == result.tomorrow.count == result.overdue.count == 0
    assert result.blocked.count == 1
    assert result.blocked.items[0].blocker_ids == (active.id,)
    assert {'missing_due_date', 'naive_due_date', 'cancellation_unsupported'} <= set(result.coverage_warnings)


@pytest.mark.asyncio
async def test_status_semantics_conflicts_and_no_arbitrary_cancellation():
    q = Query([task(10, status='closed', completed_at=NOW),
               task(11, status='REMOVIDA'), task(12, status='cancelled'),
               task(13, completed_at=NOW), task(14, status='closed'),
               task(15, board_id=UUID(int=90))])
    result = await summary(q)
    assert [t.id.int for t in result.today.items] == [11]
    assert {'unknown_status', 'unknown_board', 'completion_conflict',
            'cancellation_unsupported'} <= set(result.coverage_warnings)
    empty = await summary(Query([task()], boards=[board(statuses=())]))
    assert empty.today.count == 0
    assert 'unknown_status' in empty.coverage_warnings


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['task_tenant', 'assignee', 'snapshot', 'board', 'edge', 'blocker', 'endpoint'])
async def test_scope_mismatch_fails_closed_without_titles(kind):
    q = Query([task(title='PRIVATE')])
    foreign = UUID(int=999)
    if kind == 'task_tenant':
        q.snapshot = replace(q.snapshot, tasks=(task(organization_id=foreign),))
    elif kind == 'assignee':
        q.snapshot = replace(q.snapshot, tasks=(task(assignee_id=foreign),))
    elif kind == 'snapshot':
        q.snapshot = replace(q.snapshot, user_id=foreign)
    elif kind == 'board':
        q.snapshot = replace(q.snapshot, boards=(board(organization_id=foreign),))
    else:
        blocker = task(20, organization_id=foreign if kind == 'blocker' else ORG)
        edge = BlockingEdge(foreign if kind == 'edge' else ORG,
                            foreign if kind == 'endpoint' else task().id, True, blocker)
        q.snapshot = replace(q.snapshot, edges=(edge,))
    with pytest.raises(DailySummaryError, match='scope_mismatch') as exc:
        await summary(q)
    assert 'PRIVATE' not in str(exc.value)


@pytest.mark.asyncio
async def test_deterministic_order_overlap_inactive_and_immutability():
    a, b = task(11), task(10)
    edge = BlockingEdge(ORG, b.id, True, task(20, assignee_id=None))
    result = await summary(Query([a, b, task(12, is_active=False)], edges=[edge]))
    assert [t.id.int for t in result.today.items] == [10, 11]
    assert result.blocked.items[0].id == b.id
    assert result == await summary(Query([b, a, task(12, is_active=False)], edges=[edge]))
    with pytest.raises(FrozenInstanceError):
        result.timezone = 'UTC'
    assert (await summary(Query())).coverage_warnings == ('cancellation_unsupported',)


@pytest.mark.asyncio
@pytest.mark.parametrize('zone,policy,now', [('', 'instant', NOW), ('+05:00', 'instant', NOW),
    ('America/Bogota', 'guess', NOW), ('UTC', 'instant', NOW.replace(tzinfo=None))])
async def test_invalid_temporal_inputs_never_query(zone, policy, now):
    q = Query()
    with pytest.raises(DailySummaryError):
        await summary(q, policy, now, zone)
    assert not q.calls


@pytest.mark.asyncio
async def test_bounds_duplicates_and_query_errors_are_not_empty_success():
    with pytest.raises(DailySummaryError, match='input_limit'):
        await summary(Query([task(i + 10) for i in range(1001)]))
    with pytest.raises(DailySummaryError, match='duplicate_task'):
        await summary(Query([task(), task()]))
    class Broken(Query):
        async def assigned_daily_snapshot(self, *args, **kwargs):
            raise RuntimeError('query unavailable')
    with pytest.raises(RuntimeError, match='query unavailable'):
        await summary(Broken())


@pytest.mark.asyncio
async def test_inactive_edges_and_blockers_cannot_block():
    edges = [BlockingEdge(ORG, task().id, False, task(20)),
             BlockingEdge(ORG, task().id, True, task(21, is_active=False))]
    assert (await summary(Query([task()], edges=edges))).blocked.count == 0
    with pytest.raises(DailySummaryError, match='input_limit'):
        await summary(Query([task()], edges=[edges[0]] * 5001))


@pytest.mark.asyncio
async def test_required_policy_clock_once_and_unknown_modification_time():
    q, clock = Query([task(updated_at=NOW.replace(tzinfo=None))]), Clock()
    service = DailySummaryService(q, clock)
    with pytest.raises(TypeError):
        await service.summarize(DailyContext(ORG, USER), timezone='UTC')
    result = await service.summarize(DailyContext(ORG, USER), timezone='UTC', date_policy='instant')
    assert clock.calls == 1
    assert result.today.items[0].updated_at is None
    assert 'naive_updated_at' in result.coverage_warnings
