"""Disposable PostgreSQL characterization; execute separately via guarded launcher.

Only synthetic fixtures, committed before repository reads. No ORM entities are
constructed: Core tables avoid global relationship mapper configuration. The
real migration chain creates foreign-key targets. Container cleanup belongs to
the parent launcher; this module neither starts services nor drops schemas.
"""
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.test_migration_project_is_system_postgres import (
    disposable_url, migrate, new_schema_engine, seed_organization, seed_project,
    target_url,  # noqa: F401 -- disables dotenv before application imports
)

# The inherited guard also runs on import, before SQLAlchemy/application imports.
disposable_url()


@asynccontextmanager
async def database(url):
    engine = await new_schema_engine(url)
    try:
        await migrate(engine, '0026')
        yield engine
    finally:
        await engine.dispose()


async def seed_member(connection, tenant, *, first='Synthetic', last='Person',
                      membership=True, **changes):
    from sqlalchemy import insert

    from app.modules.organizations.models import OrganizationMember
    from app.modules.users.models import User

    user = uuid4()
    await connection.execute(insert(User.__table__).values(
        id=user, email=f'{user.hex}@example.invalid', primer_nombre=first,
        primer_apellido=last, **changes,
    ))
    if membership:
        await connection.execute(insert(OrganizationMember.__table__).values(
            organization_id=tenant, user_id=user, role='viewer',
        ))
    return user


async def load(engine, tenant, **query):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.modules.task_import.options_repository import OptionsRepository
    from app.modules.task_import.schemas import OptionsQuery

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        return await OptionsRepository(session).load(str(tenant), OptionsQuery(**query))


def ids(page):
    return [item.id for item in page.items]


@pytest.mark.asyncio
async def test_tenant_lifecycle_and_canonical_default(target_url):
    async with database(target_url) as engine:
        async with engine.begin() as connection:
            tenant = await seed_organization(connection)
            other = await seed_organization(connection)
            canonical = await seed_project(
                connection, tenant, name='Renamed default', code='GENERALES',
                is_system=True, methodology='custom', status='active',
            )
            # Name is not identity; lifecycle status alone does not exclude an
            # ordinary active/nondeleted project from the options list.
            ordinary = []
            for status in ('active', 'archived'):
                ordinary.append(await seed_project(
                    connection, tenant, name='Generales', code=None,
                    methodology='scrum', status=status,
                ))
            await seed_project(connection, other, code='GENERALES', is_system=True,
                               methodology='custom', name='Foreign default')
            await seed_project(connection, tenant, code=None, is_active=False)
            await seed_project(connection, tenant, code=None,
                               deleted_at=datetime(2020, 1, 1, tzinfo=UTC))
            member = await seed_member(connection, tenant, first='Ada', last='Example')
            await seed_member(connection, other)
            await seed_member(connection, tenant, is_active=False)
            await seed_member(connection, tenant, deleted_at=datetime(2020, 1, 1, tzinfo=UTC))
            await seed_member(connection, tenant, membership=False)
        result = await load(engine, tenant)
        assert result is not None
        assert set(ids(result.projects)) == {str(canonical), *(str(p) for p in ordinary)}
        assert result.projects.meta.total == 3
        assert ids(result.members) == [str(member)]
        assert result.members.meta.total == 1
        assert result.members.items[0].label == 'Ada Example'
        assert result.default_project.id == str(canonical)
        assert result.default_project.label == 'Renamed default'

        # A code/name/shape match without the marker is never a default. Invalid
        # marked shapes cannot be inserted under 0026's real CHECK constraint.
        from sqlalchemy import text

        async with engine.begin() as connection:
            await connection.execute(text('UPDATE projects SET is_system=false WHERE id=:id'),
                                     {'id': canonical})
        unmarked = await load(engine, tenant)
        assert unmarked.default_project is None
        assert set(ids(unmarked.projects)) == set(ids(result.projects))


@pytest.mark.asyncio
async def test_ineligible_organization_returns_no_labels(target_url):
    from sqlalchemy import event, text

    async with database(target_url) as engine:
        async with engine.begin() as connection:
            inactive = await seed_organization(connection)
            deleted = await seed_organization(connection)
            for tenant in (inactive, deleted):
                await seed_project(connection, tenant, code=None, name='Must not leak')
                await seed_member(connection, tenant, first='Must not', last='Leak')
            await connection.execute(text('UPDATE organizations SET is_active=false WHERE id=:id'),
                                     {'id': inactive})
            await connection.execute(text('UPDATE organizations SET deleted_at=:date WHERE id=:id'),
                                     {'id': deleted, 'date': datetime(2020, 1, 1, tzinfo=UTC)})
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine.sync_engine, 'before_cursor_execute', record)
        try:
            for tenant in (inactive, deleted, uuid4()):
                statements.clear()
                assert await load(engine, tenant) is None
                assert len(statements) == 1
                assert statements[0].lstrip().upper().startswith('SELECT')
                assert 'organizations' in statements[0]
                assert 'projects' not in statements[0] and 'users' not in statements[0]
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', record)


@pytest.mark.asyncio
async def test_independent_counts_pages_stable_ties_and_default(target_url):
    async with database(target_url) as engine:
        async with engine.begin() as connection:
            tenant = await seed_organization(connection)
            canonical = await seed_project(connection, tenant, code='GENERALES',
                                           is_system=True, methodology='custom', name='Zulu default')
            projects = [await seed_project(connection, tenant, code=None, name='Tie')
                        for _ in range(3)]
            members = [await seed_member(connection, tenant, first='Tie', last='Person')
                       for _ in range(4)]
        ordered_projects = sorted(str(p) for p in projects)
        ordered_members = sorted(str(m) for m in members)
        first = await load(engine, tenant, projects_size=2, members_page=2, members_size=1)
        assert ids(first.projects) == ordered_projects[:2]
        assert first.projects.meta.model_dump() == {'page': 1, 'size': 2, 'total': 4}
        assert ids(first.members) == ordered_members[1:2]
        assert first.members.meta.model_dump() == {'page': 2, 'size': 1, 'total': 4}
        second = await load(engine, tenant, projects_page=2, projects_size=2, members_size=3)
        assert ids(second.projects) == ordered_projects[2:] + [str(canonical)]
        assert ids(second.members) == ordered_members[:3]
        repeated = await load(engine, tenant, projects_size=2, members_page=2, members_size=1)
        assert repeated == first
        filtered = await load(engine, tenant, projects_q='tie', projects_page=2,
                              projects_size=2, members_q='absent')
        assert ids(filtered.projects) == ordered_projects[2:]
        assert filtered.projects.meta.total == 3
        assert filtered.members.items == [] and filtered.members.meta.total == 0
        beyond = await load(engine, tenant, projects_page=99, members_page=99)
        assert beyond.projects.items == [] and beyond.projects.meta.total == 4
        assert beyond.members.items == [] and beyond.members.meta.total == 4
        for result in (first, second, filtered, beyond):
            assert result.default_project.id == str(canonical)
            assert result.default_project.label == 'Zulu default'


@pytest.mark.asyncio
@pytest.mark.parametrize(('needle', 'literal', 'decoy'), [
    ('a%', 'a%literal', 'axliteral'),
    ('a_', 'a_literal', 'axliteral'),
    ('a\\', r'a\literal', 'aliteral'),
])
async def test_literal_search_never_expands_wildcards(target_url, needle, literal, decoy):
    async with database(target_url) as engine:
        async with engine.begin() as connection:
            tenant = await seed_organization(connection)
            project = await seed_project(connection, tenant, code=None, name=literal)
            await seed_project(connection, tenant, code=None, name=decoy)
            member = await seed_member(connection, tenant, first=literal, last='Person')
            await seed_member(connection, tenant, first=decoy, last='Person')
        result = await load(engine, tenant, projects_q=needle.upper(), members_q=needle.upper())
        assert ids(result.projects) == [str(project)]
        assert result.projects.items[0].label == literal
        assert result.projects.meta.total == 1
        assert ids(result.members) == [str(member)]
        assert result.members.items[0].label == literal + ' Person'
        assert result.members.meta.total == 1
        assert result.default_project is None
        project_only = await load(engine, tenant, projects_q=needle)
        assert ids(project_only.projects) == [str(project)]
        assert project_only.members.meta.total == 2
        member_only = await load(engine, tenant, members_q=needle)
        assert ids(member_only.members) == [str(member)]
        assert member_only.projects.meta.total == 2
