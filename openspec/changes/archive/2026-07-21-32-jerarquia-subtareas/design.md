# Design: 32 · Jerarquía de subtareas en el backlog (padre → subtareas indentadas)

## Technical Approach

Cambio de solo lectura + composición de UI, sin migración. El backend **suministra**
las subtareas en el MISMO listado (`GET /projects/{id}/tasks?include_subtasks=true`)
levantando `top_level_only` (`tasks/service.py:111`) y conserva el orden existente
(`order asc, created_at asc`); NO serializa un árbol. El cliente arma la indentación
agrupando `allTasks()` por `parent_task_id` dentro de cada sección del 30. La regla
innegociable del filtro por asignado vive SOLO en backend: con `assignee_id`, una
segunda pasada trae los **padres de contexto** (`is_context=true`) de subtareas cuyo
padre no matchea. `is_context` es aditivo (default `false`), espeja el patrón de campo
aditivo del 30 (`SprintListItem`).

## Architecture Decisions

### D1: Listado plano con `include_subtasks`, jerarquía compuesta en cliente

**Choice**: query param `include_subtasks: bool = False`. Con `true`,
`top_level_only = parent_task_id is None and not include_subtasks` → devuelve top-level
+ subtareas planas en un solo listado; el cliente agrupa por `parent_task_id`.
**Alternatives**: (a) backend serializa árbol u ordena jerárquicamente — acopla la
serialización a la vista y complica la paginación; (b) N consultas por padre
(`loadEpicChildren`) — N+1.
**Rationale**: una query, sin N+1, reutiliza el patrón del 30 (`allTasks()` agrupado en
cliente). Default `false` preserva el listado plano top-level (sin regresión); `is_context`
aditivo default `false` no rompe consumidores previos.

### D2: Padres de contexto en backend — única fuente de verdad del filtro por asignado

**Choice**: la regla innegociable vive SERVER-SIDE. Con `assignee_id`, tras traer los
matches, una segunda pasada resuelve los `parent_task_id` distintos cuyo padre NO está en
el set de matches y los reinyecta con `is_context=true`. Dedup: si el padre ya matchea el
filtro, `is_context=false` y no se reinyecta. `is_context` se calcula SOLO cuando hay
`assignee_id`.
**Alternatives**: resolver el padre en el cliente — el padre ajeno puede estar filtrado
fuera o en otra página; el cliente no lo resuelve con fiabilidad y duplicaría la regla en
dos capas.
**Rationale**: una sola fuente de verdad, testeable con TDD backend; el 33 (fila de
avatares) consume este contrato sin reimplementar la regla. Se mantiene `assignee_id`
singular (firma actual, spec `tasks` R4); el multi-asignado queda para el 33.

### D3: Agregados del 30 invariantes bajo filtro

**Choice**: no se tocan. Las cabeceras (`story_count`/`estimation_hours_sum`) las calcula
`aggregate_tasks_by_sprint` en `GET /projects/{id}/sprints`, SIN filtro por asignado y en
query independiente del listado de tareas. Filtrar por asignado NO cambia las cabeceras;
subtareas y padres de contexto no inflan conteos.
**Rationale**: coherencia con el 30 (riesgo #1 de esa propuesta): cabecera = agregado
backend, cuerpo = tasks filtradas; nunca convergen.

### D4: Render de sección y padre de contexto atenuado

**Choice**: dentro de cada sección del 30, un view-model por padre
`{ parent, isContext, subtasks[] }`: padre → hijos indentados (margen/borde izquierdo).
Avatar = círculo de inicial reutilizando `taskCardInitial()` (verificado: NO existe
`SolAvatar`, no se crea componente). Padre de contexto atenuado (`opacity-60`), NO
arrastrable, fuera de agregados, clicable solo para abrir su detalle en lectura.
**Subtarea con padre en OTRA sección** (subtarea en sprint A, padre en backlog): el padre
aparece atenuado como contexto DENTRO de la sección de la subtarea, SIN mover el padre real
(que sigue renderizado normal en su propia sección). El origen del contexto es doble y
comparte el mismo render: backend `is_context` (padre filtrado/ausente del set) o cliente
(padre presente en otra sección de `allTasks()`).
**Rationale**: nada se oculta por posición jerárquica; el padre real nunca se reubica.

### D5: Orden por `Task.order` entre hermanos

**Choice**: el backend ya ordena `order asc, created_at asc`. El cliente, tras agrupar,
ordena subtareas por `order` y los grupos por el `order` del padre. Alinea con el seam del
31 (DnD por `task.order`).

## Data Flow

    GET /projects/{id}/tasks?include_subtasks=true[&assignee_id=X]
      │ service.list_tasks → repo.list_for_project (top_level_only levantado)
      │   └─ si assignee_id: 2ª pasada → context parents (is_context=true, dedup)
      ▼
    data: TaskRead[] (planas; is_context)   meta.total = solo matches (contexto NO suma)
      │
    Front: sección(30) → group by parent_task_id → padre + subtareas indentadas; contexto atenuado

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/tasks/router.py` | Modify | Query param `include_subtasks`; se pasa al service |
| `backend/app/modules/tasks/service.py` | Modify | `top_level_only` respeta `include_subtasks`; 2ª pasada de padres de contexto con `assignee_id`; dedup; `total` solo matches |
| `backend/app/modules/tasks/repository.py` | Modify | Helper para traer tareas por ids (padres de las subtareas matcheadas), scoped org/project |
| `backend/app/modules/tasks/schemas.py` | Modify | `TaskRead.is_context: bool = False` (aditivo) |
| `backend/tests/**` | Create | Subtarea de padre ajeno aparece; padre como contexto (no cuenta match, no duplica); `total`; scoping; listado plano por defecto sin regresión |
| `frontend/src/entities/workspace/workspace.service.ts` | Modify | `TaskQuery.include_subtasks`; set param |
| `frontend/src/entities/workspace/workspace.model.ts` | Modify | `Task.is_context?: boolean` |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modify | `loadTasks` con `include_subtasks=true`; view-model por sección (group by parent); padre atenuado; avatar `taskCardInitial` |
| `frontend/src/assets/i18n/es-CO.json` | Modify | Textos (tuteo) |

## Interfaces / Contracts

```python
class TaskRead(BaseModel):
    ...
    is_context: bool = False  # true solo bajo assignee_id: padre traído como contexto
```

Router: `include_subtasks: bool = Query(False)`. El `meta.total` cuenta SOLO los matches
reales; los padres de contexto (`is_context=true`) son suplementarios y NO suman al `total`.

```ts
interface Task { /* … */ is_context?: boolean; }
interface TaskQuery { /* … */ include_subtasks?: boolean; }
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | `include_subtasks=true` devuelve top-level + subtareas planas; default sigue plano top-level | `client` + seed jerárquico |
| Integration | `assignee_id=X` devuelve subtareas de padres ajenos + padres `is_context=true`; dedup si el padre ya matchea | `client` |
| Integration | `meta.total` cuenta solo matches (contexto no suma); scoping multi-tenant | `client` |
| Unit (front) | agrupación por `parent_task_id` dentro de la sección; orden por `order`; padre de contexto atenuado / no arrastrable; avatar inicial | signals |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. Listado de solo lectura + composición de UI.

## Migration / Rollout

No migration required. Solo código; `is_context` e `include_subtasks` son aditivos y opt-in.
Revertir el commit restaura el listado plano top-level y el filtro por asignado previo;
ningún cliente escribe con estos campos.

## Open Questions

- [ ] Ninguna bloqueante. `assignee_id` multi-valor (fila de avatares) y extender la regla
      de contexto a otros filtros (estado/etiqueta) quedan para cambios posteriores (33+).
