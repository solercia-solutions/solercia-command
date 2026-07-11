#!/bin/sh
# Creates the `solercia_test` database on the first init of the Postgres data
# volume. Scripts under /docker-entrypoint-initdb.d only run once, against an
# empty data directory — existing volumes need the manual step documented in
# backend/README.md.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE solercia_test'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'solercia_test')\gexec
EOSQL
