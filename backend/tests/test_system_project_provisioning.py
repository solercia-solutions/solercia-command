"""Offline orchestration and SQL construction checks, not PostgreSQL proof."""
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.modules.projects.system_project import GENERALES
from app.modules.projects.system_project_ports import ProjectSnapshot, BoardSnapshot, ColumnSnapshot
from app.modules.projects.system_project_provisioning import ensure_generales, SystemProjectConflict, InvalidSystemOrganization
from app.modules.projects.system_project_repository import SystemProjectRepository


ORG, ACTOR, PARENT = uuid4(), uuid4(), uuid4()


def snapshot():
    return ProjectSnapshot(uuid4(), ORG, 'GENERALES', True, 'custom', 'active', True, None)


def board():
    return BoardSnapshot(True, None, tuple(ColumnSnapshot(s, s, i, True, None) for i, s in enumerate(GENERALES.statuses)))


class Port:
    def __init__(self, project=None, structure=None, valid=True):
        self.project, self.structure, self.valid = project, structure, valid
        self.calls = []

    async def lock_organization(self, org):
        self.calls.append(('lock', org))
        return self.valid

    async def find_reserved(self, org):
        self.calls.append(('lookup', org))
        return self.project

    async def read_board(self, org, project):
        self.calls.append(('board', org, project))
        return self.structure

    async def create_generales(self, org, actor, parent):
        self.calls.append(('create', org, actor, parent))
        self.project, self.structure = snapshot(), board()
        return self.project


@pytest.mark.asyncio
async def test_create_then_reuse_and_explicit_parent():
    port = Port()
    first = await ensure_generales(port, organization_id=ORG, actor_id=ACTOR, parent_id=PARENT)
    second = await ensure_generales(port, organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert first == second
    assert port.calls == [('lock', ORG), ('lookup', ORG), ('create', ORG, ACTOR, PARENT), ('lock', ORG), ('lookup', ORG), ('board', ORG, first.id)]
    with pytest.raises(TypeError):
        await ensure_generales(port, organization_id=ORG, actor_id=ACTOR)


@pytest.mark.asyncio
async def test_invalid_org_stops_before_lookup():
    port = Port(valid=False)
    with pytest.raises(InvalidSystemOrganization):
        await ensure_generales(port, organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert port.calls == [('lock', ORG)]


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [dict(organization_id=uuid4()), dict(code='generales'), dict(is_system=False), dict(methodology='kanban'), dict(status='archived'), dict(is_active=False), dict(deleted_at='deleted')])
async def test_conflicting_project_never_repaired(changes):
    port = Port(replace(snapshot(), **changes), board())
    with pytest.raises(SystemProjectConflict):
        await ensure_generales(port, organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert [c[0] for c in port.calls] == ['lock', 'lookup']


@pytest.mark.asyncio
@pytest.mark.parametrize('structure', [None, replace(board(), is_active=False), replace(board(), deleted_at='deleted'), replace(board(), columns=board().columns[:-1]), replace(board(), columns=board().columns + board().columns[:1]), replace(board(), columns=(replace(board().columns[0], name='Wrong'),) + board().columns[1:]), replace(board(), columns=(replace(board().columns[0], status_key='Wrong'),) + board().columns[1:]), replace(board(), columns=(replace(board().columns[0], order=1),) + board().columns[1:]), replace(board(), columns=(replace(board().columns[0], is_active=False),) + board().columns[1:]), replace(board(), columns=(replace(board().columns[0], deleted_at='deleted'),) + board().columns[1:])])
async def test_malformed_board_is_conflict(structure):
    port = Port(snapshot(), structure)
    with pytest.raises(SystemProjectConflict):
        await ensure_generales(port, organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert not any(c[0] == 'create' for c in port.calls)


class Result:
    def __init__(self, value):
        self.value = value
    def scalar_one_or_none(self):
        return self.value
    def scalars(self):
        return self
    def all(self):
        return self.value


class Session:
    """No transaction lifecycle methods: invoking one fails the test."""
    def __init__(self, results=(), fail_flush=None):
        self.results = iter(results)
        self.events, self.rows, self.sql = [], [], []
        self.flushes, self.fail_flush = 0, fail_flush
    async def execute(self, statement):
        if not self.sql:
            self.first_execution_options = statement.get_execution_options()
        self.sql.append(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})))
        self.events.append('select')
        return Result(next(self.results))
    def add(self, row):
        self.rows.append(row)
        self.events.append(type(row).__name__)
        row.id = uuid4()
    async def flush(self):
        self.events.append('flush')
        self.flushes += 1
        if self.flushes == self.fail_flush:
            raise RuntimeError('injected')


@pytest.mark.asyncio
async def test_adapter_creation_order_fields_and_tenant_sql():
    session = Session([ORG, None])
    result = await ensure_generales(SystemProjectRepository(session), organization_id=ORG, actor_id=ACTOR, parent_id=PARENT)
    assert session.events == ['select', 'select', 'Project', 'flush', 'Board', 'flush'] + ['BoardColumn'] * 7 + ['flush']
    project, persisted_board, *columns = session.rows
    assert result.id == project.id
    assert project.organization_id == ORG and project.parent_project_id == PARENT
    assert project.project_kind == 'proyecto' and project.lead_user_id is None
    assert project.name == 'Generales' and project.is_system is True
    assert persisted_board.project_id == project.id
    assert [(c.name, c.status_key, c.order) for c in columns] == [(s, s, i) for i, s in enumerate(GENERALES.statuses)]
    assert all(c.board_id == persisted_board.id for c in columns)
    assert all(r.created_by == ACTOR and r.updated_by == ACTOR for r in session.rows)
    assert session.first_execution_options['autoflush'] is False
    assert 'FOR UPDATE' in session.sql[0] and str(ORG) in session.sql[0]
    assert 'organizations.is_active IS true' in session.sql[0] and 'organizations.deleted_at IS NULL' in session.sql[0]
    where = session.sql[1].split('WHERE')[1]
    assert str(ORG) in where and "projects.code = 'GENERALES'" in where
    assert 'is_active' not in where and 'deleted_at' not in where


@pytest.mark.asyncio
@pytest.mark.parametrize('stage', [1, 2, 3])
async def test_flush_failure_propagates_without_transaction_ownership(stage):
    session = Session([ORG, None], fail_flush=stage)
    with pytest.raises(RuntimeError, match='injected'):
        await ensure_generales(SystemProjectRepository(session), organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert session.flushes == stage


@pytest.mark.asyncio
async def test_board_queries_tenant_scoped_and_include_inactive():
    from app.modules.boards.models import Board
    persisted = Board(id=uuid4(), project_id=uuid4(), is_active=True, deleted_at=None)
    session = Session([persisted, []])
    structure = await SystemProjectRepository(session).read_board(ORG, persisted.project_id)
    assert structure.columns == ()
    for sql in session.sql:
        where = sql.split('WHERE')[1]
        assert str(ORG) in where and str(persisted.project_id) in where
        assert 'is_active' not in where and 'deleted_at' not in where
    assert str(persisted.id) in session.sql[1]


@pytest.mark.asyncio
async def test_adapter_reuses_without_mutating_hierarchy():
    session = Session([ORG, None])
    repository = SystemProjectRepository(session)
    first = await ensure_generales(repository, organization_id=ORG, actor_id=ACTOR, parent_id=PARENT)
    project, persisted_board, *columns = session.rows
    session.results = iter([ORG, project, persisted_board, columns])
    session.events.clear()
    second = await ensure_generales(repository, organization_id=ORG, actor_id=ACTOR, parent_id=None)
    assert first == second and project.parent_project_id == PARENT
    assert session.events == ['select'] * 4
    assert len(session.rows) == 9


@pytest.mark.asyncio
@pytest.mark.parametrize('known', [True, False])
async def test_constraint_errors_do_not_rollback_or_expose_details(known):
    from types import SimpleNamespace
    from sqlalchemy.exc import IntegrityError

    original = Exception('private database detail')
    original.diag = SimpleNamespace(constraint_name='uq_project_code_per_org' if known else 'other')
    error = IntegrityError('insert', {}, original)

    class FailingSession(Session):
        async def flush(self):
            raise error

    session = FailingSession([ORG, None])
    with pytest.raises(SystemProjectConflict if known else IntegrityError) as caught:
        await ensure_generales(SystemProjectRepository(session), organization_id=ORG, actor_id=ACTOR, parent_id=None)
    if known:
        assert 'private' not in str(caught.value)
        assert caught.value.code == 'system_project_conflict'
    assert session.events == ['select', 'select', 'Project']
