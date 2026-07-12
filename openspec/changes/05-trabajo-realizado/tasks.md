# Tasks: 05 · Trabajo realizado (TimeLog + TaskHistory + cruce asignado vs. realizado)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1200–1800 (10 archivos nuevos, 4 modificados, 1 migración, 3 suites de test) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Commit 1 (time_logs) → Commit 2 (activity + integración) → Commit 3 (dashboard work_gap) → Commit 4 (docs) |
| Estrategia de entrega | local commits directos a main, sin PR |
| Estrategia de encadenado | stacked-to-main (secuencial, cada commit deja la suite en verde) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Dependencia dura: `sdd-apply` NO puede iniciar hasta que **02-contrato-api** esté aplicado (`AuditMixin`/`get_actor_id`, paginación, cadena de Alembic). El orden entre 03/04 es flexible; `down_revision` de la migración de este cambio se resuelve contra el head vigente al momento de aplicar.

### Suggested Work Units

| Unit | Objetivo | Commit | Notas |
|------|----------|--------|-------|
| 1 | Módulo `time_logs` completo (CRUD + permisos + agregación) | 1 — `feat(time-logs): ...` | Requiere migración de ambas tablas (ver T01) |
| 2 | Módulo `activity` + integración en `tasks`/`sprints` | 2 — `feat(activity): ...` | Depende de Unit 1 solo por la migración compartida |
| 3 | Bloque `work_gap` en dashboard ejecutivo | 3 — `feat(dashboard): ...` | Depende de Units 1 y 2 (lee ambas tablas) |
| 4 | Documentación | 4 — `docs(api): ...` | Incluye verificación final (T26) antes de commitear |

## Fase A — Módulo `time_logs` (Commit 1)

- [x] T01 [Foundation] Migración Alembic `xxxx_add_time_logs_and_task_history.py`: crea `task_time_logs` y `task_history` (`down_revision`=head al aplicar).
- [x] T02 [Foundation] `app/modules/time_logs/models.py`: `TaskTimeLog` (Pk+Timestamp+SoftDelete+AuditMixin).
- [x] T03 RED `backend/tests/test_time_logs.py`: registro válido/horas inválidas (R1); edición/borrado propio y ajeno→403 incl. `manager`/`admin` (R2); visibilidad `member` vs. `manager` (R3); paginación+`date_from/date_to` (R4); agregación diaria/semanal (R5). Todo fallando.
- [x] T04 GREEN `time_logs/schemas.py`: `TimeLogCreate/Update/Response`, alias `date`→`work_date`, `hours>0`. [R1]
- [x] T05 GREEN `time_logs/repository.py`: CRUD + `SORTABLE_FIELDS` + queries de agregación diaria/semanal. [R4,R5]
- [x] T06 GREEN `time_logs/service.py`: alta propia vía `get_actor_id`; edición/borrado exige `log.user_id == membership.user_id` sin excepción de rol; lectura ajena vía `require_role(admin, manager)`. [R2,R3]
- [x] T07 GREEN `time_logs/router.py` con las 6 rutas del alcance propuesto; registrar en `app/main.py`. [R1–R5]
- [x] T08 VERIFY `pytest backend/tests/test_time_logs.py -v` en verde; confirmar los 403 explícitos de T03.

## Fase B — Módulo `activity` + integración (Commit 2)

- [x] T09 [Foundation] `app/modules/activity/models.py`: `TaskHistory` (Pk+Timestamp, sin soft delete, `actor_id` nullable, `actor_type`). Adelantado a Batch A: `alembic check` (test_migrations_baseline.py) exige que la migración compartida de T01 tenga su modelo ORM registrado de inmediato, así que el modelo se creó junto con la migración para mantener la suite en verde entre batches.
- [x] T10 GREEN `activity/recorder.py`: `record_task_history(db, task_id, actor_id, actor_type, changes)` (`add_all` sin commit). Firma real incluye `organization_id` (columna `NOT NULL` de `TenantMixin`, ausente en la firma abreviada del design.md).
- [x] T11 RED `backend/tests/test_activity.py`: cambio de `status` deja historial (R6); múltiples campos en un PATCH (R6); sin cambio→sin fila (R6); cierre de sprint deja historial de sistema (R7); historial por tarea paginado desc (R8); actividad por usuario/día (R9); sin ruta PATCH/DELETE en `/tasks/{id}/history/{id}`→404 (R10). Todo fallando.
- [x] T12 GREEN `activity/schemas.py`: `TaskHistoryResponse` con alias `changed_at`→`created_at`. [R8,R9]
- [x] T13 GREEN `activity/repository.py`: listado por tarea (desc) y por actor/día, `SORTABLE_FIELDS`. [R8,R9]
- [x] T14 GREEN `activity/service.py` + `router.py`: `GET /tasks/{id}/history`, `GET /users/{id}/activity`; registrar en `app/main.py`. [R8,R9,R10]
- [x] T15 GREEN Modificar `tasks/service.py::update_task`: snapshot pre-mutación de `{status, assignee_id, estimation_points, estimation_hours, sprint_id, priority}`, diff post-mutación, `record_task_history(actor_type=user)`. [R6]
- [x] T16 REFACTOR `sprints/repository.py::count_and_move_incomplete_tasks` → `list[uuid.UUID]` (ids movidos), misma lógica de query.
- [x] T17 GREEN Modificar `sprints/service.py::close_sprint`: `tasks_moved=len(ids)`; `record_task_history` por tarea movida (`field=sprint_id`, `actor_type=system`, `actor_id=None`). [R7]
- [x] T18 VERIFY `pytest backend/tests/test_sprint_close.py -v` en verde tras el refactor (contrato `SprintCloseResponse.tasks_moved` intacto).
- [x] T19 VERIFY `pytest backend/tests/test_activity.py -v` en verde.

## Fase C — Dashboard: bloque `work_gap` (Commit 3)

- [ ] T20 RED `backend/tests/test_dashboard_work_gap.py`: `hours_logged` vs `hours_estimated` (R11); `tasks_assigned` vs `tasks_with_activity` (R11); `no_recent_activity` con umbral por defecto 3 días (R12); `?threshold_days` configurable (R12); colaborador con actividad reciente no marcado (R12). Todo fallando.
- [ ] T21 GREEN `dashboard/service.py`: agregaciones `hours_by_user` y `last_activity_by_user`; renombrar `discrepancy()`→`_work_gap(org_id, threshold_days)` plegado dentro de `executive()`. [R11,R12]
- [ ] T22 GREEN `dashboard/router.py`: query param `?threshold_days` (default 3) en `GET /dashboard/executive`. [R12]
- [ ] T23 VERIFY `pytest backend/tests/test_dashboard_work_gap.py` + suite de dashboard existente en verde; confirmar que `performance` no cambia.

## Fase D — Documentación y cierre (Commit 4)

- [ ] T24 Actualizar `docs/API.md`: rutas de `time_logs`/`activity` y bloque `work_gap` en `GET /dashboard/executive` (request/response de ejemplo).
- [ ] T25 Actualizar `docs/ARCHITECTURE.md`: entidades `TaskTimeLog`/`TaskHistory` y flujo `work_gap` en el diagrama de vista ejecutiva.
- [ ] T26 VERIFY final — `cd backend && pytest tests/ -v`, `ruff check .`, `mypy app` en verde; sin regresiones en `test_sprint_close.py`, `test_comments.py`, `test_attachments.py`, `test_mention_notifications.py`, `test_subtasks.py`, `test_task_key.py`.

## Trazabilidad de requisitos

R1 Registro propio · R2 Edición/borrado del dueño · R3 Visibilidad propia vs. supervisión · R4 Listados paginados · R5 Agregación diaria/semanal (`specs/time-logs`). R6 Captura en mutación de usuario · R7 Captura en mutación de sistema · R8 Historial por tarea · R9 Actividad por usuario/día · R10 Solo lectura (`specs/activity-history`). R11 Cruce horas/tareas · R12 Colaboradores sin actividad reciente (`specs/dashboard-executive`).
