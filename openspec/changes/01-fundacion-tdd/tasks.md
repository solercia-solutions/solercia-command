# Tareas: Fundación TDD del backend

Marca cada tarea con `[x]`. TDD estricto. Cada fase = un commit sobre `main` (sin PR).

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas | 700–1000 (domina la migración Alembic autogenerada) |
| Riesgo 400 líneas | Alto, concentrado en Fase 3 |
| Slicing en commits | Sí, 6 commits |
| Estrategia de entrega | Commits directos a `main`, sin PR |
| Chain strategy | stacked-to-main |

```text
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: High
```

Riesgo a señalar: la Fase 3 es código generado (autogenerate), no lógica manual; se acepta como excepción de tamaño en su propio commit. Las demás fases quedan bajo 400 líneas.

## Fase 1 — BD de test (commit 1, R1)
- [x] 1.1 Crear `backend/docker/initdb/create-test-db.sh`: crea `solercia_test` si no existe.
- [x] 1.2 `docker-compose.yml`: montar el script en `postgres`, agregar `TEST_DATABASE_URL` a `backend`.
- [x] 1.3 `backend/README.md`: documentar `CREATE DATABASE solercia_test` manual para volúmenes existentes.
- [x] 1.4 Verificar: `docker compose up -d postgres` + `psql -c '\l'` confirma `solercia_test`.

## Fase 2 — ruff + mypy (commit 2, R6, R7)
- [x] 2.1 Agregar `ruff` y `mypy` a `backend/requirements-dev.txt`.
- [x] 2.2 Crear `backend/pyproject.toml`: ruff (`E,F,I,B,UP,SIM,C4`, `line-length=100`, ignores en `alembic/`/`tests/`), mypy no estricto sobre `app/`, `[tool.pytest.ini_options]` con `asyncio_default_fixture_loop_scope="session"`.
- [x] 2.3 `ruff check .` en `backend/`: corregir hasta cero hallazgos.
- [x] 2.4 `mypy app/`: corregir hasta cero hallazgos.
- [x] 2.5 Verificar: ambos comandos, exit code 0.

## Fase 3 — Baseline Alembic + entrypoint (commit 3, R4, R5)
- [x] 3.1 [RED] Crear `backend/tests/test_migrations_baseline.py`: falla (no hay revisión baseline).
- [x] 3.2 [GREEN] `alembic revision --autogenerate -m baseline` contra `solercia_test` → `backend/alembic/versions/0001_baseline.py`; revisar el diff.
- [x] 3.3 [GREEN] Confirmar 3.1 en verde (`alembic check` sin diffs).
- [x] 3.4 Crear `backend/docker/entrypoint.sh` (`alembic upgrade head` + `exec uvicorn`); ajustar `ENTRYPOINT`/`CMD` de `backend/Dockerfile`.
- [x] 3.5 `backend/app/main.py`: retirar `init_db()` del `lifespan`, conservar `seed_default()`.
- [x] 3.6 Verificar: `docker compose up --build backend` migra antes de uvicorn; `GET /api/v1/health` → 200.

## Fase 4 — Fixtures compartidos (commit 4, R2, R3)
- [x] 4.1 [RED] Crear `backend/tests/test_conftest_fixtures.py` (usa `engine`/`session`/`client`/`tenant`/`user`): falla, fixtures no existen.
- [x] 4.2 [GREEN] `backend/tests/conftest.py`: `engine` (scope=session, `NullPool`, `create_all`), `session` (SAVEPOINT + rollback), `client` (`ASGITransport` + override `get_db`), factories `tenant`/`user` con JWT; conservar `skip_no_db`.
- [x] 4.3 Verificar 4.1 en verde.
- [x] 4.4 Verificar: `pytest tests/ -v` con `TEST_DATABASE_URL` — 43 tests existentes + nuevos, cero skips.
- [x] 4.5 Verificar: sin `TEST_DATABASE_URL` — integración se salta con razón explícita (R1, caso borde).

## Fase 5 — README (commit 5, R5, R7)
- [ ] 5.1 Documentar venv + `pip install -r requirements.txt -r requirements-dev.txt`.
- [ ] 5.2 Documentar comandos `pytest`, `ruff check`, `mypy`.
- [ ] 5.3 Reemplazar sección "Migraciones" (ADR 0003 diferido) por el flujo vigente: `alembic revision --autogenerate` por cambio de modelo.

## Fase 6 — Verificación final (sin commit propio)
- [ ] 6.1 Suite completa con `TEST_DATABASE_URL`: 43+N tests en verde, cero fallos, cero skips inesperados.
- [ ] 6.2 `ruff check backend/` y `mypy backend/app`: exit 0 en ambos.
- [ ] 6.3 `alembic check` sobre `solercia_test` limpia: diff vacío.
- [ ] 6.4 Registrar evidencia en el mensaje del último commit del cambio.
