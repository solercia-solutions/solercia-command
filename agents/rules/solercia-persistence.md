---
name: solercia-persistence
description: "Requires Solercia persistence boundaries for Command repositories, services, transactions, migrations, and persistence tests."
type: rule
scope: path-scoped
paths:
  - "backend/app/database.py"
  - "backend/app/dependencies.py"
  - "backend/app/**/*repository*.py"
  - "backend/app/**/*service*.py"
  - "backend/app/**/*unit_of_work*.py"
  - "backend/alembic/**/*.py"
  - "backend/tests/**/*repository*.py"
  - "backend/tests/**/*service*.py"
  - "backend/tests/**/*database*.py"
severity: required
metadata:
  author: solercia
  version: "1.0.0"
  category: architecture
  tags: [persistence, sqlalchemy, repositories, transactions, multi-tenant]
---

# Solercia Persistence — Command

## Required reading

Before editing a matching path, read:

1. `~/.agents/skills/solercia-persistence/SKILL.md`
2. `~/.agents/skills/solercia-persistence/references/repository-contract.md`
3. `~/.agents/skills/solercia-persistence/references/python-sqlalchemy.md`
4. `~/.agents/skills/solercia-persistence/references/transaction-boundaries.md`
5. `~/.agents/skills/solercia-persistence/references/testing-and-migration.md`

## Hard rules

- Keep generic CRUD mechanics local to Command and its Python/SQLAlchemy stack.
- Define application-facing Protocols; extend local generic contracts with aggregate-specific semantic methods.
- Do not create a cross-product persistence package, shared database/entity, or cross-database foreign key.
- Repositories never commit or roll back. Services/use cases own completion; use UnitOfWork only for atomic multi-repository workflows.
- Require `organization_id` or an equivalent tenant scope for reads, updates, and deletes; do not expose service-level `get(id)`.
- Do not expose universal generic HTTP controllers for sensitive or tenant-owned resources.
- Test services with fakes; test adapters and PostgreSQL-specific SQL against real PostgreSQL.
- Keep locks, recursive queries, upserts, pg_trgm/GIN, JSONB/ARRAY, and textual SQL inside adapters.
- Migrate one aggregate/workflow at a time with characterization tests and temporary compatibility facades.

## Project paths

- Session/transaction wiring: `backend/app/database.py`, `backend/app/dependencies.py`
- Repositories and use cases: `backend/app/modules/*/{repository,service}.py`
- Migrations: `backend/alembic/`
- Persistence/service tests: `backend/tests/`
