"""Guarded disposable PostgreSQL contract; run separately with the existing launcher.

Never request conftest's database fixtures. This file is authored but must not be
executed by the offline writer. SQL filtering remains pending until it runs.
"""
from uuid import uuid4

import pytest

from tests.test_migration_project_is_system_postgres import (
    disposable_url, migrate, new_schema_engine, seed_organization, seed_project,
    target_url,  # noqa: F401 -- guarded fixture, disables dotenv before app imports
)

# Refuse before any application import or engine construction.
disposable_url()


@pytest.mark.asyncio
async def test_persisted_lifecycle_membership_and_detached_snapshot(target_url):
    from datetime import UTC, datetime

    from sqlalchemy import event, insert, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.modules.boards.models import Board, BoardColumn
    from app.modules.organizations.models import OrganizationMember
    from app.modules.task_import.review_facts_repository import ReviewFactsRepository
    from app.modules.users.models import User

    engine = await new_schema_engine(target_url)
    try:
        await migrate(engine, '0026')
        projects = {}
        users = {}
        columns = {}
        async with engine.begin() as connection:
            tenant = await seed_organization(connection)
            other = await seed_organization(connection)
            for case in ('usable', 'foreign', 'project_inactive', 'project_deleted',
                         'board_inactive', 'board_deleted', 'column_inactive',
                         'column_deleted', 'missing_board', 'empty_board'):
                project = await seed_project(
                    connection, other if case == 'foreign' else tenant,
                    code=None, is_active=case != 'project_inactive',
                    deleted_at=datetime(2020, 1, 1, tzinfo=UTC) if case == 'project_deleted' else None,
                )
                projects[case] = project
                if case == 'missing_board':
                    continue
                board = uuid4()
                await connection.execute(insert(Board.__table__).values(
                    id=board, project_id=project, is_active=case != 'board_inactive',
                    deleted_at=datetime(2020, 1, 1, tzinfo=UTC) if case == 'board_deleted' else None,
                ))
                if case == 'empty_board':
                    continue
                column = uuid4()
                columns[case] = column
                await connection.execute(insert(BoardColumn.__table__).values(
                    id=column, board_id=board, name='Not the status', status_key='persisted_only',
                    is_active=case != 'column_inactive',
                    deleted_at=datetime(2020, 1, 1, tzinfo=UTC) if case == 'column_deleted' else None,
                ))
            for case in ('member', 'foreign', 'inactive', 'deleted', 'no_membership'):
                user = uuid4()
                users[case] = user
                await connection.execute(insert(User.__table__).values(
                    id=user, email=f'{user.hex}@example.invalid',
                    primer_nombre='Synthetic', primer_apellido='Person',
                    is_active=case != 'inactive',
                    deleted_at=datetime(2020, 1, 1, tzinfo=UTC) if case == 'deleted' else None,
                ))
                if case != 'no_membership':
                    await connection.execute(insert(OrganizationMember.__table__).values(
                        organization_id=other if case == 'foreign' else tenant,
                        user_id=user, role='viewer',
                    ))
        sessions = async_sessionmaker(engine, autoflush=True, expire_on_commit=False)
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        requested_projects = [str(p) for p in projects.values()] + [str(uuid4())]
        requested_users = [str(u) for u in users.values()] + [str(uuid4())]
        event.listen(engine.sync_engine, 'before_cursor_execute', record)
        try:
            async with sessions() as session:
                facts = await ReviewFactsRepository(session).load(
                    str(tenant), requested_projects * 2, requested_users * 2,
                )
            assert len(statements) == 2
            assert all(sql.lstrip().upper().startswith('SELECT') for sql in statements)
            for case, project in projects.items():
                fact = facts.active_project(str(tenant), str(project))
                if case in ('foreign', 'project_inactive', 'project_deleted'):
                    assert fact is None
                else:
                    assert fact is not None
                    assert fact.supported_statuses == (
                        frozenset({'persisted_only'}) if case == 'usable' else frozenset()
                    )
                assert facts.active_project(str(other), str(project)) is None
            for case, user in users.items():
                assert facts.active_member(str(tenant), str(user)) == (case == 'member')
                assert not facts.active_member(str(other), str(user))
            assert facts.active_project(str(tenant), requested_projects[-1]) is None
            assert not facts.active_member(str(tenant), requested_users[-1])
            assert len(statements) == 2  # no synchronous database reads after session close
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', record)

        async with engine.begin() as connection:
            await connection.execute(update(BoardColumn.__table__).where(
                BoardColumn.__table__.c.id == columns['usable'],
            ).values(status_key='changed_status'))
            await connection.execute(update(User.__table__).where(
                User.__table__.c.id == users['member'],
            ).values(is_active=False))
        async with sessions() as session:
            fresh = await ReviewFactsRepository(session).load(
                str(tenant), requested_projects, requested_users,
            )
        assert facts.active_project(str(tenant), str(projects['usable'])).supported_statuses == frozenset({'persisted_only'})
        assert fresh.active_project(str(tenant), str(projects['usable'])).supported_statuses == frozenset({'changed_status'})
        assert facts.active_member(str(tenant), str(users['member']))
        assert not fresh.active_member(str(tenant), str(users['member']))
    finally:
        await engine.dispose()
