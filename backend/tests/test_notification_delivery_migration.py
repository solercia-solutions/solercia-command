"""Tests for migration ``0013`` (rename ``email_outbox`` -> ``notification_deliveries``,
change 12-notification-hub, Fase 1).

Runs against a disposable database (created and dropped by this test, same
isolation pattern as ``test_boards_backfill_migration.py``): upgrades to
``0012`` (pre-rename schema), inserts a pre-migration ``email_outbox`` row
with raw SQL (typed columns: ``recipient_email``/``subject``/``text_body``/
``html_body``), then upgrades to ``0013`` and asserts the row survives in
``notification_deliveries`` with ``channel='email'`` and ``payload``
populated from those same typed columns, which no longer exist. Finally
downgrades back to ``0012`` and asserts the typed columns are restored with
the SAME values, with zero rows lost.

Test functions are plain ``def`` (NOT ``async def``), same as
``test_boards_backfill_migration.py``: ``alembic.command.upgrade``/
``downgrade`` call ``asyncio.run()`` internally (see ``alembic/env.py``),
which cannot nest inside an already-running pytest-asyncio event loop.
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
_MIGRATION_DB_NAME = "solercia_test_notification_delivery_migration"


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


async def _seed_pre_migration_row(dsn: str) -> dict:
    """Insert an organization + one live ``email_outbox`` row via raw SQL
    against the pre-rename (post-0012) schema. Returns the generated ids and
    the exact field values inserted, for later comparison."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Delivery Migration Org",
            f"delivery-migration-org-{uuid.uuid4().hex[:12]}",
        )

        row_id = uuid.uuid4()
        fields = {
            "recipient_email": "pre-migration@example.com",
            "subject": "Asunto pre-migración",
            "text_body": "Cuerpo de texto pre-migración.",
            "html_body": "<p>Cuerpo HTML pre-migración.</p>",
            "dedup_key": f"immediate:pre-migration-{uuid.uuid4().hex[:8]}",
        }
        await conn.execute(
            "INSERT INTO email_outbox "
            "(id, organization_id, notification_id, recipient_email, subject, "
            " text_body, html_body, dedup_key, status, attempts) "
            "VALUES ($1, $2, NULL, $3, $4, $5, $6, $7, 'pending', 0)",
            row_id,
            org_id,
            fields["recipient_email"],
            fields["subject"],
            fields["text_body"],
            fields["html_body"],
            fields["dedup_key"],
        )

        return {"organization_id": org_id, "row_id": row_id, "fields": fields}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_renames_table_and_populates_payload_dropping_typed_columns() -> None:
    """T1.3 (upgrade half): the row survives the rename with ``channel='email'``
    and ``payload`` populated from the 4 typed columns, which no longer exist."""

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
        command.upgrade(cfg, "0012")

        seeded = asyncio.run(_seed_pre_migration_row(sync_dsn))

        command.upgrade(cfg, "0013")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT channel, payload, dedup_key, status FROM "
                    "notification_deliveries WHERE id = $1",
                    seeded["row_id"],
                )
                assert row is not None
                assert row["channel"] == "email"
                assert row["dedup_key"] == seeded["fields"]["dedup_key"]
                assert row["status"] == "pending"

                import json

                payload = json.loads(row["payload"])
                assert payload["recipient_email"] == seeded["fields"]["recipient_email"]
                assert payload["subject"] == seeded["fields"]["subject"]
                assert payload["text_body"] == seeded["fields"]["text_body"]
                assert payload["html_body"] == seeded["fields"]["html_body"]

                dropped_columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'notification_deliveries' "
                    "AND column_name IN "
                    "('recipient_email', 'subject', 'text_body', 'html_body')"
                )
                assert dropped_columns == []

                old_table = await conn.fetch(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename = 'email_outbox'"
                )
                assert old_table == []
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_migration_database(test_database_url))


@skip_no_db
def test_downgrade_restores_typed_columns_with_same_values_no_row_lost() -> None:
    """T1.3 (downgrade half): downgrading to 0012 re-adds the typed columns,
    back-filled from ``payload`` with the ORIGINAL values, drops
    ``channel``/``payload`` and renames the table back — zero rows lost."""

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
        command.upgrade(cfg, "0012")
        seeded = asyncio.run(_seed_pre_migration_row(sync_dsn))
        command.upgrade(cfg, "0013")
        command.downgrade(cfg, "0012")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT recipient_email, subject, text_body, html_body, "
                    "dedup_key, status FROM email_outbox WHERE id = $1",
                    seeded["row_id"],
                )
                assert row is not None
                assert row["recipient_email"] == seeded["fields"]["recipient_email"]
                assert row["subject"] == seeded["fields"]["subject"]
                assert row["text_body"] == seeded["fields"]["text_body"]
                assert row["html_body"] == seeded["fields"]["html_body"]
                assert row["dedup_key"] == seeded["fields"]["dedup_key"]

                dropped_columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'email_outbox' "
                    "AND column_name IN ('channel', 'payload')"
                )
                assert dropped_columns == []

                remaining_rows = await conn.fetch("SELECT id FROM email_outbox")
                assert len(remaining_rows) == 1
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_migration_database(test_database_url))
