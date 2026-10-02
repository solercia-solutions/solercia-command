"""Offline ASGI requests: no main, lifespan, database, files or real runner."""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from threading import Event, get_ident
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
import pytest

from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot
from app.modules.task_import.preview_runner import PreviewRunnerError
from app.modules.task_import.schemas import PreviewResponse
from app.shared.exceptions import AppException, register_exception_handlers


def preview(title='Synthetic task'):
    headers = ';'.join(ChecklistProfile().headers) + ';Secret extra\n'
    row = f'T1;;;;;{title};;2026-01-02;;;private-note;excluded-extra\n'
    parsed = parse_checklist(
        SourceSnapshot('private-locator.csv', (headers + row).encode(), 'private-provenance'),
        ChecklistProfile(), ParseLimits(),
    )
    return parsed


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.results = {}
        self.started = Event()
        self.finished = Event()
        self.release = Event()
        self.block = False
        self.ignore_cancel = False

    def run(self, data, *, format, profile, cancel):
        self.calls.append((data, format, profile, cancel, get_ident()))
        self.started.set()
        try:
            if self.block:
                while not self.release.wait(.005):
                    if cancel.is_set() and not self.ignore_cancel:
                        raise PreviewRunnerError('cancelled')
            if self.failure:
                raise self.failure
            return self.results.get(data) or preview()
        finally:
            self.finished.set()


@pytest.fixture
def harness(monkeypatch):
    # Load an isolated module with auth/config import seams, not app.main/DB.
    dependencies = ModuleType('app.dependencies')
    config = ModuleType('app.config')
    config.settings = SimpleNamespace(TASK_IMPORT_PREVIEW_ENABLED=False)
    auth_calls = []

    async def membership(request: Request):
        auth_calls.append(request.headers.get('x-organization-id'))
        if request.headers.get('authorization') != 'Bearer synthetic':
            raise HTTPException(401, 'No has iniciado sesión.')
        if request.headers.get('x-organization-id') == 'denied':
            raise HTTPException(403, 'No perteneces a esa organización.')
        return SimpleNamespace(organization_id=request.headers.get('x-organization-id', 'first'),
                               user_id='trusted-actor')

    async def get_db():
        yield SimpleNamespace(marker='request-session')

    dependencies.get_db = get_db
    dependencies.get_current_membership = membership
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'app.dependencies', dependencies)
        patch.setitem(sys.modules, 'app.config', config)
        name = 'app.modules.task_import._isolated_router'
        path = Path(__file__).parents[1] / 'app/modules/task_import/router.py'
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        patch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(module.router, prefix='/api/v1')
    runner = FakeRunner()
    app.dependency_overrides[module.get_preview_runner] = lambda: runner
    state = SimpleNamespace(app=app, module=module, runner=runner, settings=config.settings,
                            auth_calls=auth_calls)
    yield state
    runner.release.set()
    module._EXECUTOR.shutdown(wait=True)


class Exchange:
    def __init__(self, chunks=(b'synthetic',), *, query='format=csv&profile=checklist',
                 authorized=True, organization='allowed', content_type='application/octet-stream',
                 stall=False, path='/api/v1/task-import/preview'):
        self.path = path
        self.chunks = list(chunks)
        self.query = query
        self.authorized = authorized
        self.organization = organization
        self.content_type = content_type
        self.stall = stall
        self.reads = 0
        self.disconnect = asyncio.Event()
        self.messages = []

    async def receive(self):
        if self.chunks:
            if self.stall:
                await self.disconnect.wait()
            self.reads += 1
            chunk = self.chunks.pop(0)
            return {'type': 'http.request', 'body': chunk, 'more_body': bool(self.chunks)}
        await self.disconnect.wait()
        return {'type': 'http.disconnect'}

    async def send(self, message):
        self.messages.append(message)

    async def run(self, app):
        headers = [(b'content-type', self.content_type.encode()),
                   (b'x-organization-id', self.organization.encode())]
        if self.authorized:
            headers.append((b'authorization', b'Bearer synthetic'))
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'POST', 'scheme': 'http', 'path': self.path,
                 'raw_path': self.path.encode(), 'query_string': self.query.encode(),
                 'headers': headers, 'server': ('test', 80), 'client': ('test', 1), 'root_path': ''}
        await app(scope, self.receive, self.send)
        return self

    @property
    def status(self):
        return next(m['status'] for m in self.messages if m['type'] == 'http.response.start')

    @property
    def payload(self):
        return json.loads(b''.join(m.get('body', b'') for m in self.messages))


def assert_preview_error(exchange, status, code):
    assert exchange.status == status
    assert exchange.payload == {
        'detail': 'No se pudo completar la vista previa.', 'code': code, 'status': status,
    }
    start = next(m for m in exchange.messages if m['type'] == 'http.response.start')
    assert (b'cache-control', b'no-store') in start['headers']
    assert 'private' not in json.dumps(exchange.payload)


@pytest.mark.asyncio
async def test_deployed_error_contract(harness):
    disabled = await Exchange().run(harness.app)
    assert_preview_error(disabled, 404, 'preview_disabled')
    assert disabled.reads == 0 and not harness.runner.calls
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    for failure, status, code in [
        (PreviewRunnerError('busy'), 503, 'busy'),
        (PreviewRunnerError('timeout'), 504, 'timeout'),
        (PreviewRunnerError('cleanup_failed'), 503, 'cleanup_failed'),
        (PreviewRunnerError('input_limit'), 413, 'input_limit'),
        (PreviewRunnerError('response_limit'), 413, 'response_limit'),
        (PreviewRunnerError('cancelled'), 499, 'cancelled'),
        (PreviewRunnerError('private-unknown'), 502, 'preview_failed'),
        (RuntimeError('private-runtime'), 502, 'preview_failed'),
    ]:
        harness.runner.failure = failure
        assert_preview_error(await Exchange().run(harness.app), status, code)


@pytest.mark.asyncio
async def test_shared_exception_backward_compatibility():
    for meta in (None, {}, {'session': 'synthetic'}):
        for headers in (None, {'Cache-Control': 'no-store'}):
            app = FastAPI()
            register_exception_handlers(app)

            @app.post('/api/v1/task-import/preview')
            async def probe():
                kwargs = {} if headers is None else {'headers': headers}
                raise AppException('Mensaje seguro.', 'stable', 409, meta=meta, **kwargs)

            exchange = await Exchange().run(app)
            expected = {'detail': 'Mensaje seguro.', 'code': 'stable', 'status': 409}
            if meta is not None:
                expected['meta'] = meta
            assert exchange.status == 409 and exchange.payload == expected
            start = next(m for m in exchange.messages if m['type'] == 'http.response.start')
            assert ((b'cache-control', b'no-store') in start['headers']) == (headers is not None)


@pytest.mark.asyncio
async def test_http_exception_headers_and_sanitized_dict():
    for detail in ('Mensaje seguro.', {'code': 'private-code', 'message': 'private-message'}):
        app = FastAPI()
        register_exception_handlers(app)

        @app.post('/api/v1/task-import/preview')
        async def probe():
            raise HTTPException(401, detail, headers={'WWW-Authenticate': 'Bearer'})

        exchange = await Exchange().run(app)
        assert exchange.status == 401
        assert exchange.payload == {
            'detail': detail if isinstance(detail, str) else 'Ocurrió un error.',
            'code': 'http_error', 'status': 401,
        }
        start = next(m for m in exchange.messages if m['type'] == 'http.response.start')
        assert (b'www-authenticate', b'Bearer') in start['headers']
        assert 'private' not in json.dumps(exchange.payload)


async def wait_started(runner):
    async with asyncio.timeout(2):
        while not runner.started.is_set():
            await asyncio.sleep(.005)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,authorized,organization,status', [
    (False, True, 'allowed', 404), (False, False, 'allowed', 401),
    (True, False, 'allowed', 401), (True, True, 'denied', 403),
    (False, True, 'denied', 403),
])
async def test_auth_and_flag_before_any_body(harness, enabled, authorized, organization, status):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = enabled
    exchange = await Exchange(authorized=authorized, organization=organization).run(harness.app)
    assert exchange.status == status
    assert exchange.reads == 0 and not harness.runner.calls
    assert harness.auth_calls == [organization]


@pytest.mark.asyncio
@pytest.mark.parametrize('query,content_type', [
    ('format=pdf&profile=checklist', 'application/octet-stream'),
    ('format=csv&profile=other', 'application/octet-stream'),
    ('format=csv', 'application/octet-stream'),
    ('format=csv&format=xlsx&profile=checklist', 'application/octet-stream'),
    ('format=csv&profile=checklist&max_input_bytes=999999', 'application/octet-stream'),
    ('format=csv&profile=checklist&organization_id=other', 'application/octet-stream'),
    ('format=csv&profile=checklist', 'multipart/form-data; boundary=synthetic'),
])
async def test_allowlist_before_body(harness, query, content_type):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    exchange = await Exchange(query=query, content_type=content_type).run(harness.app)
    assert exchange.status in (415, 422)
    assert exchange.reads == 0 and not harness.runner.calls


@pytest.mark.asyncio
async def test_chunked_overflow_stops_before_remaining_chunks(harness, monkeypatch):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    monkeypatch.setattr(harness.module, 'MAX_INPUT_BYTES', 4)
    exchange = await Exchange((b'12', b'345', b'must-not-read')).run(harness.app)
    assert_preview_error(exchange, 413, 'input_limit')
    assert exchange.reads == 2 and not harness.runner.calls


@pytest.mark.asyncio
async def test_upload_deadline_and_disconnect_never_start_runner(harness, monkeypatch):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    monkeypatch.setattr(harness.module, 'UPLOAD_SECONDS', .02)
    exchange = await Exchange(stall=True).run(harness.app)
    assert exchange.status == 408 and not harness.runner.calls
    disconnected = Exchange(chunks=())
    disconnected.disconnect.set()
    await disconnected.run(harness.app)
    assert disconnected.status == 499 and not harness.runner.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('format', ['csv', 'xlsx'])
async def test_explicit_projection_off_loop_and_no_cache(harness, format, caplog):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    exchange = await Exchange(query=f'format={format}&profile=checklist').run(harness.app)
    assert exchange.status == 200
    assert harness.runner.calls[0][1:3] == (format, 'checklist')
    assert harness.runner.calls[0][-1] != get_ident()
    PreviewResponse.model_validate(exchange.payload)
    data = exchange.payload['data']
    assert set(data) == {'complete', 'rows', 'issues', 'counts', 'source_hash', 'profile_version'}
    assert data['source_hash'] == preview().sha256
    assert data['profile_version'] == 'checklist-v1'
    assert data['rows'][0]['key'] == {
        'source_hash': data['source_hash'], 'sheet': None, 'row': 2,
    }
    assert data['counts'] == {'candidate': 1, 'rejected': 0, 'blank_skipped': 0, 'total': 1}
    assert data['rows'][0]['fields'][5] == {'name': 'Tarea', 'value': 'Synthetic task'}
    text = json.dumps(exchange.payload)
    for secret in ('private-locator', 'private-provenance', 'excluded-extra',
                   'sha256', 'source_bytes', 'sheet_names', 'Secret extra'):
        assert secret not in text
    assert 'Synthetic task' not in caplog.text and 'private' not in caplog.text
    start = next(m for m in exchange.messages if m['type'] == 'http.response.start')
    assert (b'cache-control', b'no-store') in start['headers']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,status,code', [
    (PreviewRunnerError('busy'), 503, 'busy'),
    (PreviewRunnerError('timeout'), 504, 'timeout'),
    (PreviewRunnerError('cleanup_failed'), 503, 'cleanup_failed'),
    (PreviewRunnerError('response_limit'), 413, 'response_limit'),
    (PreviewRunnerError('worker_crash'), 502, 'preview_failed'),
    (RuntimeError('private-worker-error'), 502, 'preview_failed'),
])
async def test_failures_are_stable_and_release_capacity(harness, failure, status, code, caplog):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.runner.failure = failure
    exchange = await Exchange().run(harness.app)
    assert exchange.status == status
    assert_preview_error(exchange, status, code)
    assert 'private' not in json.dumps(exchange.payload) + caplog.text
    harness.runner.failure = None
    assert (await Exchange().run(harness.app)).status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize('disconnect', [False, True])
async def test_cancel_or_disconnect_waits_for_runner_cleanup(harness, disconnect):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.runner.block = True
    exchange = Exchange()
    task = asyncio.create_task(exchange.run(harness.app))
    await wait_started(harness.runner)
    if disconnect:
        exchange.disconnect.set()
        await asyncio.wait_for(task, 2)
        assert exchange.status == 499
    else:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
    assert harness.runner.calls[0][3].is_set()
    assert harness.runner.finished.is_set()
    harness.runner.block = False
    assert (await Exchange().run(harness.app)).status == 200


@pytest.mark.asyncio
async def test_noncooperative_job_is_owned_quarantined_and_later_reclaimed(harness, monkeypatch):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    monkeypatch.setattr(harness.module, 'CLEANUP_SECONDS', .03)
    monkeypatch.setattr(harness.module, 'RUN_SECONDS', .03)
    harness.runner.block = harness.runner.ignore_cancel = True
    exchange = await Exchange().run(harness.app)
    assert exchange.status == 503
    assert_preview_error(exchange, 503, 'cleanup_failed')
    pending = harness.module._QUARANTINED_JOB
    assert pending is not None and not pending.done()
    rejected = await Exchange().run(harness.app)
    assert rejected.status == 503 and rejected.reads == 0
    assert len(harness.runner.calls) == 1
    harness.runner.release.set()
    async with asyncio.timeout(2):
        while not pending.done():
            await asyncio.sleep(.005)
    assert (await Exchange().run(harness.app)).status == 200
    assert harness.module._QUARANTINED_JOB is None


@pytest.mark.asyncio
async def test_incomplete_preview_has_issues_without_partial_rows(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.runner.results[b'broken'] = parse_checklist(
        SourceSnapshot('private.csv', b'\xff', 'private-provenance'),
        ChecklistProfile(), ParseLimits(),
    )
    exchange = await Exchange((b'broken',)).run(harness.app)
    assert exchange.status == 200
    data = exchange.payload['data']
    assert data['complete'] is False and data['counts'] is None and data['rows'] == []
    assert data['issues'] == [{'code': 'encoding_error', 'severity': 'error',
                              'row': None, 'column': None}]
    assert 'private' not in json.dumps(exchange.payload)


@pytest.mark.asyncio
async def test_upload_deadline_also_checked_between_immediately_available_chunks(harness, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(harness.module, 'monotonic', lambda: clock[0])

    class BufferedStream:
        async def stream(self):
            yield b'a'
            clock[0] = harness.module.UPLOAD_SECONDS + 1
            yield b'b'

    with pytest.raises(AppException) as error:
        await harness.module._upload(BufferedStream())
    assert error.value.status_code == 408
    assert error.value.code == 'upload_timeout'


@pytest.mark.asyncio
async def test_upload_cancellation_releases_admission_without_worker(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    task = asyncio.create_task(Exchange(stall=True).run(harness.app))
    async with asyncio.timeout(2):
        while not harness.auth_calls:
            await asyncio.sleep(.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not harness.runner.calls
    assert (await Exchange().run(harness.app)).status == 200


@pytest.mark.asyncio
async def test_cancellation_exhaustion_keeps_owned_job_and_capacity(harness, monkeypatch):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    monkeypatch.setattr(harness.module, 'CLEANUP_SECONDS', .03)
    harness.runner.block = harness.runner.ignore_cancel = True
    task = asyncio.create_task(Exchange().run(harness.app))
    await wait_started(harness.runner)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    pending = harness.module._QUARANTINED_JOB
    assert pending is not None and not pending.done()
    assert harness.runner.calls[0][3].is_set()
    denied = await Exchange().run(harness.app)
    assert denied.status == 503 and denied.reads == 0
    harness.runner.release.set()
    async with asyncio.timeout(2):
        while not pending.done():
            await asyncio.sleep(.005)
    assert (await Exchange().run(harness.app)).status == 200


@pytest.mark.asyncio
async def test_cleanup_failure_takes_precedence_over_disconnect(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.runner.block = harness.runner.ignore_cancel = True
    harness.runner.failure = PreviewRunnerError('cleanup_failed')
    exchange = Exchange()
    task = asyncio.create_task(exchange.run(harness.app))
    await wait_started(harness.runner)
    exchange.disconnect.set()
    async with asyncio.timeout(2):
        while not harness.runner.calls[0][3].is_set():
            await asyncio.sleep(.005)
    harness.runner.release.set()
    await task
    assert exchange.status == 503
    assert_preview_error(exchange, 503, 'cleanup_failed')


def test_feature_default_and_registration_without_importing_application():
    root = Path(__file__).parents[1] / 'app'
    config = ast.parse((root / 'config.py').read_text())
    settings = next(node for node in config.body if isinstance(node, ast.ClassDef)
                    and node.name == 'Settings')
    flag = next(node for node in settings.body if isinstance(node, ast.AnnAssign)
                and node.target.id == 'TASK_IMPORT_PREVIEW_ENABLED')
    assert isinstance(flag.value, ast.Constant) and flag.value.value is False
    main = ast.parse((root / 'main.py').read_text())
    assert any(isinstance(node, ast.ImportFrom)
               and node.module == 'app.modules.task_import.router'
               and any(alias.name == 'router' and alias.asname == 'task_import_router'
                       for alias in node.names) for node in main.body)
    assert any(isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Attribute)
               and node.value.func.attr == 'include_router'
               and isinstance(node.value.args[0], ast.Name)
               and node.value.args[0].id == 'task_import_router'
               and any(keyword.arg == 'prefix' and isinstance(keyword.value, ast.Name)
                       and keyword.value.id == 'API_PREFIX' for keyword in node.value.keywords)
               for node in main.body)


@pytest.mark.asyncio
async def test_cancellation_during_timeout_cleanup_is_not_swallowed(harness, monkeypatch):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    monkeypatch.setattr(harness.module, 'RUN_SECONDS', .02)
    harness.runner.block = harness.runner.ignore_cancel = True
    task = asyncio.create_task(Exchange().run(harness.app))
    await wait_started(harness.runner)
    async with asyncio.timeout(2):
        while not harness.runner.calls[0][3].is_set():
            await asyncio.sleep(.005)
    # The original timeout has already entered cleanup. New cancellation must
    # still propagate, but only after ownership/cleanup has been accounted for.
    task.cancel()
    await asyncio.sleep(.02)
    assert not task.done()
    task.cancel()
    harness.runner.release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert harness.runner.finished.is_set()
    assert (await Exchange().run(harness.app)).status == 200


@pytest.mark.asyncio
async def test_busy_upload_and_sequential_requests_are_isolated(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    harness.runner.block = True
    harness.runner.results = {b'first': preview('Only one'), b'third': preview('Only two')}
    first = Exchange((b'first',), organization='one')
    task = asyncio.create_task(first.run(harness.app))
    await wait_started(harness.runner)
    second = await Exchange((b'second',), organization='two').run(harness.app)
    assert_preview_error(second, 503, 'busy')
    assert second.reads == 0
    harness.runner.release.set()
    await task
    third = await Exchange((b'third',), organization='two').run(harness.app)
    assert third.status == 200
    assert 'Only one' in json.dumps(first.payload) and 'Only two' not in json.dumps(first.payload)
    assert 'Only two' in json.dumps(third.payload) and 'Only one' not in json.dumps(third.payload)
    assert [call[0] for call in harness.runner.calls] == [b'first', b'third']
    assert harness.runner.calls[0][3] is not harness.runner.calls[1][3]
    assert harness.auth_calls == ['one', 'two', 'two']
