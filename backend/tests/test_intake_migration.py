"""Tests for migration 0019 (4 tablas: intake_items, intake_rules,
intake_runs, intake_settings).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_project_hierarchy_migration.py``: upgrades to
``0018`` (pre-intake schema), upgrades to ``0019`` and asserts the new
tables/unique constraints exist, then downgrades and asserts a clean round
trip with zero residue (change 22-intake-classifier, tasks.md T1.7).

Test functions are plain ``def`` (NOT ``async def``), same as
``test_project_hierarchy_migration.py``: ``alembic.command.upgrade``/
``downgrade`` call ``asyncio.run()`` internally, which cannot nest inside an
already-running pytest-asyncio event loop.
"""

import asyncio
import os
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
_INTAKE_DB_NAME = "solercia_test_intake_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _intake_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_INTAKE_DB_NAME}"


async def _recreate_intake_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_INTAKE_DB_NAME}" WITH (FORCE)')
        await admin_conn.execute(f'CREATE DATABASE "{_INTAKE_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_intake_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_INTAKE_DB_NAME}" WITH (FORCE)')
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


async def _assert_tables_present(sync_dsn: str) -> None:
    conn = await asyncpg.connect(dsn=sync_dsn)
    try:
        for table in ("intake_items", "intake_rules", "intake_runs", "intake_settings"):
            row = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = $1",
                table,
            )
            assert row is not None, f"tabla {table} no fue creada por 0019"

        items_unique = await conn.fetchrow(
            "SELECT conname FROM pg_constraint "
            "WHERE conname = 'uq_intake_items_org_connector_external'"
        )
        assert items_unique is not None

        settings_unique = await conn.fetchrow(
            "SELECT conname FROM pg_constraint "
            "WHERE conname = 'uq_intake_settings_organization'"
        )
        assert settings_unique is not None
    finally:
        await conn.close()


async def _assert_tables_absent(sync_dsn: str) -> None:
    conn = await asyncpg.connect(dsn=sync_dsn)
    try:
        for table in ("intake_items", "intake_rules", "intake_runs", "intake_settings"):
            row = await conn.fetchrow(
                "SELECT table_name FROM information_schema.tables WHERE table_name = $1",
                table,
            )
            assert row is None, f"tabla {table} sigue existiendo tras el downgrade"
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_creates_four_tables_with_unique_constraints() -> None:
    """T1.7: upgrade a 0019 crea las 4 tablas + las 2 unicidades."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_intake_database(test_database_url))
        intake_url = _intake_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _intake_db_dsn(test_database_url)

        cfg = _run_against(intake_url)
        command.upgrade(cfg, "0018")
        command.upgrade(cfg, "0019")

        asyncio.run(_assert_tables_present(sync_dsn))
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_intake_database(test_database_url))


@skip_no_db
def test_downgrade_removes_tables_in_reverse_order_without_residue() -> None:
    """T1.7: downgrade() elimina las 4 tablas en orden inverso, sin residuos."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_intake_database(test_database_url))
        intake_url = _intake_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _intake_db_dsn(test_database_url)

        cfg = _run_against(intake_url)
        command.upgrade(cfg, "0018")
        command.upgrade(cfg, "0019")
        command.downgrade(cfg, "0018")

        asyncio.run(_assert_tables_absent(sync_dsn))
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_intake_database(test_database_url))
