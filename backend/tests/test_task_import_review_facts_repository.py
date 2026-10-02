"""Offline control flow and SQL shape only; not PostgreSQL execution evidence."""
from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.modules.task_import.review_facts_repository import (
    MAX_REVIEW_FACT_IDS, ReviewFactsInputError, ReviewFactsRepository,
)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class RecordingSession:
    def __init__(self, *results):
        self.results = iter(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return Result(result)


@pytest.mark.asyncio
async def test_snapshot_is_detached_immutable_and_exact_tenant():
    tenant, project, empty, user = (uuid4() for _ in range(4))
    rows = [(project, 'persisted'), (project, 'persisted'), (empty, None)]
    session = RecordingSession(rows, [(user,)])
    facts = await ReviewFactsRepository(session).load(
        str(tenant), [str(project), str(empty), str(project)], [str(user), str(user)],
    )
    rows.clear()
    assert facts.active_project(str(tenant), str(project)).supported_statuses == frozenset({'persisted'})
    assert facts.active_project(str(tenant), str(empty)).supported_statuses == frozenset()
    assert facts.active_member(str(tenant), str(user))
    for foreign in (str(uuid4()), str(tenant).upper(), ''):
        assert facts.active_project(foreign, str(project)) is None
        assert not facts.active_member(foreign, str(user))
    assert facts.active_project(str(tenant), str(uuid4())) is None
    assert not facts.active_member(str(tenant), str(uuid4()))
    with pytest.raises(FrozenInstanceError):
        facts.tenant_id = 'changed'
    with pytest.raises(TypeError):
        facts.projects[str(project)] = None
    with pytest.raises(FrozenInstanceError):
        facts.active_project(str(tenant), str(project)).project_id = 'changed'
    assert len(session.statements) == 2
    assert all(s.get_execution_options()['autoflush'] is False for s in session.statements)
    project_sql, user_sql = [str(s.compile(dialect=postgresql.dialect())) for s in session.statements]
    project_where = project_sql.split('WHERE')[1]
    assert 'LEFT OUTER JOIN boards ON' in project_sql
    assert 'LEFT OUTER JOIN board_columns ON' in project_sql
    for table in ('boards', 'board_columns'):
        assert f'{table}.is_active IS true' in project_sql.split('WHERE')[0]
        assert f'{table}.deleted_at IS NULL' in project_sql.split('WHERE')[0]
        assert f'{table}.' not in project_where
    for clause in ('projects.organization_id =', 'projects.id IN',
                   'projects.is_active IS true', 'projects.deleted_at IS NULL'):
        assert clause in project_where
    assert [c.name for c in session.statements[0].selected_columns] == ['id', 'status_key']
    assert [c.name for c in session.statements[1].selected_columns] == ['user_id']
    for clause in ('organization_members.organization_id =', 'organization_members.user_id IN',
                   'users.is_active IS true', 'users.deleted_at IS NULL'):
        assert clause in user_sql
    assert 'role' not in user_sql and 'organization_members.is_active' not in user_sql
    assert 'FOR UPDATE' not in project_sql + user_sql
    params = session.statements[0].compile().params
    assert tenant in params.values()
    assert set(next(v for v in params.values() if isinstance(v, list))) == {project, empty}


@pytest.mark.asyncio
@pytest.mark.parametrize('projects,users,count', [(False, False, 0), (True, False, 1), (False, True, 1)])
async def test_empty_inputs_skip_queries(projects, users, count):
    session = RecordingSession([], [])
    facts = await ReviewFactsRepository(session).load(
        str(uuid4()), [str(uuid4())] if projects else [], [str(uuid4())] if users else [],
    )
    assert len(session.statements) == count
    assert facts.projects == {} and facts.members == frozenset()


@pytest.mark.asyncio
@pytest.mark.parametrize('field', [0, 1])
async def test_limits_precede_deduplication_and_any_io(field):
    session = RecordingSession()
    inputs = [[], []]
    inputs[field] = ['private-input'] * (MAX_REVIEW_FACT_IDS + 1)
    with pytest.raises(ReviewFactsInputError) as error:
        await ReviewFactsRepository(session).load(str(uuid4()), *inputs)
    assert 'private-input' not in str(error.value)
    assert session.statements == []


@pytest.mark.asyncio
async def test_generator_rejected_without_consumption():
    def forbidden():
        raise AssertionError('must not iterate')
        yield
    session = RecordingSession()
    with pytest.raises(ReviewFactsInputError):
        await ReviewFactsRepository(session).load(str(uuid4()), forbidden(), [])
    assert not session.statements


@pytest.mark.asyncio
async def test_invalid_identifiers_fail_closed_and_limit_boundary_works():
    tenant, project = str(uuid4()), str(uuid4())
    session = RecordingSession([])
    facts = await ReviewFactsRepository(session).load(tenant, [project] * MAX_REVIEW_FACT_IDS, ['bad'])
    assert len(session.statements) == 1
    assert facts.active_project(tenant, project) is None
    assert not facts.active_member(tenant, 'bad')


@pytest.mark.asyncio
async def test_same_snapshot_drives_repeated_domain_review_without_io():
    from dataclasses import replace
    from app.modules.task_import.review_plan import TrustedContext, build_review_plan
    from tests.test_task_import_review_plan import fixture

    tenant, project, user = (uuid4() for _ in range(3))
    session = RecordingSession([(project, 'PENDIENTE')], [(user,)])
    snapshot = await ReviewFactsRepository(session).load(str(tenant), [str(project)], [str(user)])
    preview, request = fixture()
    request = replace(request, decisions=(replace(
        request.decisions[0], project_id=str(project), assignee_id=str(user),
    ),))
    context = TrustedContext(str(tenant), str(uuid4()))
    first = build_review_plan(preview, 'v1', request, context, snapshot)
    second = build_review_plan(preview, 'v1', request, context, snapshot)
    assert first == second
    assert first.status == 'validated_for_review'
    assert len(session.statements) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_index', [0, 1])
async def test_database_errors_propagate(failure_index):
    failure = SQLAlchemyError('synthetic')
    session = RecordingSession(*([[]] * failure_index + [failure]))
    with pytest.raises(SQLAlchemyError) as error:
        await ReviewFactsRepository(session).load(str(uuid4()), [str(uuid4())], [str(uuid4())])
    assert error.value is failure
