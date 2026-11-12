"""Tests for migration 0014 (self-FK ``projects.parent_project_id``).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_boards_backfill_migration.py``: upgrades to
``0013`` (pre-hierarchy schema), inserts a project via raw SQL, upgrades to
``0014`` and asserts the new column/index exist and the row survives, then
downgrades and asserts a clean round trip with zero data loss (change
21-project-hierarchy, tasks.md T1.5).

Test functions are plain ``def`` (NOT ``async def``), same as
``test_migrations_baseline.py``/``test_boards_backfill_migration.py``:
``alembic.command.upgrade``/``downgrade`` call ``asyncio.run()`` internally
(see ``alembic/env.py``), which cannot nest inside an already-running
pytest-asyncio event loop.
"""

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config

from alembic import command

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")

BACKEND_DIR = Path(__file__).resolve().parent.parent
_HIERARCHY_DB_NAME = "solercia_test_project_hierarchy_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _hierarchy_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_HIERARCHY_DB_NAME}"


async def _recreate_hierarchy_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_HIERARCHY_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_HIERARCHY_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_hierarchy_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_HIERARCHY_DB_NAME}" WITH (FORCE)'
        )
    finally:
        await admin_conn.close()


def _alembic_config(sqlalchemy_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg


def _run_against(async_url: str) -> Config:
    from app.config import settings

    settings.DATABASE_URL = async_url
    return _alembic_config(async_url)


async def _seed_pre_migration_project(dsn: str) -> dict:
    """Insert an organization + a project via raw SQL against the pre-0014 schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Hierarchy Migration Org",
            f"hierarchy-migration-org-{uuid.uuid4().hex[:12]}",
        )

        project_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects "
            "(id, name, methodology, status, code, task_counter, "
            " organization_id, is_active) "
            "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true)",
            project_id,
            "Pre-Migration Project",
            "PMP",
            org_id,
        )

        return {"organization_id": org_id, "project_id": project_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_adds_parent_project_id_column_and_index_without_losing_rows() -> None:
    """T1.5: upgrade to 0014 adds the column+index; the pre-existing row survives."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_hierarchy_database(test_database_url))
        hierarchy_url = _hierarchy_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _hierarchy_db_dsn(test_database_url)

        cfg = _run_against(hierarchy_url)
        command.upgrade(cfg, "0013")

        fixtures = asyncio.run(_seed_pre_migration_project(sync_dsn))

        command.upgrade(cfg, "0014")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                column = await conn.fetchrow(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'parent_project_id'"
                )
                assert column is not None
                assert column["is_nullable"] == "YES"

                index = await conn.fetchrow(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'projects' "
                    "AND indexname = 'ix_projects_parent_project_id'"
                )
                assert index is not None

                # The row inserted BEFORE the migration survives untouched.
                row = await conn.fetchrow(
                    "SELECT id, parent_project_id FROM projects WHERE id = $1",
                    fixtures["project_id"],
                )
                assert row is not None
                assert row["parent_project_id"] is None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_hierarchy_database(test_database_url))


@skip_no_db
def test_downgrade_removes_column_and_index_without_losing_rows() -> None:
    """T1.5: downgrade() reverts the column+index cleanly; zero rows lost."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_hierarchy_database(test_database_url))
        hierarchy_url = _hierarchy_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _hierarchy_db_dsn(test_database_url)

        cfg = _run_against(hierarchy_url)
        command.upgrade(cfg, "0013")
        asyncio.run(_seed_pre_migration_project(sync_dsn))
        command.upgrade(cfg, "0014")
        command.downgrade(cfg, "0013")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                column = await conn.fetchrow(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'parent_project_id'"
                )
                assert column is None

                index = await conn.fetchrow(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'projects' "
                    "AND indexname = 'ix_projects_parent_project_id'"
                )
                assert index is None

                remaining_projects = await conn.fetch("SELECT id FROM projects")
                assert len(remaining_projects) == 1
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_hierarchy_database(test_database_url))
