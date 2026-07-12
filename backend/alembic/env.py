"""Alembic environment configured for async SQLAlchemy.

Migrations are deferred per ADR 0003; this environment is wired and ready so
``alembic revision --autogenerate`` works once migrations are introduced.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.database import Base

# Importing db_init registers every ORM model on Base.metadata.
import app.db_init  # noqa: F401,E402

config = context.config

# Override the static URL with the runtime application setting.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    # ``disable_existing_loggers`` defaults to True in ``fileConfig``, which
    # silently sets ``.disabled = True`` on every already-created logger NOT
    # listed in alembic.ini's ``[loggers]`` (root/sqlalchemy/alembic only) —
    # e.g. every ``solercia.*`` app logger. Harmless for the real ``alembic
    # upgrade head`` CLI (its own short-lived process), but the test suite
    # invokes ``alembic.command.upgrade``/``downgrade`` IN-PROCESS
    # (test_migrations_baseline.py, test_boards_backfill_migration.py):
    # without this flag, any app logger created before that point stays
    # disabled for the rest of the pytest session, silently dropping
    # ``caplog``-captured log records in unrelated later tests (discovered
    # via change 08-email-notifications' outbox/digest exhaustion tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""

    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure context and run migrations against a live connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
