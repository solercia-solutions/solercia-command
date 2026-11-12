"""Offline HTTP contract: real error handlers, fake auth/config/repository only."""
import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

from fastapi import Depends
import pytest

from tests.test_task_import_preview_router import Exchange, harness


class OptionsExchange(Exchange):
    def __init__(self, query='', **kwargs):
        super().__init__(chunks=(), query=query, path='/api/v1/task-import/options', **kwargs)

    async def run(self, app):
        async def get(scope, receive, send):
            await app({**scope, 'method': 'GET'}, receive, send)
        return await super().run(get)


class Repository:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.block = False
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.available = True

    async def load(self, tenant, query):
        self.calls.append((tenant, query.model_dump()))
        self.started.set()
        try:
            if self.block:
                await asyncio.Event().wait()
            if self.failure:
                raise self.failure
            if not self.available:
                return None
            from app.modules.task_import.schemas import OptionsData, OptionPage, OptionMeta, OptionItem
            return OptionsData(
                projects=OptionPage(items=[OptionItem(id='project-id', label='Proyecto')],
                                    meta=OptionMeta(page=query.projects_page, size=query.projects_size, total=1)),
                members=OptionPage(items=[OptionItem(id='user-id', label='Ana Pérez')],
                                   meta=OptionMeta(page=query.members_page, size=query.members_size, total=1)),
                default_project=OptionItem(id='default-id', label='Generales'),
            )
        finally:
            self.finished.set()


@pytest.fixture
def options(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.repo = Repository()
    dependency = getattr(harness.module, 'get_options_repository', None)
    if dependency is not None:
        harness.app.dependency_overrides[dependency] = lambda: harness.repo
    return harness


def no_store(result):
    assert (b'cache-control', b'no-store') in next(
        m['headers'] for m in result.messages if m['type'] == 'http.response.start')


@pytest.mark.asyncio
async def test_defaults_projection_and_trusted_tenant(options):
    result = await OptionsExchange().run(options.app)
    assert result.status == 200
    assert options.repo.calls == [('allowed', dict(projects_page=1, projects_size=20, projects_q='',
                                                 members_page=1, members_size=20, members_q=''))]
    assert result.payload['data'] == {
        'projects': {'items': [{'id': 'project-id', 'label': 'Proyecto'}],
                     'meta': {'page': 1, 'size': 20, 'total': 1}},
        'members': {'items': [{'id': 'user-id', 'label': 'Ana Pérez'}],
                    'meta': {'page': 1, 'size': 20, 'total': 1}},
        'default_project': {'id': 'default-id', 'label': 'Generales'},
    }
    assert not options.runner.calls and result.reads == 0
    no_store(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,authorized,organization,status', [
    (False, True, 'allowed', 404), (False, False, 'allowed', 401),
    (True, False, 'allowed', 401), (True, True, 'denied', 403),
])
async def test_auth_and_flag_before_options_queries(options, enabled, authorized, organization, status):
    options.settings.TASK_IMPORT_PREVIEW_ENABLED = enabled
    result = await OptionsExchange(authorized=authorized, organization=organization).run(options.app)
    assert result.status == status
    assert not options.repo.calls and not options.runner.calls and result.reads == 0
    no_store(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('query', [
    'projects_page=0', 'projects_page=1001', 'members_page=0', 'members_page=1001',
    'projects_size=0', 'projects_size=101', 'members_size=0', 'members_size=101',
    'projects_page=private-secret', 'members_page=1.5', 'projects_q=x', 'members_q=%20x%20',
    'projects_q=' + 'x'*101, 'members_q=' + 'x'*101, 'q=private-secret',
    'tenant_id=private-secret', 'projects_page=1&projects_page=2',
    'members_size=20&members_size=20', 'projects_q=ab&projects_q=cd',
    'members_q=&members_q=', 'projects_size=20&projects_size=20',
    'members_page=1&members_page=1',
])
async def test_invalid_query_is_generic_before_queries(options, query, caplog):
    result = await OptionsExchange(query).run(options.app)
    assert result.status == 422
    assert set(result.payload) == {'detail', 'code', 'status'}
    assert 'private-secret' not in json.dumps(result.payload) + caplog.text
    assert not options.repo.calls and not options.runner.calls
    no_store(result)


@pytest.mark.asyncio
async def test_independent_bounds_and_trim(options):
    query = 'projects_page=1000&projects_size=100&projects_q=%20ab%20&members_page=2&members_size=1&members_q=%20%20'
    result = await OptionsExchange(query).run(options.app)
    assert result.status == 200
    assert options.repo.calls[-1][1] == dict(projects_page=1000, projects_size=100, projects_q='ab',
                                           members_page=2, members_size=1, members_q='')
    result = await OptionsExchange('members_q=' + 'x'*100).run(options.app)
    assert result.status == 200


@pytest.mark.asyncio
async def test_ineligible_organization_fails_closed(options):
    options.repo.available = False
    result = await OptionsExchange().run(options.app)
    assert result.status == 403
    assert 'data' not in result.payload
    no_store(result)


@pytest.mark.asyncio
async def test_query_errors_timeout_disconnect_and_cancellation_are_safe_and_joined(options, monkeypatch, caplog):
    options.repo.failure = RuntimeError('private-database-secret')
    result = await OptionsExchange().run(options.app)
    assert result.status == 502
    assert 'private' not in json.dumps(result.payload) + caplog.text
    no_store(result)
    options.repo.failure = None
    options.repo.block = True
    options.repo.finished.clear()
    monkeypatch.setattr(options.module, 'FACTS_SECONDS', .02)
    result = await OptionsExchange().run(options.app)
    assert result.status == 504 and options.repo.finished.is_set()
    no_store(result)
    monkeypatch.setattr(options.module, 'FACTS_SECONDS', 2)
    for disconnect in (True, False):
        options.repo.started.clear()
        options.repo.finished.clear()
        request = OptionsExchange()
        task = asyncio.create_task(request.run(options.app))
        await asyncio.wait_for(options.repo.started.wait(), 2)
        if disconnect:
            request.disconnect.set()
            await asyncio.wait_for(task, 2)
            assert request.status == 499
            no_store(request)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert options.repo.finished.is_set()


@pytest.mark.asyncio
async def test_repository_uses_request_session(options, monkeypatch):
    adapter = ModuleType('app.modules.task_import.options_repository')
    sessions = []
    def repository(session):
        sessions.append(session)
        return options.repo
    adapter.OptionsRepository = repository
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    del options.app.dependency_overrides[options.module.get_options_repository]
    auth_sessions = []

    async def membership(db=Depends(options.module.get_db)):
        auth_sessions.append(db)
        return SimpleNamespace(organization_id='trusted-tenant', user_id='trusted-user')

    options.app.dependency_overrides[options.module.get_current_membership] = membership
    result = await OptionsExchange(organization='untrusted-header').run(options.app)
    assert result.status == 200
    assert len(sessions) == 1 and sessions[0].marker == 'request-session'
    assert auth_sessions[0] is sessions[0]
    assert options.repo.calls[0][0] == 'trusted-tenant'


@pytest.mark.asyncio
async def test_dependency_failure_is_safe(options):
    def broken():
        raise RuntimeError('private-dependency')
    options.app.dependency_overrides[options.module.get_options_repository] = broken
    result = await OptionsExchange().run(options.app)
    assert result.status == 500
    assert 'private' not in json.dumps(result.payload)
    no_store(result)
