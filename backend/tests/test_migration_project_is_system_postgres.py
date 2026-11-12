"""Disposable-only migration characterization; never uses conftest's engine.

Launch each PostgreSQL file separately. The owning launcher must attest the
container identity before setting SOLERCIA_DISPOSABLE_TEST to its UUID hex run
ID and SOLERCIA_DISPOSABLE_TEST_PORT to its captured localhost port. Both URL
variables must be identical, with synthetic command_test user/database and a
32-128 character hex password. No URL defaults, query overrides or dotenv.

Migration functions run through Alembic Operations on a fresh schema, not
through env.py (which imports provider registries via app.db_init). This tests
actual revision DDL/data operations, not env.py wiring or autogenerate parity;
test_migrations_baseline.py remains the separate serial check for that.
Schemas live until the owning launcher removes its disposable container.
"""

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import pytest


def disposable_url():
    """Refuse before importing application settings or constructing an engine."""
    marker = os.environ.get("SOLERCIA_DISPOSABLE_TEST")
    if not marker:
        pytest.skip("Explicit disposable PostgreSQL target required", allow_module_level=True)
    url = os.environ.get("TEST_DATABASE_URL", "")
    port = os.environ.get("SOLERCIA_DISPOSABLE_TEST_PORT", "")
    valid = False
    try:
        parsed = urlsplit(url)
        valid = bool(
            re.fullmatch(r"[0-9a-f]{32}", marker)
            and port.isascii() and port.isdecimal() and 1024 < int(port) <= 65535
            and int(port) != 5432
            and url == os.environ.get("DATABASE_URL")
            and parsed.scheme == "postgresql+asyncpg"
            and parsed.hostname == "127.0.0.1"
            and parsed.port == int(port)
            and parsed.username == "command_test"
            and re.fullmatch(r"[0-9a-f]{32,128}", parsed.password or "")
            and parsed.path == "/command_test"
            and not parsed.query and not parsed.fragment
            and parsed.netloc == f"command_test:{parsed.password}@127.0.0.1:{port}"
        )
    except (ValueError, TypeError):
        pass
    if not valid:
        raise pytest.UsageError("Refusing unverified disposable PostgreSQL target")
    return url


# Deliberately before SQLAlchemy, Alembic and all application imports.
disposable_url()


def safe_settings():
    """Disable dotenv BEFORE Settings() and verify its resolved URL, never log it.

    Fresh subprocess per file is required. A launcher that imports app.config
    early is rejected, rather than retroactively trusting a settings singleton
    that might already have read secrets. conftest imports no app modules at
    collection time; none of its database/client fixtures are requested here.
    """
    from unittest.mock import patch

    from pydantic_settings import BaseSettings

    url = disposable_url()
    if "app.config" in sys.modules:
        raise pytest.UsageError("Application settings imported before disposable guard")
    original_init = BaseSettings.__init__

    def without_files(self, *args, **kwargs):
        kwargs["_env_file"] = None
        kwargs["_secrets_dir"] = None
        original_init(self, *args, **kwargs)

    with patch.object(BaseSettings, "__init__", without_files):
        from app.config import settings

    if settings.DATABASE_URL != url:
        raise pytest.UsageError("Resolved settings do not match disposable target")
    if settings.EMAIL_ENABLED or settings.EMAIL_BACKEND != "console" or settings.LLM_PROVIDER != "fake":
        raise pytest.UsageError("Disposable tests require disabled external delivery")
    return url


@pytest.fixture(scope="module")
def target_url():
    return safe_settings()


async def new_schema_engine(url):
    """Only explicit guarded URL; no global application engine or create_all."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    if disposable_url() != url:
        raise pytest.UsageError("Disposable target changed")
    schema = "system_test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool, hide_parameters=True,
                                connect_args={"timeout": 5, "command_timeout": 30})
    try:
        async with admin.begin() as connection:
            identity = (await connection.execute(text(
                "SELECT current_database(), current_user"
            ))).one()
            if tuple(identity) != ("command_test", "command_test"):
                raise pytest.UsageError("Unexpected disposable database identity")
            # Shared extension only; every tested table starts in an empty schema.
            await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public"))
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        await admin.dispose()
    return create_async_engine(
        url, poolclass=NullPool, hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 30, "server_settings": {
            "search_path": f"{schema},public", "lock_timeout": "8000",
            "statement_timeout": "15000",
        }},
    )


async def migrate(engine, target, *, current="base"):
    """Execute the real revision chain with Alembic's public operation context.

    Deliberately no synthetic alembic_version stamping: caller supplies the
    observed previous revision. env.py/command.upgrade are covered separately.
    """
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    scripts = ScriptDirectory.from_config(cfg)

    def apply(connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            if current == "0026" and target == "0025":
                scripts.get_revision("0026").module.downgrade()
            else:
                for revision in reversed(list(scripts.iterate_revisions(target, current))):
                    revision.module.upgrade()

    async with engine.begin() as connection:
        await connection.run_sync(apply)


async def seed_organization(connection):
    from sqlalchemy import text

    organization_id = uuid4()
    await connection.execute(text(
        "INSERT INTO organizations (id, name, slug, is_active, working_hours_per_day, working_days) "
        "VALUES (:id, 'Synthetic test organization', :slug, true, 8, ARRAY[1,2,3,4,5])"
    ), {"id": organization_id, "slug": "synthetic-" + organization_id.hex})
    return organization_id


async def seed_project(connection, organization_id, **changes):
    """SQL historical fixture: does not depend on today's Project mapper."""
    from sqlalchemy import text

    values = dict(id=uuid4(), organization_id=organization_id, name="Historical project",
                  code="HISTORY", methodology="kanban", status="active", is_active=True,
                  deleted_at=None, task_counter=7, project_kind="proyecto")
    values.update(changes)
    # Keys are test-authored only, never environment/request input.
    await connection.execute(text(
        f"INSERT INTO projects ({', '.join(values)}) "
        f"VALUES ({', '.join(':' + key for key in values)})"
    ), values)
    return values["id"]


@pytest.mark.asyncio
async def test_0026_preserves_history_checks_shape_and_round_trips(target_url):
    from datetime import UTC, datetime

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    engine = await new_schema_engine(target_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema=current_schema()"
            )) == 0
        await migrate(engine, "0025")
        async with engine.begin() as connection:
            org = await seed_organization(connection)
            await seed_project(connection, org)
            await seed_project(connection, org, code="GENERALES", status="archived",
                               is_active=False, deleted_at=datetime(2020, 1, 1, tzinfo=UTC))
            await seed_project(connection, org, code=None, methodology="planner")
            before = (await connection.execute(text(
                "SELECT to_jsonb(p) FROM projects p ORDER BY id"
            ))).scalars().all()
        await migrate(engine, "0026", current="0025")
        async with engine.begin() as connection:
            assert (await connection.execute(text(
                "SELECT to_jsonb(p) - 'is_system' FROM projects p ORDER BY id"
            ))).scalars().all() == before
            assert await connection.scalar(text("SELECT count(*) FROM projects WHERE is_system")) == 0
            metadata = (await connection.execute(text(
                "SELECT is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name='projects' AND column_name='is_system'"
            ))).one()
            assert metadata.is_nullable == "NO" and metadata.column_default == "false"
            fresh = await seed_organization(connection)
            valid_id = await seed_project(connection, fresh, code="GENERALES",
                                          methodology="custom", is_system=True)
        # Each violation uses a REAL independent transaction, not a savepoint.
        for changes in [dict(code=None), dict(code="OTHER"), dict(methodology="kanban"),
                        dict(status="archived"), dict(is_active=False),
                        dict(deleted_at=datetime(2020, 1, 1, tzinfo=UTC))]:
            with pytest.raises(IntegrityError) as error:
                async with engine.begin() as connection:
                    await connection.execute(text(
                        "UPDATE projects SET " + ", ".join(f"{key}=:{key}" for key in changes)
                        + " WHERE id=:id"
                    ), {**changes, "id": valid_id})
            cause = error.value.orig.__cause__
            assert cause.sqlstate == "23514"
            assert cause.constraint_name == "ck_projects_system_shape"
        async with engine.begin() as connection:
            ordinary = await seed_project(connection, fresh, code="ORDINARY")
            assert await connection.scalar(text("SELECT is_system FROM projects WHERE id=:id"),
                                           {"id": ordinary}) is False
            preserved = (await connection.execute(text(
                "SELECT to_jsonb(p) - 'is_system' FROM projects p ORDER BY id"
            ))).scalars().all()
        await migrate(engine, "0025", current="0026")
        async with engine.connect() as connection:
            assert (await connection.execute(text(
                "SELECT to_jsonb(p) FROM projects p ORDER BY id"
            ))).scalars().all() == preserved
            assert await connection.scalar(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() "
                "AND table_name='projects' AND column_name='is_system'"
            )) == 0
            assert await connection.scalar(text(
                "SELECT count(*) FROM pg_constraint WHERE conrelid='projects'::regclass "
                "AND conname='ck_projects_system_shape'"
            )) == 0
        await migrate(engine, "0026", current="0025")
        async with engine.connect() as connection:
            assert (await connection.execute(text(
                "SELECT to_jsonb(p) - 'is_system' FROM projects p ORDER BY id"
            ))).scalars().all() == preserved
            # Downgrade intentionally loses the marker; reupgrade never guesses it.
            assert await connection.scalar(text("SELECT count(*) FROM projects WHERE is_system")) == 0
    finally:
        await engine.dispose()
