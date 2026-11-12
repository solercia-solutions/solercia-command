"""Tests for migration 0015 (``connectors``/``connected_accounts``/
``connection_credentials``, change 14-integration-ports).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_project_hierarchy_migration.py``: upgrades to
``0014`` (pre-connectors schema), inserts an organization+user via raw SQL,
upgrades to ``0015`` and asserts the three tables/unique constraints exist
and the pre-existing rows survive untouched, then downgrades and asserts a
clean round trip with zero data loss (tasks.md T2.6, [C-R1, C-R3]).

Test functions are plain ``def`` (NOT ``async def``), same as the
precedent: ``alembic.command.upgrade``/``downgrade`` call ``asyncio.run()``
internally (see ``alembic/env.py``), which cannot nest inside an
already-running pytest-asyncio event loop.
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
_CONNECTORS_DB_NAME = "solercia_test_connectors_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _connectors_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_CONNECTORS_DB_NAME}"


async def _recreate_connectors_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_CONNECTORS_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_CONNECTORS_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_connectors_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_CONNECTORS_DB_NAME}" WITH (FORCE)'
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


async def _seed_pre_migration_org_and_user(dsn: str) -> dict:
    """Insert an organization + user via raw SQL against the pre-0015 schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Connectors Migration Org",
            f"connectors-migration-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, hashed_password, is_active) "
            "VALUES ($1, $2, $3, $4, $5, true)",
            user_id,
            f"connectors-migration-{uuid.uuid4().hex[:12]}@example.com",
            "Connectors",
            "Migration",
            "x",
        )

        return {"organization_id": org_id, "user_id": user_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_creates_three_tables_with_unique_constraints_without_losing_rows() -> (
    None
):
    """T2.6: upgrade to 0015 creates connectors/connected_accounts/
    connection_credentials with their UNIQUE constraints; the pre-existing
    organization/user rows survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_connectors_database(test_database_url))
        connectors_url = _connectors_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _connectors_db_dsn(test_database_url)

        cfg = _run_against(connectors_url)
        command.upgrade(cfg, "0014")

        fixtures = asyncio.run(_seed_pre_migration_org_and_user(sync_dsn))

        command.upgrade(cfg, "0015")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "connectors",
                    "connected_accounts",
                    "connection_credentials",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is not None, f"missing table {table}"

                unique_names = {
                    r["conname"]
                    for r in await conn.fetch(
                        "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                        "AND conrelid::regclass::text IN "
                        "('connectors', 'connected_accounts', 'connection_credentials')"
                    )
                }
                assert "uq_connectors_organization_provider" in unique_names
                assert "uq_connected_accounts_connector_external" in unique_names
                assert "uq_connection_credentials_connected_account" in unique_names

                # Pre-existing rows survive the migration untouched.
                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
                user_row = await conn.fetchrow(
                    "SELECT id FROM users WHERE id = $1", fixtures["user_id"]
                )
                assert user_row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_connectors_database(test_database_url))


@skip_no_db
def test_downgrade_drops_three_tables_in_reverse_order_without_losing_other_rows() -> (
    None
):
    """T2.6: downgrade() reverts connection_credentials -> connected_accounts
    -> connectors cleanly; the pre-existing organization/user rows survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_connectors_database(test_database_url))
        connectors_url = _connectors_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _connectors_db_dsn(test_database_url)

        cfg = _run_against(connectors_url)
        command.upgrade(cfg, "0014")
        fixtures = asyncio.run(_seed_pre_migration_org_and_user(sync_dsn))
        command.upgrade(cfg, "0015")
        command.downgrade(cfg, "0014")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "connectors",
                    "connected_accounts",
                    "connection_credentials",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is None, f"table {table} should be dropped"

                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
                user_row = await conn.fetchrow(
                    "SELECT id FROM users WHERE id = $1", fixtures["user_id"]
                )
                assert user_row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_connectors_database(test_database_url))
