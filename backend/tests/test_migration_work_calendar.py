"""Tests for migration 0024 (``organizations``/``projects`` work-calendar
columns).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_project_hierarchy_migration.py``: upgrades to
``0023`` (the revision immediately BEFORE this change), inserts an
organization and a project via raw SQL, upgrades to ``0024`` and asserts the
new columns exist with the right nullability/defaults and the pre-existing
rows survive (organization backfilled to 8/[1..5], project's override columns
NULL), then downgrades and asserts a clean round trip with zero data loss
(change 28-calendario-laboral, tasks.md T1.1/T1.3).

Test functions are plain ``def`` (NOT ``async def``), same as
``test_migrations_baseline.py``/``test_project_hierarchy_migration.py``:
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
_WORK_CALENDAR_DB_NAME = "solercia_test_work_calendar_migration"

# The revision immediately before this change's migration (Fase 0, tasks.md
# 0.1/0.2): the head verified live in disk was "0023", no fork.
_PRE_REVISION = "0023"
_THIS_REVISION = "0024"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _work_calendar_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_WORK_CALENDAR_DB_NAME}"


async def _recreate_work_calendar_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_WORK_CALENDAR_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_WORK_CALENDAR_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_work_calendar_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_WORK_CALENDAR_DB_NAME}" WITH (FORCE)'
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


async def _seed_pre_migration_rows(dsn: str) -> dict:
    """Insert an organization + a project via raw SQL against the ``0023`` schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Work Calendar Migration Org",
            f"work-calendar-migration-org-{uuid.uuid4().hex[:12]}",
        )

        project_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects "
            "(id, name, methodology, status, code, task_counter, "
            " organization_id, is_active, project_kind) "
            "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true, 'proyecto')",
            project_id,
            "Pre-Migration Project",
            "PWC",
            org_id,
        )

        return {"organization_id": org_id, "project_id": project_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_adds_the_four_columns_with_correct_defaults_without_losing_rows() -> (
    None
):
    """T1.1/T1.2: upgrade to 0024 backfills org defaults; project columns stay NULL."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_work_calendar_database(test_database_url))
        work_calendar_url = _work_calendar_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _work_calendar_db_dsn(test_database_url)

        cfg = _run_against(work_calendar_url)
        command.upgrade(cfg, _PRE_REVISION)

        fixtures = asyncio.run(_seed_pre_migration_rows(sync_dsn))

        command.upgrade(cfg, _THIS_REVISION)

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                org_columns = await conn.fetch(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'organizations' "
                    "AND column_name IN ('working_hours_per_day', 'working_days')"
                )
                org_column_map = {row["column_name"]: row["is_nullable"] for row in org_columns}
                assert org_column_map == {
                    "working_hours_per_day": "NO",
                    "working_days": "NO",
                }

                project_columns = await conn.fetch(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'projects' "
                    "AND column_name IN ('working_hours_per_day', 'working_days')"
                )
                project_column_map = {
                    row["column_name"]: row["is_nullable"] for row in project_columns
                }
                assert project_column_map == {
                    "working_hours_per_day": "YES",
                    "working_days": "YES",
                }

                org_row = await conn.fetchrow(
                    "SELECT working_hours_per_day, working_days FROM organizations "
                    "WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
                assert org_row["working_hours_per_day"] == 8
                assert list(org_row["working_days"]) == [1, 2, 3, 4, 5]

                project_row = await conn.fetchrow(
                    "SELECT working_hours_per_day, working_days FROM projects "
                    "WHERE id = $1",
                    fixtures["project_id"],
                )
                assert project_row is not None
                assert project_row["working_hours_per_day"] is None
                assert project_row["working_days"] is None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_work_calendar_database(test_database_url))


@skip_no_db
def test_downgrade_removes_the_four_columns_without_losing_rows() -> None:
    """T1.3: downgrade removes the 4 columns; no row is lost either side."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_work_calendar_database(test_database_url))
        work_calendar_url = _work_calendar_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _work_calendar_db_dsn(test_database_url)

        cfg = _run_against(work_calendar_url)
        command.upgrade(cfg, _PRE_REVISION)
        asyncio.run(_seed_pre_migration_rows(sync_dsn))
        command.upgrade(cfg, _THIS_REVISION)
        command.downgrade(cfg, _PRE_REVISION)

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                org_columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'organizations' "
                    "AND column_name IN ('working_hours_per_day', 'working_days')"
                )
                assert org_columns == []

                project_columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'projects' "
                    "AND column_name IN ('working_hours_per_day', 'working_days')"
                )
                assert project_columns == []

                remaining_orgs = await conn.fetch("SELECT id FROM organizations")
                remaining_projects = await conn.fetch("SELECT id FROM projects")
                assert len(remaining_orgs) == 1
                assert len(remaining_projects) == 1
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_work_calendar_database(test_database_url))
