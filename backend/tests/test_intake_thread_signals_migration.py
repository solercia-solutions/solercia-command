"""Migration 0030 (C03): ``intake_items`` gains ``conversation_id``,
``internet_message_id`` and ``direction`` (indexed), and the data step fills
them from ``raw_payload`` only where the payload already carries them.

Runs on a throwaway database created and dropped by this test inside the
``TEST_DATABASE_URL`` server — never the real one. Plain ``def`` tests because
``alembic.command`` runs its own event loop.
"""

import asyncio
import json
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
_DB_NAME = "solercia_test_intake_thread_signals"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _server_dsn(test_database_url: str, database: str) -> str:
    base, _, _ = _sync_dsn(test_database_url).rpartition("/")
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


async def _seed_items(dsn: str) -> dict[str, uuid.UUID]:
    """Three pre-0030 mail rows: a legacy payload without signals, one whose
    payload already carries them, and a non-mail row that must stay NULL."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations "
            "(id, name, slug, is_active, working_hours_per_day, working_days) "
            "VALUES ($1, $2, $3, true, 8, ARRAY[1,2,3,4,5])",
            org_id,
            "Signals Org",
            f"signals-org-{uuid.uuid4().hex[:12]}",
        )
        connector_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO connectors (id, organization_id, provider, status, is_active) "
            "VALUES ($1, $2, 'solercia_connect', 'active', true)",
            connector_id,
            org_id,
        )
        payloads = {
            "legacy": ("email", {"external_id": "legacy", "subject": "s", "body_text": "b"}),
            "carrying": (
                "email",
                {
                    "external_id": "carrying",
                    "conversation_id": "CONV-7",
                    "internet_message_id": "<m7@entidad>",
                    "direction": "outbound",
                },
            ),
            "bogus": ("email", {"external_id": "bogus", "direction": "sideways"}),
            "event": ("calendar_event", {"external_id": "event", "conversation_id": "NOPE"}),
        }
        ids: dict[str, uuid.UUID] = {}
        for name, (item_type, payload) in payloads.items():
            ids[name] = uuid.uuid4()
            await conn.execute(
                "INSERT INTO intake_items (id, organization_id, source_provider, connector_id, "
                "item_type, external_id, title, origin_actor, occurred_at, raw_payload, status, "
                "is_active, created_at, updated_at) VALUES ($1, $2, 'solercia_connect', $3, $4, "
                "$5, 't', 'a@b', now(), $6::jsonb, 'pending', true, now(), now())",
                ids[name],
                org_id,
                connector_id,
                item_type,
                name,
                json.dumps(payload),
            )
        return ids
    finally:
        await conn.close()


async def _signals(dsn: str) -> dict[uuid.UUID, tuple]:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch(
            "SELECT id, conversation_id, internet_message_id, direction, raw_payload::text "
            "FROM intake_items"
        )
        return {row["id"]: tuple(row)[1:] for row in rows}
    finally:
        await conn.close()


async def _indexes(dsn: str) -> set[str]:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'intake_items'")
        return {row["indexname"] for row in rows}
    finally:
        await conn.close()


async def _columns(dsn: str) -> set[str]:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'intake_items'"
        )
        return {row["column_name"] for row in rows}
    finally:
        await conn.close()


_NEW_INDEXES = {
    "ix_intake_items_org_conversation",
    "ix_intake_items_org_internet_message",
    "ix_intake_items_direction",
}


@skip_no_db
def test_upgrade_adds_indexed_signals_and_backfills_only_what_the_payload_carries() -> None:
    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    dsn = _server_dsn(test_database_url, _DB_NAME)
    try:
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
        asyncio.run(_admin(test_database_url, f'CREATE DATABASE "{_DB_NAME}"'))
        cfg = _config(dsn.replace("postgresql://", "postgresql+asyncpg://"))
        command.upgrade(cfg, "0029")
        ids = asyncio.run(_seed_items(dsn))
        before = asyncio.run(_signals_payloads(dsn))

        command.upgrade(cfg, "0030")

        signals = asyncio.run(_signals(dsn))
        assert signals[ids["legacy"]][:3] == (None, None, None)
        assert signals[ids["carrying"]][:3] == ("CONV-7", "<m7@entidad>", "outbound")
        # An unknown direction is never copied; non-mail rows are untouched.
        assert signals[ids["bogus"]][2] is None
        assert signals[ids["event"]][:3] == (None, None, None)
        # The payload itself is never rewritten by the data step.
        assert {key: value[3] for key, value in signals.items()} == before
        assert _NEW_INDEXES <= asyncio.run(_indexes(dsn))

        # Round trip: downgrade leaves no residue and a re-upgrade rebuilds the
        # same signals from the untouched payloads.
        command.downgrade(cfg, "0029")
        assert not {"conversation_id", "internet_message_id", "direction"} & asyncio.run(
            _columns(dsn)
        )
        assert not _NEW_INDEXES & asyncio.run(_indexes(dsn))
        command.upgrade(cfg, "0030")
        assert asyncio.run(_signals(dsn)) == signals
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_admin(test_database_url, f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))


async def _signals_payloads(dsn: str) -> dict[uuid.UUID, str]:
    conn = await asyncpg.connect(dsn=dsn)
    try:
        rows = await conn.fetch("SELECT id, raw_payload::text AS payload FROM intake_items")
        return {row["id"]: row["payload"] for row in rows}
    finally:
        await conn.close()
