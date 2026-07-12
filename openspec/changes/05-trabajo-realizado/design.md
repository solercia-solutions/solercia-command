# Design: 05 · Trabajo realizado (TimeLog + TaskHistory + cruce asignado vs realizado)

## Technical Approach

Dos módulos backend nuevos (`time_logs`, `activity`) con patrón `router → service → repository` y scope tenant transitivo vía join `Task → Project → organization_id` (idéntico a tasks/sprints). El historial se captura por **asignación explícita en el servicio** (no event listeners), reutilizando `get_actor_id` y `AuditMixin` de 02. Un `record_task_history()` compartido inserta filas en la misma transacción que la mutación, invocado por `TaskService.update_task` (actor usuario) y por `SprintService.close_sprint` (actor sistema). El dashboard agrega sobre las tablas nuevas con `GROUP BY` sin N+1: el cruce se expone como bloque aditivo `work_gap` DENTRO de la respuesta de `GET /api/v1/dashboard/executive` (sin endpoint nuevo); el contrato de `performance` no cambia. TDD estricto. Depende de 02 (auditoría, paginación, actor).

## Architecture Decisions

### Decisión: captura de historial explícita en servicio (no event listeners)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `record_task_history()` explícito llamado por cada servicio que muta | Firma explícita, testeable, controla actor/contexto | **Elegida** |
| SQLAlchemy `before_flush`/event listeners | `close_sprint` mueve tareas con `UPDATE ... .values(sprint_id=...)` (bulk) → NO dispara eventos por fila → historial incompleto; sin actor en jobs | Rechazada |

**Rationale**: `count_and_move_incomplete_tasks` es un UPDATE masivo que evita el tracking por objeto; los listeners perderían justo la mutación del sistema (riesgo HIGH del proposal). 02 ya optó por asignación explícita por la misma razón (alert evaluator fuera de request). `actor_id` nullable + `actor_type ∈ {user, system}`.

### Decisión: recorder compartido, no ligado a TaskService

**Choice**: helper `record_task_history(db, task_id, actor_id, actor_type, changes)` en el módulo `activity` (`add_all` SIN commit; el `repo.save()`/`repo.create()` existente sella la transacción).
**Alternatives**: método privado en TaskService (SprintService no lo alcanza); duplicar en cada servicio (drift).
**Rationale**: reutilizable por `update_task`, `close_sprint` y flujos de sistema futuros; atomicidad garantizada con la mutación (una sola transacción, un solo commit).

**Alcance frente al motor de alertas (corrección de gate 2026-07-11)**: las estrategias de alerta actuales NO mutan tareas — solo crean notificaciones —, por lo que HOY no se requiere ningún punto de captura de historial en `alerts/`. Regla defensiva vinculante: cualquier mutación futura de tarea originada por el sistema (motor de alertas incluido) DEBE pasar por `record_task_history` con `actor_type=system` y `actor_id=null`. Esto cierra la ambigüedad del proposal sin ampliar el alcance de este cambio.

### Decisión: detección de cambios por snapshot pre-mutación

**Choice**: en `update_task`, capturar un snapshot de los campos rastreados `{status, assignee_id, estimation_points, estimation_hours, sprint_id, priority}` desde la tarea YA cargada por `_require_task`, aplicar cambios, y diferenciar snapshot vs. valor final. El conjunto rastreado es EXACTAMENTE el que exige `specs/activity-history/spec.md` (incluye `priority`; NO incluye `due_date`) — corrección de gate 2026-07-11.
**Rationale**: sin doble carga; la tarea ya está en sesión. En este modelo "movimiento de columna" == cambio de `status` (no existe `board_column_id`).

### Decisión: modelo de datos e índices

| Tabla | Campos clave | Índices | Soft delete |
|-------|--------------|---------|-------------|
| `task_time_logs` | `task_id` FK, `user_id` FK, `work_date` Date, `hours` Numeric(5,2), `note` Text? | `(user_id, work_date)`, `(task_id)` | Sí + AuditMixin |
| `task_history` | `task_id` FK, `actor_id` UUID?, `actor_type` String, `field` String, `old_value` Text?, `new_value` Text?, `created_at` | `(task_id, created_at)`, `(actor_id, created_at)` | No (append-only, como Notification) |

Valores como Text (`status` es string libre; ids serializados) — agnóstico de metodología. Sin `unique` en time logs: un usuario puede registrar varios tramos el mismo día; la agregación suma.

**Alias API vs. columnas internas (corrección de gate 2026-07-11)**: el contrato observable usa los nombres de la spec; la columna interna puede diferir. La API expone `changed_at` (alias de la columna `created_at` de `TaskHistory`) y `date` (alias de la columna `work_date` de `TaskTimeLog`). Los schemas Pydantic declaran estos alias explícitamente (ver Interfaces).

### Decisión: permisos propio-vs-todos con MemberRole (corrección de gate 2026-07-11)

**Choice**: registrar tiempo propio requiere solo membresía. **Editar (`PATCH`) y eliminar (`DELETE`) son estrictamente del dueño**: el service exige `log.user_id == membership.user_id` SIN excepción de rol — un `admin` o `manager` que intente editar o borrar la entrada de otro usuario recibe 403, exactamente como exige `specs/time-logs/spec.md`. La exención `admin`/`manager` aplica SOLO a lecturas "ver todos" (`GET /users/{user_id}/time-logs` y su `summary` de otro usuario), vía `require_role(MemberRole.admin, MemberRole.manager)`; un `member`/`viewer` solo puede consultar sus propias entradas (403 al consultar las ajenas).
**Rationale**: tasks/sprints ya usan `get_current_membership` (MemberRole), no el RBAC `ADMIN`. Se conserva RBAC `require_admin` para el plano administrativo; MemberRole gobierna este feature, mitigando el riesgo del doble sistema por alineación con el estilo del módulo. Nota de precedente: `require_role` existe en `app/dependencies.py` pero hoy tiene CERO call sites; este cambio es el PRIMER uso real de autorización por `MemberRole`, por lo que su gating exige cobertura de tests explícita (ver Testing Strategy).

### Decisión: cruce dashboard como bloque `work_gap` dentro de `executive` (corrección de gate 2026-07-11)

**Choice**: NO existe endpoint separado (`GET /dashboard/discrepancy` queda eliminado del diseño). El cruce vive DENTRO de `GET /api/v1/dashboard/executive` como bloque `work_gap`, con query param `?threshold_days` (default 3), exactamente como exige `specs/dashboard-executive/spec.md`. El método `_work_gap()` del `DashboardService` es interno (antes `discrepancy()`) y su salida se pliega en la respuesta de `executive()`. Por colaborador, `work_gap` DEBE incluir: `hours_logged`, `hours_estimated`, `tasks_assigned`, `tasks_with_activity`, más la lista de colaboradores sin actividad reciente (`no_recent_activity`). Reutiliza `list_for_org` + `_bounds_for` (horas estimadas de tareas activas por asignado, en Python), una agregación `hours_by_user` (GROUP BY sobre `task_time_logs`) y una `last_activity_by_user` (GROUP BY sobre `task_history`). Cero-actividad = asignados activos sin registros ni historial en la ventana (diferencia de conjuntos en Python).
**Rationale**: 2–3 agregaciones + la carga de tareas ya existente = O(1) queries. `work_gap` es un bloque aditivo: no rompe los campos existentes de `executive` ni altera `performance`.

## Data Flow

    PATCH /tasks/{id}     → update_task: snapshot→mutar→diff→record_task_history(actor=user)→repo.save() (commit sella mutación+historial)
    POST  /sprints/close  → close_sprint: fetch ids a mover→record_task_history(field=sprint_id, actor=system, actor_id=None)→bulk move→sprint.save()
    POST  /tasks/{id}/time-logs → actor=get_actor_id → service(user_id=actor) → repo
    GET   /dashboard/executive?threshold_days=N → executive() + _work_gap(): list_for_org + hours_by_user + last_activity_by_user → bloque work_gap en la respuesta

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/time_logs/{models,schemas,repository,service,router}.py` | Create | CRUD tiempo + agregación diaria/semanal; `SORTABLE_FIELDS`; paginación de 02 |
| `app/modules/activity/{models,schemas,repository,service,router,recorder}.py` | Create | `TaskHistory` + `record_task_history` + lectura por tarea y por usuario/día |
| `app/modules/tasks/service.py` | Modify | Snapshot + diff + `record_task_history` en `update_task` |
| `app/modules/sprints/{service,repository}.py` | Modify | Refactor: `count_and_move_incomplete_tasks(...) -> list[uuid.UUID]` (ids movidos); el service calcula `tasks_moved=len(ids)`; historial de sistema en `close_sprint` |
| `app/modules/dashboard/{service,router}.py` | Modify | Método interno `_work_gap()` plegado en `executive()`; query param `threshold_days` en `GET /dashboard/executive`; sin endpoint nuevo |
| `app/main.py` | Modify | Registrar routers nuevos |
| `alembic/versions/xxxx_add_time_logs_and_task_history.py` | Create | 2 tablas nuevas; `down_revision` = head al aplicar |

## Interfaces / Contracts

```python
def record_task_history(db, task_id, actor_id: UUID | None, actor_type: str,
                        changes: dict[str, tuple[str | None, str | None]]) -> None: ...
async def hours_by_user(org_id, start, end) -> dict[UUID, Decimal]: ...

# Refactor close_sprint (corrección de gate 2026-07-11) — firma exacta:
async def count_and_move_incomplete_tasks(
    self, organization_id: uuid.UUID, sprint_id: uuid.UUID,
    target_sprint_id: uuid.UUID | None,
) -> list[uuid.UUID]: ...  # ids movidos
# El service calcula tasks_moved=len(ids), preservando el contrato existente
# SprintCloseResponse.tasks_moved: int (tests actuales en tests/test_sprint_close.py dependen de él).

# Schemas Pydantic con alias (corrección de gate 2026-07-11) — el contrato
# observable usa los nombres de la spec; la columna interna puede diferir:
class TaskHistoryResponse(BaseModel):
    changed_at: datetime = Field(validation_alias="created_at")  # columna TaskHistory.created_at
    ...

class TimeLogResponse(BaseModel):
    date: date = Field(validation_alias="work_date")  # columna TaskTimeLog.work_date
    ...

# GET /api/v1/dashboard/executive?threshold_days=N (default 3) → respuesta executive existente
# + bloque aditivo work_gap:
# work_gap: {
#   by_user: [{user, hours_logged, hours_estimated, tasks_assigned, tasks_with_activity}],
#   no_recent_activity: [user]   # asignados activos sin TaskHistory ni TaskTimeLog en N días
# }
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | diff de snapshot (incluye `priority`); recorder arma filas; permiso propio-vs-todos | pytest sin BD |
| Integration | CRUD time-log + agregación; PATCH deja historial; **close_sprint deja historial de sistema (`actor_id NULL`, `actor_type=system`)**; `work_gap` en `GET /dashboard/executive` (horas vs estimación, `tasks_assigned` vs `tasks_with_activity`, cero-actividad, `threshold_days`); paginación de listas nuevas | httpx AsyncClient + fixtures de 01 |
| Integration (permisos) | **Cobertura explícita del gating por `MemberRole` (corrección de gate 2026-07-11)**: primer uso real de `require_role` — cada escenario de permisos de `specs/time-logs/spec.md` tiene test propio: edición/borrado ajeno → 403 incluso para `manager`/`admin`; `GET /users/{otro}/time-logs` por `member` → 403; misma consulta por `manager`/`admin` → 200 | httpx AsyncClient + fixtures de 01 |

## Migration / Rollout

Una migración aditiva (2 tablas). `down_revision` = head vigente al aplicar (tras 02; 03/04 si existen — se resuelve en apply). Rollback: `downgrade` elimina ambas tablas; sin backfill, sin impacto en datos existentes.

## Open Questions

- [ ] ¿Registrar también historial para `create_task` y `delete_task` (soft-delete)? Propuesta: sí, como eventos `created`/`deleted`; confirmar en spec.
- [x] Ventana por defecto de cero-actividad (N días): RESUELTO — la spec fija default 3, configurable vía `?threshold_days` de `GET /dashboard/executive` (corrección de gate 2026-07-11).

## Correcciones de gate (2026-07-11)

Correcciones confirmadas por el gate adversarial. Son VINCULANTES para tasks y apply; ante cualquier discrepancia con texto anterior de este documento, prevalece esta lista (y siempre la spec como contrato).

1. **CRITICAL — Dashboard**: eliminado el endpoint separado `GET /dashboard/discrepancy`. El cruce vive dentro de `GET /api/v1/dashboard/executive` como bloque `work_gap`, con query param `threshold_days` (default 3). Por colaborador incluye `hours_logged`, `hours_estimated`, `tasks_assigned`, `tasks_with_activity`, más la lista de colaboradores sin actividad reciente. `discrepancy()` pasa a método interno `_work_gap()` plegado en la respuesta de `executive()`.
2. **CRITICAL — Permisos de time logs**: la exención `admin`/`manager` aplica SOLO a lecturas ("ver todos"). Editar/eliminar es estrictamente del dueño: `log.user_id == membership.user_id` sin excepción de rol (403 incluso para `manager`/`admin`), como exige `specs/time-logs/spec.md`.
3. **CRITICAL — Snapshot de historial**: el conjunto rastreado del snapshot pre-mutación es `{status, assignee_id, estimation_points, estimation_hours, sprint_id, priority}` — exactamente el listado de `specs/activity-history/spec.md` (no incluye `due_date`).
4. **WARNING — Alias API vs. columnas**: la API expone `changed_at` (alias de `TaskHistory.created_at`) y `date` (alias de `TaskTimeLog.work_date`); el contrato observable usa los nombres de la spec, la columna interna puede diferir (schemas con alias en Interfaces).
5. **WARNING — Firma del refactor de `close_sprint`**: `count_and_move_incomplete_tasks(...) -> list[uuid.UUID]` (ids movidos); el service calcula `tasks_moved=len(ids)` preservando `SprintCloseResponse.tasks_moved: int` (tests actuales en `tests/test_sprint_close.py` dependen de él).
6. **WARNING — `require_role` sin precedente**: `require_role` existe en `app/dependencies.py` pero tiene CERO call sites hoy; este cambio es el PRIMER uso real de autorización por `MemberRole`. El gating exige cobertura de tests explícita: cada escenario de permisos de la spec tiene test propio (ver Testing Strategy).
7. **WARNING — Historial desde el motor de alertas**: las estrategias de alerta actuales NO mutan tareas (solo crean notificaciones); no se requiere punto de captura en `alerts/` hoy. Regla defensiva: cualquier mutación futura de sistema DEBE pasar por `record_task_history`.
