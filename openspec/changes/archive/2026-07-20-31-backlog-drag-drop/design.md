# Design: 31 · Backlog drag & drop (arrastrar historias entre backlog y sprints)

## Technical Approach

Se añade una capa de **Angular CDK DragDrop** sobre las secciones que el cambio 30 dejó
como seams (contenedores con id estable `sprint-<uuid>` / `backlog`, tareas pintadas por
`task.order`). Cada sección pasa a ser un `cdkDropList` dentro de un `cdkDropListGroup`;
las tarjetas, `cdkDrag`. Un `enterPredicate` aplica las reglas de destino y las clases de
zona visible. Cada drop persiste con **un solo write atómico** vía un endpoint nuevo
`POST /tasks/reorder` (mueve `sprint_id` + reindexa `order` del contenedor destino en una
transacción). El store de tareas (`allTasks` signal) se actualiza de forma **optimista** y
se revierte a un snapshot ante 4xx/5xx con toast. Un menú "Mover a…" por tarjeta ofrece la
ruta de teclado equivalente sobre el mismo endpoint.

Fact que fija el diseño: `Task.order` es `Integer default=0` y `create_task` **no** asigna
order → hoy todos valen 0 y el orden real lo da el tiebreak `created_at` (repository.py:122).
Insertar en una posición arbitraria con un solo `PATCH` entero es imposible sin reescribir
hermanos; por eso el reindexado por lotes en servidor.

## Architecture Decisions

### D1: Persistencia — `POST /tasks/reorder` (reindexado por lotes, 1 transacción)

**Choice**: endpoint nuevo; body `{ task_id, sprint_id: UUID|null, ordered_task_ids: [UUID] }`.
En una transacción: valida destino (guard D3), fija `task.sprint_id`, y reasigna
`order = índice` a cada id de `ordered_task_ids` del contenedor destino (org+proyecto+`is_active`).
`order` **no** está en `_HISTORY_TRACKED_FIELDS` → sin spam de historial; solo el cambio de
`sprint_id` genera una fila de historia. `tasks` pasa a **Modified**; spec añade el delta con TDD.
**Alternatives**: (a) N `PATCH /tasks/{id}` por hermano — N round-trips, rechazado por el
orquestador; (b) un `PATCH` entero con punto medio — imposible entre `order` iguales (todos 0
hoy) sin re-espaciar; (c) migrar `order` a numérico/float — tampoco resuelve el caso legacy
"todos iguales" en el primer drop y toca una columna compartida por el board.
**Rationale**: un HTTP call por drop, determinista y sin colisiones jamás; absorbe el caso
legacy de ceros; aloja el guard. El orquestador lo pre-aprobó ("preferible a 20 PATCHes").

### D2: Estructura CDK sobre los seams de 30

**Choice**: `cdkDropListGroup` envuelve las secciones; cada sección `cdkDropList` con
`[id]="sprint-<uuid>|backlog"`, `[cdkDropListData]` = su lista (`tasksBySprint()` / `backlogTasks()`),
`[cdkDropListEnterPredicate]="canDropInto(section)"`. Tarjetas `cdkDrag [cdkDragData]="task"`,
placeholder `*cdkDragPlaceholder` (fila punteada). `(cdkDragStarted)` fija `draggingFrom = signal<id|null>`,
`(cdkDragEnded)` lo limpia; `isValidTarget(id)` deriva clases: destino válido → anillo resaltado,
inválido → atenuado/`pointer-events-none`. Secciones `closed` (si se revelan) → dropList rechaza y
sus tarjetas `[cdkDragDisabled]="true"`. `(cdkDropListDropped)` → `onTaskDropped(event)`.
**Rationale**: primitiva estándar y accesible, aislada a la vista de 30; auto-conexión por grupo.

### D3: Guard server-side mínimo (destino closed → 422)

**Choice**: `_verify_sprint` (service.py:822) recibe `reject_closed: bool = False`; `reorder_tasks`
lo llama con `reject_closed=True`. Si el sprint destino existe pero `status == "closed"` →
`AppException("No puedes mover tareas a un sprint cerrado.", code="sprint_closed", status_code=422)`.
`update_task`/`create_task` conservan el default `False` (sin ripple a sus tests).
**Alternatives**: centralizar sin flag (cambia el modal existente → churn de tests).
**Rationale**: guard mínimo en un solo punto; las reglas finas (both-draft, nunca desde closed)
siguen UI-enforced como hoy. RED test: `POST /tasks/reorder` a sprint closed → 422 `sprint_closed`.

### D4: Optimista + rollback sobre `allTasks` (signal)

**Choice**: espeja `onKanbanItemMoved` (component:1264). En el drop: `const snapshot = this.allTasks()`;
`moveItemInArray`/`transferArrayItem` sobre las listas derivadas; `allTasks.update(...)` fija el nuevo
`sprint_id` y los `order` del destino (las `computed()` de 30 re-renderizan). Llama `reorderTasks(...)`;
`error: () => { this.allTasks.set(snapshot); this.toast(errorMsg); this.loadTasks(); }`.
**Rationale**: rollback total con un snapshot inmutable; reconciliación con `loadTasks` tras fallo.

### D5: Menú "Mover a…" (ruta de teclado)

**Choice**: control secundario en `taskCardTpl` (la tarjeta hoy solo tiene "Abrir detalle", sin menú):
dropdown/botón "Mover a…" que lista los destinos válidos de esa tarjeta según `canDropInto`. Al elegir,
invoca el mismo `reorderTasks` **anexando** la tarea al final del destino (`ordered_task_ids = destino + [id]`).
El drag por teclado de CDK queda como complemento. Reutiliza el dropdown de `@solercia/ui` si existe;
si no, botón + menú accesible (`aria-haspopup`, `role="menu"`).

## Data Flow

    drop / "Mover a…"
        │ onTaskDropped → allTasks.update (optimista)
        ▼
    POST /tasks/reorder { task_id, sprint_id, ordered_task_ids }
        │ service.reorder_tasks → _verify_sprint(reject_closed=True)  (D3)
        │                       → task.sprint_id = dest ; order = índice (1 tx)
        ▼
    { data: TaskRead }  → éxito: mantener  |  4xx/5xx: allTasks.set(snapshot) + toast + loadTasks

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/tasks/router.py` | Modify | `POST /tasks/reorder` (get_current_membership, get_actor_id) |
| `backend/app/modules/tasks/service.py` | Modify | `reorder_tasks`; `_verify_sprint(reject_closed=...)` guard closed |
| `backend/app/modules/tasks/repository.py` | Modify | reasignación de `order` por lista de ids (contenedor scoped) |
| `backend/app/modules/tasks/schemas.py` | Modify | `TaskReorder` (task_id, sprint_id, ordered_task_ids) |
| `backend/tests/**` | Create | happy (move+reorder), error (closed→422), permisos (cross-org) |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modify | CDK dropLists/predicate; drop handler; optimista/rollback; menú "Mover a…" |
| `frontend/src/entities/workspace/workspace.service.ts` | Modify | `reorderTasks(payload)` → POST |
| `frontend/src/entities/workspace/workspace.model.ts` | Modify | `TaskReorderPayload` |
| `frontend/src/assets/i18n/es-CO.json` | Modify | textos (tuteo): "Mover a…", estados de arrastre, errores |
| `frontend/.../project-workspace.component.spec.ts` | Create/Modify | reglas de destino, optimista/rollback, agrupación |

## Interfaces / Contracts

```python
class TaskReorder(BaseModel):
    task_id: uuid.UUID
    sprint_id: uuid.UUID | None = None      # destino (null = backlog)
    ordered_task_ids: list[uuid.UUID]       # orden del contenedor destino tras el drop
# POST /tasks/reorder -> { "data": TaskRead }; 422 sprint_closed | invalid_sprint; 404 task
```

```ts
interface TaskReorderPayload { task_id: string; sprint_id: string | null; ordered_task_ids: string[]; }
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | reorder mueve `sprint_id` + reindexa `order` contiguo; 1 transacción | `client` + seed tareas backlog/sprint |
| Integration | destino `closed` → 422 `sprint_closed`; destino inexistente → 422 `invalid_sprint` | `client` |
| Integration | permisos/aislamiento: miembro de otra org no reordena (404) | `client` |
| Unit (front) | `canDropInto` (backlog↔draft/active; sprint↔sprint solo draft; nunca closed); rollback en error; ids destino | signals + HTTP mock |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. Es CRUD HTTP autorizado (`get_current_membership`,
scoping por `organization_id`) + UI DnD.

## Migration / Rollout

No migration required. `Task.order` sigue `Integer`; el reindexado sobrescribe los ceros legacy
en el primer drop de cada contenedor. Revertir el commit restaura la vista de 30 (mover sigue por
el modal). El endpoint es aditivo y reversible por commit.

## Open Questions

- [ ] Ninguna bloqueante. Centralizar el guard closed también en el modal (`update_task`) y el
      drag por teclado nativo de CDK como complemento del menú quedan como mejoras posteriores.
