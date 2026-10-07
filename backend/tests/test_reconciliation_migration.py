"""Migration 0032 (C05): ``task_embeddings`` and ``intake_proposals`` —
constraints and round trip upgrade/downgrade/upgrade.

Runs on a throwaway database created and dropped by this test inside the
``TEST_DATABASE_URL`` server — never the real one. Plain ``def`` tests because
``alembic.command`` runs its own event loop.
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
_DB_NAME = "solercia_test_reconciliation"
_TABLES = ("task_embeddings", "intake_proposals")


def _server_dsn(test_database_url: str, database: str) -> str:
    base, _, _ = test_database_url.replace("postgresql+asyncpg://", "postgresql://").rpartition("/")
    return f"{base}/{database}"


async def _admin(test_database_url: str, statement: str) -> None:
    conn = await asyncpg.connect(dsn=_server_dsn(test_database_url, "postgres"))
    try:
        await conn.execute(statement)
    finally:
        await conn.close()


def _config(async_url: str) -> Config:
    from app.config import settings

    settings.DATABASE_URL = async_url
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", async_url)
    return cfg


async def _tables(dsn: str) -> set[str]:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        return {t for t in _TABLES if await conn.fetchval("SELECT to_regclass($1)", t)}
    finally:
        await conn.close()


async def _exercise(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations "
            "(id, name, slug, is_active, working_hours_per_day, working_days) "
            "VALUES ($1, 'Org', $2, true, 8, ARRAY[1,2,3,4,5])",
            org_id,
            f"org-{uuid.uuid4().hex[:12]}",
        )
        insert = (
            "INSERT INTO intake_proposals (id, organization_id, conversation_key, subject, "
            "item_ids, message_count, last_message_at, thread_state, status) "
            "VALUES ($1, $2, 'conv:x', 's', '[]', 1, now(), 'respondido', $3)"
        )
        await conn.execute(insert, uuid.uuid4(), org_id, "descartada")
        await conn.execute(insert, uuid.uuid4(), org_id, "propuesta")
        row = await conn.fetchrow("SELECT candidates::text AS c FROM intake_proposals LIMIT 1")
        assert row["c"] == "[]"
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(insert, uuid.uuid4(), org_id, "propuesta")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(insert, uuid.uuid4(), org_id, "otra")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("UPDATE intake_proposals SET relation = 'quizas'")
    finally:
        await conn.close()


@skip_no_db
def test_0032_round_trip_creates_and_drops_the_tables() -> None:
    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    dsn = _server_dsn(test_database_url, _DB_NAME)
    try:
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
        asyncio.run(_admin(test_database_url, f'CREATE DATABASE "{_DB_NAME}"'))
        cfg = _config(dsn.replace("postgresql://", "postgresql+asyncpg://"))
        command.upgrade(cfg, "0031")
        assert asyncio.run(_tables(dsn)) == set()
        command.upgrade(cfg, "0032")
        asyncio.run(_exercise(dsn))
        command.downgrade(cfg, "0031")
        assert asyncio.run(_tables(dsn)) == set()
        command.upgrade(cfg, "0032")
        assert asyncio.run(_tables(dsn)) == set(_TABLES)
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
