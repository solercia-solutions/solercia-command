# Design: 30 · Backlog con sprints agrupados (secciones colapsables estilo Jira)

## Technical Approach

Cambio de solo lectura + reutilización de acciones existentes, sin migración. En
backend, la lectura de sprints (`GET /projects/{id}/sprints`) se enriquece con
agregados calculados en servidor mediante **una sola** consulta agrupada
(`GROUP BY sprint_id`) que reutiliza el precedente `func.count`/`func.coalesce`/
`func.sum` del repositorio (`sum_done_points_for_sprint`, `count_backlog_points_for_project`).
`SprintRead` queda intacto (lo usan `create`/`update`/`close`/`burndown`); los
agregados viven en un schema de lista propio (`SprintListItem`) y en `meta.backlog`.
En frontend, la pestaña **Backlog** se reorganiza en secciones colapsables: la
**cabecera** usa el conteo autoritativo del servidor; el **cuerpo** reutiliza
`allTasks()` agrupado por `sprint_id` (sin fetch extra). Colapso persistido en
`localStorage`. Acciones contextuales reutilizan los seams de 29 (badge, mapa
estado→acción, `POST /sprints/{id}/start`).

## Architecture Decisions

### D1: Agregados en el repositorio con una consulta agrupada

**Choice**: nuevo `SprintRepository.aggregate_tasks_by_sprint(org, project) -> dict[UUID|None, tuple[int, float]]`
= `SELECT sprint_id, count(*), coalesce(sum(estimation_hours),0) ... GROUP BY sprint_id`
(join `Project` para scoping, `Task.is_active`). Una sola query cubre **todos** los
sprints **y** el backlog (fila `sprint_id IS NULL`). `service.list_sprints` compone
`SprintListItem` por sprint y `meta.backlog` con la fila `None`.
**Alternatives**: (a) endpoint dedicado `GET /projects/{id}/backlog-overview` — más
superficie, duplica scoping; (b) N queries (una por sprint) — N+1; (c) contar en
cliente sobre `allTasks()` — depende del subconjunto filtrado/paginado (rompe con 33).
**Rationale**: una fuente de verdad, O(1) queries, aditivo, reutiliza el patrón ya
probado del repo. `?with=aggregates` opt-in se descarta: la vista siempre los necesita.

### D2: `SprintListItem` aditivo, `SprintRead` intacto

**Choice**: `class SprintListItem(SprintRead): story_count:int=0; estimation_hours_sum:float=0.0`.
Backlog vía `class BacklogAggregate` en `meta`. Consumidores previos ignoran campos extra.
**Alternatives**: añadir campos a `SprintRead` — contamina `burndown`/`close`.
**Rationale**: contrato aditivo, cero ruptura (constraint `additive-only-sprintread-untouched`).

### D3: Sección colapsable como composición app-local con signals

**Choice**: `@solercia/ui` 0.3.0 no expone acordeón → composición en
`project-workspace.component.ts` que espeja el toggle de burndown (`selectedSprintId`).
`collapsedSections = signal<Set<string>>` + `backlogSections = computed()` +
`tasksBySprint = computed()` (agrupa `allTasks()` por `sprint_id`).
**Alternatives**: subir un `sol-accordion` a la librería ahora — amplía alcance fuera de 30.
**Rationale**: mínimo, candidata a promover luego; el cuerpo no recomputa el conteo
(cabecera = agregado backend, evita divergencia — riesgo #1 de la propuesta).

### D4: Orden y visibilidad de secciones

**Choice**: `active` → `draft` (por `created_at`) → sección **Backlog** al final.
Sprints `closed` **ocultos** por defecto tras un enlace "Ver sprints cerrados (N)"
(`showClosedSprints = signal(false)`); al revelarlos se renderizan como secciones
colapsables extra antes del Backlog.
**Alternatives**: mostrar closed siempre — ruido; ordenar por fecha de fin — menos claro.
**Rationale**: lo más simple; prioriza el trabajo accionable arriba.

### D5: Acción contextual (reutiliza 29, sin nuevos endpoints)

Un solo mapa estado→acción (centralizado por 29):

| Estado | Botón | Condición | Endpoint |
|---|---|---|---|
| `active` | Completar | siempre | `POST /sprints/{id}/close` (existente) |
| `draft` + ambas fechas | Iniciar | `start_date && end_date` | `POST /sprints/{id}/start` (29) |
| `draft` sin fechas | Añadir fechas | falta alguna fecha | `PATCH /sprints/{id}` (modal de 29) |
| `closed` | — (solo lectura aquí) | — | reactivar sigue en pestaña Sprints |

### D6: Estado de colapso en localStorage

**Choice**: clave `sp-backlog-sections-<project_id>`; valor = ids colapsados; **default
expandido** (set vacío). Helpers `readPersistedSections`/`persistSections` con `try/catch`
espejando `readPersistedCollapsed`/`persistCollapsed` de `layout-shell.component.ts`.
**Rationale**: patrón `localStorage` ya establecido en el repo; degradación a memoria
si el storage no está disponible (modo privado/quota).

### D7: Frontera con 31 (seams, sin drag & drop)

- Cada sección se envuelve en un contenedor con **id estable**: `sprint-<uuid>` y `backlog`.
- Las tareas dentro de cada sección se pintan en orden de `task.order` (fuente que 31 mutará).
- `tasksBySprint` + `backlogTasks` son las listas de origen/destino del futuro DnD.
- NO se añaden `cdkDropList`/handlers aquí — solo los contenedores y el orden.

## Data Flow

    GET /projects/{id}/sprints
        │ service.list_sprints → repo.list_for_project (sprints)
        │                      → repo.aggregate_tasks_by_sprint (1 query agrupada)
        ▼
    data: SprintListItem[] (story_count, estimation_hours_sum)   meta.backlog: {…}
        │
    Frontend: cabecera ← agregado backend ; cuerpo ← tasksBySprint(allTasks())

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/sprints/repository.py` | Modify | `aggregate_tasks_by_sprint` (1 query `GROUP BY sprint_id`) |
| `backend/app/modules/sprints/service.py` | Modify | `list_sprints` compone `SprintListItem` + backlog aggregate |
| `backend/app/modules/sprints/schemas.py` | Modify | `SprintListItem`, `BacklogAggregate` (aditivos) |
| `backend/app/modules/sprints/router.py` | Modify | lista devuelve items + `meta.backlog` |
| `backend/tests/**` | Create | contrato conteo/suma; backlog `sprint_id IS NULL`; scoping; una sola query |
| `frontend/src/entities/workspace/workspace.model.ts` | Modify | `SprintListItem`, `BacklogAggregate`, `meta.backlog`; `SprintStatus += 'draft'` (29) |
| `frontend/src/entities/workspace/workspace.service.ts` | Modify | parsea `meta.backlog` (sin endpoint nuevo) |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modify | secciones colapsables; `collapsedSections`/`backlogSections`/`tasksBySprint`; acción contextual (29); seams 31 |
| `frontend/src/assets/i18n/es-CO.json` | Modify | textos nuevos (tuteo) |

## Interfaces / Contracts

```python
class SprintListItem(SprintRead):
    story_count: int = 0
    estimation_hours_sum: float = 0.0

class BacklogAggregate(BaseModel):
    story_count: int = 0
    estimation_hours_sum: float = 0.0
```

Lista (envelope `{data, meta}`): `data: SprintListItem[]`, `meta: {total, backlog: BacklogAggregate}`.

```ts
interface SprintListItem extends Sprint { story_count: number; estimation_hours_sum: number; }
interface BacklogAggregate { story_count: number; estimation_hours_sum: number; }
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | `list_sprints` devuelve `story_count`/`estimation_hours_sum` por sprint; backlog en `meta` | `client` + seed tareas con/sin sprint |
| Integration | tareas `is_active=False` excluidas; `estimation_hours` null cuenta 0 | `client` |
| Regresión | scoping multi-tenant; `SprintRead`/`burndown`/`close` intactos; suite completa verde | suite |
| Unit (front) | agrupación `tasksBySprint`; orden de secciones (active→draft→backlog); toggle persiste | signals/localStorage mock |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. Lectura agregada + composición de UI.

## Migration / Rollout

No migration required. Solo código; los agregados son de solo lectura. Revertir el
commit restaura el Backlog plano y la pestaña Sprints; ningún cliente escribe con ellos.

## Open Questions

- [ ] Ninguna bloqueante. Promover la sección colapsable a `@solercia/ui` y persistir
      el colapso en servidor quedan como mejoras futuras (fuera de 30).
