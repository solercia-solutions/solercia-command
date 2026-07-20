# Design: 33 · Búsqueda y filtros compartidos en backlog y cronograma (Gantt)

## Technical Approach

Composición de UI **híbrida**: el filtro por **asignado es server-side** (reusa el
contrato del 32: `assignee_id` + `is_context`), y **texto/`task_key`/épica/tipo/fechas
son client-side en AND** sobre el set ya cargado. La feature `filter-tasks` concentra el
estado (store con signals, provisto a nivel del `project-workspace`) y una **función pura**
`applyTaskFilters(tasks, filters)` que anota `visibleIds`, `matchIds`, `sectionsToExpand` y
`highlightQuery`. El widget `task-filter-bar` es la única barra, montada en el workspace y
compartida por backlog (30) y Gantt (`sprint-gantt`). La regla del 32 (contexto por
asignado) NO se replica en cliente: al tocar avatares se **recarga** el listado con la
regla autoritativa del backend; el resto de filtros vive en el store y se re-aplica sin
refetch, así que se conservan al recargar.

## Architecture Decisions

### D1: Feature `filter-tasks` + store component-scoped; barra como widget compartido
**Choice**: `TaskFilterStore` (signals) provisto en `providers` del `project-workspace`
(no `root`), instancia fresca por proyecto que resetea al navegar. `task-filter-bar`
(widget) inyecta ese store; el workspace lee el mismo. Una barra sirve backlog y timeline.
**Alternatives**: (a) servicio `providedIn:'root'` — estado global filtra entre proyectos;
(b) estado local en el componente + `@Input`/`@Output` en cascada — acopla la barra al host.
**Rationale**: DI component-scoped da fuente única sin singleton global; espeja el idiom de
Angular y aísla por vista.

### D2: Filtrado híbrido — asignado server-side (32), resto client-side AND
**Choice**: avatar → `loadTasks({ assignee_id: [...ids], include_subtasks: true })`; el
backend devuelve matches + padres `is_context` (32). `applyTaskFilters` cubre SOLO
texto/`task_key`/épica/tipo/fechas.
**Alternatives**: (a) todo client-side (supuesto original de la propuesta) — duplica la
regla del 32 en dos capas y diverge (riesgo #2 de la propuesta); (b) N llamadas single-`assignee_id`
mergeadas en cliente — N+1 y rompe el dedup de contexto del backend.
**Rationale**: una sola fuente de verdad para el contexto (32 D2). Requiere delta menor:
`assignee_id` repetible (OR), hoy es UUID único → **TDD backend** (divergencia respecto al
constraint `no-api-delta` de la propuesta, decidida por el orquestador).

### D3: Función pura `applyTaskFilters` (predicados AND + anotación de árbol)
**Choice**: `(tasks, filters) -> FilterResult`, determinista, sin deps de Angular; el
workspace la envuelve en `computed()`. Épica **derivada in-memory** subiendo `parent_task_id`
(subtarea→historia→épica) porque no existe `epic_id`. Predicados vacíos = todo pasa.
`sectionsToExpand` = ids de sección (`sprint-<uuid>`|`backlog`, seam del 30) con algún match.
**Alternatives**: predicado dentro del componente — no testeable sin runner.
**Rationale**: función libre → verificable por build + prueba manual hoy, y con vitest
mañana sin reescribir (vitest opcional NO bloqueante).

### D4: Auto-expand por override no persistido; resaltado sin `innerHTML`
**Choice**: `effectiveCollapsed = collapsedSections(30) − sectionsToExpand`; el override
NO se escribe en `localStorage`, así al limpiar la búsqueda vuelve el colapso guardado.
Resaltado vía `sol-highlight` (componente standalone en la feature) que renderiza
`Segment[]` (`{text, match}`) con `<mark>` por interpolación → cero superficie de inyección.
**Alternatives**: `DomSanitizer.bypassSecurityTrustHtml` + `[innerHTML]` — XSS con títulos
de usuario. Rechazado.
**Rationale**: nada se oculta por colapso, y el marcado es seguro por construcción.

### D5: Avatares desde `members`, multi-select con overflow "+N"
**Choice**: fuente = signal `members` (ya cargado), estable y completa (incluye asignables
sin tarea en vista). Inicial reusando `taskCardInitial` (no hay `SolAvatar`, coherente con
32). Overflow "+N" = panel app-local togglable por signal (no depende de dropdown de la
lib, sin verificar). Estado activo = anillo/relleno; multi-select togglea ids en el store.
**Alternatives**: derivar avatares de los asignados presentes en las tareas cargadas — la
fila parpadea al cambiar filtros y omite miembros sin tarea.
**Rationale**: estabilidad visual. Edge documentado: asignado ex-miembro no tiene avatar.

### D6: Integración Gantt — mismas tareas filtradas + `forceExpandIds`; recarga debounced
**Choice**: `<sol-sprint-gantt [tasks]="filteredGanttTasks()">` (visibleIds ∪ `is_context`).
Input opcional `forceExpandIds` fuerza expandir grupos-épica con match (colapso del Gantt es
solo memoria → override sin persistencia). Toggle de avatares **debounced** (~250 ms) →
una sola recarga; los filtros client-side permanecen en el store y se re-aplican al set nuevo.
**Rationale**: seam mínimo; misma barra arriba, filas filtradas/expandidas; sin refetch por
los filtros de texto/épica/tipo/fecha.

## Data Flow

    [avatares] → store.assigneeIds ──(debounce)──▶ loadTasks(assignee_id[]&include_subtasks)
                                                     │  backend 32: matches + is_context
                                                     ▼
                     allTasks() (con is_context) ──▶ applyTaskFilters(tasks, clientFilters)
    [texto/épica/tipo/fecha] → store ──────────────▶ FilterResult{visibleIds,matchIds,
                                                        sectionsToExpand,highlightQuery}
                                                     │
      backlog(30): effectiveCollapsed = collapsed − sectionsToExpand ; <sol-highlight>
      gantt: [tasks]=filtrado ; forceExpandIds=sectionsToExpand(épicas)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/features/filter-tasks/filter-model.ts` | Create | `TaskFilters`, `FilterResult`, `HighlightSegment` |
| `frontend/src/features/filter-tasks/apply-filters.ts` | Create | `applyTaskFilters` puro (AND, match, `sectionsToExpand`) |
| `frontend/src/features/filter-tasks/epic-of.ts` | Create | `resolveEpicId` (sube `parent_task_id` hasta épica) |
| `frontend/src/features/filter-tasks/highlight.ts` | Create | `buildHighlightSegments`, `normalizeText` (sin tildes) |
| `frontend/src/features/filter-tasks/highlight.component.ts` | Create | `sol-highlight` (segmentos + `<mark>`, sin `innerHTML`) |
| `frontend/src/features/filter-tasks/task-filter.store.ts` | Create | store signals (setters + `clear`) |
| `frontend/src/widgets/task-filter-bar/task-filter-bar.component.ts` | Create | barra única: búsqueda, avatares+overflow, épica/tipo/fecha, chip Limpiar, estado vacío |
| `frontend/src/entities/workspace/workspace.service.ts` | Modify | `TaskQuery.assignee_id?: string \| string[]`; serializa params repetidos; `include_subtasks` (32) |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modify | provee store; monta barra; `computed(applyTaskFilters)`; `effectiveCollapsed`; Gantt filtrado; recarga debounced por asignado |
| `frontend/src/widgets/sprint-gantt/sprint-gantt.component.ts` | Modify | input opcional `forceExpandIds`; `effectiveCollapsed` interno |
| `backend/app/modules/tasks/router.py` | Modify | `assignee_id` repetible (`list[UUID]`, OR); backward-compat single |
| `backend/app/modules/tasks/service.py` / `repository.py` | Modify | filtro `assignee_id IN (...)`; padres de contexto (seam 32) para la unión + dedup |
| `backend/tests/**` | Create | `assignee_id` repetible OR + contexto/dedup; compat single; `total` solo matches; scoping |
| `frontend/src/assets/i18n/es-CO.json` | Modify | textos de la barra (tuteo) |

## Interfaces / Contracts

```ts
interface TaskFilters {
  searchText: string;                 // task_key + título (client-side)
  assigneeIds: ReadonlySet<string>;   // server-side (32)
  epicIds: ReadonlySet<string>;       // derivada por parent chain
  taskTypes: ReadonlySet<string>;     // 'epic'|'story'|'task'|'bug'
  dueFrom: string | null; dueTo: string | null; // rango UTC-día
}
interface FilterResult {
  visibleIds: ReadonlySet<string>;      // pasa AND de predicados client-side
  matchIds: ReadonlySet<string>;        // coincidencias de búsqueda (resaltar)
  sectionsToExpand: ReadonlySet<string>;// 'sprint-<uuid>' | 'backlog' con match
  highlightQuery: string;
}
export function applyTaskFilters(tasks: Task[], f: TaskFilters): FilterResult;
```
Backend: `assignee_id: list[UUID] = Query(default_factory=list)` (OR). `meta.total` cuenta
solo matches; `is_context` (32) no suma. Un solo valor mantiene el comportamiento actual.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration (backend, TDD) | `assignee_id` repetible → unión OR + padres de contexto (32) + dedup; compat 1 valor; `total`; scoping | `client` + seed |
| Unit puro (front) | `applyTaskFilters` AND, épica por parent chain, rango UTC, vacío=todo; `buildHighlightSegments` (segmentación, sin tildes, sin HTML) | funciones libres (build; vitest opcional) |
| Manual (front) | búsqueda auto-expande sección colapsada + resalta; avatares recargan y conservan filtros; chip Limpiar; estado vacío; filas del Gantt | prueba en navegador |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de
ejecutables ni integración de procesos. El delta backend es un query param repetible sobre
un listado de solo lectura.

## Migration / Rollout

No migration required. Frontend aditivo; `assignee_id` repetible es backward-compatible
(un valor sigue funcionando). Revertir el commit restaura backlog (30) y Gantt sin barra y
el endpoint single-`assignee_id`; ningún dato se toca.

## Open Questions

- [ ] Fuente de avatares fijada en `members` (edge: asignado ex-miembro sin avatar) —
      confirmable en verify.
- [ ] Resaltado dentro de las etiquetas del Gantt: opcional, diferido (MVP = solo filas).
- [ ] `vitest` para las funciones puras: propuesto como opcional NO bloqueante.
- [ ] Divergencia con el constraint `no-api-delta` de la propuesta: el asignado server-side
      añade delta menor con TDD (decisión del orquestador) — el spec/tasks deben reflejarlo.
