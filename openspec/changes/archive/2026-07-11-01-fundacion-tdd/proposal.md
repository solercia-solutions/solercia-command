# Proposal: Fundación TDD del backend

## Intent

El TDD estricto es obligatorio para los cambios 02-10, pero hoy es inviable: los tests de integración requieren `TEST_DATABASE_URL` y se saltan solos porque la BD `solercia_test` no existe en `docker-compose.yml` (solo crea `solercia`). Cada archivo de test se auto-bootstrapea (sin fixtures compartidos en `conftest.py`), el esquema se crea con `Base.metadata.create_all` (cero revisiones Alembic) y no hay linting ni type-checking. Este cambio es PRIORIDAD 1: construye la base que desbloquea el TDD de todo lo demás.

## Scope

### In Scope
- Infraestructura de pruebas: provisionar `solercia_test` vía `docker-compose.yml`; fixtures compartidos en `backend/tests/conftest.py` (cliente async + sesión + factory de tenant/usuario); documentar setup de venv local (`requirements.txt` + `requirements-dev.txt`).
- Adopción de Alembic: migración inicial descriptiva que refleja el esquema ACTUAL + flujo documentado para que los cambios futuros envíen migraciones.
- Linting/typing: ruff + mypy con línea base limpia (añadir a `requirements-dev.txt`, config en `pyproject.toml`, comandos documentados).

### Out of Scope
- Paginación estándar (`?page&size&sort&order`) — es el cambio 02.
- Auditoría `created_by`/`updated_by` — es el cambio 02.
- Cualquier feature de producto nueva (cambios 02+).
- Frontend: CONGELADO (`constraint frontend-frozen`), no se toca.

## Capabilities

### New Capabilities
- `dev-tooling`: base de desarrollo del backend — BD de test provisionada, fixtures compartidos de pytest, flujo de migraciones Alembic y línea base limpia de ruff/mypy como requisitos verificables.

### Modified Capabilities
- `api-conventions`: la inicialización de esquema evoluciona de `create_all` en startup (cero revisiones) a una línea base Alembic gestionada + flujo de migraciones para cambios futuros. La spec debe decidir si el startup pasa a `alembic upgrade` o conserva `create_all` como puente.

## Approach

Tres pilares independientes que se pueden implementar en paralelo pero verificar juntos. (1) Añadir servicio/init que cree `solercia_test` en docker-compose y refactorizar el bootstrap disperso de los tests hacia fixtures reutilizables en `conftest.py`. (2) Generar una revisión baseline con `alembic revision --autogenerate` validada contra el esquema vivo, dejando `env.py` conectado a los modelos. (3) Configurar ruff + mypy con reglas pragmáticas y sanear la línea base hasta cero hallazgos. Todo respeta el patrón router → service → repository y el soft delete/auditoría existentes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `docker-compose.yml` | Modified | Crear BD `solercia_test` |
| `backend/tests/conftest.py` | Modified | Fixtures compartidos (client/session/factory) |
| `backend/alembic/versions/` | New | Migración baseline (hoy solo .gitkeep) |
| `backend/alembic/env.py` | Modified | Conectar metadata para autogenerate |
| `backend/requirements-dev.txt` | Modified | Añadir ruff, mypy |
| `backend/pyproject.toml` | New | Config ruff + mypy |
| `backend/README` o docs | Modified | Documentar venv + flujo de migraciones + comandos lint |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| El baseline autogenerado diverge del esquema real de `create_all` | Med | Validar con `alembic upgrade` sobre BD limpia y comparar contra `create_all` |
| Refactor de fixtures rompe los 43 tests existentes | Med | Migrar incrementalmente; suite verde antes de cerrar |
| Línea base ruff/mypy demasiado ruidosa | Med | Empezar con reglas pragmáticas; ignores puntuales documentados |

## Rollback Plan

Cada pilar es reversible por separado: revertir el commit correspondiente. El baseline Alembic no altera datos (solo describe el esquema existente); si falla, se mantiene `create_all` en startup. Config de ruff/mypy y fixtures son puramente de tooling: revertir no afecta runtime de producción.

## Dependencies

- Ninguna externa. Requiere Postgres 16 vía docker-compose (ya existe).

## Success Criteria

- [ ] `docker compose up` deja disponible `solercia_test`; los tests dejan de saltarse por falta de `TEST_DATABASE_URL`.
- [ ] Los tests usan fixtures compartidos de `conftest.py` (sin bootstrap duplicado); los 43 tests existentes pasan.
- [ ] Existe una revisión Alembic baseline verificable con `alembic upgrade head` sobre BD limpia; flujo de migraciones documentado.
- [ ] `ruff check` y `mypy` corren con cero hallazgos; comandos documentados.
