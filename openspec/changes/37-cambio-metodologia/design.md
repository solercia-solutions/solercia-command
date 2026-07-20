# Design: 37 · Cambio de metodología de un proyecto existente

## Technical Approach

Módulo nuevo Screaming `app/modules/methodology_migration/` (`service`, `repository`,
`schemas`, `router`; SIN `models` — cero tablas nuevas). El router se monta bajo el
espacio de URL de projects (`/projects/{id}/methodology-migration`).
`MethodologyMigrationService` orquesta un caso de uso que cruza projects+boards+
sprints+tasks: compara `resolve_board_strategy(project)` (board actual) contra
`get_strategy(target)` (destino) y ejecuta la reconstrucción en UNA transacción.
Reúsa `BoardService` (add/remove/reassign de columnas), la Strategy (`allowed_statuses`
+ flags) y su propio repository para las escrituras masivas no cubiertas por primitivas
existentes (recompute de `completed_at`, cierre+desvinculación de sprints, chequeo de
invariante, `project.methodology`). Cero `if methodology == ...`. **No requiere
migración Alembic.**

## Architecture Decisions

### D1: Módulo orquestador dedicado (no dentro de projects)

| Opción | Tradeoff | Decisión |
|---|---|---|
| **Módulo `methodology_migration` (service+repository+router, sin models)** | Screaming: la capability nueva se ve en el árbol; mantiene `ProjectService` (490 líneas) sin inflar; respeta "el service no toca SQLAlchemy" con repository propio | **Elegida** |
| Service dentro de `projects` | Menos archivos, pero mezcla un caso de uso cross-aggregate en un service ya grande; contradice Screaming | Rechazada |

Refina la nota proposal-time de state.yaml ("sin nuevo módulo"): el espacio de URL NO
cambia (`/projects/{id}/...`), así que la spec de comportamiento no se ve afectada.

### D2: Mapeo por defecto — slug exacto → bucket semántico → ordinal

El GET plan propone el mapeo (editable): (1) match de slug case-insensitive; (2) bucket
semántico por rol ordinal `{todo=primera, done=última, doing/review=intermedias}`; si el
destino carece del bucket (p. ej. planner sin review) colapsa al anterior
(review→doing); (3) fallback por índice proporcional. Matriz por defecto:

| Destino → | planner | kanban | scrum |
|---|---|---|---|
| **desde planner** | — | Sin iniciar→Backlog, En curso→Doing, Completada→Done | Sin iniciar→To Do, En curso→In Progress, Completada→Done (In Review vacía) |
| **desde kanban** | Backlog→Sin iniciar, Doing→En curso, Done→Completada | — | Backlog→To Do, Doing→In Progress, Done→Done (In Review vacía) |
| **desde scrum** | To Do→Sin iniciar, In Progress→En curso, In Review→En curso, Done→Completada | To Do→Backlog, In Progress→Doing, In Review→Doing, Done→Done | — |

`custom`: el usuario define las columnas destino en el paso 1; el mapeo cae a slug-match
+ ordinal.

### D3: Transaccionalidad — `commit=False` + un único commit final

Las primitivas `BoardService.add_column`/`remove_column` HOY commitean por operación
(`boards/service.py:221,285`); `reassign_column_tasks` NO commitea (delega en un UPDATE
puro). Para todo-o-nada añado `commit: bool = True` a `add_column`/`remove_column` (mismo
precedente que `move_to_column`/`_create_project_unit`: flush sin commit, un commit al
final). Secuencia en la MISMA sesión:

```
validar exhaustividad (422 mapping_not_exhaustive)
 → add_column(dest, commit=False) por columna destino faltante
 → reassign_column_tasks(src→dest)   # status + board_column_id; subtareas remapeadas por su propia columna origen (heredan mapeo)
 → repo.recompute_completed_at(done_key)  # sella si status==done & completed_at NULL; limpia si no
 → remove_column(src, commit=False)  # columnas origen ya vacías; nunca la última (destino ya existe)
 → if not target.sprints_enabled: repo.close_and_unlink_sprints()  # status=closed, closed_at; tasks.sprint_id=NULL
 → repo.set_methodology(project, target)
 → [D4 invariante]
 → db.commit()   # ÚNICO
```

Cualquier excepción → `db.rollback()` total. Orden clave: reasignar ANTES de eliminar
(las columnas origen quedan vacías) y crear destino ANTES de eliminar origen (el board
nunca queda con 0 columnas → `remove_column` nunca choca con su guard de última columna).

### D4: Invariante post-migración (cinturón)

Antes del commit: `repo.count_invalid_tasks(project_id, target.allowed_statuses())`
cuenta tareas activas con `status ∉ allowed`. Si `> 0` → `db.rollback()` + 500
`migration_invariant_violated`. No debería dispararse si D2 + la validación de
exhaustividad funcionan; es el cinturón de seguridad.

### D5: Inmutabilidad preservada

`ProjectService.update_project` MANTIENE el 422 `methodology_not_editable`; el PATCH
normal sigue rechazando `methodology`. La migración persiste `project.methodology` vía
`repository.set_methodology` (nunca por `update_project`).

### D6: UI — asistente 2 pasos en settings

`entities/methodology-migration/{model,service}.ts` + `widgets/methodology-migration-wizard/`
en `pages/projects` (settings). Reúsa dropdown/modal de `shared/ui`. Paso 1: elegir
destino (+ definir columnas si `custom`) → GET plan → mapeo propuesto con dropdown
editable por estado origen. Paso 2: confirmación con impacto (N tareas por estado,
sprints a cerrar, estimaciones que se ocultan) → POST. Estados de carga; el botón
Confirmar queda deshabilitado mientras la petición responde. Solo admin/manager.

## Data Flow

```
GET /projects/{id}/methodology-migration/plan?target=<m>
   resolve_board_strategy(actual) ─┐
   get_strategy(target) ───────────┴─▶ MigrationPlanner ─▶ {mapping propuesto, impacto}

POST /projects/{id}/methodology-migration  (mapping confirmado)
   MethodologyMigrationService.execute ── UNA transacción ──▶
     BoardService(add/reassign/remove, commit=False) + repo(completed_at, sprints, methodology)
     → invariante D4 → commit único | rollback total
```

## File Changes

| File | Action | Description |
|---|---|---|
| `app/modules/methodology_migration/{__init__,schemas,repository,service,router}.py` | Create | Orquestador plan + ejecución; repo con recompute/sprints/invariante/methodology |
| `app/modules/boards/service.py` | Modify | `commit: bool = True` en `add_column`/`remove_column` (precedente `move_to_column`) |
| `app/main.py` | Modify | Registrar router `methodology_migration` |
| `frontend/src/entities/methodology-migration/*` | Create | Cliente plan + execute |
| `frontend/src/widgets/methodology-migration-wizard/*`, `pages/projects/*` | Create/Modify | Asistente 2 pasos |
| `backend/tests/**` | Create | Contratos TDD (ver abajo) |

## Interfaces / Contracts

```python
class StatusMapping(BaseModel):
    source_status_key: str
    target_status_key: str

class StatusImpact(BaseModel):
    status_key: str; name: str; active_task_count: int

class MigrationPlan(BaseModel):            # GET plan
    source_statuses: list[StatusImpact]
    target_columns: list[str]              # default_columns() del destino
    proposed_mapping: list[StatusMapping]
    sprints_to_close: int
    estimations_hidden: bool

class MigrationExecute(BaseModel):         # POST body
    target: Methodology
    mapping: list[StatusMapping]
    custom_columns: list[str] | None       # requerido si target == custom
    confirm_close_sprints: bool

class MethodologyMigrationService:
    async def plan(org_id, project_id, target) -> MigrationPlan
    async def execute(org_id, project_id, data, *, actor_id) -> MigrationResult
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | heurística de mapeo por defecto (slug/bucket/ordinal); colapso review→doing | `MigrationPlanner` con strategies fijas |
| Integration | post-ejecución: toda tarea `status ∈ allowed(destino)` (TDD núcleo) | client + DB |
| Integration | mapeo no exhaustivo → 422; `custom` sin columnas → 422 | client |
| Integration | scrum→planner cierra+desvincula sprints (`sprint_id=NULL`), preserva puntos | client + fixtures |
| Integration | `completed_at` sellado/limpiado contra columna done del destino | client |
| Integration | rollback total ante error inyectado; invariante D4 → 500 | fault injection |
| Integration | permisos admin/manager (403 member/viewer); scoping por org | client |
| Regresión | PATCH normal sigue 422 `methodology_not_editable`; suite verde | suite |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. El riesgo es de dominio (tareas en estado
inválido, `completed_at` inconsistente), mitigado por D3 (transacción única) y D4
(invariante antes del commit).

## Migration / Rollout

Sin migración de esquema Alembic (reúsa `board_columns`/`tasks`/`sprints`). La
"migración" es por-proyecto en runtime, transaccional y reversible: re-ejecutar hacia el
destino inverso restaura columnas/estados; `estimation_points`/sprints cerrados quedan
como historial (no destructivo). Rollback del feature = retirar router + wizard (el PATCH
ya bloquea `methodology`).

## Open Questions

- [ ] `target == methodology actual`: ¿422 `same_methodology` o no-op? Propuesta: 422. No bloqueante.
- [ ] D1 refina la nota state.yaml ("sin nuevo módulo"); la spec paralela debe confirmar que el módulo dedicado no rompe supuestos (URL space intacto). No bloqueante.
