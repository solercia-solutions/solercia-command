"""Real committed transactions on explicitly attested disposable PostgreSQL.

Uses only the two-file test support, never shared conftest engine/session/client
fixtures, application main/lifespan, db_init, or provider registries. Run in a
fresh process separately from the baseline and migration characterization file.
See test_migration_project_is_system_postgres.py for the launcher env contract.
"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from tests.test_migration_project_is_system_postgres import (
    disposable_url,
    migrate,
    new_schema_engine,
    seed_organization,
    seed_project,
    target_url,  # noqa: F401 -- explicitly imported pytest fixture
)

# Shared support refuses before any application import, also when collected alone.
disposable_url()


@asynccontextmanager
async def provision_database(url):
    """New schema for each case, migrated rather than populated with create_all."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # Only model registration needed for mapper FK/relationship resolution.
    import app.modules.dependencies.models  # noqa: F401
    import app.modules.menus.models  # noqa: F401
    import app.modules.roles.models  # noqa: F401
    import app.modules.users.models  # noqa: F401
    from app.modules.projects.system_project_provisioning import ensure_generales
    from app.modules.projects.system_project_repository import SystemProjectRepository

    engine = await new_schema_engine(url)
    try:
        await migrate(engine, "0026")
        async with engine.begin() as connection:
            org_a = await seed_organization(connection)
            org_b = await seed_organization(connection)
            actor = uuid4()
            await connection.execute(text(
                "INSERT INTO users (id, email, primer_nombre, primer_apellido, is_active) "
                "VALUES (:id, :email, 'Synthetic', 'Actor', true)"
            ), {"id": actor, "email": f"{actor.hex}@example.invalid"})
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        yield engine, factory, org_a, org_b, actor, ensure_generales, SystemProjectRepository
    finally:
        await engine.dispose()


async def counts(connection, organization_id):
    from sqlalchemy import text

    return tuple((await connection.execute(text("""
        SELECT
          (SELECT count(*) FROM projects WHERE organization_id=:org),
          (SELECT count(*) FROM boards b JOIN projects p ON p.id=b.project_id
           WHERE p.organization_id=:org),
          (SELECT count(*) FROM board_columns c JOIN boards b ON b.id=c.board_id
           JOIN projects p ON p.id=b.project_id WHERE p.organization_id=:org)
    """), {"org": organization_id})).one())


@pytest.mark.asyncio
async def test_create_reuse_seven_columns_and_tenant_isolation(target_url):
    from sqlalchemy import text

    async with provision_database(target_url) as data:
        engine, sessions, org_a, org_b, actor, ensure, repository = data
        async with sessions.begin() as session:
            a = await ensure(repository(session), organization_id=org_a,
                             actor_id=actor, parent_id=None)
        async with sessions.begin() as session:
            reused = await ensure(repository(session), organization_id=org_a,
                                  actor_id=actor, parent_id=None)
        async with sessions.begin() as session:
            b = await ensure(repository(session), organization_id=org_b,
                             actor_id=actor, parent_id=None)
        assert reused.id == a.id != b.id
        async with sessions.begin() as session:
            assert await repository(session).read_board(org_b, a.id) is None
            assert await repository(session).read_board(org_a, b.id) is None
            assert (await repository(session).find_reserved(org_a)).id == a.id
            assert (await repository(session).find_reserved(org_b)).id == b.id
        async with engine.connect() as connection:
            assert await counts(connection, org_a) == (1, 1, 7)
            assert await counts(connection, org_b) == (1, 1, 7)
            rows = (await connection.execute(text("""
                SELECT c.name, c.status_key, c.column_order, c.created_by, c.updated_by,
                       c.is_active, c.deleted_at, c.wip_limit
                FROM board_columns c JOIN boards b ON b.id=c.board_id
                WHERE b.project_id=:id ORDER BY c.column_order
            """), {"id": a.id})).all()
            expected = ("PENDIENTE", "EN CURSO", "DIFERIDA", "RECURRENTE",
                        "GESTIONADA APARTE", "REMOVIDA", "COMPLETADA")
            assert [tuple(row) for row in rows] == [
                (status, status, index, actor, actor, True, None, None)
                for index, status in enumerate(expected)
            ]
            for table in ("projects", "boards"):
                key = "id" if table == "projects" else "project_id"
                audit = (await connection.execute(text(
                    f"SELECT created_by, updated_by, is_active, deleted_at FROM {table} WHERE {key}=:id"
                ), {"id": a.id})).one()
                assert tuple(audit) == (actor, actor, True, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("inactive", [False, True], ids=["ordinary", "inactive-ordinary"])
async def test_reserved_ordinary_collision_is_not_taken_over(target_url, inactive):
    from sqlalchemy import text

    from app.modules.projects.system_project_provisioning import SystemProjectConflict

    async with provision_database(target_url) as data:
        engine, sessions, org, _, actor, ensure, repository = data
        async with engine.begin() as connection:
            await seed_project(connection, org, code="GENERALES", is_active=not inactive)
            original = await connection.scalar(text("SELECT to_jsonb(p) FROM projects p"))
        with pytest.raises(SystemProjectConflict):
            async with sessions.begin() as session:
                await ensure(repository(session), organization_id=org, actor_id=actor, parent_id=None)
        async with engine.connect() as connection:
            assert await counts(connection, org) == (1, 0, 0)
            assert await connection.scalar(text("SELECT to_jsonb(p) FROM projects p")) == original


@pytest.mark.asyncio
async def test_inactive_board_conflict_does_not_repair(target_url):
    from sqlalchemy import text

    from app.modules.projects.system_project_provisioning import SystemProjectConflict

    async with provision_database(target_url) as data:
        engine, sessions, org, _, actor, ensure, repository = data
        async with sessions.begin() as session:
            project = await ensure(repository(session), organization_id=org,
                                   actor_id=actor, parent_id=None)
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE boards SET is_active=false WHERE project_id=:id"),
                                     {"id": project.id})
        with pytest.raises(SystemProjectConflict):
            async with sessions.begin() as session:
                await ensure(repository(session), organization_id=org, actor_id=actor, parent_id=None)
        async with engine.connect() as connection:
            assert await counts(connection, org) == (1, 1, 7)
            assert await connection.scalar(text("SELECT is_active FROM boards")) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", [1, 2, 3], ids=["project", "board", "columns"])
async def test_real_flush_failure_rolls_back_entire_provision(target_url, stage):
    from sqlalchemy.exc import IntegrityError

    async with provision_database(target_url) as data:
        engine, sessions, org, _, actor, ensure, repository = data
        from app.modules.projects.models import Project

        observed = []

        class FailingRepository(repository):
            flushes = 0

            async def _flush(self):
                await super()._flush()
                self.flushes += 1
                if self.flushes == stage:
                    observed.append(await counts(self.session, org))
                    # Real NOT NULL violation in a subsequent ORM flush, after
                    # the requested stage was actually sent to PostgreSQL.
                    self.session.add(Project(
                        organization_id=org, name=None, code="BROKEN",
                        methodology="kanban", status="active", is_system=False,
                    ))
                    await self.session.flush()

        with pytest.raises(IntegrityError) as error:
            async with sessions.begin() as session:
                await ensure(FailingRepository(session), organization_id=org,
                             actor_id=actor, parent_id=None)
        assert error.value.orig.__cause__.sqlstate == "23502"
        assert observed == [{1: (1, 0, 0), 2: (1, 1, 0), 3: (1, 1, 7)}[stage]]
        # A fresh connection sees committed state, not this session's identity map.
        async with engine.connect() as connection:
            assert await counts(connection, org) == (0, 0, 0)
        async with sessions.begin() as session:
            await ensure(repository(session), organization_id=org, actor_id=actor, parent_id=None)
        async with engine.connect() as connection:
            assert await counts(connection, org) == (1, 1, 7)


async def bootstrap_counts(connection):
    """Whole-schema cardinality detects leaked tenants/members as well as projects."""
    from sqlalchemy import text

    return tuple((await connection.execute(text("""
        SELECT (SELECT count(*) FROM organizations),
               (SELECT count(*) FROM organization_members),
               (SELECT count(*) FROM projects),
               (SELECT count(*) FROM boards),
               (SELECT count(*) FROM board_columns)
    """))).one())


@pytest.mark.asyncio
@pytest.mark.parametrize("autobegin", [False, True], ids=["fresh", "auth-select"])
async def test_new_organization_bootstrap_commits_admin_and_root_generales(target_url, autobegin):
    from sqlalchemy import select, text
    from app.modules.organizations.schemas import OrganizationCreate, OrganizationRead
    from app.modules.organizations.service import OrganizationService
    from app.modules.users.models import User
    from app.shared.exceptions import AppException

    async with provision_database(target_url) as data:
        engine, sessions, existing, _, actor, ensure, repository = data
        async with sessions.begin() as session:
            await ensure(repository(session), organization_id=existing, actor_id=actor, parent_id=None)
        async with engine.connect() as connection:
            before = await bootstrap_counts(connection)
            old_project = await connection.scalar(text(
                "SELECT to_jsonb(p) FROM projects p WHERE organization_id=:org"
            ), {"org": existing})
        payload = OrganizationCreate(name="Synthetic new tenant", slug="new-tenant")
        async with sessions() as session:
            if autobegin:
                assert await session.scalar(select(User.id).where(User.id == actor)) == actor
                assert session.in_transaction()
            result = await OrganizationService(session).create_bootstrap(
                payload, creator_id=actor, actor_id=actor,
            )
            assert isinstance(result, OrganizationRead)
            assert not session.in_transaction()
        async with engine.connect() as connection:
            assert await bootstrap_counts(connection) == tuple(
                a + b for a, b in zip(before, (1, 1, 1, 1, 7))
            )
            assert await counts(connection, result.id) == (1, 1, 7)
            member = (await connection.execute(text(
                "SELECT user_id, role FROM organization_members WHERE organization_id=:org"
            ), {"org": result.id})).one()
            assert tuple(member) == (actor, "admin")
            project = (await connection.execute(text(
                "SELECT parent_project_id, is_system, created_by, updated_by FROM projects "
                "WHERE organization_id=:org"
            ), {"org": result.id})).one()
            assert tuple(project) == (None, True, actor, actor)
            assert await connection.scalar(text(
                "SELECT to_jsonb(p) FROM projects p WHERE organization_id=:org"
            ), {"org": existing}) == old_project
            completed = await bootstrap_counts(connection)
        async with sessions() as session:
            with pytest.raises(AppException) as error:
                await OrganizationService(session).create_bootstrap(
                    payload, creator_id=actor, actor_id=actor,
                )
            assert error.value.status_code == 409
            assert error.value.code == "organization_slug_taken"
            assert not session.in_transaction()
        async with engine.connect() as connection:
            assert await bootstrap_counts(connection) == completed


@pytest.mark.asyncio
async def test_new_organization_failure_after_provision_rolls_back_every_row(target_url):
    from sqlalchemy import text
    from app.modules.organizations.bootstrap import bootstrap_organization
    from app.modules.organizations.bootstrap_uow import OrganizationBootstrapUow
    from app.modules.organizations.schemas import OrganizationCreate

    async with provision_database(target_url) as data:
        engine, sessions, existing, _, actor, ensure, repository = data
        async with sessions.begin() as session:
            await ensure(repository(session), organization_id=existing, actor_id=actor, parent_id=None)
        async with engine.connect() as connection:
            before = await bootstrap_counts(connection)
            old_project = await connection.scalar(text(
                "SELECT to_jsonb(p) FROM projects p WHERE organization_id=:org"
            ), {"org": existing})
        observed = []

        class FailAfterProvision(repository):
            async def create_generales(self, organization_id, actor_id, parent_id):
                await super().create_generales(organization_id, actor_id, parent_id)
                observed.append(await counts(self.session, organization_id))
                raise RuntimeError("synthetic failure after provision")

        async with sessions() as session:
            # Authentication already started the transaction on the same session.
            await session.scalar(text("SELECT id FROM users WHERE id=:id"), {"id": actor})
            uow = OrganizationBootstrapUow(session)
            uow.projects = FailAfterProvision(session)
            with pytest.raises(RuntimeError, match="after provision"):
                await bootstrap_organization(
                    uow, OrganizationCreate(name="Failed tenant", slug="failed-tenant"),
                    creator_id=actor, actor_id=actor,
                )
            assert not session.in_transaction()
        assert observed == [(1, 1, 7)]
        async with engine.connect() as connection:
            assert await bootstrap_counts(connection) == before
            assert await connection.scalar(text(
                "SELECT count(*) FROM organizations WHERE slug='failed-tenant'"
            )) == 0
            assert await connection.scalar(text(
                "SELECT to_jsonb(p) FROM projects p WHERE organization_id=:org"
            ), {"org": existing}) == old_project


async def observe_wait(engine, waiter_pid, owner_pid):
    """Prove the exact backend is blocked by the owner, not elapsed-time guessing."""
    from sqlalchemy import text

    async with asyncio.timeout(5):
        async with engine.connect() as observer:
            while True:
                waiting = await observer.scalar(text("""
                    SELECT EXISTS (
                      SELECT 1 FROM pg_stat_activity
                      WHERE pid=:waiter AND wait_event_type='Lock'
                        AND :owner = ANY(pg_blocking_pids(pid))
                    )
                """), {"waiter": waiter_pid, "owner": owner_pid})
                if waiting:
                    return
                # Clear the statistics snapshot: each poll observes new state.
                await observer.rollback()
                await asyncio.sleep(0.02)


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback_owner", [False, True], ids=["commit-reuse", "rollback-release"])
async def test_two_transactions_wait_and_converge(target_url, rollback_owner):
    from sqlalchemy import text

    async with provision_database(target_url) as data:
        engine, sessions, org, _, actor, ensure, repository = data
        ready = asyncio.Event()
        attempt = asyncio.Event()
        waiter_pid = None

        async def contender():
            nonlocal waiter_pid
            async with sessions.begin() as session:
                waiter_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                ready.set()
                await attempt.wait()
                result = await ensure(repository(session), organization_id=org,
                                      actor_id=actor, parent_id=None)
            return result  # returned only AFTER the independent transaction commits

        async with sessions() as owner:
            await owner.begin()
            task = None
            try:
                owner_pid = await owner.scalar(text("SELECT pg_backend_pid()"))
                first = await ensure(repository(owner), organization_id=org,
                                     actor_id=actor, parent_id=None)
                # First transaction has flushed, but is deliberately still open.
                async with engine.connect() as observer:
                    assert await counts(observer, org) == (0, 0, 0)
                task = asyncio.create_task(contender())
                await asyncio.wait_for(ready.wait(), timeout=5)
                assert waiter_pid != owner_pid
                attempt.set()
                await observe_wait(engine, waiter_pid, owner_pid)
                assert not task.done()
                if rollback_owner:
                    await owner.rollback()
                else:
                    await owner.commit()
                second = await asyncio.wait_for(task, timeout=5)
                if rollback_owner:
                    assert second.id != first.id
                else:
                    assert second.id == first.id
                async with engine.connect() as connection:
                    assert await counts(connection, org) == (1, 1, 7)
                    assert await connection.scalar(text(
                        "SELECT id FROM projects WHERE organization_id=:org"
                    ), {"org": org}) == second.id
            finally:
                if task is not None:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                await owner.rollback()
