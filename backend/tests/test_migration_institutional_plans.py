"""Tests for migration 0027 (institutional plans, change 45a-planes-modelo-api).

Same scaffolding as ``test_migration_project_kind.py``: every test builds a
DISPOSABLE database next to the configured ``TEST_DATABASE_URL`` (never that
database itself), drives Alembic against it and drops it afterwards. All
synchronous with ``asyncio.run`` + ``@skip_no_db``.

Layers in this file:

1. Migration (slice A1): ``upgrade``/``downgrade`` over a schema seeded by raw
   SQL, plus the two engine-level guards (self-link CHECK, duplicate
   task/activity UNIQUE).
2. DDL equivalence (slice A2, design.md D-B): the schema built by
   ``alembic upgrade head`` and the one built by ``Base.metadata.create_all``
   must declare the same indexes and constraints — ``alembic check`` does not
   compare ``CheckConstraint``, so this is the real gate.
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
_PLANS_DB_NAME = "solercia_test_institutional_plans_migration"
_PLANS_ORM_DB_NAME = "solercia_test_institutional_plans_orm"

PLANS_TABLES = (
    "plans",
    "plan_activities",
    "plan_activity_reports",
    "plan_activity_links",
    "task_plan_activities",
)
PLANS_UNIQUES = {
    "uq_plans_org_code",
    "uq_plan_activities_plan_code",
    "uq_plan_activity_reports_activity_period",
    "uq_plan_activity_links_from_to_type",
    "uq_task_plan_activities_task_activity",
}
PLANS_CHECKS = {"ck_plan_activity_links_no_self"}
PLANS_INDEXES = {
    "ix_plans_organization_id",
    "ix_plans_org_type_year",
    "ix_plan_activities_plan_id",
    "ix_plan_activities_plan_is_mine",
    "ix_plan_activity_reports_plan_activity_id",
    "ix_plan_activity_links_from_activity_id",
    "ix_plan_activity_links_to_activity_id",
    "ix_task_plan_activities_task_id",
    "ix_task_plan_activities_plan_activity_id",
}


# ---------------------------------------------------------------------------
# Scaffolding (same shape as test_migration_project_kind.py)
# ---------------------------------------------------------------------------


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _db_dsn(test_database_url: str, db_name: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{db_name}"


def _async_url(sync_dsn: str) -> str:
    return sync_dsn.replace("postgresql://", "postgresql+asyncpg://")


async def _recreate_database(test_database_url: str, db_name: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()


async def _drop_database(test_database_url: str, db_name: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
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


async def _seed_pre_migration_rows(dsn: str) -> dict:
    """Insert organization + user + project + task via raw SQL (pre-0027).

    ``is_active`` is passed EXPLICITLY everywhere: ``SoftDeleteMixin`` only
    sets a Python-side default, the column has no ``server_default``
    (design.md D-A gotcha).
    """

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations "
            "(id, name, slug, is_active, working_hours_per_day, working_days) "
            "VALUES ($1, $2, $3, true, 8, ARRAY[1,2,3,4,5])",
            org_id,
            "Plans Migration Org",
            f"plans-migration-org-{uuid.uuid4().hex[:12]}",
        )

        user_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users "
            "(id, email, primer_nombre, primer_apellido, is_active) "
            "VALUES ($1, $2, 'Plans', 'Migration', true)",
            user_id,
            f"plans-migration-{uuid.uuid4().hex[:12]}@example.com",
        )

        project_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects "
            "(id, name, methodology, status, code, task_counter, "
            " organization_id, is_active, project_kind) "
            "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true, 'proyecto')",
            project_id,
            "Pre-Plans Project",
            "PPL",
            org_id,
        )

        task_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO tasks "
            "(id, project_id, title, task_type, status, priority, task_order, "
            " risk_flag, is_active) "
            "VALUES ($1, $2, 'Pre-plans task', 'task', 'To Do', 'medium', 0, "
            "        false, true)",
            task_id,
            project_id,
        )

        return {
            "organization_id": org_id,
            "user_id": user_id,
            "project_id": project_id,
            "task_id": task_id,
        }
    finally:
        await conn.close()


async def _seed_plan_with_two_activities(dsn: str, organization_id: uuid.UUID) -> dict:
    """Seed one plan and two activities by raw SQL against the 0027 schema."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        plan_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO plans "
            "(id, organization_id, code, name, plan_type, period_year, status, "
            " is_active) "
            "VALUES ($1, $2, 'PSPI-2026', 'Plan de seguridad', 'pspi', 2026, "
            "        'active', true)",
            plan_id,
            organization_id,
        )
        activity_ids = []
        for code in ("1.1", "1.2"):
            activity_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO plan_activities "
                "(id, plan_id, code, name, is_mine, sort_order, is_active) "
                "VALUES ($1, $2, $3, $4, true, 0, true)",
                activity_id,
                plan_id,
                code,
                f"Actividad {code}",
            )
            activity_ids.append(activity_id)
        return {"plan_id": plan_id, "activity_ids": activity_ids}
    finally:
        await conn.close()


def _build_seeded_database(target: str = "0027") -> tuple[Config, str, dict, dict]:
    """Recreate the disposable DB, upgrade to 0026, seed, then upgrade."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    asyncio.run(_recreate_database(test_database_url, _PLANS_DB_NAME))
    sync_dsn = _db_dsn(test_database_url, _PLANS_DB_NAME)
    cfg = _run_against(_async_url(sync_dsn))

    command.upgrade(cfg, "0026")
    fixtures = asyncio.run(_seed_pre_migration_rows(sync_dsn))
    command.upgrade(cfg, target)

    plan = {}
    if target == "0027":
        plan = asyncio.run(_seed_plan_with_two_activities(sync_dsn, fixtures["organization_id"]))
    return cfg, sync_dsn, fixtures, plan


def _cleanup(original_url: str) -> None:
    from app.config import settings

    settings.DATABASE_URL = original_url
    test_database_url = os.environ["TEST_DATABASE_URL"]
    asyncio.run(_drop_database(test_database_url, _PLANS_DB_NAME))
    asyncio.run(_drop_database(test_database_url, _PLANS_ORM_DB_NAME))


# ---------------------------------------------------------------------------
# Slice A1 — migration 0027
# ---------------------------------------------------------------------------


@skip_no_db
def test_upgrade_adds_the_five_tables_without_touching_existing_rows() -> None:
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        _, sync_dsn, fixtures, _ = _build_seeded_database()

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                tables = {
                    r["table_name"]
                    for r in await conn.fetch(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = ANY($1)",
                        list(PLANS_TABLES),
                    )
                }
                assert tables == set(PLANS_TABLES)

                constraints = await conn.fetch(
                    "SELECT k.conname, k.contype::text AS contype FROM pg_constraint k "
                    "JOIN pg_class t ON t.oid = k.conrelid "
                    "WHERE t.relname = ANY($1)",
                    list(PLANS_TABLES),
                )
                uniques = {c["conname"] for c in constraints if c["contype"] == "u"}
                checks = {c["conname"] for c in constraints if c["contype"] == "c"}
                assert uniques == PLANS_UNIQUES
                assert checks == PLANS_CHECKS

                indexes = {
                    r["indexname"]
                    for r in await conn.fetch(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = ANY($1) "
                        "AND indexname NOT LIKE '%_pkey' "
                        "AND indexname NOT LIKE 'uq_%'",
                        list(PLANS_TABLES),
                    )
                }
                assert indexes == PLANS_INDEXES

                task = await conn.fetchrow(
                    "SELECT id, title, status FROM tasks WHERE id = $1",
                    fixtures["task_id"],
                )
                assert task is not None
                assert task["title"] == "Pre-plans task"
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        _cleanup(original_url)


@skip_no_db
def test_downgrade_drops_the_five_tables_without_losing_seeded_rows() -> None:
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        cfg, sync_dsn, fixtures, _ = _build_seeded_database()
        command.downgrade(cfg, "0026")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                remaining = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = ANY($1)",
                    list(PLANS_TABLES),
                )
                assert remaining == []

                for table, key in (
                    ("organizations", "organization_id"),
                    ("users", "user_id"),
                    ("projects", "project_id"),
                    ("tasks", "task_id"),
                ):
                    row = await conn.fetchrow(
                        f"SELECT id FROM {table} WHERE id = $1", fixtures[key]
                    )
                    assert row is not None, f"{table} lost its seeded row"
            finally:
                await conn.close()

        asyncio.run(_assert())

        # A new upgrade rebuilds an equivalent schema.
        command.upgrade(cfg, "0027")
    finally:
        _cleanup(original_url)


@skip_no_db
def test_self_link_raises_check_violation() -> None:
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        _, sync_dsn, _, plan = _build_seeded_database()
        activity_id = plan["activity_ids"][0]

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                with pytest.raises(asyncpg.exceptions.CheckViolationError):
                    await conn.execute(
                        "INSERT INTO plan_activity_links "
                        "(id, from_activity_id, to_activity_id, link_type, "
                        " resolution) "
                        "VALUES ($1, $2, $2, 'contributes_to', 'manual')",
                        uuid.uuid4(),
                        activity_id,
                    )
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        _cleanup(original_url)


@skip_no_db
def test_duplicate_task_activity_pair_raises_unique_violation() -> None:
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        _, sync_dsn, fixtures, plan = _build_seeded_database()
        activity_id = plan["activity_ids"][0]

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                insert = (
                    "INSERT INTO task_plan_activities "
                    "(id, task_id, plan_activity_id, role) "
                    "VALUES ($1, $2, $3, 'primary')"
                )
                await conn.execute(insert, uuid.uuid4(), fixtures["task_id"], activity_id)
                with pytest.raises(asyncpg.exceptions.UniqueViolationError):
                    await conn.execute(insert, uuid.uuid4(), fixtures["task_id"], activity_id)
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        _cleanup(original_url)


# ---------------------------------------------------------------------------
# Slice A2 — DDL equivalence (design.md D-B)
# ---------------------------------------------------------------------------


async def _collect_plans_ddl(dsn: str) -> dict[str, dict[str, str]]:
    """Normalized index/constraint definitions of the five plans tables."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        index_rows = await conn.fetch(
            "SELECT c.relname AS name, pg_get_indexdef(i.indexrelid) AS definition "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "WHERE t.relname = ANY($1) AND NOT i.indisprimary "
            "AND c.relname NOT LIKE 'uq_%'",
            list(PLANS_TABLES),
        )
        constraint_rows = await conn.fetch(
            "SELECT k.conname AS name, pg_get_constraintdef(k.oid) AS definition "
            "FROM pg_constraint k "
            "JOIN pg_class t ON t.oid = k.conrelid "
            "WHERE t.relname = ANY($1) AND k.contype IN ('u', 'c')",
            list(PLANS_TABLES),
        )
        return {
            "indexes": {r["name"]: r["definition"] for r in index_rows},
            "constraints": {r["name"]: r["definition"] for r in constraint_rows},
        }
    finally:
        await conn.close()


async def _build_orm_schema(test_database_url: str) -> None:
    """pg_trgm -> import app.db_init -> Base.metadata.create_all (D-B order)."""

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    import app.db_init  # noqa: F401  (populates Base.metadata with EVERY model)
    from app.database import Base

    orm_dsn = _db_dsn(test_database_url, _PLANS_ORM_DB_NAME)
    engine = create_async_engine(_async_url(orm_dsn), poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


@skip_no_db
def test_create_all_and_migration_declare_the_same_plans_ddl() -> None:
    from app.config import settings

    original_url = settings.DATABASE_URL
    test_database_url = os.environ["TEST_DATABASE_URL"]
    try:
        # Database 1: schema built by `alembic upgrade head`.
        asyncio.run(_recreate_database(test_database_url, _PLANS_DB_NAME))
        migrated_dsn = _db_dsn(test_database_url, _PLANS_DB_NAME)
        cfg = _run_against(_async_url(migrated_dsn))
        command.upgrade(cfg, "head")

        # Database 2: schema built by the ORM, as the test harness does.
        asyncio.run(_recreate_database(test_database_url, _PLANS_ORM_DB_NAME))
        asyncio.run(_build_orm_schema(test_database_url))

        migrated = asyncio.run(_collect_plans_ddl(migrated_dsn))
        orm = asyncio.run(_collect_plans_ddl(_db_dsn(test_database_url, _PLANS_ORM_DB_NAME)))

        assert set(migrated["indexes"]) == PLANS_INDEXES
        assert set(migrated["constraints"]) == PLANS_UNIQUES | PLANS_CHECKS
        assert orm["indexes"] == migrated["indexes"]
        assert orm["constraints"] == migrated["constraints"]
    finally:
        _cleanup(original_url)
