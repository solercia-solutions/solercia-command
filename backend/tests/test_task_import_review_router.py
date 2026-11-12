"""Stateless review HTTP contract with isolated auth, parser and facts seams."""
import asyncio
import base64
import json
from types import ModuleType
import sys

import pytest

from tests.test_task_import_preview_router import Exchange, harness
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot
from app.modules.task_import.review_ports import ProjectFacts
from app.modules.task_import.preview_runner import PreviewRunnerError
from app.shared.exceptions import AppException


class Facts:
    def active_project(self, tenant, project):
        return ProjectFacts(tenant, project, frozenset({'to_do'}))

    def active_member(self, tenant, user):
        return True


class Repository:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.block = False
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def load(self, tenant, projects, users):
        self.calls.append((tenant, projects, users))
        self.started.set()
        try:
            if self.block:
                await asyncio.Event().wait()
            if self.failure:
                raise self.failure
            return Facts()
        finally:
            self.finished.set()


def document(count=1, invalid=False):
    headers = ';'.join(ChecklistProfile().headers) + '\n'
    rows = ''.join(f'T{i};to_do;;;;Synthetic task;;{"bad" if invalid else "2026-01-02"};;;\n'
                   for i in range(count))
    data = (headers + rows).encode()
    parsed = parse_checklist(SourceSnapshot('private.csv', data), ChecklistProfile(), ParseLimits())
    return data, parsed


def payload(count=1, invalid=False):
    data, parsed = document(count, invalid)
    return {
        'format': 'csv', 'profile': 'checklist',
        'source_base64': base64.b64encode(data).decode(),
        'source_hash': parsed.sha256, 'profile_version': 'checklist-v1',
        'decisions': [{'key': {'source_hash': parsed.sha256, 'sheet': row.sheet, 'row': row.number},
                       'action': 'include', 'project_id': 'project', 'assignee_id': 'user'}
                      for row in parsed.rows],
    }


def exchange(body=None, **kwargs):
    return Exchange((json.dumps(body or payload()).encode(),), path='/api/v1/task-import/review',
                    query='', content_type='application/json', **kwargs)


def no_store(result):
    assert (b'cache-control', b'no-store') in next(
        m['headers'] for m in result.messages if m['type'] == 'http.response.start')


@pytest.fixture
def review(harness):
    harness.settings.TASK_IMPORT_PREVIEW_ENABLED = True
    repo = Repository()
    dependency = getattr(harness.module, 'get_review_facts_repository', None)
    if dependency is not None:
        harness.app.dependency_overrides[dependency] = lambda: repo
    harness.repo = repo
    for invalid in (False, True):
        for count in (1, 5, 1001):
            data, parsed = document(count, invalid)
            harness.runner.results[data] = parsed
    return harness


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,authorized,organization,status', [
    (False, True, 'allowed', 404), (True, False, 'allowed', 401),
    (True, True, 'denied', 403), (False, False, 'allowed', 401),
])
async def test_auth_and_disabled_read_zero_bytes(review, enabled, authorized, organization, status):
    review.settings.TASK_IMPORT_PREVIEW_ENABLED = enabled
    result = await exchange(authorized=authorized, organization=organization).run(review.app)
    assert result.status == status
    assert result.reads == 0 and not review.runner.calls and not review.repo.calls
    no_store(result)


@pytest.mark.asyncio
async def test_fresh_bytes_trusted_context_and_public_projection(review, caplog):
    result = await exchange().run(review.app)
    assert result.status == 200
    data = result.payload['data']
    assert data['status'] == 'validated_for_review'
    assert data['counts']['total'] == 1
    assert data['rows'][0]['key'] == payload()['decisions'][0]['key']
    assert data['rows'][0]['effective_due_date'] == '2026-01-02'
    assert review.runner.calls[0][0] == document()[0]
    assert review.repo.calls == [('allowed', ['project'], ['user'])]
    assert set(data) == {'status', 'source_hash', 'profile_version', 'counts', 'issues', 'rows'}
    assert set(data['rows'][0]) == {'key', 'action', 'project_id', 'assignee_id',
                                  'effective_due_date', 'effective_status', 'issues'}
    for secret in ('private.csv', 'trusted-actor', 'source_base64', 'original', 'context'):
        assert secret not in json.dumps(result.payload) + caplog.text
    no_store(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['root', 'decision', 'key', 'correction'])
@pytest.mark.parametrize('field', ['actor_id', 'tenant_id', 'limits', 'path', 'source_preview'])
async def test_recursive_unknown_fields_are_private(review, location, field, caplog):
    body = payload()
    decision = body['decisions'][0]
    target = body if location == 'root' else decision if location == 'decision' else decision['key']
    if location == 'correction':
        decision['corrections'] = {'due_date': None}
        target = decision['corrections']
    target[field] = 'private-secret'
    result = await exchange(body).run(review.app)
    assert result.status == 422
    assert 'private-secret' not in json.dumps(result.payload) + caplog.text
    assert 'errors' not in result.payload
    assert not review.runner.calls and not review.repo.calls
    no_store(result)


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value,issue', [
    ('source_hash', '0' * 64, 'source_hash_mismatch'),
    ('profile_version', 'checklist-old', 'profile_version_mismatch'),
])
async def test_claims_are_checked_against_fresh_parse(review, field, value, issue):
    body = payload()
    body[field] = value
    result = await exchange(body).run(review.app)
    assert result.status == 200
    assert result.payload['data']['status'] == 'blocked'
    assert issue in result.payload['data']['issues']
    no_store(result)


@pytest.mark.asyncio
async def test_all_five_invalid_rows_corrections_and_exclusions_accounted(review):
    body = payload(5, True)
    result = await exchange(body).run(review.app)
    assert result.status == 200
    assert result.payload['data']['status'] == 'blocked'
    assert len(result.payload['data']['rows']) == 5
    assert all('invalid_date' in row['issues'] for row in result.payload['data']['rows'])
    for decision in body['decisions'][:4]:
        decision['corrections'] = {'due_date': None}
    body['decisions'][4] = {'key': body['decisions'][4]['key'], 'action': 'exclude', 'reason': 'Duplicado'}
    result = await exchange(body).run(review.app)
    assert result.payload['data']['status'] == 'validated_for_review'
    assert result.payload['data']['counts']['total'] == 5
    assert result.payload['data']['rows'][4]['action'] == 'exclude'
    assert all(row['effective_due_date'] is None for row in result.payload['data']['rows'])


@pytest.mark.asyncio
async def test_decisions_above_1000_deduplicate_fact_ids(review):
    result = await exchange(payload(1001)).run(review.app)
    assert result.status == 200
    assert len(result.payload['data']['rows']) == 1001
    assert review.repo.calls == [('allowed', ['project'], ['user'])]


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['!!!!', 'Y Q==', 'YQ=', 'é'])
async def test_strict_base64(review, value):
    body = payload()
    body['source_base64'] = value
    result = await exchange(body).run(review.app)
    assert result.status == 422
    assert not review.runner.calls
    no_store(result)


@pytest.mark.asyncio
async def test_caps_and_timeout(review, monkeypatch):
    monkeypatch.setattr(review.module, 'MAX_INPUT_BYTES', 1)
    result = await exchange().run(review.app)
    assert result.status == 413
    no_store(result)
    monkeypatch.setattr(review.module, 'MAX_REVIEW_BODY_BYTES', 1)
    result = await exchange().run(review.app)
    assert result.status == 413 and not review.runner.calls
    no_store(result)
    monkeypatch.setattr(review.module, 'UPLOAD_SECONDS', .01)
    result = await exchange(stall=True).run(review.app)
    assert result.status == 408
    no_store(result)


@pytest.mark.asyncio
async def test_facts_timeout_failure_and_cancellation_are_joined(review, monkeypatch):
    review.repo.failure = RuntimeError('private-database-error')
    result = await exchange().run(review.app)
    assert result.status == 502
    assert 'private' not in json.dumps(result.payload)
    no_store(result)
    review.repo.failure = None
    review.repo.block = True
    review.repo.started.clear()
    review.repo.finished.clear()
    monkeypatch.setattr(review.module, 'FACTS_SECONDS', .02)
    result = await exchange().run(review.app)
    assert result.status == 504 and review.repo.finished.is_set()
    no_store(result)
    monkeypatch.setattr(review.module, 'FACTS_SECONDS', 2)
    for disconnect in (True, False):
        review.repo.started.clear()
        review.repo.finished.clear()
        request = exchange()
        task = asyncio.create_task(request.run(review.app))
        await asyncio.wait_for(review.repo.started.wait(), 2)
        if disconnect:
            request.disconnect.set()
            await asyncio.wait_for(task, 2)
            assert request.status == 499
            no_store(request)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert review.repo.finished.is_set()


@pytest.mark.asyncio
async def test_dependency_uses_request_session_and_trusted_actor(review, monkeypatch):
    adapter = ModuleType('app.modules.task_import.review_facts_repository')
    sessions = []

    def repository(session):
        sessions.append(session)
        return review.repo

    adapter.ReviewFactsRepository = repository
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    del review.app.dependency_overrides[review.module.get_review_facts_repository]
    contexts = []
    original = review.module.build_review_plan

    def build(parsed, version, decisions, context, facts):
        contexts.append(context)
        return original(parsed, version, decisions, context, facts)

    monkeypatch.setattr(review.module, 'build_review_plan', build)
    result = await exchange().run(review.app)
    assert result.status == 200
    assert len(sessions) == 1 and sessions[0].marker == 'request-session'
    assert contexts[0].tenant_id == 'allowed' and contexts[0].actor_id == 'trusted-actor'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['null', 'empty', 'unsupported', 'exclude_project',
                                   'exclude_correction', 'exclude_empty', 'long_reason',
                                   'long_id', 'long_sheet', 'boolean_row', 'missing_sheet',
                                   'missing_project', 'missing_assignee'])
async def test_strict_decision_shapes(review, change):
    body = payload()
    decision = body['decisions'][0]
    if change in ('null', 'empty', 'unsupported'):
        decision['corrections'] = {'null': None, 'empty': {},
                                   'unsupported': {'status': 'done'}}[change]
    elif change.startswith('exclude') or change == 'long_reason':
        decision = {'key': decision['key'], 'action': 'exclude', 'reason': 'Duplicado'}
        body['decisions'][0] = decision
        if change == 'exclude_project':
            decision['project_id'] = 'project'
        elif change == 'exclude_correction':
            decision['corrections'] = {'due_date': None}
        elif change == 'exclude_empty':
            decision['reason'] = '   '
        else:
            decision['reason'] = 'x' * 513
    elif change == 'long_id':
        decision['project_id'] = 'x' * 37
    elif change == 'long_sheet':
        decision['key']['sheet'] = 'x' * 129
    elif change == 'boolean_row':
        decision['key']['row'] = True
    elif change == 'missing_project':
        del decision['project_id']
    elif change == 'missing_assignee':
        del decision['assignee_id']
    else:
        del decision['key']['sheet']
    result = await exchange(body).run(review.app)
    assert result.status == 422 and not review.runner.calls and not review.repo.calls
    no_store(result)


@pytest.mark.asyncio
async def test_missing_duplicate_and_wrong_coordinate_decisions_stay_blocked(review):
    for variant in ('missing', 'duplicate', 'sheet', 'hash'):
        body = payload()
        if variant == 'missing':
            body['decisions'] = []
        elif variant == 'duplicate':
            body['decisions'] *= 2
        else:
            body['decisions'][0]['key']['sheet' if variant == 'sheet' else 'source_hash'] = (
                'Other sheet' if variant == 'sheet' else '0' * 64)
        result = await exchange(body).run(review.app)
        assert result.status == 200 and result.payload['data']['status'] == 'blocked'
        assert len(result.payload['data']['rows']) == 1
        no_store(result)


@pytest.mark.asyncio
async def test_decision_and_unique_fact_budgets(review):
    body = payload()
    body['decisions'] *= ParseLimits().max_rows
    result = await exchange(body).run(review.app)
    assert result.status == 422 and not review.runner.calls
    body = payload(1001)
    for i, decision in enumerate(body['decisions']):
        decision['project_id'] = f'project-{i}'
    result = await exchange(body).run(review.app)
    assert result.status == 422 and result.payload['code'] == 'facts_limit'
    assert not review.repo.calls
    no_store(result)


@pytest.mark.asyncio
async def test_explicit_date_correction_and_blank_accounting(review):
    body = payload(1, True)
    body['decisions'][0]['corrections'] = {'due_date': '2026-02-03'}
    result = await exchange(body).run(review.app)
    assert result.payload['data']['status'] == 'validated_for_review'
    assert result.payload['data']['rows'][0]['effective_due_date'] == '2026-02-03'
    body['decisions'][0]['corrections']['due_date'] = '2026-02-30'
    result = await exchange(body).run(review.app)
    assert 'invalid_date_correction' in result.payload['data']['rows'][0]['issues']
    data, _ = document()
    data += b';;;;;;;;;;\n'
    parsed = parse_checklist(SourceSnapshot('private.csv', data), ChecklistProfile(), ParseLimits())
    review.runner.results[data] = parsed
    body = payload()
    body['source_base64'] = base64.b64encode(data).decode()
    body['source_hash'] = body['decisions'][0]['key']['source_hash'] = parsed.sha256
    result = await exchange(body).run(review.app)
    assert result.payload['data']['counts']['blank_skipped'] == 1
    assert result.payload['data']['rows'][1]['action'] == 'blank_skipped'
    assert result.payload['data']['status'] == 'validated_for_review'


@pytest.mark.asyncio
async def test_app_auth_and_dependency_failures_have_no_store(review):
    async def denied():
        raise AppException('No autorizado.', 'not_authenticated', 401)

    review.app.dependency_overrides[review.module.get_current_membership] = denied
    result = await exchange().run(review.app)
    assert result.status == 401 and result.reads == 0
    assert result.payload['code'] == 'not_authenticated'
    no_store(result)
    del review.app.dependency_overrides[review.module.get_current_membership]

    def broken():
        raise RuntimeError('private-dependency')

    review.app.dependency_overrides[review.module.get_review_facts_repository] = broken
    result = await exchange().run(review.app)
    assert result.status == 500 and result.reads == 0
    assert 'private' not in json.dumps(result.payload)
    no_store(result)


@pytest.mark.asyncio
async def test_runner_failure_timeout_cancel_and_shared_admission(review, monkeypatch):
    review.runner.failure = PreviewRunnerError('worker_crash')
    result = await exchange().run(review.app)
    assert result.status == 502 and not review.repo.calls
    no_store(result)
    review.runner.failure = None
    review.runner.block = True
    review.runner.started.clear()
    review.runner.finished.clear()
    task = asyncio.create_task(exchange().run(review.app))
    async with asyncio.timeout(2):
        while not review.runner.started.is_set():
            await asyncio.sleep(.005)
    busy = await exchange().run(review.app)
    assert busy.status == 503 and busy.reads == 0
    no_store(busy)
    preview_busy = await Exchange().run(review.app)
    assert preview_busy.status == 503 and preview_busy.reads == 0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert review.runner.finished.is_set() and review.runner.calls[-1][3].is_set()
    monkeypatch.setattr(review.module, 'RUN_SECONDS', .02)
    result = await exchange().run(review.app)
    assert result.status == 504 and review.runner.finished.is_set()
    no_store(result)


@pytest.mark.asyncio
async def test_json_media_and_malformed_envelopes(review):
    for raw in (b'{', b'[]', b'null', b'{"source_base64":"private-secret"}'):
        request = exchange()
        request.chunks = [raw]
        result = await request.run(review.app)
        assert result.status == 422
        assert 'private-secret' not in json.dumps(result.payload)
        no_store(result)
    request = exchange()
    request.content_type = 'multipart/form-data'
    result = await request.run(review.app)
    assert result.status == 415 and result.reads == 0
    no_store(result)


@pytest.mark.asyncio
async def test_review_xlsx_and_profile_options(review):
    body = payload()
    body['format'] = 'xlsx'
    result = await exchange(body).run(review.app)
    assert result.status == 200 and review.runner.calls[-1][1:3] == ('xlsx', 'checklist')
    body['profile'] = 'other'
    result = await exchange(body).run(review.app)
    assert result.status == 422
    no_store(result)


@pytest.mark.asyncio
async def test_actual_five_mib_decoded_cap(review):
    body = payload()
    body['source_base64'] = base64.b64encode(b'x' * (5 * 1024 * 1024 + 1)).decode()
    result = await exchange(body).run(review.app)
    assert result.status == 413 and not review.runner.calls
    no_store(result)


@pytest.mark.asyncio
async def test_review_buffered_upload_deadline(review, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(review.module, 'monotonic', lambda: clock[0])
    request = exchange()
    original = request.receive

    async def receive():
        message = await original()
        clock[0] = 16.0
        return message

    request.receive = receive
    result = await request.run(review.app)
    assert result.status == 408 and not review.runner.calls
    no_store(result)


@pytest.mark.asyncio
async def test_review_quarantine_reuses_preview_admission(review, monkeypatch):
    monkeypatch.setattr(review.module, 'RUN_SECONDS', .01)
    monkeypatch.setattr(review.module, 'CLEANUP_SECONDS', .01)
    review.runner.block = review.runner.ignore_cancel = True
    result = await exchange().run(review.app)
    assert result.status == 503 and result.payload['code'] == 'cleanup_failed'
    no_store(result)
    pending = review.module._QUARANTINED_JOB
    assert pending is not None and not pending.done()
    rejected = await exchange().run(review.app)
    assert rejected.status == 503 and rejected.reads == 0
    rejected_preview = await Exchange().run(review.app)
    assert rejected_preview.status == 503 and rejected_preview.reads == 0
    review.runner.release.set()
    async with asyncio.timeout(2):
        while not pending.done():
            await asyncio.sleep(.005)
    monkeypatch.setattr(review.module, 'RUN_SECONDS', 1)
    assert (await exchange().run(review.app)).status == 200
    assert review.module._QUARANTINED_JOB is None
