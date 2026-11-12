"""Tests for migration 0022 (``projects.project_kind``, change
27-plantillas-idempotentes).

Two layers, same file (tasks.md Fase 1):

1. A fast API-level RED (T1.1): ``POST /projects`` without a template must
   create the project with ``project_kind = proyecto`` — fails TODAY because
   ``Project``/``ProjectRead`` do not expose the field yet.
2. The isolated migration test (T1.4), same pattern as
   ``test_project_hierarchy_migration.py``/``test_org_role_templates_
   migration.py``: a disposable database upgrades to ``0021`` (pre-column
   schema), seeds a project via raw SQL, upgrades to ``0022`` and asserts the
   column is ``NOT NULL`` with every pre-existing row backfilled to
   ``'proyecto'``, then downgrades and asserts the column is gone without
   losing the row.
"""

import asyncio
import os
import uuid
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from httpx import AsyncClient

from alembic import command

try:
    from tests.conftest import skip_no_db
except ImportError:
    skip_no_db = pytest.mark.skip(reason="conftest not found")

BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_KIND_DB_NAME = "solercia_test_project_kind_migration"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# T1.1 — RED rápido a nivel API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_project_create_defaults_to_proyecto_when_column_is_missing_or_omitted(
    client: AsyncClient, tenant, user
) -> None:
    """``POST /projects`` sin plantilla crea el proyecto con
    ``project_kind = proyecto`` — specs/projects/spec.md (delta)."""

    _, token = user

    response = await client.post(
        "/projects",
        json={"name": "Sin Plantilla Kind", "methodology": "planner"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["project_kind"] == "proyecto"


# ---------------------------------------------------------------------------
# T1.4 — migración aislada 0022 (aditiva y reversible)
# ---------------------------------------------------------------------------


def _sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _admin_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/postgres"


def _project_kind_db_dsn(test_database_url: str) -> str:
    dsn = _sync_dsn(test_database_url)
    base, _, _ = dsn.rpartition("/")
    return f"{base}/{_PROJECT_KIND_DB_NAME}"


async def _recreate_project_kind_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_PROJECT_KIND_DB_NAME}" WITH (FORCE)'
        )
        await admin_conn.execute(f'CREATE DATABASE "{_PROJECT_KIND_DB_NAME}"')
    finally:
        await admin_conn.close()


async def _drop_project_kind_database(test_database_url: str) -> None:
    admin_conn = await asyncpg.connect(dsn=_admin_dsn(test_database_url))
    try:
        await admin_conn.execute(
            f'DROP DATABASE IF EXISTS "{_PROJECT_KIND_DB_NAME}" WITH (FORCE)'
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


async def _seed_pre_migration_project(dsn: str) -> dict:
    """Insert an organization + a project via raw SQL against the pre-0022
    schema (no ``project_kind`` yet)."""

    conn = await asyncpg.connect(dsn=dsn)
    try:
        org_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id, name, slug, is_active) "
            "VALUES ($1, $2, $3, true)",
            org_id,
            "Project Kind Migration Org",
            f"project-kind-migration-org-{uuid.uuid4().hex[:12]}",
        )

        project_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO projects "
            "(id, name, methodology, status, code, task_counter, "
            " organization_id, is_active) "
            "VALUES ($1, $2, 'planner', 'active', $3, 0, $4, true)",
            project_id,
            "Pre-ProjectKind Project",
            "PPK",
            org_id,
        )

        return {"organization_id": org_id, "project_id": project_id}
    finally:
        await conn.close()


@skip_no_db
def test_upgrade_backfills_existing_projects_to_proyecto_without_losing_rows() -> None:
    """T1.4: upgrade to 0022 adds ``project_kind NOT NULL``; the pre-existing
    row is backfilled to ``'proyecto'``."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_project_kind_database(test_database_url))
        project_kind_url = _project_kind_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _project_kind_db_dsn(test_database_url)

        cfg = _run_against(project_kind_url)
        command.upgrade(cfg, "0021")

        fixtures = asyncio.run(_seed_pre_migration_project(sync_dsn))

        command.upgrade(cfg, "0022")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                column = await conn.fetchrow(
                    "SELECT column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'project_kind'"
                )
                assert column is not None
                assert column["is_nullable"] == "NO"

                row = await conn.fetchrow(
                    "SELECT project_kind FROM projects WHERE id = $1",
                    fixtures["project_id"],
                )
                assert row is not None
                assert row["project_kind"] == "proyecto"
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_project_kind_database(test_database_url))


@skip_no_db
def test_downgrade_removes_project_kind_column_without_losing_rows() -> None:
    """T1.4: downgrade() drops the column cleanly; zero rows lost."""

    test_database_url = os.environ["TEST_DATABASE_URL"]
    from app.config import settings

    original_url = settings.DATABASE_URL
    try:
        asyncio.run(_recreate_project_kind_database(test_database_url))
        project_kind_url = _project_kind_db_dsn(test_database_url).replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        sync_dsn = _project_kind_db_dsn(test_database_url)

        cfg = _run_against(project_kind_url)
        command.upgrade(cfg, "0021")
        fixtures = asyncio.run(_seed_pre_migration_project(sync_dsn))
        command.upgrade(cfg, "0022")
        command.downgrade(cfg, "0021")

        async def _assert() -> None:
            conn = await asyncpg.connect(dsn=sync_dsn)
            try:
                column = await conn.fetchrow(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'projects' AND column_name = 'project_kind'"
                )
                assert column is None

                row = await conn.fetchrow(
                    "SELECT id FROM projects WHERE id = $1", fixtures["project_id"]
                )
                assert row is not None
            finally:
                await conn.close()

        asyncio.run(_assert())
    finally:
        settings.DATABASE_URL = original_url
        asyncio.run(_drop_project_kind_database(test_database_url))
