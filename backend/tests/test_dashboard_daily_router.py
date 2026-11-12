"""Offline daily HTTP contracts, real handlers; no main, lifespan or database."""
import asyncio
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from pydantic_settings import BaseSettings

from app.modules.dashboard.daily_contracts import DailyContext, DailySnapshot, DailyTask, BoardStatuses, BlockingEdge
from app.modules.dashboard.daily_service import DailySummaryError
from app.shared.exceptions import AppException, register_exception_handlers

ORG, USER, PROJECT, BOARD = (UUID(int=i) for i in range(1, 5))
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
VALID = 'timezone=America%2FBogota&date_policy=instant'


class Repository:
    def __init__(self):
        self.calls = []
        self.available = True
        self.gate_block = False
        self.failure = None
        self.block = False
        self.started = asyncio.Event()
        self.cleaning = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()
        self.slow_cleanup = False
        self.snapshot = DailySnapshot(ORG, USER, (), (), ())

    async def organization_available(self, context):
        self.calls.append(('gate', context))
        if self.gate_block:
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cleaning.set()
                await self.release.wait()
                self.finished.set()
        return self.available

    async def assigned_daily_snapshot(self, context, **limits):
        self.calls.append(('facts', context))
        self.started.set()
        try:
            if self.block:
                await asyncio.Event().wait()
            if self.failure:
                raise self.failure
            return self.snapshot
        finally:
            self.cleaning.set()
            if self.slow_cleanup:
                await self.release.wait()
            self.finished.set()


@pytest.fixture
def daily(monkeypatch):
    original = BaseSettings.__init__
    def no_files(self, *args, **kwargs):
        kwargs.update(_env_file=None, _secrets_dir=None)
        original(self, *args, **kwargs)
    with patch.object(BaseSettings, '__init__', no_files):
        spec = importlib.util.spec_from_file_location(
            'app.modules.dashboard._daily_test_router',
            Path(__file__).parents[1] / 'app/modules/dashboard/router.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(module.router, prefix='/api/v1')
    state = SimpleNamespace(app=app, module=module, repo=Repository(), released=False)
    async def membership(request: Request):
        if request.headers.get('authorization') != 'synthetic':
            raise AppException('No has iniciado sesión.', 'not_authenticated', 401)
        if request.headers.get('x-organization-id') == 'foreign':
            raise AppException('No perteneces a esa organización.', 'not_a_member', 403)
        return SimpleNamespace(organization_id=ORG, user_id=USER)
    async def db():
        try:
            yield object()
        finally:
            assert not state.repo.started.is_set() or state.repo.finished.is_set()
            state.released = True
    app.dependency_overrides[module.get_current_membership] = membership
    app.dependency_overrides[module.get_db] = db
    if hasattr(module, 'get_daily_repository'):
        app.dependency_overrides[module.get_daily_repository] = lambda: state.repo
        app.dependency_overrides[module.get_daily_clock] = lambda: SimpleNamespace(now=lambda: NOW)
    monkeypatch.setattr(module, 'settings', SimpleNamespace(DAILY_DASHBOARD_ENABLED=True), raising=False)
    return state


class Exchange:
    def __init__(self, query=VALID, auth=True, foreign=False):
        self.query, self.auth, self.foreign = query, auth, foreign
        self.disconnect = asyncio.Event()
        self.messages = []
    async def run(self, app):
        async def receive():
            await self.disconnect.wait()
            return {'type': 'http.disconnect'}
        async def send(message):
            self.messages.append(message)
        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': 'GET', 'scheme': 'http', 'path': '/api/v1/dashboard/daily',
                   'query_string': self.query.encode(), 'root_path': '',
                   'headers': [(b'authorization', b'synthetic' if self.auth else b''),
                               (b'x-organization-id', b'foreign' if self.foreign else b'allowed')],
                   'server': ('test', 80), 'client': ('test', 1)}, receive, send)
        return self
    @property
    def status(self):
        start = next(m for m in self.messages if m['type'] == 'http.response.start')
        assert (b'cache-control', b'no-store') in start['headers']
        return start['status']
    @property
    def payload(self):
        return json.loads(b''.join(m.get('body', b'') for m in self.messages))


@pytest.mark.asyncio
async def test_defaults_empty_and_trusted_context(daily):
    from app.config import Settings
    assert Settings.model_fields['DAILY_DASHBOARD_ENABLED'].default is False
    result = await Exchange().run(daily.app)
    assert result.status == 200
    data = result.payload['data']
    assert data['timezone'] == 'America/Bogota' and data['date_policy'] == 'instant'
    assert data['today_date'] == '2026-09-05' and data['tomorrow_date'] == '2026-09-06'
    assert data['generated_at'] == '2026-09-05T12:00:00Z'
    assert data['provider_freshness'] == 'unknown'
    for name in ('today', 'tomorrow', 'overdue', 'blocked'):
        assert data[name] == {'count': 0, 'items': []}
    assert 'cancellation_unsupported' in data['coverage_warnings']
    assert daily.repo.calls == [('gate', DailyContext(ORG, USER)), ('facts', DailyContext(ORG, USER))]


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', 'timezone=UTC', 'date_policy=instant',
    VALID + '&assignee_id=PRIVATE', VALID + '&organization_id=PRIVATE',
    VALID + '&user_id=PRIVATE', VALID + '&timezone=UTC', VALID + '&date_policy=instant',
    'timezone=PRIVATE&date_policy=instant', 'timezone=&date_policy=instant',
    'timezone=UTC&date_policy=PRIVATE', 'timezone=%2Fetc%2FPRIVATE&date_policy=instant',
    'timezone=localtime&date_policy=instant', 'timezone=UTC&date_policy=',
    VALID + '&unexpected=PRIVATE'])
async def test_invalid_parameters_no_facts_no_reflection(daily, query, caplog):
    result = await Exchange(query).run(daily.app)
    assert result.status == 422
    assert set(result.payload) == {'detail', 'code', 'status'}
    assert 'PRIVATE' not in json.dumps(result.payload) + caplog.text
    assert daily.repo.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,auth,foreign,available,status', [
    (False, True, False, True, 404), (False, False, False, True, 401),
    (True, False, False, True, 401), (True, True, True, True, 403),
    (True, True, False, False, 403)])
async def test_gates_precede_facts(daily, enabled, auth, foreign, available, status):
    daily.module.settings.DAILY_DASHBOARD_ENABLED = enabled
    daily.repo.available = available
    result = await Exchange(auth=auth, foreign=foreign).run(daily.app)
    assert result.status == status
    assert not any(call[0] == 'facts' for call in daily.repo.calls)


def fact(n, **kwargs):
    values = dict(id=UUID(int=n), organization_id=ORG, project_id=PROJECT, board_id=BOARD,
                  assignee_id=USER, title='Assigned synthetic', status='open', due_date=NOW,
                  updated_at=NOW, completed_at=None, is_active=True, task_key=f'CODE-{n}')
    return DailyTask(**(values | kwargs))


@pytest.mark.asyncio
async def test_projection_privacy_overlap_and_incomplete_coverage(daily):
    target, blocker = fact(10), fact(99, title='PRIVATE BLOCKER', assignee_id=UUID(int=99))
    daily.repo.snapshot = DailySnapshot(ORG, USER,
        (target, fact(11, due_date=None), fact(12, board_id=None), fact(13, task_key=None)),
        (BoardStatuses(ORG, PROJECT, BOARD, ('open', 'closed')),),
        (BlockingEdge(ORG, target.id, True, blocker),))
    result = await Exchange().run(daily.app)
    assert result.status == 200
    data = result.payload['data']
    assert data['today']['count'] == 2 and data['blocked']['count'] == 1
    item = data['blocked']['items'][0]
    assert item['task_key'] == 'CODE-10' and item['blocked_count'] == 1
    assert set(item) == {'id', 'project_id', 'task_key', 'title', 'status', 'due_date', 'updated_at', 'blocked_count'}
    assert {'groups_overlap', 'missing_due_date', 'unknown_board', 'missing_task_key',
            'cancellation_unsupported'} <= set(data['coverage_warnings'])
    assert 'PRIVATE' not in json.dumps(data) and str(blocker.id) not in json.dumps(data)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,status,code', [(DailySummaryError('input_limit'), 413, 'input_limit'),
    (DailySummaryError('scope_mismatch'), 503, 'daily_unavailable'),
    (RuntimeError('PRIVATE'), 500, 'internal_error')])
async def test_safe_failures(daily, failure, status, code):
    daily.repo.failure = failure
    result = await Exchange().run(daily.app)
    assert result.status == status and result.payload['code'] == code
    assert 'PRIVATE' not in json.dumps(result.payload)
    assert daily.repo.finished.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['timeout', 'disconnect', 'cancel', 'repeat_cancel'])
@pytest.mark.parametrize('phase', ['gate', 'facts'])
async def test_cleanup_joined_before_session_release(daily, monkeypatch, mode, phase):
    # Keep get_db in the dependency tree even when the adapter is replaced.
    from fastapi import Depends
    async def repository(db=Depends(daily.module.get_db)):
        return daily.repo
    daily.app.dependency_overrides[daily.module.get_daily_repository] = repository
    daily.repo.block = daily.repo.slow_cleanup = True
    daily.repo.gate_block = phase == 'gate'
    monkeypatch.setattr(daily.module, 'DAILY_QUERY_SECONDS', .02 if mode == 'timeout' else 5)
    exchange = Exchange()
    request = asyncio.create_task(exchange.run(daily.app))
    await asyncio.wait_for(daily.repo.started.wait(), 1)
    if mode == 'disconnect':
        exchange.disconnect.set()
    elif mode in ('cancel', 'repeat_cancel'):
        request.cancel()
    await asyncio.wait_for(daily.repo.cleaning.wait(), 1)
    if mode == 'repeat_cancel':
        request.cancel()
        await asyncio.sleep(0)
    assert not request.done() and not daily.released
    daily.repo.release.set()
    if mode in ('cancel', 'repeat_cancel'):
        with pytest.raises(asyncio.CancelledError):
            await request
    else:
        await request
        assert exchange.status == (504 if mode == 'timeout' else 499)
    assert daily.repo.finished.is_set() and daily.released
    if phase == 'gate':
        assert not any(call[0] == 'facts' for call in daily.repo.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('policy,group', [('instant', 'overdue'), ('stored_calendar_date', 'today')])
async def test_explicit_calendar_policy_survives_http(daily, policy, group):
    daily.repo.snapshot = DailySnapshot(ORG, USER,
        (fact(10, due_date=NOW.replace(hour=0)),),
        (BoardStatuses(ORG, PROJECT, BOARD, ('open', 'closed')),), ())
    result = await Exchange(f'timezone=America/Bogota&date_policy={policy}').run(daily.app)
    assert result.status == 200
    data = result.payload['data']
    assert data['date_policy'] == policy and data[group]['count'] == 1
    assert 'groups_overlap' not in data['coverage_warnings']


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['overflow', 'foreign_scope', 'unknown_status'])
async def test_actual_domain_rejections_and_unknown_coverage(daily, kind):
    tasks = (fact(10),)
    if kind == 'overflow':
        tasks = tuple(fact(n + 10) for n in range(1001))
    elif kind == 'foreign_scope':
        tasks = (fact(10, assignee_id=UUID(int=999)),)
    else:
        tasks = (fact(10, status='unrecognized'),)
    daily.repo.snapshot = DailySnapshot(ORG, USER, tasks,
        (BoardStatuses(ORG, PROJECT, BOARD, ('open', 'closed')),), ())
    result = await Exchange().run(daily.app)
    assert result.status == {'overflow': 413, 'foreign_scope': 503, 'unknown_status': 200}[kind]
    if kind == 'unknown_status':
        assert result.payload['data']['today']['count'] == 0
        assert 'unknown_status' in result.payload['data']['coverage_warnings']
    else:
        assert 'data' not in result.payload
