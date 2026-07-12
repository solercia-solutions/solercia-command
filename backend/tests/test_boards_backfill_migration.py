"""Tests for the boards backfill (Batch E — migration 0003's SECOND commit).

Runs against a disposable database (created and dropped by this test, same
isolation pattern as ``test_migrations_baseline.py``): upgrades to ``0002``
(pre-boards schema), inserts pre-migration fixtures with raw SQL (projects
with no board, tasks with varied ``status``), then upgrades to ``0003`` and
asserts the backfilled state (tasks.md delta, "Backfill de tareas existentes
a columnas por status").

Test functions are plain ``def`` (NOT ``async def``), same as
``test_migrations_baseline.py``: ``alembic.command.upgrade``/``downgrade``
call ``asyncio.run()`` internally (see ``alembic/env.py``), which cannot
nest inside an already-running pytest-asyncio event loop.
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
_BACKFILL_DB_NAME = "solercia_test_boards_backfill"


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _backfill_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_BACKFILL_DB_NAME}"


async def _recreate_backfill_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_BACKFILL_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_BACKFILL_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_backfill_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_BACKFILL_DB_NAME}" WITH (FORCE)'
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


async def _seed_pre_migration_fixtures(dsn: str) -> dict:
    """Insert an organization, 4 projects (one per methodology) and tasks
    with a mix of matching and non-matching ``status`` values, using RAW SQL
    against the pre-boards (post-0002) schema. Returns the generated ids.
    """

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Backfill Org",
            f"backfill-org-{uuid.uuid4().hex[:12]}",
        )

        project_ids: dict[str, uuid.UUID] = {}
        for methodology, code in (
            ("planner", "PLB"),
            ("kanban", "KLB"),
            ("scrum", "SLB"),
            ("custom", "CLB"),
        ):
            project_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO projects "
                "(id, name, methodology, status, code, task_counter, "
                " organization_id, is_active) "
                "VALUES ($1, $2, $3, 'active', $4, 0, $5, true)",
                project_id,
                f"{methodology.title()} Backfill Project",
                methodology,
                code,
                org_id,
            )
            project_ids[methodology] = project_id

        task_ids: dict[str, uuid.UUID] = {}

        async def _insert_task(project_id: uuid.UUID, status: str, label: str) -> None:
            task_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO tasks "
                "(id, project_id, title, task_type, status, priority, "
                " task_order, risk_flag, is_active) "
                "VALUES ($1, $2, $3, 'task', $4, 'medium', 0, false, true)",
                task_id,
                project_id,
                f"Task {label}",
                status,
            )
            task_ids[label] = task_id

        # Direct match: kanban task already sitting in "Done".
        await _insert_task(project_ids["kanban"], "Done", "kanban_done")
        # No match: legacy/archived status not among kanban's seeded columns.
        await _insert_task(project_ids["kanban"], "archived", "kanban_archived")
        # Direct match: scrum task in "In Progress".
        await _insert_task(project_ids["scrum"], "In Progress", "scrum_in_progress")
        # Custom project task: board will have ZERO columns after backfill.
        await _insert_task(project_ids["custom"], "todo", "custom_todo")

        return {"organization_id": org_id, "projects": project_ids, "tasks": task_ids}
    finally:
        await conn.close()


@skip_no_db
def test_backfill_assigns_board_column_id_by_status_match_and_fallback() -> None:
    """T34/T36: direct status match, fallback-to-first-column, and NULL for custom."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_backfill_database(test_database_url))
        backfill_url = _backfill_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _backfill_db_dsn(test_database_url)

        cfg = _run_against(backfill_url)
        command.upgrade(cfg, "0002")

        fixtures = asyncio.run(_seed_pre_migration_fixtures(sync_dsn))

        command.upgrade(cfg, "0003")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                # Every project (including custom) gets exactly one board.
                board_rows = await conn.fetch(
                    "SELECT project_id, id FROM boards "
                    "WHERE project_id = ANY($1::uuid[])",
                    list(fixtures["projects"].values()),
                )
                assert len(board_rows) == 4
                board_by_project = {row["project_id"]: row["id"] for row in board_rows}

                # kanban board has 3 columns, verbatim, in order.
                kanban_columns = await conn.fetch(
                    "SELECT name, status_key, column_order FROM board_columns "
                    "WHERE board_id = $1 ORDER BY column_order",
                    board_by_project[fixtures["projects"]["kanban"]],
                )
                assert [r["status_key"] for r in kanban_columns] == [
                    "Backlog",
                    "Doing",
                    "Done",
                ]

                # custom board has ZERO columns.
                custom_columns = await conn.fetch(
                    "SELECT id FROM board_columns WHERE board_id = $1",
                    board_by_project[fixtures["projects"]["custom"]],
                )
                assert custom_columns == []

                # Direct match: kanban_done -> the "Done" column.
                done_column_row = await conn.fetchrow(
                    "SELECT id FROM board_columns "
                    "WHERE board_id = $1 AND status_key = 'Done'",
                    board_by_project[fixtures["projects"]["kanban"]],
                )
                row = await conn.fetchrow(
                    "SELECT board_column_id FROM tasks WHERE id = $1",
                    fixtures["tasks"]["kanban_done"],
                )
                assert row["board_column_id"] == done_column_row["id"]

                # No match: kanban_archived -> first column by order ("Backlog").
                backlog_column_row = await conn.fetchrow(
                    "SELECT id FROM board_columns "
                    "WHERE board_id = $1 AND status_key = 'Backlog'",
                    board_by_project[fixtures["projects"]["kanban"]],
                )
                row = await conn.fetchrow(
                    "SELECT board_column_id FROM tasks WHERE id = $1",
                    fixtures["tasks"]["kanban_archived"],
                )
                assert row["board_column_id"] == backlog_column_row["id"]

                # Direct match: scrum_in_progress -> "In Progress" column.
                scrum_in_progress_row = await conn.fetchrow(
                    "SELECT id FROM board_columns "
                    "WHERE board_id = $1 AND status_key = 'In Progress'",
                    board_by_project[fixtures["projects"]["scrum"]],
                )
                row = await conn.fetchrow(
                    "SELECT board_column_id FROM tasks WHERE id = $1",
                    fixtures["tasks"]["scrum_in_progress"],
                )
                assert row["board_column_id"] == scrum_in_progress_row["id"]

                # custom project's task: board has no columns -> NULL.
                row = await conn.fetchrow(
                    "SELECT board_column_id, status FROM tasks WHERE id = $1",
                    fixtures["tasks"]["custom_todo"],
                )
                assert row["board_column_id"] is None
                assert row["status"] == "todo"  # status itself is untouched
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_backfill_database(test_database_url))


@skip_no_db
def test_backfill_downgrade_reverts_boards_cleanly() -> None:
    """T38: downgrade() removes board_column_id, board_columns and boards cleanly."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_backfill_database(test_database_url))
        backfill_url = _backfill_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _backfill_db_dsn(test_database_url)

        cfg = _run_against(backfill_url)
        command.upgrade(cfg, "0002")
        asyncio.run(_seed_pre_migration_fixtures(sync_dsn))
        command.upgrade(cfg, "0003")
        command.downgrade(cfg, "0002")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                tables = await conn.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename IN ('boards', 'board_columns')"
                )
                assert tables == []

                columns = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'tasks' AND column_name = 'board_column_id'"
                )
                assert columns == []

                # Original task rows survive the round trip.
                remaining_tasks = await conn.fetch("SELECT status FROM tasks")
                assert len(remaining_tasks) == 4
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_backfill_database(test_database_url))
