# Design: Fundación TDD del backend

## Technical Approach

Tres pilares desacoplados sobre el backend existente (router → service → repository, soft delete, seed idempotente), sin tocar frontend. Se respeta y ejecuta la ruta de transición ya prevista en **ADR 0003**: pasar de `create_all` en arranque a Alembic como fuente de verdad del esquema, conservando el seed. Las fixtures nuevas son **aditivas**: `skip_no_db` se mantiene intacto para no reescribir los 43 tests actuales (los de integración son black-box HTTP contra el servidor vivo; los unitarios no usan BD).

## Architecture Decisions

### Decisión 1 — Arranque: migraciones como fuente de verdad, ejecutadas en el entrypoint

**Choice**: El entrypoint del contenedor corre `alembic upgrade head` **antes** de uvicorn. El `lifespan` conserva solo `_wait_for_db` + `seed_default`; se retira `init_db()`/`create_all` del arranque (la función queda disponible solo para las fixtures de test). Los volúmenes existentes se sellan con `alembic stamp head`.
**Alternatives considered**: (a) conservar `create_all` como puente en runtime y dejar las migraciones decorativas; (b) invocar `alembic upgrade` dentro del `lifespan` async.
**Rationale**: (a) garantiza deriva de esquema y elimina disciplina — los cambios 02-10 no estarían obligados a enviar migración. (b) choca con el bucle de eventos (`env.py` usa `asyncio.run`). El entrypoint es lo que ADR 0003 (pasos 2-4) prescribe y fuerza que la app no arranque sin migración.

### Decisión 2 — Baseline Alembic: autogenerate + revisión + guardia `alembic check`

**Choice**: `alembic revision --autogenerate -m baseline` (env.py ya cablea `target_metadata` y `compare_type=True`), revisión manual, commit como `0001_baseline`. Validación sobre BD limpia con `alembic check` (soportado en Alembic 1.14) más un test `test_migrations_baseline.py` que exige diff vacío.
**Alternatives considered**: baseline escrito a mano; confiar en autogenerate sin guardia.
**Rationale**: a mano es frágil frente a 15+ modelos; la guardia prueba en cada corrida que el baseline iguala a los modelos y detecta deriva silenciosa.

### Decisión 3 — Fixtures de test: BD provisionada por init-script, aislamiento SAVEPOINT+rollback, cliente ASGI in-process

**Choice**: Script en `/docker-entrypoint-initdb.d/` crea `solercia_test` en un único Postgres. `conftest.py` agrega: `engine` (scope sesión) + `create_all`; `session` sobre una conexión con transacción externa y `join_transaction_mode="create_savepoint"`, con rollback por test; `client` = `httpx.AsyncClient(ASGITransport(app))` con override de `get_db`; factories `tenant`/`user` + emisión de JWT. `skip_no_db` permanece.
**Alternatives considered**: aislamiento por `TRUNCATE` (más lento; se documenta como respaldo para tests que hacen commit) o esquema fresco por test (el más lento); servicio Postgres aparte; patrón `POSTGRES_MULTIPLE_DATABASES` por env.
**Rationale**: el SAVEPOINT+rollback es el aislamiento por test más rápido; el cliente ASGI in-process elimina la dependencia de servidor vivo que arrastran los tests actuales y desbloquea el TDD real de 02-10. El init-script es explícito y de un solo Postgres.

### Decisión 4 — ruff + mypy en `pyproject.toml`, línea base pragmática

**Choice**: Nuevo `backend/pyproject.toml`. ruff `select = E,F,I,B,UP,SIM,C4`, `line-length = 100`, `per-file-ignores` para `alembic/` y `tests/`. mypy sobre `app/` no estricto (`check_untyped_defs`, `warn_unused_ignores`, `no_implicit_optional`), tipado nativo de SQLAlchemy 2.0 (sin plugin), `ignore_missing_imports` por módulo para `apscheduler`/`redis`. Se agregan `ruff` y `mypy` a `requirements-dev.txt`.
**Alternatives considered**: mypy `strict`; ruff `ALL`; configuración en `setup.cfg`.
**Rationale**: `strict`/`ALL` obligan a refactor masivo; la base pragmática logra cero hallazgos sin refactor y mantiene válidos los `# noqa` existentes. `pyproject.toml` es el estándar y no existe hoy.

## Data Flow

    Arranque (contenedor):
      entrypoint → alembic upgrade head → uvicorn → lifespan(_wait_for_db → seed_default)

    Test (in-process, sin servidor vivo):
      engine(TEST_DATABASE_URL) → create_all
        └─ por test: conn.begin() → session(SAVEPOINT) → AsyncClient(ASGITransport, get_db=session)
             → assert → rollback (limpia)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `docker-compose.yml` | Modify | Montar init-script; `TEST_DATABASE_URL` en backend; comando/entrypoint corre `alembic upgrade head` |
| `backend/docker/initdb/create-test-db.sh` | Create | Crea `solercia_test` en el primer init del volumen |
| `backend/Dockerfile` | Modify | Entrypoint: `alembic upgrade head` antes de uvicorn |
| `backend/app/main.py` | Modify | Retirar `init_db()` del `lifespan`; conservar `seed_default()` |
| `backend/alembic/versions/0001_baseline.py` | Create | Baseline autogenerada y revisada |
| `backend/tests/conftest.py` | Modify | Fixtures `engine`/`session`/`client`/factories; conservar `skip_no_db` |
| `backend/tests/test_migrations_baseline.py` | Create | Guardia de diff vacío (`alembic check`) |
| `backend/pyproject.toml` | Create | Config ruff + mypy + `[tool.pytest.ini_options]` (`asyncio_default_fixture_loop_scope = "session"`) |
| `backend/requirements-dev.txt` | Modify | Añadir `ruff`, `mypy` |
| `backend/README.md` | Modify | venv + flujo de migraciones + comandos lint/type/test |

## Interfaces / Contracts

```python
# conftest.py (firmas objetivo; aditivas, skip_no_db se conserva)
# Corrección de gate (2026-07-11): el engine de test DEBE crearse con
# poolclass=NullPool y pytest-asyncio DEBE configurarse con
# asyncio_default_fixture_loop_scope = "session" en [tool.pytest.ini_options].
# Sin ambas medidas, un engine scope="session" ata las conexiones asyncpg al
# event loop del primer test y los siguientes fallan de forma intermitente
# ("Future attached to a different loop" / "another operation is in progress").
@pytest.fixture(scope="session")
async def engine() -> AsyncEngine: ...          # TEST_DATABASE_URL + create_all + NullPool
@pytest.fixture
async def session(engine) -> AsyncSession: ...   # SAVEPOINT + rollback por test
@pytest.fixture
async def client(session) -> AsyncClient: ...    # ASGITransport + override get_db
@pytest.fixture
async def tenant(session) -> Organization: ...
@pytest.fixture
async def user(session, tenant) -> tuple[User, str]: ...  # (user, bearer_token)
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Fixtures y helpers | Pytest; los unitarios existentes siguen sin BD |
| Integration | CRUD futuro (02-10) | Cliente ASGI in-process + session SAVEPOINT |
| Migration | Baseline == modelos | `alembic check` sobre BD limpia (test dedicado) |
| Quality gate | Estilo/tipos | `ruff check` y `mypy` con cero hallazgos |

> Brecha residual aceptada (señalada por el gate): la suite de integración construye el esquema de test con `create_all`, mientras dev/prod usan `alembic upgrade head`; el camino real de migraciones solo lo ejercita `test_migrations_baseline.py` (`alembic check`). Un defecto exclusivo de migración (server_default, orden de creación de enums, nombres de índices) solo aparecería en esa guardia.

## Migration / Rollout

Reversible por pilar (revertir commit). El baseline no altera datos (solo describe el esquema); entornos con volumen previo se sellan con `alembic stamp head`. El init-script solo corre en el primer init del volumen: para volúmenes ya creados, `CREATE DATABASE solercia_test` manual (documentado). Fixtures, ruff y mypy no afectan runtime de producción.

## Open Questions

- [ ] Confirmar que `alembic check` (Alembic 1.14) reporta diff limpio con `compare_type=True` en el CI local; si no, fallback a `revision --autogenerate` que produzca migración vacía.
- [ ] Definir si el entrypoint vive en `Dockerfile` (`CMD`) o en un `start.sh` versionado — sin impacto arquitectónico, se decide en tasks.
