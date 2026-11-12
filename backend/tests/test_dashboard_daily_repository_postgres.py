"""Disposable-only PostgreSQL draft: NOT executed by the offline writer.

Run this file alone through the existing attested disposable-target launcher.
No conftest database fixtures, default URL, dotenv or production data. Offline
SQL compilation is not evidence for PostgreSQL filtering, JSON or MVCC behavior.
"""
from uuid import uuid4

import pytest

from tests.test_migration_project_is_system_postgres import (
    disposable_url, migrate, new_schema_engine, seed_organization, seed_project,
    target_url,  # noqa: F401 -- explicit guarded fixture
)

disposable_url()  # refuse before application imports or engine construction


@pytest.mark.asyncio
async def test_daily_scoping_order_incoming_edges_and_admission(target_url):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import event, insert, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # Register the real User RBAC relationship and its FK targets before Task
    # construction configures the shared mapper registry (no app bootstrap).
    import app.modules.dependencies.models  # noqa: F401
    import app.modules.menus.models  # noqa: F401
    import app.modules.roles.models  # noqa: F401
    from app.modules.boards.models import Board, BoardColumn
    from app.modules.dashboard.daily_contracts import DailyContext
    from app.modules.dashboard.daily_repository import DailyRepository
    from app.modules.dashboard.daily_service import DailySummaryError
    from app.modules.task_links.models import TaskDependency
    from app.modules.tasks.models import Task
    from app.modules.users.models import User

    engine = await new_schema_engine(target_url)
    now = datetime(2026, 9, 5, 12, tzinfo=UTC)
    try:
        await migrate(engine, '0026')
        projects, boards, tasks = {}, {}, {}
        async with engine.begin() as connection:
            tenant = await seed_organization(connection)
            foreign = await seed_organization(connection)
            owner, other_user = uuid4(), uuid4()
            for user_id in (owner, other_user):
                await connection.execute(insert(User.__table__).values(
                    id=user_id, email=f'{user_id.hex}@example.invalid',
                    primer_nombre='Synthetic', primer_apellido='Person'))
            cases = ('normal', 'foreign', 'project_inactive', 'project_deleted',
                     'task_inactive', 'task_deleted', 'other_assignee', 'missing_board',
                     'board_inactive', 'board_deleted', 'column_inactive', 'column_deleted')
            for case in cases:
                project = await seed_project(
                    connection, foreign if case == 'foreign' else tenant,
                    code='DAILY' if case == 'normal' else None,
                    is_active=case != 'project_inactive',
                    deleted_at=now if case == 'project_deleted' else None)
                projects[case] = project
                if case != 'missing_board':
                    board = boards[case] = uuid4()
                    await connection.execute(insert(Board.__table__).values(
                        id=board, project_id=project, is_active=case != 'board_inactive',
                        deleted_at=now if case == 'board_deleted' else None))
                    # Reverse insertion; created_at resolves equal column_order.
                    for key, created in (('closed', now), ('open', now - timedelta(seconds=1))):
                        await connection.execute(insert(BoardColumn.__table__).values(
                            board_id=board, name='Not a status key', status_key=key,
                            column_order=1, created_at=created,
                            is_active=case != 'column_inactive',
                            deleted_at=now if case == 'column_deleted' else None))
                task_id = tasks[case] = uuid4()
                await connection.execute(insert(Task.__table__).values(
                    id=task_id, project_id=project, title='Synthetic task', status='open',
                    assignee_id=other_user if case == 'other_assignee' else owner,
                    due_date=now, task_number=7 if case == 'normal' else None,
                    completed_at=now if case == 'normal' else None,
                    is_active=case != 'task_inactive',
                    deleted_at=now if case == 'task_deleted' else None))
            # Only the other-assignee blocker is valid; both endpoint projects
            # must be tenant-scoped/live even for corrupted cross-project edges.
            for case in ('other_assignee', 'foreign', 'project_inactive', 'project_deleted',
                         'task_inactive', 'task_deleted'):
                await connection.execute(insert(TaskDependency.__table__).values(
                    organization_id=tenant, blocker_task_id=tasks[case], blocked_task_id=tasks['normal']))
            # Outgoing edge is not an incoming dependency for an assigned target.
            await connection.execute(insert(TaskDependency.__table__).values(
                organization_id=tenant, blocker_task_id=tasks['normal'], blocked_task_id=tasks['other_assignee']))
            for case, values in (
                ('missing_board', dict(organization_id=foreign)),
                ('board_inactive', dict(organization_id=tenant, is_active=False)),
                ('board_deleted', dict(organization_id=tenant, deleted_at=now)),
            ):
                await connection.execute(insert(TaskDependency.__table__).values(
                    blocker_task_id=tasks[case], blocked_task_id=tasks['normal'], **values))

        statements = []
        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        sessions = async_sessionmaker(engine, autoflush=True, expire_on_commit=False)
        context = DailyContext(tenant, owner)
        event.listen(engine.sync_engine, 'before_cursor_execute', record)
        try:
            async with sessions() as session:
                # A pending object must not be flushed by this read.
                session.add(Task(project_id=projects['normal'], title='Pending', status='open'))
                snapshot = await DailyRepository(session).assigned_daily_snapshot(
                    context, task_limit=100, edge_limit=100)
                assert session.new
                assert len(statements) == 1 and statements[0].lstrip().upper().startswith('WITH')
            assert len(statements) == 1
        finally:
            event.remove(engine.sync_engine, 'before_cursor_execute', record)
        visible = {'normal', 'missing_board', 'board_inactive', 'board_deleted', 'column_inactive', 'column_deleted'}
        assert {task.id for task in snapshot.tasks} == {tasks[case] for case in visible}
        assert len(snapshot.edges) == 1
        assert snapshot.edges[0].target_id == tasks['normal']
        assert snapshot.edges[0].blocker.id == tasks['other_assignee']
        assert snapshot.edges[0].blocker.assignee_id == other_user
        facts = {task.id: task for task in snapshot.tasks}
        assert facts[tasks['normal']].completed_at == now  # preserve conflicting facts
        assert facts[tasks['normal']].task_key == 'DAILY-7'
        assert facts[tasks['missing_board']].task_key is None
        for case in ('missing_board', 'board_inactive', 'board_deleted'):
            assert facts[tasks[case]].board_id is None
        statuses = {board.board_id: board.statuses for board in snapshot.boards}
        assert statuses[boards['normal']] == ('open', 'closed')
        assert statuses[boards['column_inactive']] == statuses[boards['column_deleted']] == ()
        async with sessions() as session:
            with pytest.raises(DailySummaryError, match='input_limit'):
                await DailyRepository(session).assigned_daily_snapshot(context, task_limit=1, edge_limit=100)
        # A second valid incoming edge exercises edge overflow independently.
        async with engine.begin() as connection:
            await connection.execute(insert(TaskDependency.__table__).values(
                organization_id=tenant, blocker_task_id=tasks['column_inactive'], blocked_task_id=tasks['normal']))
        async with sessions() as session:
            with pytest.raises(DailySummaryError, match='input_limit'):
                await DailyRepository(session).assigned_daily_snapshot(context, task_limit=100, edge_limit=1)
        # Canonical order ambiguity must fail, never invent a UUID order.
        async with engine.begin() as connection:
            await connection.execute(update(BoardColumn.__table__).where(
                BoardColumn.__table__.c.board_id == boards['normal']).values(created_at=now))
        async with sessions() as session:
            with pytest.raises(DailySummaryError, match='ambiguous_board_order'):
                await DailyRepository(session).assigned_daily_snapshot(context, task_limit=100, edge_limit=100)
    finally:
        await engine.dispose()
