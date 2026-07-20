"""Tests for migration 0021 — dedup + unique ``(organization_id, user_id)``.

Runs against a disposable database (same isolation pattern as
``test_boards_backfill_migration.py``): upgrades to ``0020`` (pre-unique
schema), seeds duplicate ``organization_members`` rows with raw SQL, then
upgrades to ``0021`` and asserts the dedup + constraint (multi-tenancy spec,
"Unicidad de membresía por empresa y usuario").
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
_MIGRATION_DB_NAME = "solercia_test_org_member_unique"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _migration_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_MIGRATION_DB_NAME}"


async def _recreate_migration_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_MIGRATION_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_MIGRATION_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_migration_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_MIGRATION_DB_NAME}" WITH (FORCE)'
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


async def _seed_duplicate_membership(dsn: str) -> dict:
    """Insert one org, one user, and TWO duplicate ``(org, user)`` rows in
    ``organization_members`` with distinct ``created_at`` and role, using raw
    SQL against the pre-0021 (post-0020) schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Dedup Org",
            f"dedup-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, is_active) "
            "VALUES ($1, $2, 'Dedup', 'User', true)",
            user_id,
            f"dedup-{uuid.uuid4().hex[:12]}@example.com",
        )

        older_row_id = uuid.uuid4()
        newer_row_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organization_members "
            "(id, organization_id, user_id, role, created_at) "
            "VALUES ($1, $2, $3, 'admin', now() - interval '1 day')",
            older_row_id,
            org_id,
            user_id,
        )
        await conn.execute(
            "INSERT INTO organization_members "
            "(id, organization_id, user_id, role, created_at) "
            "VALUES ($1, $2, $3, 'member', now())",
            newer_row_id,
            org_id,
            user_id,
        )

        return {
            "organization_id": org_id,
            "user_id": user_id,
            "older_row_id": older_row_id,
            "newer_row_id": newer_row_id,
        }
    finally:
        await conn.close()


@skip_no_db
def test_dedup_keeps_the_oldest_membership_row() -> None:
    """T2.1: after upgrading to 0021, only the oldest duplicate row survives."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_migration_database(test_database_url))
        migration_url = _migration_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _migration_db_dsn(test_database_url)

        cfg = _run_against(migration_url)
        command.upgrade(cfg, "0020")

        fixtures = asyncio.run(_seed_duplicate_membership(sync_dsn))

        command.upgrade(cfg, "0021")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                rows = await conn.fetch(
                    "SELECT id, role FROM organization_members "
                    "WHERE organization_id = $1 AND user_id = $2",
                    fixtures["organization_id"],
                    fixtures["user_id"],
                )
                assert len(rows) == 1
                assert rows[0]["id"] == fixtures["older_row_id"]
                assert rows[0]["role"] == "admin"
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_migration_database(test_database_url))


@skip_no_db
def test_unique_constraint_rejects_new_duplicate_after_upgrade() -> None:
    """T2.2: once 0021 is applied, the DB itself rejects another duplicate."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_migration_database(test_database_url))
        migration_url = _migration_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _migration_db_dsn(test_database_url)

        cfg = _run_against(migration_url)
        command.upgrade(cfg, "0020")
        fixtures = asyncio.run(_seed_duplicate_membership(sync_dsn))
        command.upgrade(cfg, "0021")

        async def _assert_rejected() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                with pytest.raises(asyncpg.UniqueViolationError):
                    await conn.execute(
                        "INSERT INTO organization_members "
                        "(id, organization_id, user_id, role, created_at) "
                        "VALUES ($1, $2, $3, 'viewer', now())",
                        uuid.uuid4(),
                        fixtures["organization_id"],
                        fixtures["user_id"],
                    )
            finally:
                await conn.close()

        asyncio.run(_assert_rejected())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_migration_database(test_database_url))


@skip_no_db
def test_downgrade_removes_constraint_without_losing_rows() -> None:
    """T2.3: downgrade to 0020 drops the constraint; row count is unchanged."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_migration_database(test_database_url))
        migration_url = _migration_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _migration_db_dsn(test_database_url)

        cfg = _run_against(migration_url)
        command.upgrade(cfg, "0020")
        fixtures = asyncio.run(_seed_duplicate_membership(sync_dsn))
        command.upgrade(cfg, "0021")

        async def _count_rows() -> int:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                rows = await conn.fetch(
                    "SELECT id FROM organization_members "
                    "WHERE organization_id = $1 AND user_id = $2",
                    fixtures["organization_id"],
                    fixtures["user_id"],
                )
                return len(rows)
            finally:
                await conn.close()

        post_dedup_count = asyncio.run(_count_rows())

        command.downgrade(cfg, "0020")

        async def _assert_downgrade() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                constraints = await conn.fetch(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conname = 'uq_organization_members_org_user'"
                )
                assert constraints == []

                rows = await conn.fetch(
                    "SELECT id FROM organization_members "
                    "WHERE organization_id = $1 AND user_id = $2",
                    fixtures["organization_id"],
                    fixtures["user_id"],
                )
                assert len(rows) == post_dedup_count
            finally:
                await conn.close()

        asyncio.run(_assert_downgrade())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_migration_database(test_database_url))
