## Verification Report

**Change**: 01-fundacion-tdd
**Version**: N/A
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 26 |
| Tasks complete | 26 |
| Tasks incomplete | 0 |

Todas las casillas de `tasks.md` están marcadas `[x]`. `state.yaml` confirma `apply: done` con los 7 commits (`f512753`, `00bdfdb`, `32d192d`, `97b3d61`, `06edcfb`, `1cb0f75`, `bec98df`) — verificado contra `git log --oneline` en `main`, coincide exactamente.

### Build & Tests Execution

**Lint (ruff)**: ✅ Passed
```text
$ cd backend && source .venv/bin/activate && ruff check .
exit code: 0 (ejecutado por mí, no solo tomado del reporte de apply)
```

**Types (mypy)**: ✅ Passed
```text
$ cd backend && source .venv/bin/activate && mypy app/
exit code: 0 — corrido desde backend/ (mypy es sensible al cwd; correrlo desde
la raíz del repo omite backend/pyproject.toml y su override de apscheduler/redis,
tal como documenta el README).
```

**Tests sin `TEST_DATABASE_URL`** (R1, caso borde): ✅ 30 passed / 0 failed / 20 skipped
```text
$ pytest tests/ -v -rs
30 passed, 20 skipped in 0.29s
Cada skip trae razón explícita: "TEST_DATABASE_URL not set — skipping integration tests"
(no hay skips silenciosos, no hay fallos).
```

**Tests con `TEST_DATABASE_URL` + `API_BASE_URL` + `TEST_AUTH_TOKEN`** (Docker levantado,
login real contra `admin@solercia.com`): ⚠️ 48 passed / 2 failed / 0 skipped
```text
$ pytest tests/ -v
48 passed, 2 failed in 1.80s
FAILED tests/test_sprint_close.py::test_close_sprint_sums_only_done_tasks
FAILED tests/test_sprint_close.py::test_close_sprint_moves_incomplete_to_backlog
  assert 404 == 200  (PATCH/GET /projects/{project_id}/tasks/{task_id})
```
Los 2 fallos son un bug preexistente confirmado (ver sección "Known Gap" abajo) — no
regresión de este cambio. Aislando los 2 tests nuevos de la Fase 3-4: `pytest
tests/test_conftest_fixtures.py tests/test_migrations_baseline.py -v` → **7 passed / 0
failed** (evidencia GREEN limpia, sin el ruido del bug preexistente).

**Alembic check** (`solercia_test`, Docker levantado): ✅ Passed (verificado dos veces,
por dos caminos independientes)
```text
Camino 1 — directo contra solercia_test (reseteada a vacía por mí para la prueba):
$ DATABASE_URL=...solercia_test alembic upgrade head
  Running upgrade  -> 0001, baseline
$ alembic check
  No new upgrade operations detected.
(solercia_test se restauró vacía al terminar, mismo estado documentado por apply-progress)

Camino 2 — guardia automatizada del propio cambio, contra BD desechable
(test_migrations_baseline.py, no colisiona con solercia_test por diseño):
test_alembic_upgrade_head_creates_full_schema PASSED
test_alembic_check_reports_no_diff_after_upgrade PASSED
```

**Coverage**: N/A — sin herramienta de cobertura en `requirements-dev.txt`. No exigida por
la spec ni por `openspec/config.yaml` (`coverage_threshold: 0`). No es un hallazgo.

### Spec Compliance Matrix — dev-tooling

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R1 | docker-compose provisiona `solercia_test` sin pasos manuales | `psql -l` muestra `solercia`+`solercia_test`; `docker/initdb/create-test-db.sh` montado en `/docker-entrypoint-initdb.d` | ✅ COMPLIANT |
| R1 (edge) | Sin `TEST_DATABASE_URL` → skip explícito, no falla | `pytest tests/ -v -rs` → 30 passed, 20 skipped con razón | ✅ COMPLIANT |
| R2 | `conftest.py` expone fixtures compartidos (client/session/tenant/user) | `test_conftest_fixtures.py` → 5/5 passed | ✅ COMPLIANT |
| R3 | Suite existente sigue pasando tras adoptar fixtures compartidos | 48/50 passed con BD real; los 2 fallos son bug preexistente no relacionado con fixtures (ver Known Gap) | ⚠️ COMPLIANT CON NOTA (ver Issues — desviación de diseño) |
| R4 | `alembic upgrade head` en BD vacía ≡ `create_all` | Verificado por partida doble (directo + `test_migrations_baseline.py` 2/2) | ✅ COMPLIANT |
| R5 | Flujo de migraciones futuras documentado | `backend/README.md` sección "Desarrollo local" + Dockerfile/entrypoint | ✅ COMPLIANT (evidencia estática — requisito documental) |
| R6 | `ruff check` + `mypy` sin hallazgos | Corridos por mí, exit 0 ambos | ✅ COMPLIANT |
| R7 | Setup local reproducible sin conocimiento tácito | README documenta venv + `pip install -r requirements.txt -r requirements-dev.txt`; flujo replicado exactamente por mí | ✅ COMPLIANT |

**Compliance summary**: 8/8 escenarios cumplidos (R3 con nota de desviación de diseño documentada, no rompe la spec en la práctica — ver Issues).

### Spec Compliance Matrix — api-conventions (delta)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| MODIFIED: Inicialización de esquema por Alembic | `alembic upgrade head` en BD limpia ≡ `create_all` | Mismo que R4 arriba | ✅ COMPLIANT |
| MODIFIED: arranque no ejecuta `create_all` | `lifespan` solo corre `_wait_for_db`+`seed_default` | Lectura de `main.py` (sin `init_db`/`create_all` en el lifespan) + runtime: contenedor vivo, `RestartCount=0`, `GET /api/v1/health` → 200, logs muestran `alembic upgrade head` → `Running upgrade -> 0001, baseline` antes de arrancar uvicorn | ✅ COMPLIANT |
| MODIFIED: `seed_default` sigue idempotente | Sin cambios de comportamiento | `db_init.py` conserva `seed_default()` intacto; `init_db()` se conserva como utilidad (usada solo por tests), ya no se llama desde `main.py` | ✅ COMPLIANT |
| ADDED: flujo de migraciones documentado | Modelo modificado → `alembic revision --autogenerate` | README documenta el flujo | ✅ COMPLIANT (evidencia estática) |

### Correctness (Static Evidence) — gate binding "Corrección de gate" (design.md)

| Item del binding | Estado | Notas |
|---|---|---|
| Engine de test con `poolclass=NullPool` | ✅ Presente | `tests/conftest.py:70` |
| `asyncio_default_fixture_loop_scope = "session"` en `backend/pyproject.toml` | ✅ Presente | `[tool.pytest.ini_options]` |
| `@pytest.mark.asyncio(loop_scope="session")` en los tests de fixtures | ✅ Presente en los 5 tests de `test_conftest_fixtures.py` | Hallazgo del propio apply, documentado: el binding original omitía `asyncio_default_test_loop_scope` (queda en `function` por defecto); sin el marcador por-test seguía fallando con "Future attached to a different loop". Fix real: marcador explícito por test, sin tocar el default global (no afecta los 43 tests preexistentes). Verificado estable en mi propia corrida repetida. |
| `create_all` retirado del `lifespan` | ✅ Confirmado | `main.py` solo importa/llama `seed_default`; `init_db()` se conserva en `db_init.py` como utilidad de tests, sin wiring en el arranque |
| Entrypoint corre `alembic upgrade head` | ✅ Confirmado | `docker/entrypoint.sh` + `Dockerfile` (`ENTRYPOINT`, `chmod +x`); runtime verificado contra el contenedor vivo |
| Seed preservado | ✅ Confirmado | `seed_default()` sin cambios de comportamiento |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — migraciones como fuente de verdad en el entrypoint | ✅ Yes | Verificado en runtime y estático |
| D2 — baseline autogenerate + guardia `alembic check` | ✅ Yes | Doble verificación (directa + test dedicado) |
| D3 — fixtures aditivas, SAVEPOINT+rollback, cliente ASGI in-process | ✅ Yes (implementación) | ⚠️ Pero el texto de R3 en la spec dice "tras migrar los 43 tests a los fixtures compartidos", mientras D3 dice explícitamente que son aditivos y los 43 NO se reescriben. La intención (suite verde) se cumple por un mecanismo distinto al que describe la spec. No se detectó en la propia nota de "Consistencia con design.md" del artefacto de spec (que solo verificó D1 contra el MODIFIED de api-conventions, no D3 contra R3). |
| D4 — ruff+mypy pragmáticos en `pyproject.toml` | ✅ Yes | Reglas y ignores tal como diseñados |

### Scope Check (no scope creep)

| Chequeo | Resultado |
|---|---|
| `frontend/` no tocado por los 7 commits | ✅ Confirmado — `git show --stat` de cada uno de los 7 commits: 0 rutas bajo `frontend/` |
| `.gitignore` no incluido en los commits | ✅ Confirmado — sigue modificado sin commitear (`git status` actual), ajeno a este cambio |
| `docs/TRANSCRIPCIONES.md` no incluido en los commits | ❌ **NO se cumple** — ver Issues (WARNING) |

### Issues Found

**CRITICAL**: None

**WARNING**:
1. **Scope creep — borrado de `docs/TRANSCRIPCIONES.md` mezclado en el commit `f512753`**.
   `git show --stat f512753` muestra `docs/TRANSCRIPCIONES.md | 92 -----` junto a los
   archivos legítimos de la Fase 1 (`create-test-db.sh`, `docker-compose.yml`,
   `README.md`, artefactos de `openspec/`). El archivo no tiene relación con
   `dev-tooling`; su borrado ya está en `main` (commit `f512753`, confirmado con
   `git log --oneline --all -- docs/TRANSCRIPCIONES.md`). No es un defecto funcional
   del cambio ni rompe ninguna spec, pero sí viola la regla de "no scope creep" pedida
   explícitamente para esta verificación. Recomendación: si el borrado de
   `TRANSCRIPCIONES.md` fue intencional (fuera de este cambio), documentarlo en un
   commit dedicado con su propio mensaje; si fue accidental, evaluar si vale la pena
   recuperarlo en un commit de corrección separado. No bloquea el archivado de
   `01-fundacion-tdd` porque el contenido técnico del commit es correcto — es un
   problema de higiene de commits, no de la funcionalidad entregada.
2. **Desviación de diseño no reconciliada — texto de R3 vs. Decisión D3**. La spec dice
   "La suite existente de 43 tests DEBE seguir pasando tras migrar a los fixtures
   compartidos"; el design (D3) documenta explícitamente que las fixtures son
   ADITIVAS y los 43 tests NO se reescriben. El resultado observable (suite verde,
   sin regresión atribuible a fixtures) es correcto, pero el texto de R3 quedaría
   desalineado con la implementación al fusionarse en `openspec/specs/` durante el
   archivado. Recomendación: al archivar, reescribir R3 (o su escenario) para reflejar
   "fixtures aditivas para tests nuevos; los 43 tests preexistentes conservan su patrón
   black-box contra servidor vivo" en vez de "migrados a los fixtures compartidos".

**SUGGESTION**:
1. **Known Gap — bug preexistente en `test_sprint_close.py`, confirmado y aceptado
   como fuera de alcance.** `test_close_sprint_sums_only_done_tasks` y
   `test_close_sprint_moves_incomplete_to_backlog` fallan con 404 real: usan
   `PATCH/GET /projects/{project_id}/tasks/{task_id}`, pero la ruta registrada en
   `app/modules/tasks/router.py` es `PATCH /tasks/{task_id}` (sin prefijo
   `/projects/{project_id}`; solo el `POST` de creación usa ese prefijo). Confirmado
   con `git show d55ff0a:backend/tests/test_sprint_close.py` que la URL incorrecta ya
   existía en la primera versión del archivo (commit `d55ff0a`, anterior a
   `01-fundacion-tdd`); el único touch posterior (`00bdfdb`) solo removió 2 líneas por
   lint, sin tocar URLs. El bug nunca se había ejercitado porque estos tests siempre
   estuvieron bajo `skip_no_db` y nadie había corrido la suite negra con servidor vivo
   + token real antes de este cambio — es exactamente el tipo de deuda que R1 busca
   sacar a la luz. Correctamente documentado en `tasks.md` (6.1) y `apply-progress`
   como excepción, NO corregido aquí por estar fuera de alcance de `dev-tooling`.
   Recomendación: fix de una línea (agregar el prefijo `/projects/{project_id}` a las
   rutas `PATCH`/`GET` de tarea individual, o quitarlo de la ruta de creación para
   consistencia) en un cambio dedicado o al iniciar `02-contrato-api`.
2. Cobertura de código no medida (sin herramienta instalada) — informativo, no
   bloqueante; no exigido por spec ni config.

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Tabla "TDD Cycle Evidence" presente en apply-progress (Fases 3-4) |
| All tasks have tests | ✅ | 3.1/4.1 crean `test_migrations_baseline.py` / `test_conftest_fixtures.py` |
| RED confirmed (tests exist) | ✅ | Ambos archivos existen en el árbol actual, nuevos (confirmado por `git show --stat` de `32d192d`/`97b3d61`: creación, no modificación) |
| GREEN confirmed (tests pass) | ✅ | 7/7 passed en corrida aislada por mí (`test_conftest_fixtures.py` + `test_migrations_baseline.py`) |
| Triangulation adequate | ✅ | 5 casos (fixtures: tenant, auth ok, auth rechazado, aislamiento paso A/B) + 2 casos (migración: esquema completo, diff vacío) |
| Safety Net for modified files | ✅ | Ambos son archivos nuevos (N/A por diseño, no modificaron tests existentes) |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (sin BD) | 30 | 6 (`test_attachments`, `test_comments`, `test_mention_notifications`, `test_sprint_close` [parcial], `test_subtasks`, `test_task_key` [parcial]) | pytest |
| Integration — nueva (ASGI in-process / BD desechable) | 7 | 2 (`test_conftest_fixtures.py`, `test_migrations_baseline.py`) | pytest-asyncio, httpx ASGITransport, asyncpg |
| Integration — preexistente (black-box, servidor vivo) | 13 | 5 (`test_attachments`, `test_comments`, `test_sprint_close`, `test_subtasks`, `test_task_key`) | httpx contra `API_BASE_URL` + `TEST_AUTH_TOKEN` |
| **Total** | **50** | **11** | |

---

### Changed File Coverage
Sin herramienta de cobertura configurada (`requirements-dev.txt` no incluye `pytest-cov` ni
equivalente). `openspec/config.yaml` fija `coverage_threshold: 0` — no exigido.
**Coverage analysis skipped — no coverage tool detected.**

---

### Assertion Quality
Auditados los 2 archivos de test nuevos (`test_conftest_fixtures.py`,
`test_migrations_baseline.py`). Todas las aserciones ejercitan código de producción real
(fixtures reales, endpoints reales vía cliente ASGI, `alembic upgrade`/`alembic check`
reales contra Postgres) con valores concretos esperados (status codes, emails, conteos
antes/después de rollback, tablas esperadas, ausencia de diff). El par
`test_session_writes_are_isolated_step_a`/`step_b` está bien triangulado (1 → 0,
demuestra aislamiento real, no un conteo trivial). Sin tautologías, sin bucles fantasma,
sin aserciones huérfanas de tipo.

**Assertion quality**: ✅ All assertions verify real behavior

---

### Quality Metrics
**Linter**: ✅ No errors (`ruff check .`, exit 0, corrido por mí desde `backend/`)
**Type Checker**: ✅ No errors (`mypy app/`, exit 0, corrido por mí desde `backend/`)

### Verdict
**PASS WITH WARNINGS** — 26/26 tareas completas, 0 CRITICAL, 2 WARNING (scope creep de
`docs/TRANSCRIPCIONES.md` en `f512753`; desalineación de texto R3 vs. diseño D3 a
reconciliar en el archivado), 2 SUGGESTION (bug preexistente confirmado y ya documentado
en `test_sprint_close.py`, fuera de alcance; cobertura no medida). Ninguno de los
hallazgos bloquea el archivado: el binding de corrección de gate, el retiro de
`create_all` del arranque, el entrypoint con `alembic upgrade head` y el seed preservado
están física y funcionalmente confirmados con evidencia de ejecución real, no solo
inspección estática.
