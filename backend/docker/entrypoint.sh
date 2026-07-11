#!/bin/sh
# Container entrypoint: apply pending Alembic migrations, then hand off to
# uvicorn. The app's lifespan no longer creates the schema (see db_init.py /
# main.py) — migrations are the single source of truth for the schema, per
# ADR 0003 and design.md Decision 1 of change 01-fundacion-tdd.
set -e

echo "Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "Starting the application server..."
exec "$@"
