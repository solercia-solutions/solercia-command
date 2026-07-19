"""Tests for migration 0018 (``org_role_templates``, ``org_role_template_nodes``,
``org_role_template_instantiations`` and ``projects.lead_user_id``, change
23-org-role-templates).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_glpi_sync_migration.py``: upgrades to ``0017``
(pre-templates schema), inserts an organization+user+project via raw SQL,
upgrades to ``0018`` and asserts every new table/column/unique constraint
exists and the pre-existing rows survive untouched, then downgrades and
asserts a clean round trip with zero data loss (tasks.md Lote 1, T1.1).

Test functions are plain ``def`` (NOT ``async def``), same as the precedent:
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
_TEMPLATES_DB_NAME = "solercia_test_org_role_templates_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _templates_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_TEMPLATES_DB_NAME}"


async def _recreate_templates_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_TEMPLATES_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_TEMPLATES_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_templates_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_TEMPLATES_DB_NAME}" WITH (FORCE)'
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


async def _seed_pre_migration_org_user_project(dsn: str) -> dict:
    """Insert an organization + user + project via raw SQL against the
    pre-0018 schema (no ``lead_user_id`` yet)."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Templates Migration Org",
            f"templates-migration-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, hashed_password, is_active) "
            "VALUES ($1, $2, $3, $4, $5, true)",
            user_id,
            f"templates-migration-{uuid.uuid4().hex[:12]}@example.com",
            "Templates",
            "Migration",
            "x",
        )

        project_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects "
            "(id, name, methodology, status, code, task_counter, "
            " organization_id, is_active) "
            "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true)",
            project_id,
            "Pre-Templates Project",
            "PTP",
            org_id,
        )

        return {"organization_id": org_id, "user_id": user_id, "project_id": project_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_creates_templates_tables_and_lead_user_id_without_losing_rows() -> None:
    """T1.1: upgrade to 0018 adds the 3 tables and ``projects.lead_user_id``;
    pre-existing rows survive untouched."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_templates_database(test_database_url))
        templates_url = _templates_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _templates_db_dsn(test_database_url)

        cfg = _run_against(templates_url)
        command.upgrade(cfg, "0017")

        fixtures = asyncio.run(_seed_pre_migration_org_user_project(sync_dsn))

        command.upgrade(cfg, "0018")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "org_role_templates",
                    "org_role_template_nodes",
                    "org_role_template_instantiations",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is not None, f"missing table {table}"

                column = await conn.fetchrow(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'lead_user_id'"
                )
                assert column is not None
                assert column["is_nullable"] == "YES"

                unique_names = {
                    r["conname"]
                    for r in await conn.fetch(
                        "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                        "AND conrelid::regclass::text = 'org_role_template_instantiations'"
                    )
                }
                assert "uq_org_role_template_instantiation" in unique_names

                # Pre-existing rows survive the migration untouched.
                project_row = await conn.fetchrow(
                    "SELECT id, lead_user_id FROM projects WHERE id = $1",
                    fixtures["project_id"],
                )
                assert project_row is not None
                assert project_row["lead_user_id"] is None
                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_templates_database(test_database_url))


@skip_no_db
def test_downgrade_drops_templates_pieces_in_reverse_order_without_losing_other_rows() -> None:
    """T1.1: downgrade() reverts org_role_template_instantiations ->
    org_role_template_nodes -> org_role_templates -> projects.lead_user_id
    cleanly; pre-existing organization/project rows survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_templates_database(test_database_url))
        templates_url = _templates_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _templates_db_dsn(test_database_url)

        cfg = _run_against(templates_url)
        command.upgrade(cfg, "0017")
        fixtures = asyncio.run(_seed_pre_migration_org_user_project(sync_dsn))
        command.upgrade(cfg, "0018")
        command.downgrade(cfg, "0017")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "org_role_templates",
                    "org_role_template_nodes",
                    "org_role_template_instantiations",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is None, f"table {table} should be dropped"

                column = await conn.fetchrow(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'lead_user_id'"
                )
                assert column is None

                project_row = await conn.fetchrow(
                    "SELECT id FROM projects WHERE id = $1", fixtures["project_id"]
                )
                assert project_row is not None
                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_templates_database(test_database_url))
