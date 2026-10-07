"""Migration 0031 (C04): ``ai_provider_settings`` — one row per organization,
defaults, UNIQUE, round trip upgrade/downgrade/upgrade.

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
_DB_NAME = "solercia_test_ai_provider_settings"


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


async def _table_exists(dsn: str) -> bool:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        return bool(await conn.fetchval("SELECT to_regclass('ai_provider_settings') IS NOT NULL"))
    finally:
        await conn.close()


async def _exercise(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations "
            "(id, name, slug, is_active, working_hours_per_day, working_days) "
            "VALUES ($1, 'AI Org', $2, true, 8, ARRAY[1,2,3,4,5])",
            org_id,
            f"ai-org-{uuid.uuid4().hex[:12]}",
        )
        await conn.execute(
            "INSERT INTO ai_provider_settings (id, organization_id, preset, chat_model) "
            "VALUES ($1, $2, 'ollama_local', 'qwen3.5:9b-q4_K_M')",
            uuid.uuid4(),
            org_id,
        )
        row = await conn.fetchrow(
            "SELECT enabled, reasoning_effort, timeout_seconds, max_tokens, temperature, "
            "options::text AS options FROM ai_provider_settings"
        )
        assert row["enabled"] is True and row["reasoning_effort"] == "none"
        assert row["timeout_seconds"] == 60 and row["max_tokens"] == 1024
        assert row["temperature"] == 0 and row["options"] == "{}"
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO ai_provider_settings (id, organization_id, preset, chat_model) "
                "VALUES ($1, $2, 'openai', 'gpt')",
                uuid.uuid4(),
                org_id,
            )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("UPDATE ai_provider_settings SET reasoning_effort = 'maximal'")
    finally:
        await conn.close()


@skip_no_db
def test_0031_round_trip_creates_and_drops_the_table() -> None:
    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    dsn = _server_dsn(test_database_url, _DB_NAME)
    try:
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
        asyncio.run(_admin(test_database_url, f'CREATE DATABASE "{_DB_NAME}"'))
        cfg = _config(dsn.replace("postgresql://", "postgresql+asyncpg://"))
        command.upgrade(cfg, "0030")
        assert asyncio.run(_table_exists(dsn)) is False
        command.upgrade(cfg, "0031")
        asyncio.run(_exercise(dsn))
        command.downgrade(cfg, "0030")
        assert asyncio.run(_table_exists(dsn)) is False
        command.upgrade(cfg, "0031")
        assert asyncio.run(_table_exists(dsn)) is True
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
