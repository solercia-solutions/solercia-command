# Verification Report: 05 · Trabajo realizado (TimeLog + TaskHistory + cruce asignado vs. realizado)

**Change**: 05-trabajo-realizado
**Mode**: Full artifact set (proposal, specs, design, tasks) — Strict TDD active
**Verdict**: **PASS**

## Completeness

| Ítem | Estado |
|------|--------|
| Tareas completadas | 26/26 (100%) |
| Commits de apply | 5 (c4e35e0, f6370e7, 5aa92b4, ea5f356, 03888eb) — todos presentes en `main` |
| `state.yaml` | `apply: done`, `verify: pending` (actualizado en este reporte a `done`) |
| Scope creep | Ninguno — `git show --stat` en los 3 commits de features (c4e35e0, f6370e7, 5aa92b4) confirma **cero** rutas bajo `frontend/` tocadas |

## Build / Tests / Quality — evidencia de ejecución real

Rebuild obligatorio ejecutado primero: `docker compose up -d --build backend` — migración `0006 -> 0007, add_time_logs_and_task_history` aplicada limpiamente por el entrypoint, arranque sin errores.

| Comando | Resultado |
|---------|-----------|
| `cd backend && pytest tests/ -v` (con `TEST_DATABASE_URL`, `API_BASE_URL`, `TEST_AUTH_TOKEN` frescos) | **258 passed**, 1 warning (preexistente, no relacionado — SAWarning de ciclos FK en `alembic env.py`) |
| `pytest tests/test_activity.py -v` × 3 corridas consecutivas | **8 passed** las 3 veces, mismo orden, mismo tiempo (~3.20s) — confirma que el fix de `created_at` Python-side eliminó la intermitencia documentada en T26 |
| `ruff check .` | **All checks passed!** |
| `mypy app` | **Success: no issues found in 145 source files** |

Nota de entorno: la primera corrida de la suite (sin `TEST_AUTH_TOKEN`) falló 12 tests HTTP-based (`test_attachments`, `test_comments`, `test_sprint_close`, `test_subtasks`, `test_task_key`) con `httpx.LocalProtocolError: Illegal header value b'Bearer '` — no es una regresión del cambio, es un requisito de entorno (login `POST /auth/login` con `admin@solercia.com` para obtener un JWT fresco). Con el token seteado, la suite completa pasa en verde.

## Spot-checks HTTP en vivo (post-rebuild)

Ejecutados contra el backend reconstruido (`localhost:8000/api/v1`), con `admin@solercia.com` (rol `admin`) y elevando temporalmente a `carlos@solercia.com` a `MemberRole.manager` vía SQL directo (revertido a `member` al finalizar) para probar la regla vinculante de "dueño estricto":

| Escenario | Resultado observado |
|-----------|----------------------|
| `POST /tasks/{id}/time-logs` como usuario autenticado | `201`, `user_id` = actor, `date` alias funcionando correctamente |
| `PATCH /time-logs/{id}` de otro usuario con token `manager` | **`403`** — `{"detail":"Solo el dueño del registro de tiempo puede editarlo.","code":"time_log_forbidden"}` — confirma la corrección de gate #2 (dueño estricto, sin excepción de rol) |
| `GET /users/{otro_id}/time-logs` con token `manager` | `200` con las entradas del otro usuario — exención de lectura para supervisión funcionando |
| `PATCH /tasks/{id}` con `status` + `priority` en el mismo request | `200`; `GET /tasks/{id}/history` devuelve 2 filas nuevas (`status: To Do->In Progress`, `priority: high->critical`) con `old_value`/`new_value`/`changed_at` correctos, orden descendente por `changed_at` confirmado en un tercer PATCH posterior |
| `POST /sprints/{id}/close` con una tarea incompleta asignada | `200`, `tasks_moved: 1` (int, contrato preservado); `GET /tasks/{id}/history` muestra fila `field=sprint_id`, `old_value`=id del sprint, `new_value=null`, `actor_type=system`, `actor_id=null` |
| `GET /dashboard/executive?threshold_days=3` | `200`; payload incluye bloque `work_gap` con `by_user[].{hours_logged,hours_estimated,tasks_assigned,tasks_with_activity}` y `no_recent_activity[]` |
| `GET /dashboard/performance` | `200`; sin bloque `work_gap` — contrato de `performance` intacto, confirmando T23 |

## Spec Compliance Matrix

### time-logs (R1–R5)

| Requirement | Escenario | Test cubriendo | Estado |
|-------------|-----------|-----------------|--------|
| R1 Registro propio | Registro válido / horas inválidas | `test_create_time_log_valid_returns_201_with_own_user_id`, `test_create_time_log_rejects_non_positive_hours[0,-1]` + spot-check `POST /tasks/{id}/time-logs` | ✅ PASS |
| R2 Edición/borrado del dueño | Edición propia / ajena (incl. manager/admin) | `test_owner_can_edit_own_time_log`, `test_edit_by_other_member_forbidden`, `test_edit_and_delete_by_manager_or_admin_forbidden[manager,admin]` + spot-check PATCH ajeno con manager → 403 | ✅ PASS |
| R3 Visibilidad propia vs. supervisión | Consulta ajena por member rechazada / por manager permitida | `test_member_cannot_list_other_users_time_logs`, `test_manager_or_admin_can_list_other_users_time_logs[manager,admin]` + spot-check GET ajeno con manager → 200 | ✅ PASS |
| R4 Listados paginados | Filtro de fechas, paginación por tarea | `test_date_range_filter_on_user_time_logs`, `test_task_time_logs_listing_is_paginated` | ✅ PASS |
| R5 Agregación diaria/semanal | Suma mismo día, agregación semanal ISO | `test_daily_summary_sums_two_entries_same_day`, `test_weekly_summary_sums_entries_within_iso_week` | ✅ PASS |

### activity-history (R6–R10)

| Requirement | Escenario | Test cubriendo | Estado |
|-------------|-----------|-----------------|--------|
| R6 Captura en mutación de usuario | Cambio de estado / múltiples campos / sin cambio | `test_status_change_via_patch_creates_history_row`, `test_multiple_fields_in_one_patch_creates_multiple_rows`, `test_no_op_patch_creates_no_history_row` + spot-check PATCH status+priority | ✅ PASS |
| R7 Captura en mutación de sistema | Cierre de sprint deja historial `actor_type=system` | `test_close_sprint_leaves_system_history_row` + spot-check `POST /sprints/{id}/close` → `tasks_moved:1` + fila de sistema | ✅ PASS |
| R8 Historial por tarea | Timeline paginado desc | `test_task_history_timeline_ordered_most_recent_first`, `test_task_history_listing_is_paginated` + spot-check orden `changed_at` desc con 3 PATCH consecutivos | ✅ PASS |
| R9 Actividad por usuario/día | Filtro por día específico | `test_user_activity_filtered_by_specific_day` | ✅ PASS |
| R10 Solo lectura | Sin ruta PATCH/DELETE | `test_no_edit_or_delete_route_for_task_history` + inspección de `activity/router.py` (solo 2 `GET`, sin `PATCH`/`DELETE`) | ✅ PASS |

### dashboard-executive delta (R11–R12)

| Requirement | Escenario | Test cubriendo | Estado |
|-------------|-----------|-----------------|--------|
| R11 Cruce horas/tareas | Horas logueadas vs. estimadas; tareas asignadas vs. con actividad | `test_work_gap_reports_hours_logged_vs_estimated`, `test_work_gap_reports_tasks_assigned_vs_with_activity` + spot-check `GET /dashboard/executive` payload | ✅ PASS |
| R12 Colaboradores sin actividad reciente | Umbral por defecto 3 días / configurable / colaborador con actividad no marcado | Tests de `test_dashboard_work_gap.py` (umbral por defecto, `?threshold_days`, colaborador con actividad reciente) + spot-check `?threshold_days=3` | ✅ PASS |

**12/12 requisitos trazados a implementación + test que corrió en verde.**

## Correcciones de gate (binding) — verificación física

| # | Corrección | Verificación |
|---|------------|--------------|
| 1 | Sin endpoint `GET /dashboard/discrepancy`; `work_gap` dentro de `executive()` | `grep -rn "discrepancy" backend/app/` → 0 resultados en código (solo 1 mención en comentario de test explicando la ausencia); `dashboard/router.py` solo expone `/executive` y `/performance`; spot-check confirma `work_gap` en `executive` y ausente en `performance` | ✅ Confirmado |
| 2 | Permisos: edición/borrado estrictamente del dueño, sin excepción de rol | `time_logs/service.py::update_time_log`/`delete_time_log` no consultan `require_role` para el dueño; spot-check PATCH ajeno con `manager` → 403 real | ✅ Confirmado |
| 3 | Snapshot incluye `priority`, excluye `due_date` | `tasks/service.py::_HISTORY_TRACKED_FIELDS = (status, assignee_id, estimation_points, estimation_hours, sprint_id, priority)` — sin `due_date`; spot-check PATCH `priority` genera fila de historial | ✅ Confirmado |
| 4 | Alias API: `changed_at`↔`created_at`, `date`↔`work_date` | `TaskHistoryResponse.changed_at = Field(validation_alias="created_at")`, `TimeLogResponse.date = Field(validation_alias="work_date")`; spot-checks devuelven ambos alias correctamente | ✅ Confirmado |
| 5 | `count_and_move_incomplete_tasks(...) -> list[uuid.UUID]`, `tasks_moved=len(ids)` | Firma exacta en `sprints/repository.py`; spot-check `tasks_moved: 1` (int) tras cierre con 1 tarea movida | ✅ Confirmado |

## Correctness — Tasks vs. Código

| Tarea | Estado en tasks.md | Evidencia en código |
|-------|---------------------|----------------------|
| T01–T08 (Fase A, time_logs) | [x] | `alembic/versions/0007_...py`, `time_logs/{models,schemas,repository,service,router}.py` presentes; `test_time_logs.py` en verde |
| T09–T19 (Fase B, activity) | [x] | `activity/{models,recorder,schemas,repository,service,router}.py`; integración en `tasks/service.py` y `sprints/{service,repository}.py`; `test_activity.py`/`test_sprint_close.py` en verde |
| T20–T23 (Fase C, dashboard) | [x] | `dashboard/{service,router}.py::_work_gap`/`executive`; `test_dashboard_work_gap.py` en verde |
| T24–T26 (Fase D, docs + cierre) | [x] | `docs/API.md`, `docs/ARCHITECTURE.md` actualizados; T26 (verificación final) reproducida en esta fase: 258 passed, ruff/mypy limpios |

Ninguna tarea marcada como completa carece de evidencia en código o test.

## Desviaciones de diseño documentadas — no son drift silencioso

Las 5 desviaciones reportadas en `apply-progress` fueron verificadas contra el código real:

1. **T09 adelantado a Batch A** (modelo ORM `TaskHistory` junto con la migración compartida): confirmado — `git show c4e35e0 --stat` incluye `activity/models.py` (57 líneas) en el commit de time_logs, requerido por el gate de paridad de `alembic check` (`test_migrations_baseline.py`).
2. **`record_task_history` incluye `organization_id`**: confirmado en `activity/recorder.py` — parámetro real requerido por `TenantMixin` (`NOT NULL`), ausente en la firma abreviada de `design.md`. Razonado, no un descuido.
3. **Lógica de permisos inline en el servicio** (`TimeLogService._require_visibility`) en vez de `Depends(require_role(...))` literal en la ruta: confirmado — la regla "propio siempre permitido, ajeno requiere admin/manager" no es expresable con una dependencia de ruta pura. Razonamiento válido.
4. **`_work_gap` como código nuevo** (no existía `discrepancy()` previo para renombrar): confirmado, coincide con el histórico del repo — no hay ningún método `discrepancy` en ningún commit anterior a este cambio.
5. **Fix de `created_at` con `default=` Python-side**: confirmado en `activity/models.py` (línea ~63-66) — `server_default=func.now()` se mantiene como fallback de BD; `default=lambda: datetime.now(UTC)` añadido para evaluación fresca por INSERT ORM. `alembic check` permanece verde porque `default=` no altera el esquema. Verificado empíricamente: 3 corridas consecutivas de `test_activity.py` sin intermitencia.

## History es append-only (verificación explícita)

`activity/router.py` expone únicamente 2 rutas `GET` (`/tasks/{id}/history`, `/users/{id}/activity`); no existe ningún decorador `@router.patch`/`@router.delete` para historial en el módulo. `test_no_edit_or_delete_route_for_task_history` confirma 404 de enrutamiento (no de autorización) al intentar `PATCH`/`DELETE` sobre `/tasks/{id}/history/{history_id}`.

## Assertion Quality Audit (Strict TDD)

Archivos escaneados: `test_time_logs.py`, `test_activity.py`, `test_dashboard_work_gap.py` (28 tests nuevos, 81 aserciones).

- Sin tautologías (`assert True`, `expect(true).toBe(true)`).
- Sin ghost loops: los `for` encontrados (`test_activity.py:189,214`, `test_dashboard_work_gap.py:140`, `test_time_logs.py:332`) son bucles de **setup** (crear fixtures), no de aserciones sobre colecciones potencialmente vacías.
- Todas las aserciones verifican valores de comportamiento real (status codes, campos específicos, conteos, orden), no solo `toBeDefined()`/smoke tests.
- Sin acoplamiento a detalles de implementación (clases CSS, conteos de mocks).

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real.

### TDD Compliance

| Check | Resultado | Detalle |
|-------|-----------|---------|
| TDD Evidence reportada | ✅ | tasks.md documenta RED/GREEN/VERIFY por fase (T03/T11/T20 = RED; T04-T07/T12-T17/T21-T22 = GREEN; T08/T18/T19/T23/T26 = VERIFY) |
| Todas las tareas tienen tests | ✅ | 3/3 suites nuevas (`test_time_logs.py`, `test_activity.py`, `test_dashboard_work_gap.py`) |
| RED confirmado (archivos existen) | ✅ | 3/3 archivos verificados en el filesystem |
| GREEN confirmado (tests pasan) | ✅ | 258/258 en la corrida completa de esta verificación |
| Triangulación adecuada | ✅ | Cada requisito tiene 1-3 escenarios con tests independientes (ver matriz de compliance) |
| Safety Net (archivos modificados) | ✅ | `tasks/service.py`, `sprints/{service,repository}.py`, `dashboard/{service,router}.py` — `test_sprint_close.py` (11 tests preexistentes) corrido en verde tras el refactor de T16-T17 |

**TDD Compliance**: 6/6 checks pasados

## Quality Metrics

**Linter (ruff)**: ✅ No errors
**Type Checker (mypy)**: ✅ No errors (145 archivos)

## Issues

Ninguno. **0 CRITICAL, 0 WARNING, 0 SUGGESTION.**

## Veredicto Final

**PASS** — Los 12 requisitos de las 3 specs están trazados a implementación y respaldados por tests que corrieron en verde en esta verificación (no solo inspección estática). Las 5 correcciones de gate vinculantes de `design.md` están físicamente presentes en el código. Las 5 desviaciones documentadas en `apply-progress` son razonadas y verificables, no drift silencioso. Historial append-only confirmado a nivel de router. Sin scope creep hacia `frontend/`. Suite completa (258 tests), `ruff` y `mypy` limpios. Listo para `sdd-archive`.
