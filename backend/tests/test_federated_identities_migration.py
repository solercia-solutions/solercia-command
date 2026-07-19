"""Tests for migration 0016 (``federated_identities`` + ``users.hashed_password``
nullable, change 20-sso-keycloak).

Same disposable-database isolation pattern as
``test_connectors_migration.py``: upgrades to ``0015`` (pre-federated-identities
schema), inserts an organization+user via raw SQL, upgrades to ``0016`` and
asserts the table/unique constraint/nullable column, then downgrades and
asserts a clean round trip. A THIRD scenario proves the downgrade guard:
with an SSO-only user (``hashed_password IS NULL``) present, ``downgrade()``
MUST raise instead of corrupting/dropping that row (T05).

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
_FEDERATED_DB_NAME = "solercia_test_federated_identities_migration"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _federated_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_FEDERATED_DB_NAME}"


async def _recreate_federated_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_FEDERATED_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_FEDERATED_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_federated_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_FEDERATED_DB_NAME}" WITH (FORCE)'
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
    """Insert an organization + user via raw SQL against the pre-0016 schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Federated Identities Migration Org",
            f"federated-migration-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, hashed_password, is_active) "
            "VALUES ($1, $2, $3, $4, $5, true)",
            user_id,
            f"federated-migration-{uuid.uuid4().hex[:12]}@example.com",
            "Federated",
            "Migration",
            "x",
        )

        return {"organization_id": org_id, "user_id": user_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_creates_table_and_relaxes_password_without_losing_rows() -> None:
    """T05: upgrade to 0016 creates federated_identities with its UNIQUE
    constraint and makes users.hashed_password nullable; pre-existing rows
    survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_federated_database(test_database_url))
        federated_url = _federated_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _federated_db_dsn(test_database_url)

        cfg = _run_against(federated_url)
        command.upgrade(cfg, "0015")

        fixtures = asyncio.run(_seed_pre_migration_org_and_user(sync_dsn))

        command.upgrade(cfg, "0016")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                table_row = await conn.fetchrow(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'federated_identities'"
                )
                assert table_row is not None, "missing table federated_identities"

                unique_names = {
                    r["conname"]
                    for r in await conn.fetch(
                        "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                        "AND conrelid::regclass::text = 'federated_identities'"
                    )
                }
                assert "uq_federated_identities_issuer_subject" in unique_names

                column_row = await conn.fetchrow(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'hashed_password'"
                )
                assert column_row["is_nullable"] == "YES"

                # Pre-existing rows survive the migration untouched.
                org_row = await conn.fetchrow(
                    "SELECT id FROM organizations WHERE id = $1",
                    fixtures["organization_id"],
                )
                assert org_row is not None
                user_row = await conn.fetchrow(
                    "SELECT id, hashed_password FROM users WHERE id = $1",
                    fixtures["user_id"],
                )
                assert user_row is not None
                assert user_row["hashed_password"] == "x"
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_federated_database(test_database_url))


@skip_no_db
def test_downgrade_drops_table_and_restores_not_null_without_losing_other_rows() -> (
    None
):
    """T05: downgrade() reverts federated_identities and NOT NULL cleanly
    when no SSO-only user exists; the pre-existing organization/user rows
    survive."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_federated_database(test_database_url))
        federated_url = _federated_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _federated_db_dsn(test_database_url)

        cfg = _run_against(federated_url)
        command.upgrade(cfg, "0015")
        fixtures = asyncio.run(_seed_pre_migration_org_and_user(sync_dsn))
        command.upgrade(cfg, "0016")
        command.downgrade(cfg, "0015")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                table_row = await conn.fetchrow(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'federated_identities'"
                )
                assert table_row is None, "federated_identities should be dropped"

                column_row = await conn.fetchrow(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'users' AND column_name = 'hashed_password'"
                )
                assert column_row["is_nullable"] == "NO"

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
        asyncio.run(_drop_federated_database(test_database_url))


@skip_no_db
def test_downgrade_guard_rejects_when_an_sso_only_user_exists() -> None:
    """T05: downgrade() MUST raise (and leave the schema untouched) when a
    user has hashed_password IS NULL — restoring NOT NULL would corrupt or
    lose that SSO-only account."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_federated_database(test_database_url))
        federated_url = _federated_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _federated_db_dsn(test_database_url)

        cfg = _run_against(federated_url)
        command.upgrade(cfg, "0016")

        async def _make_sso_only_user() -> uuid.UUID:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                org_id = uuid.uuid4()
                await conn.execute(
                    "INSERT INTO organizations (id, name, slug, is_active) "
                    "VALUES ($1, $2, $3, true)",
                    org_id,
                    "SSO Only Org",
                    f"sso-only-org-{uuid.uuid4().hex[:12]}",
                )
                user_id = uuid.uuid4()
                await conn.execute(
                    "INSERT INTO users "
                    "(id, email, primer_nombre, primer_apellido, "
                    "hashed_password, is_active) "
                    "VALUES ($1, $2, $3, $4, NULL, true)",
                    user_id,
                    f"sso-only-{uuid.uuid4().hex[:12]}@example.com",
                    "SsoOnly",
                    "User",
                )
                return user_id
            finally:
                await conn.close()

        sso_user_id = asyncio.run(_make_sso_only_user())

        with pytest.raises(Exception, match="hashed_password"):
            command.downgrade(cfg, "0015")

        async def _assert_untouched() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                table_row = await conn.fetchrow(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'federated_identities'"
                )
                assert table_row is not None, "table must survive a failed downgrade"

                user_row = await conn.fetchrow(
                    "SELECT id, hashed_password FROM users WHERE id = $1",
                    sso_user_id,
                )
                assert user_row is not None
                assert user_row["hashed_password"] is None
            finally:
                await conn.close()

        asyncio.run(_assert_untouched())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_federated_database(test_database_url))
