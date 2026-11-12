"""Tests for migration 0017 (``users.numero_documento`` + partial unique
index, ``connectors.credential_kind``/``connectors.settings``,
``glpi_user_links``/``glpi_unmatched_assignees``/``glpi_unmatched_cases``,
change 17-adapter-glpi).

Runs against a disposable database (created and dropped by this test), same
isolation pattern as ``test_connectors_migration.py``: upgrades to ``0016``
(pre-GLPI schema), inserts an organization+user+connector via raw SQL,
upgrades to ``0017`` and asserts every new column/table/unique constraint
exists and the pre-existing rows survive untouched, then downgrades and
asserts a clean round trip with zero data loss (tasks.md T2.7, [UH-R1]).

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
_GLPI_DB_NAME = "solercia_test_glpi_sync_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _glpi_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_GLPI_DB_NAME}"


async def _recreate_glpi_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_GLPI_DB_NAME}" WITH (FORCE)')
        await admin_conn.execute(f'CREATE DATABASE "{_GLPI_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_glpi_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_GLPI_DB_NAME}" WITH (FORCE)')
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


async def _seed_pre_migration_org_user_connector(dsn: str) -> dict:
    """Insert an organization + user + connector via raw SQL against the
    pre-0017 schema (0016's shape — no ``credential_kind``/``settings``
    yet)."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "GLPI Migration Org",
            f"glpi-migration-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, hashed_password, is_active) "
            "VALUES ($1, $2, $3, $4, $5, true)",
            user_id,
            f"glpi-migration-{uuid.uuid4().hex[:12]}@example.com",
            "Glpi",
            "Migration",
            "x",
        )

        connector_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO connectors "
            "(id, organization_id, provider, status, is_active) "
            "VALUES ($1, $2, $3, $4, true)",
            connector_id,
            org_id,
            "glpi",
            "active",
        )

        return {
            "organization_id": org_id,
            "user_id": user_id,
            "connector_id": connector_id,
        }
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_creates_glpi_pieces_with_unique_constraints_without_losing_rows() -> None:
    """T2.7: upgrade to 0017 adds numero_documento/credential_kind/settings
    plus the three GLPI tables with their UNIQUE constraints; pre-existing
    rows survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_glpi_database(test_database_url))
        glpi_url = _glpi_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _glpi_db_dsn(test_database_url)

        cfg = _run_against(glpi_url)
        command.upgrade(cfg, "0016")

        fixtures = asyncio.run(_seed_pre_migration_org_user_connector(sync_dsn))

        command.upgrade(cfg, "0017")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "glpi_user_links",
                    "glpi_unmatched_assignees",
                    "glpi_unmatched_cases",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is not None, f"missing table {table}"

                for table, column in (
                    ("users", "numero_documento"),
                    ("connectors", "credential_kind"),
                    ("connectors", "settings"),
                ):
                    row = await conn.fetchrow(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = $1 AND column_name = $2",
                        table,
                        column,
                    )
                    assert row is not None, f"missing column {table}.{column}"

                unique_names = {
                    r["conname"]
                    for r in await conn.fetch(
                        "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                        "AND conrelid::regclass::text IN "
                        "('glpi_user_links', 'glpi_unmatched_assignees', "
                        "'glpi_unmatched_cases')"
                    )
                }
                assert "uq_glpi_user_links_connector_glpi_user" in unique_names
                assert "uq_glpi_unmatched_assignees_connector_glpi_user" in unique_names
                assert "uq_glpi_unmatched_cases_assignee_ticket" in unique_names

                index_names = {
                    r["indexname"]
                    for r in await conn.fetch(
                        "SELECT indexname FROM pg_indexes WHERE tablename = 'users'"
                    )
                }
                assert "uq_users_numero_documento" in index_names

                # Existing connector defaults credential_kind to 'oauth'.
                connector_row = await conn.fetchrow(
                    "SELECT credential_kind, settings FROM connectors WHERE id = $1",
                    fixtures["connector_id"],
                )
                assert connector_row is not None
                assert connector_row["credential_kind"] == "oauth"
                assert connector_row["settings"] is None

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
        asyncio.run(_drop_glpi_database(test_database_url))


@skip_no_db
def test_numero_documento_partial_index_allows_nulls_and_rejects_duplicate() -> None:
    """UH-R1: many ``NULL`` values coexist freely; a non-NULL duplicate is
    rejected by the partial unique index."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_glpi_database(test_database_url))
        glpi_url = _glpi_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _glpi_db_dsn(test_database_url)

        cfg = _run_against(glpi_url)
        command.upgrade(cfg, "0017")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                # Two users with NULL numero_documento coexist without conflict.
                for _ in range(2):
                    await conn.execute(
                        "INSERT INTO users "
                        "(id, email, primer_nombre, primer_apellido, "
                        "hashed_password, is_active, numero_documento) "
                        "VALUES ($1, $2, $3, $4, $5, true, NULL)",
                        uuid.uuid4(),
                        f"null-doc-{uuid.uuid4().hex[:12]}@example.com",
                        "Null",
                        "Doc",
                        "x",
                    )

                # A first user with a non-NULL document persists fine.
                await conn.execute(
                    "INSERT INTO users "
                    "(id, email, primer_nombre, primer_apellido, "
                    "hashed_password, is_active, numero_documento) "
                    "VALUES ($1, $2, $3, $4, $5, true, $6)",
                    uuid.uuid4(),
                    f"doc-owner-{uuid.uuid4().hex[:12]}@example.com",
                    "Doc",
                    "Owner",
                    "x",
                    "123456789",
                )

                # A second user with the SAME document is rejected.
                with pytest.raises(asyncpg.UniqueViolationError):
                    await conn.execute(
                        "INSERT INTO users "
                        "(id, email, primer_nombre, primer_apellido, "
                        "hashed_password, is_active, numero_documento) "
                        "VALUES ($1, $2, $3, $4, $5, true, $6)",
                        uuid.uuid4(),
                        f"doc-dup-{uuid.uuid4().hex[:12]}@example.com",
                        "Doc",
                        "Dup",
                        "x",
                        "123456789",
                    )
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_glpi_database(test_database_url))


@skip_no_db
def test_downgrade_drops_glpi_pieces_in_reverse_order_without_losing_other_rows() -> None:
    """T2.7: downgrade() reverts glpi_unmatched_cases ->
    glpi_unmatched_assignees -> glpi_user_links -> connectors columns ->
    numero_documento cleanly; pre-existing organization/user rows survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_glpi_database(test_database_url))
        glpi_url = _glpi_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _glpi_db_dsn(test_database_url)

        cfg = _run_against(glpi_url)
        command.upgrade(cfg, "0016")
        fixtures = asyncio.run(_seed_pre_migration_org_user_connector(sync_dsn))
        command.upgrade(cfg, "0017")
        command.downgrade(cfg, "0016")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for table in (
                    "glpi_user_links",
                    "glpi_unmatched_assignees",
                    "glpi_unmatched_cases",
                ):
                    row = await conn.fetchrow(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_name = $1",
                        table,
                    )
                    assert row is None, f"table {table} should be dropped"

                for table, column in (
                    ("users", "numero_documento"),
                    ("connectors", "credential_kind"),
                    ("connectors", "settings"),
                ):
                    row = await conn.fetchrow(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = $1 AND column_name = $2",
                        table,
                        column,
                    )
                    assert row is None, f"column {table}.{column} should be dropped"

                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
                user_row = await conn.fetchrow(
                    "SELECT id FROM users WHERE id = $1", fixtures["user_id"]
                )
                assert user_row is not None
                connector_row = await conn.fetchrow(
                    "SELECT id FROM connectors WHERE id = $1", fixtures["connector_id"]
                )
                assert connector_row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_glpi_database(test_database_url))
