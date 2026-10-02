"""Offline SQL-expression snapshots/control flow, NOT real PostgreSQL proof."""
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def first(self):
        return self.value

    def all(self):
        return self.value


class Session:
    """Only execute is supported: writes, locks, transaction completion are forbidden."""
    def __init__(self, *values):
        self.values = iter(values)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return Result(value)


def adapter():
    from app.modules.task_import.options_repository import OptionsRepository
    from app.modules.task_import.schemas import OptionsQuery
    return OptionsRepository, OptionsQuery


def sql(statement):
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_scalar_projection_pagination_counts_default_and_tenant_snapshots():
    Repository, Query = adapter()
    tenant, project, user, default = (uuid4() for _ in range(4))
    session = Session(tenant, 25, [(project, 'Proyecto')], 31, [(user, 'Ana Pérez')], (default, 'Generales'))
    result = await Repository(session).load(str(tenant), Query(projects_page=2, projects_size=3,
                                                              members_page=3, members_size=4))
    assert result.model_dump() == {
        'projects': {'items': [{'id': str(project), 'label': 'Proyecto'}],
                     'meta': {'page': 2, 'size': 3, 'total': 25}},
        'members': {'items': [{'id': str(user), 'label': 'Ana Pérez'}],
                    'meta': {'page': 3, 'size': 4, 'total': 31}},
        'default_project': {'id': str(default), 'label': 'Generales'},
    }
    gate, pc, pp, mc, mp, dp = session.statements
    assert len(session.statements) == 6
    for statement in session.statements:
        text = sql(statement)
        assert statement.get_execution_options()['autoflush'] is False
        assert statement.is_select and 'FOR UPDATE' not in text
        assert tenant in statement.compile().params.values()
        assert not any(secret in text for secret in ('email', 'numero_documento', 'hashed_password', 'roles', 'segundo_nombre', 'segundo_apellido'))
    assert [c.name for c in gate.selected_columns] == ['id']
    for clause in ('organizations.id =', 'organizations.is_active IS true', 'organizations.deleted_at IS NULL'):
        assert clause in sql(gate)
    for count, page, table in ((pc, pp, 'projects'), (mc, mp, 'organization_members')):
        assert sql(count).split('WHERE')[1] == sql(page).split('WHERE')[1].split(' ORDER BY')[0]
        assert f'{table}.organization_id =' in sql(page)
        assert ' LIMIT ' in sql(page) and ' OFFSET ' in sql(page)
        assert ' LIMIT ' not in sql(count) and ' OFFSET ' not in sql(count)
    assert pp._limit_clause.value == 3 and pp._offset_clause.value == 3
    assert mp._limit_clause.value == 4 and mp._offset_clause.value == 8
    assert [c.name for c in pp.selected_columns] == ['id', 'label']
    assert [c.name for c in mp.selected_columns] == ['id', 'label']
    assert 'ORDER BY label, projects.id' in sql(pp)
    assert 'ORDER BY label, users.id' in sql(mp)
    assert 'JOIN users ON users.id = organization_members.user_id' in sql(mp)
    assert 'users.primer_nombre' in sql(mp) and 'users.primer_apellido' in sql(mp)
    assert 'trim(concat(coalesce(' in sql(mp)
    for statement in (pc, pp):
        assert 'projects.is_active IS true' in sql(statement)
        assert 'projects.deleted_at IS NULL' in sql(statement)
        assert 'projects.status' not in sql(statement) and 'projects.methodology' not in sql(statement)
    for statement in (mc, mp):
        assert 'users.is_active IS true' in sql(statement) and 'users.deleted_at IS NULL' in sql(statement)
        assert 'organization_members.is_active' not in sql(statement)
    for clause in ('projects.is_system IS true', 'projects.code =', 'projects.status =',
                   'projects.methodology =', 'projects.is_active IS true', 'projects.deleted_at IS NULL'):
        assert clause in sql(dp)
    assert {'GENERALES', 'active', 'custom'} <= {
        getattr(v, 'value', str(v)) for v in dp.compile().params.values()
    }
    assert dp._limit_clause.value == 1


@pytest.mark.asyncio
async def test_literal_bound_search_same_count_predicates_and_unfiltered_default():
    Repository, Query = adapter()
    tenant = uuid4()
    session = Session(tenant, 0, [], 0, [], None)
    result = await Repository(session).load(str(tenant), Query(projects_q=r'a%_\b', members_q='Ana', projects_page=1000))
    assert result.default_project is None and result.projects.items == [] and result.members.items == []
    gate, pc, pp, mc, mp, dp = session.statements
    for statement in (pc, pp):
        assert ' ILIKE ' in sql(statement) and ' ESCAPE ' in sql(statement)
        assert '%a\\%\\_\\\\b%' in statement.compile().params.values()
        assert r'a%_\b' not in sql(statement)
    for statement in (mc, mp):
        assert '%Ana%' in statement.compile().params.values()
        assert ' ILIKE ' in sql(statement)
    assert ' ILIKE ' not in sql(dp) and dp._offset_clause is None
    assert sql(pc).split('WHERE')[1] == sql(pp).split('WHERE')[1].split(' ORDER BY')[0]
    assert sql(mc).split('WHERE')[1] == sql(mp).split('WHERE')[1].split(' ORDER BY')[0]


@pytest.mark.asyncio
async def test_ineligible_organization_returns_before_any_labels():
    Repository, Query = adapter()
    session = Session(None)
    assert await Repository(session).load(str(uuid4()), Query()) is None
    assert len(session.statements) == 1
    assert 'projects' not in sql(session.statements[0]) and 'users' not in sql(session.statements[0])


@pytest.mark.asyncio
async def test_empty_search_still_explicitly_paginated_and_no_fallback_default():
    Repository, Query = adapter()
    session = Session(uuid4(), 0, [], 0, [], None)
    result = await Repository(session).load(str(uuid4()), Query())
    assert result.default_project is None
    for index in (2, 4):
        statement = session.statements[index]
        assert statement._limit_clause.value == 20 and statement._offset_clause.value == 0
        assert ' ILIKE ' not in sql(statement)
    assert result.projects.meta.total == result.members.meta.total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('index', range(6))
async def test_query_failure_never_proceeds(index):
    Repository, Query = adapter()
    error = RuntimeError('synthetic')
    values = [uuid4(), 0, [], 0, [], None]
    values[index] = error
    session = Session(*values)
    with pytest.raises(RuntimeError) as caught:
        await Repository(session).load(str(uuid4()), Query())
    assert caught.value is error and len(session.statements) == index + 1
