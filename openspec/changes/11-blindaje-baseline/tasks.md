# Tasks: 11 · Blindaje de la línea base (backfill de tests as-built con TDD)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~2500–3500 (11 suites nuevas de test + 1 `conftest.py` modificado; ≈100–110 tests nuevos) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | No (no hay PRs de GitHub; ver nota) |
| Split sugerido | Lote A (conftest+multi-tenancy+auth) → Lote B (rbac-catalog+matriz+users-admin) → Lote C (alert-engine) → Lote D (methodology+projects+tasks) → Lote E (notifications+dashboard) |
| Estrategia de entrega | exception-ok — commits directos a `main` por lotes, sin PR |
| Estrategia de encadenado | size-exception — aceptada por el usuario; entrega por lotes |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Nota: `Chained PRs recommended: No` se refiere a la ausencia de cadena de Pull Requests en GitHub (no aplica en este flujo de commits directos). El volumen SÍ se fragmenta en 5 lotes/commits secuenciales (A→E, orden por criticidad de seguridad del design), cada uno dejando la suite completa en verde con ruff/mypy limpios — `size:exception` cubre el exceso de líneas por lote, no la ausencia de fragmentación.

**Convención de rojo (comportamiento ya correcto)**: cada tarea RED corre primero con una aserción invertida/estricta (valor contrario al real, ej. esperar 200 donde el código da 403, o el jti sin rotar) y se confirma el fallo; luego se corrige a la aserción real y se re-ejecuta hasta verde. Cuando el escenario depende de una fixture nueva del mismo lote (ej. `two_orgs` en T02→T03), el rojo lo da la fixture ausente en la primera corrida. Si una tarea RED destapa un defecto real de producción, se abre una tarea `Bugfix-N` ad-hoc (fuera de esta numeración): corrección mínima router→service→repository, commit propio, rollback documentado, delta spec solo si cambia comportamiento observable — antes de cerrar el checkpoint VERIFY del lote.

### Suggested Work Units

| Unit | Objetivo | Commit | Test enfocado | Arnés de ejecución | Frontera de rollback |
|------|----------|--------|----------------|---------------------|------------------------|
| A | Fixtures (`second_tenant`,`make_member`,`rbac_admin`,`two_orgs`) + `test_multi_tenancy.py` + `test_auth.py` | 1 | `pytest tests/test_multi_tenancy.py tests/test_auth.py -v` | ASGI in-process (`client`/`session`, sin servidor real) | revertir el commit elimina las 4 fixtures y ambas suites; `conftest.py` vuelve al estado de 01-fundacion-tdd |
| B | `test_rbac_catalog.py` + `test_users_admin.py` + `test_permissions_matrix.py` | 2 | `pytest tests/test_rbac_catalog.py tests/test_users_admin.py tests/test_permissions_matrix.py -v` | ASGI in-process, actores vía `make_member`/`rbac_admin` | revertir el commit elimina las 3 suites; no depende de código de producción |
| C | `test_alert_engine.py` (4 estrategias sin `blocked_task` + evaluador + dedup + scheduler) | 3 | `pytest tests/test_alert_engine.py -v` | `evaluate_organization(db, org_id)` directo sobre la sesión de prueba, sin reloj real, sin `_run_evaluation` | revertir el commit elimina la suite; `test_blocked_task_alert.py` (cambio 04) intacto |
| D | `test_methodology_strategies.py` + `test_projects.py` + `test_tasks_crud.py` | 4 | `pytest tests/test_methodology_strategies.py tests/test_projects.py tests/test_tasks_crud.py -v` | unit puro (methodology, sin BD) + ASGI in-process (projects/tasks) | revertir el commit elimina las 3 suites; `test_task_key.py`/`test_board_*` intactos |
| E | `test_notifications_inapp.py` + `test_dashboard_executive.py` | 5 | `pytest tests/test_notifications_inapp.py tests/test_dashboard_executive.py -v` | ASGI in-process | revertir el commit elimina ambas suites; `test_dashboard_work_gap.py` (cambio 05) intacto |

## Lote A — conftest (fixtures nuevas) + multi-tenancy + auth (Commit 1)

- [ ] T01 [Foundation] `backend/tests/conftest.py`: agregar `second_tenant(session)`, `make_member(session, org, role) -> (User, token)` (email único vía `uuid.uuid4().hex[:12]`, sin parámetro `suffix`) y `rbac_admin(session, org, user)` (`Role(code="ADMIN")` + `UserRole`).
- [ ] T02 RED `backend/tests/test_multi_tenancy.py`: R1 aislamiento row-level en `/projects`; R2 tenant resuelto desde `get_current_membership` (1.ª membresía por `created_at`, nunca por parámetro del cliente); R3 `MemberRole` como base de `require_role`; R4 seed idempotente de "Solercia". Usa fixture `two_orgs` (aún inexistente) → falla en colección, confirma rojo.
- [ ] T03 [Foundation] `backend/tests/conftest.py`: agregar fixture `two_orgs(session) -> TwoOrgs` — orgA/orgB, cada una con user, project, task, alert_rule y notification propios (corrección vinculante del design).
- [ ] T04 VERIFY `pytest tests/test_multi_tenancy.py -v` → verde.
- [ ] T05 RED `backend/tests/test_auth.py`: R1/R2 login (access 30 min + cookie refresh httpOnly 7 días `SameSite=lax`); R3 rotación de refresh (jti nuevo + access nuevo); R4 bcrypt con truncamiento a 72 bytes; R5 `GET /auth/me/menus` árbol filtrado por rol; logout 204 + cookie eliminada. (rojo: aserción invertida, ej. mismo jti tras refresh)
- [ ] T06 VERIFY `pytest tests/test_auth.py -v` → verde.
- [ ] T07 VERIFY checkpoint Lote A — `cd backend && pytest tests/ -v` (258+nuevos) verde, `ruff check .`, `mypy app` limpios. Commit `test(baseline): blindar multi-tenancy y auth + fixtures de dos organizaciones`.

## Lote B — rbac-catalog + matriz de permisos + users-admin (Commit 2)

- [ ] T08 RED `backend/tests/test_rbac_catalog.py`: R1 `require_admin` en `/admin/roles`,`/admin/menus`,`/admin/dependencies` (sin ADMIN → 403); R2 `PUT /admin/roles/{id}/menus` reemplaza grants (semántica de set) y `GET /auth/me/menus` refleja el cambio; R3 árbol de menús anidado por `parent_id`/`order`; R4 borrado suave. Actor autorizado vía `rbac_admin`. (rojo: aserción invertida)
- [ ] T09 VERIFY `pytest tests/test_rbac_catalog.py -v` → verde.
- [ ] T10 RED `backend/tests/test_users_admin.py`: R1 `require_admin` en todo `/admin/users`; R2 creación 201 + solo hash bcrypt almacenado; R3 `DELETE` borrado suave (204, fila persiste, desaparece del listado); R4 `PUT /{id}/roles` reemplaza el set completo de roles. (rojo: aserción invertida, ej. fila eliminada físicamente en R3)
- [ ] T11 VERIFY `pytest tests/test_users_admin.py -v` → verde.
- [ ] T12 RED `backend/tests/test_permissions_matrix.py`: `parametrize (endpoint, método, actor, esperado)` — familia `require_admin` (rbac-catalog, users-admin, `PATCH /alert-rules/{id}`, `POST /alerts/evaluate`) → `rbac_admin` 2xx, `member`/`manager` sin RBAC → 403; `GET /users/{id}/time-logs` ajeno → chequeo INLINE en `TimeLogService._require_visibility` (no `require_role()`): member/viewer 403, admin/manager 200; `PATCH`/`DELETE /time-logs/{id}` → dueño 2xx, no-dueño (incl. admin/manager) 403; CRUD `projects`/`tasks` → los 4 `MemberRole` 2xx (sin gate de rol). (rojo: aserción invertida)
- [ ] T13 VERIFY `pytest tests/test_permissions_matrix.py -v` → verde; confirma los 403 documentados en el design.
- [ ] T14 VERIFY checkpoint Lote B — suite completa verde, `ruff check .`, `mypy app` limpios. Commit `test(baseline): blindar rbac-catalog, users-admin y matriz de permisos`.

## Lote C — alert-engine (Commit 3)

- [ ] T15 RED `backend/tests/test_alert_engine.py` (estrategias): sembrar datos que satisfacen `task_overdue`, `task_at_risk`, `sprint_at_risk`, `workload_imbalance` e invocar `evaluate_organization(db, org_id)` directo; cada una produce su notificación esperada. `blocked_task` EXCLUIDA (ya cubierta por `test_blocked_task_alert.py` del cambio 04 — ningún test de este lote la ejercita). (rojo: aserción invertida)
- [ ] T16 RED `backend/tests/test_alert_engine.py` (dedup + reglas `enabled`): R1 el evaluador solo recorre reglas `enabled` de la organización; R2 segunda corrida sin cambios en los datos → una sola notificación activa por `dedup_key` vía `exists_active`. + aislamiento (`two_orgs`): candidatos solo de la org del actor. (rojo: aserción invertida)
- [ ] T17 RED `backend/tests/test_alert_engine.py` (reglas admin + scheduler): R3 `PATCH /alert-rules/{id}` permite a `rbac_admin` ajustar `enabled`/`threshold_params`; R4 `POST /alerts/evaluate` exige `require_admin` (sin rol → 403); `start_scheduler()` registra el job `id="alert_evaluation"` con `IntervalTrigger`, `stop_scheduler()` deja `_scheduler=None` — sin esperar el intervalo ni ejecutar `_run_evaluation`. (rojo: aserción invertida)
- [ ] T18 VERIFY `pytest tests/test_alert_engine.py -v` → verde; confirmar que ningún test nuevo cubre `blocked_task`.
- [ ] T19 VERIFY checkpoint Lote C — suite completa verde, `ruff check .`, `mypy app` limpios. Commit `test(baseline): blindar motor de alertas (4 estrategias + evaluador + dedup + scheduler)`.

## Lote D — methodology-strategies + projects + tasks CRUD (Commit 4)

- [ ] T20 RED `backend/tests/test_methodology_strategies.py` (unit, sin BD): `get_strategy("planner"|"kanban"|"scrum")` → `default_columns()`, `allowed_statuses()`, `sprints_enabled`, `estimation_mode`, `has_backlog`, forma de `to_info()` (R1,R4); `get_strategy("custom")` → solo la parte estática (`default_columns()==[]`, flags; su `allowed_statuses()` board-aware ya está en `test_board_aware_strategy.py`, no se duplica); `get_strategy("xp")` → 422 (R2); sprint rechazado si `sprints_enabled=False` en kanban (R3). (rojo: aserción invertida)
- [ ] T21 VERIFY `pytest tests/test_methodology_strategies.py -v` → verde.
- [ ] T22 RED `backend/tests/test_projects.py`: `POST /projects` con `methodology: "scrum"` → 201, tareas validan estados scrum (R1); `GET /{id}/velocity` puntos por sprint cerrado + promedio + proyección (R3). + aislamiento (`two_orgs`): listado `/projects` de A sin datos de B (R4); `GET`/`PATCH`/`DELETE /projects/{id}` de B desde A → 403/404. (rojo: aserción invertida)
- [ ] T23 VERIFY `pytest tests/test_projects.py -v` → verde.
- [ ] T24 RED `backend/tests/test_tasks_crud.py`: CRUD básico (create/get/update/delete/list); `PATCH` rechaza estado ajeno a la strategy planner, ej. `in_review` (R2 — camino sin board, no duplica `test_board_move_to_column.py`); progreso agregado 2/4 en `GET /tasks/{id}` con 4 subtareas y 2 completadas (R3); filtros combinables `sprint_id`+`status`+`assignee_id` (R4). + aislamiento (`two_orgs`). R1/R5/R6 YA cubiertos por `test_task_key.py`/`test_board_column_tasks.py`/`test_boards_backfill_migration.py` — no se duplican. (rojo: aserción invertida)
- [ ] T25 VERIFY `pytest tests/test_tasks_crud.py -v` → verde.
- [ ] T26 VERIFY checkpoint Lote D — suite completa verde, `ruff check .`, `mypy app` limpios. Commit `test(baseline): blindar methodology-strategies, projects y tasks CRUD`.

## Lote E — notifications-inapp + dashboard-executive (Commit 5)

- [ ] T27 RED `backend/tests/test_notifications_inapp.py`: R1 `GET /notifications` solo trae las del usuario; R2 dedup — `dedup_key` activo no se duplica al reintentar el mismo candidato; R3 `unread-count` solo cuenta `active`; R4 `PATCH /notifications/{id}` cambia `status` (read/resolved/silenced) sin borrado, `unread-count` baja. + aislamiento (`two_orgs`). (rojo: aserción invertida)
- [ ] T28 VERIFY `pytest tests/test_notifications_inapp.py -v` → verde.
- [ ] T29 RED `backend/tests/test_dashboard_executive.py`: R1 `by_assignee` agrupa tareas en curso por persona; R2 `at_risk` incluye `risk_flag`/próximas a vencer; R3 `workload`+`projects_progress`+totales; R4 `GET /dashboard/performance` con `sprint_id` opcional. Matriz de permisos: los 4 `MemberRole` reciben 2xx (sin gate de rol). + aislamiento (`two_orgs`). `work_gap` YA cubierto por `test_dashboard_work_gap.py` (cambio 05) — no se duplica. (rojo: aserción invertida)
- [ ] T30 VERIFY `pytest tests/test_dashboard_executive.py -v` → verde.
- [ ] T31 VERIFY checkpoint final — `cd backend && pytest tests/ -v` (258+~100-110 nuevos) verde, `ruff check .`, `mypy app` limpios en toda la suite; sin regresiones en las 258 suites previas. Commit `test(baseline): blindar notifications-inapp, dashboard-executive y cierre del blindaje 11`.

## Trazabilidad de requisitos

`multi-tenancy` R1–R4 (T02–T04) · `auth` R1–R5 (T05–T06) · `rbac-catalog` R1–R4 (T08–T09) · `users-admin` R1–R4 (T10–T11) · matriz de permisos transversal (T12–T13) · `alert-engine` R1–R4 sin `blocked_task` (T15–T18) · `methodology-strategies` R1–R4 (T20–T21) · `projects` R1,R3,R4 (T22–T23) · `tasks` R2,R3,R4 nuevos + R1,R5,R6 ya cubiertos (T24–T25) · `notifications-inapp` R1–R4 (T27–T28) · `dashboard-executive` R1–R4 + `work_gap` ya cubierto (T29–T30). Aislamiento entre tenants (`two_orgs`) tejido en cada suite tenant-scoped, no en un archivo aparte.
