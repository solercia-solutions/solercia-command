"""Tests for migration 0023 — dedup del ledger + swap de UNIQUE + limpieza de
árboles duplicados OAP-TI (change 27-plantillas-idempotentes).

Runs against a disposable database (same isolation pattern as
``test_org_member_unique_migration.py``): upgrades to ``0022`` (post
``project_kind``, pre-dedup schema), seeds TWO ledger rows sharing the same
``(organization_id, template_id, node_id)`` with different ``lead_user_id``
and pointing to two DIFFERENT root projects (the real OAP-TI duplicate
shape, design.md Decisión 4), then upgrades to ``0023`` and asserts the
reconciliation (survivor keeps tasks, loser is soft-deleted and its tasks
reassigned, ledger collapses to one row, the new UNIQUE constraint applies).

``reconcile_duplicate_trees`` (the migration's internal dedup function) is
also exercised DIRECTLY — via ``AsyncConnection.run_sync`` (same
sync-bridge Alembic itself uses, ``alembic/env.py::do_run_migrations``) — to
prove a second run is a no-op (T3.4): Alembic never re-applies an already
applied revision, so the only way to exercise "running the cleanup twice"
is to call the underlying function again directly.
"""

import asyncio
import importlib.util
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")

BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEDUP_DB_NAME = "solercia_test_dedup_ledger_reconcile_trees"
_MIGRATION_PATH = (
    BACKEND_DIR / "alembic" / "versions" / "0023_dedup_ledger_reconcile_trees.py"
)


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _dedup_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_DEDUP_DB_NAME}"


async def _recreate_dedup_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_DEDUP_DB_NAME}" WITH (FORCE)')
        await admin_conn.execute(f'CREATE DATABASE "{_DEDUP_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_dedup_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{_DEDUP_DB_NAME}" WITH (FORCE)')
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


def _load_migration_module() -> ModuleType:
    """Load the 0023 migration file directly (its numeric-prefixed filename
    can't be a normal ``import`` target) so ``reconcile_duplicate_trees`` can
    be exercised without going through ``alembic.command`` (T3.4)."""

    spec = importlib.util.spec_from_file_location(
        "migration_0023_dedup_ledger_reconcile_trees", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Seed:
    """Ids created by :func:`_seed_duplicate_oap_ti_trees`, for assertions."""

    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


async def _seed_duplicate_oap_ti_trees(
    dsn: str,
    *,
    survivor_created_at: datetime,
    loser_created_at: datetime,
    survivor_task_count: int,
    loser_task_count: int,
) -> _Seed:
    """Seed one organization + one org-role template (single umbrella node)
    with TWO duplicate ledger rows for that SAME node — two different leads,
    two different root projects — the real OAP-TI duplicate shape (design.md
    Decisión 4). ``survivor_*``/``loser_*`` name which root SHOULD win/lose
    once the reconciliation runs, driven by task count first, age second."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Dedup Trees Org",
            f"dedup-trees-org-{uuid.uuid4().hex[:12]}",
        )

        lead_survivor = uuid.uuid4()
        lead_loser = uuid.uuid4()
        for lead_id, label in ((lead_survivor, "Survivor"), (lead_loser, "Loser")):
            await conn.execute(
                "INSERT INTO users "
                "(id, email, primer_nombre, primer_apellido, hashed_password, is_active) "
                "VALUES ($1, $2, $3, $4, $5, true)",
                lead_id,
                f"dedup-lead-{uuid.uuid4().hex[:12]}@example.com",
                "Dedup",
                label,
                "x",
            )

        template_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO org_role_templates "
            "(id, organization_id, name, is_system, is_active) "
            "VALUES ($1, $2, $3, false, true)",
            template_id,
            org_id,
            "Jefe OAP-TI Dedup",
        )

        node_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO org_role_template_nodes "
            "(id, template_id, parent_node_id, name, default_methodology, node_order) "
            "VALUES ($1, $2, NULL, $3, 'planner', 0)",
            node_id,
            template_id,
            "OAP-TI",
        )

        survivor_project_id = uuid.uuid4()
        loser_project_id = uuid.uuid4()
        for project_id, code, created_at in (
            (survivor_project_id, "SURV", survivor_created_at),
            (loser_project_id, "LOSE", loser_created_at),
        ):
            await conn.execute(
                "INSERT INTO projects "
                "(id, name, methodology, status, code, task_counter, "
                " organization_id, is_active, project_kind, created_at, updated_at) "
                "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true, 'proyecto', $5, $5)",
                project_id,
                "OAP-TI",
                code,
                org_id,
                created_at,
            )

        for project_id, lead_id in (
            (survivor_project_id, lead_survivor),
            (loser_project_id, lead_loser),
        ):
            await conn.execute(
                "INSERT INTO org_role_template_instantiations "
                "(id, organization_id, template_id, node_id, lead_user_id, project_id) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                uuid.uuid4(),
                org_id,
                template_id,
                node_id,
                lead_id,
                project_id,
            )

        for project_id, count in (
            (survivor_project_id, survivor_task_count),
            (loser_project_id, loser_task_count),
        ):
            for i in range(count):
                await conn.execute(
                    "INSERT INTO tasks "
                    "(id, project_id, title, task_type, status, priority, "
                    " task_order, risk_flag, is_active) "
                    "VALUES ($1, $2, $3, 'task', 'Backlog', 'medium', $4, false, true)",
                    uuid.uuid4(),
                    project_id,
                    f"Tarea {i}",
                    i,
                )

        return _Seed(
            organization_id=org_id,
            template_id=template_id,
            node_id=node_id,
            survivor_project_id=survivor_project_id,
            loser_project_id=loser_project_id,
            lead_survivor=lead_survivor,
            lead_loser=lead_loser,
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# T3.1/T3.2/T3.3 — upgrade reconcilia el arbol con tareas, reasigna, soft-delete
# ---------------------------------------------------------------------------


@skip_no_db
def test_upgrade_reassigns_tasks_and_soft_deletes_the_duplicate_keeping_the_tree_with_tasks() -> None:
    """T3.1/T3.2/T3.3: el arbol CON tareas sobrevive activo, las tareas del
    duplicado quedan reasignadas a el, y el duplicado queda soft-deleted —
    spec 'Limpieza reasigna tareas y conserva el arbol con historial'."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_dedup_database(test_database_url))
        dedup_url = _dedup_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _dedup_db_dsn(test_database_url)

        cfg = _run_against(dedup_url)
        command.upgrade(cfg, "0022")

        # The OLDER root has NO tasks; the NEWER root has 3 active tasks —
        # tasks beat age (design.md Decisión 4, "prefiriendo el que tiene
        # tareas en su subárbol").
        seed = asyncio.run(
            _seed_duplicate_oap_ti_trees(
                sync_dsn,
                survivor_created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                loser_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                survivor_task_count=3,
                loser_task_count=0,
            )
        )

        command.upgrade(cfg, "0023")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                survivor = await conn.fetchrow(
                    "SELECT is_active FROM projects WHERE id = $1",
                    seed.survivor_project_id,
                )
                assert survivor is not None
                assert survivor["is_active"] is True

                loser = await conn.fetchrow(
                    "SELECT is_active, deleted_at FROM projects WHERE id = $1",
                    seed.loser_project_id,
                )
                assert loser is not None
                assert loser["is_active"] is False
                assert loser["deleted_at"] is not None

                # Tasks originally on the loser now belong to the survivor.
                remaining_on_loser = await conn.fetch(
                    "SELECT id FROM tasks WHERE project_id = $1", seed.loser_project_id
                )
                assert remaining_on_loser == []
                reassigned = await conn.fetch(
                    "SELECT id FROM tasks WHERE project_id = $1", seed.survivor_project_id
                )
                assert len(reassigned) == 3

                # Ledger collapses to ONE row per (org, template, node),
                # pointing to the survivor with its own lead_user_id.
                ledger_rows = await conn.fetch(
                    "SELECT project_id, lead_user_id "
                    "FROM org_role_template_instantiations "
                    "WHERE organization_id = $1 AND template_id = $2 AND node_id = $3",
                    seed.organization_id,
                    seed.template_id,
                    seed.node_id,
                )
                assert len(ledger_rows) == 1
                assert ledger_rows[0]["project_id"] == seed.survivor_project_id
                assert ledger_rows[0]["lead_user_id"] == seed.lead_survivor

                # New UNIQUE applies without the (already-collapsed) group
                # raising a constraint violation.
                constraint = await conn.fetchrow(
                    "SELECT conname FROM pg_constraint WHERE contype = 'u' "
                    "AND conrelid::regclass::text = 'org_role_template_instantiations' "
                    "AND conname = 'uq_org_role_template_instantiation'"
                )
                assert constraint is not None
                columns = await conn.fetch(
                    "SELECT a.attname FROM pg_constraint c "
                    "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) "
                    "  ON true "
                    "JOIN pg_attribute a ON a.attnum = k.attnum "
                    "  AND a.attrelid = c.conrelid "
                    "WHERE c.conname = 'uq_org_role_template_instantiation' "
                    "ORDER BY k.ord"
                )
                assert [c["attname"] for c in columns] == [
                    "organization_id",
                    "template_id",
                    "node_id",
                ]

                # project_kind backfilled: single-node template -> proyecto
                # (no children in org_role_template_nodes).
                kind_row = await conn.fetchrow(
                    "SELECT project_kind FROM projects WHERE id = $1",
                    seed.survivor_project_id,
                )
                assert kind_row["project_kind"] == "proyecto"
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_dedup_database(test_database_url))


# ---------------------------------------------------------------------------
# T3.4 — ejecutar la limpieza dos veces es un no-op
# ---------------------------------------------------------------------------


@skip_no_db
def test_running_the_cleanup_logic_twice_is_a_noop() -> None:
    """T3.4: invocar ``reconcile_duplicate_trees`` sobre datos YA
    reconciliados no reasigna tareas adicionales ni cambia el estado de
    ningun proyecto — spec 'Ejecutar la limpieza dos veces es un no-op'."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_dedup_database(test_database_url))
        dedup_url = _dedup_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _dedup_db_dsn(test_database_url)

        cfg = _run_against(dedup_url)
        command.upgrade(cfg, "0022")
        seed = asyncio.run(
            _seed_duplicate_oap_ti_trees(
                sync_dsn,
                survivor_created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                loser_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                survivor_task_count=2,
                loser_task_count=0,
            )
        )
        command.upgrade(cfg, "0023")

        module = _load_migration_module()

        async def _run_again() -> None:
            engine = create_async_engine(dedup_url)
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(module.reconcile_duplicate_trees)
            finally:
                await engine.dispose()

        asyncio.run(_run_again())

        async def _assert_unchanged() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                survivor_tasks = await conn.fetch(
                    "SELECT id FROM tasks WHERE project_id = $1",
                    seed.survivor_project_id,
                )
                assert len(survivor_tasks) == 2  # no additional reassignment

                loser = await conn.fetchrow(
                    "SELECT is_active FROM projects WHERE id = $1",
                    seed.loser_project_id,
                )
                assert loser["is_active"] is False  # unchanged, still soft-deleted

                ledger_rows = await conn.fetch(
                    "SELECT project_id FROM org_role_template_instantiations "
                    "WHERE organization_id = $1 AND template_id = $2 AND node_id = $3",
                    seed.organization_id,
                    seed.template_id,
                    seed.node_id,
                )
                assert len(ledger_rows) == 1
                assert ledger_rows[0]["project_id"] == seed.survivor_project_id
            finally:
                await conn.close()

        asyncio.run(_assert_unchanged())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_dedup_database(test_database_url))


# ---------------------------------------------------------------------------
# T3.5 — empate sin criterio determinista se reporta, no se adivina
# ---------------------------------------------------------------------------


@skip_no_db
def test_tie_without_deterministic_survivor_is_reported_not_guessed() -> None:
    """T3.5: dos arboles duplicados con IGUAL antiguedad e IGUAL numero de
    tareas -> ningun soft-delete ocurre, el caso queda sin resolver — spec
    'Empate sin criterio determinista se reporta, no se adivina'."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_dedup_database(test_database_url))
        dedup_url = _dedup_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _dedup_db_dsn(test_database_url)

        cfg = _run_against(dedup_url)
        command.upgrade(cfg, "0022")

        exact_same_instant = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        seed = asyncio.run(
            _seed_duplicate_oap_ti_trees(
                sync_dsn,
                survivor_created_at=exact_same_instant,
                loser_created_at=exact_same_instant,
                survivor_task_count=1,
                loser_task_count=1,
            )
        )

        with pytest.warns(UserWarning):
            command.upgrade(cfg, "0023")

        async def _assert_untouched() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                for project_id in (seed.survivor_project_id, seed.loser_project_id):
                    row = await conn.fetchrow(
                        "SELECT is_active FROM projects WHERE id = $1", project_id
                    )
                    assert row["is_active"] is True  # NINGUN árbol se soft-elimina

                ledger_rows = await conn.fetch(
                    "SELECT project_id FROM org_role_template_instantiations "
                    "WHERE organization_id = $1 AND template_id = $2 AND node_id = $3",
                    seed.organization_id,
                    seed.template_id,
                    seed.node_id,
                )
                assert len(ledger_rows) == 2  # el grupo queda intacto
            finally:
                await conn.close()

        asyncio.run(_assert_untouched())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_dedup_database(test_database_url))


# ---------------------------------------------------------------------------
# T3.6 — downgrade restaura el UNIQUE viejo sin perder filas del ledger
# ---------------------------------------------------------------------------


@skip_no_db
def test_downgrade_restores_the_old_unique_constraint_without_losing_ledger_rows() -> None:
    """T3.6: tras la limpieza, ``downgrade`` restaura
    ``UNIQUE(...,lead_user_id)`` y NINGUNA fila del ledger se pierde — la
    reasignacion de tareas y el soft-delete quedan como no-op documentado,
    sin revertirse (Decisión 3 del design)."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_dedup_database(test_database_url))
        dedup_url = _dedup_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _dedup_db_dsn(test_database_url)

        cfg = _run_against(dedup_url)
        command.upgrade(cfg, "0022")
        seed = asyncio.run(
            _seed_duplicate_oap_ti_trees(
                sync_dsn,
                survivor_created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                loser_created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                survivor_task_count=1,
                loser_task_count=0,
            )
        )
        command.upgrade(cfg, "0023")
        command.downgrade(cfg, "0022")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                columns = await conn.fetch(
                    "SELECT a.attname FROM pg_constraint c "
                    "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) "
                    "  ON true "
                    "JOIN pg_attribute a ON a.attnum = k.attnum "
                    "  AND a.attrelid = c.conrelid "
                    "WHERE c.conname = 'uq_org_role_template_instantiation' "
                    "ORDER BY k.ord"
                )
                assert [c["attname"] for c in columns] == [
                    "organization_id",
                    "template_id",
                    "node_id",
                    "lead_user_id",
                ]

                # The single collapsed row survives the downgrade untouched.
                ledger_rows = await conn.fetch(
                    "SELECT project_id FROM org_role_template_instantiations "
                    "WHERE organization_id = $1 AND template_id = $2 AND node_id = $3",
                    seed.organization_id,
                    seed.template_id,
                    seed.node_id,
                )
                assert len(ledger_rows) == 1
                assert ledger_rows[0]["project_id"] == seed.survivor_project_id
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_dedup_database(test_database_url))
