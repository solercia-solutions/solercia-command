# Tasks: 33 · Búsqueda y filtros compartidos en backlog y cronograma (Gantt)

## Reconciliación aplicada (orquestador)

1. **Constraint obsoleto en `state.yaml`** — el constraint de la fase `proposal`
   `no-api-delta-no-backend-tdd-for-mvp` asumía "cero delta de API, sin TDD
   backend" (alcance original: todo client-side). La decisión CERRADA por el
   orquestador en `design.md`/`spec.md` superó ese supuesto: el filtro por
   asignado es **server-side**, reutiliza y extiende el contrato del 32
   (`is_context`) con `assignee_id` repetible (unión OR), lo que introduce un
   delta real de la capability `tasks` y **exige TDD backend** (Fase 1 de este
   documento). Ese constraint quedó **corregido** en `state.yaml` — ver más
   abajo.
2. **Constraint `assignee-filter-honors-32-context-parent-rule-client-side`**
   — describía la regla de contexto del 32 resuelta EN CLIENTE; el diseño
   cerrado (D2) la resuelve en SERVIDOR (el cliente solo renderiza
   `is_context` tal cual llega). Corregido a
   `assignee-filter-server-side-extends-32-context-rule-to-union`.
3. **Capabilities** — `capabilities.new: [frontend-task-filters]` y
   `capabilities.modified: [tasks]` de `state.yaml` YA reflejaban la decisión
   cerrada desde la fase `spec` (no requerían corrección); se dejan
   confirmadas explícitamente en este documento como parte de la
   reconciliación pedida.
4. Los constraints restantes de la fase `proposal`
   (`client-side-filtering-over-loaded-alltasks-mvp`,
   `epic-filter-derived-from-parent-task-id-no-epic-id`,
   `multi-select-avatars-overflow-plus-n`,
   `filters-combine-AND-plus-clear-chip`, `jql-and-labels-out-of-scope`,
   `ui-copy-es-co-formal-tuteo`) siguen vigentes tal cual: describen
   comportamiento CLIENT-side (texto/`task_key`/épica/tipo/fecha) que el
   diseño no modificó.

## Gate de secuenciación (decidido por el orquestador)

El `apply` de este cambio **NO debe arrancar** hasta que **30-backlog-sprints-agrupados**
Y **32-jerarquia-subtareas** estén completamente cerrados (`apply` + `verify` +
`archive` + merge a `preview`). Ambos hoy están en `design: done` / `tasks:
pending` (32) o `tasks: done` / `apply: pending` (30) — ninguno tiene código
aplicado en el árbol de trabajo todavía (confirmado: `tasks/router.py` sigue
con `assignee_id: uuid.UUID | None` singular, sin `include_subtasks` ni
`is_context`; `project-workspace.component.ts` sigue con `epicChildren`/
`loadEpicChildren`, sin `collapsedSections` ni agrupación por sprint).

Este cambio depende de los siguientes seams, que 33 **consume pero no crea**:

- Del 30: señal `collapsedSections` (`Set<string>`), función `sectionId(sprint
  | null): string` (`sprint-<uuid>` | `'backlog'`), agrupación
  `tasksBySprint`/`backlogTasks` sobre `allTasks()`.
- Del 32: query param `include_subtasks: bool` en `GET
  /projects/{id}/tasks`, campo aditivo `TaskRead.is_context: bool = False`,
  la "segunda pasada" de padres de contexto en `TaskService.list_tasks` (hoy
  con `assignee_id` singular) y su helper de repositorio para traer tareas
  por ids scoped a org/proyecto.

La Fase 0 de este documento verifica en disco que esos seams existen ANTES de
tocar código; si falta cualquiera, este cambio se detiene y no continúa.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~950–1150 (producción ~480–560: backend `tasks/{router,service,repository}.py` ~35-45 + tests backend ~180-220; frontend `features/filter-tasks/**` nuevo ~260-320 (`filter-model.ts` ~25, `apply-filters.ts` ~90, `epic-of.ts` ~20, `highlight.ts` ~45, `highlight.component.ts` ~30, `task-filter.store.ts` ~60) + `widgets/task-filter-bar/**` nuevo ~200-260 + `workspace.service.ts`/`workspace.model.ts` ~20 + `project-workspace.component.ts` ~130-170 + `sprint-gantt.component.ts` ~25-35 + `es-CO.json` ~30-40) |
| 400-line budget risk | High — muy por encima del presupuesto de revisión, principalmente por `task-filter-bar.component.ts` (widget nuevo con plantilla completa) + la integración en `project-workspace.component.ts`; sin migración ni datos tocados |
| Chained PRs recommended | No — instrucción explícita: single-pr, merge local a `preview` (mismo patrón que 30/34: commits escalonados dentro de una sola integración) |
| Suggested split | Fase 0 gate 30+32→33 → Fase 1 backend TDD (`assignee_id` repetible + contexto sobre la unión) → Fase 2 función pura `applyTaskFilters` + widget `task-filter-bar` integrado en backlog → Fase 3 integración Gantt → Fase 4 estados vacíos + textos es-CO → Fase 5 suite completa + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |
| Decision needed before apply | Sí — el presupuesto de 400 líneas se supera con holgura; se requiere `size:exception` explícito del mantenedor antes de fusionar (ya aceptado por instrucción de este documento, igual que 30/34) |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U0 | Fase 0 — confirmar que 30 y 32 están aplicados en disco (seams `collapsedSections`, `sectionId`, `include_subtasks`, `is_context`) | (sin commit propio) | `rg -n "collapsedSections|sectionId" frontend/src/widgets/project-workspace/project-workspace.component.ts` y `rg -n "include_subtasks|is_context" backend/app/modules/tasks/{router,schemas,service}.py` | N/A — solo lectura de disco | N/A |
| U1 | Fase 1 — `assignee_id` repetible (unión OR) + extensión de `is_context` a la unión de asignados (TDD backend) | 1 — `feat(tasks): permite assignee_id repetible y extiende el contexto de padres a la union de asignados` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_task_assignee_multiselect.py` | Pytest contra Postgres real de test | Revert commit; el endpoint vuelve a `assignee_id` singular, `is_context` (32) sigue intacto para un único valor |
| U2 | Fase 2 — función pura `applyTaskFilters` + widget `task-filter-bar` (búsqueda, avatares multi-select, épica/tipo/fecha, chips, Limpiar) integrado en backlog | 2 — `feat(filter-tasks): agrega la barra de filtros compartida y la integra en el backlog` | N/A — sin runner de tests configurado en `frontend/package.json` | `cd frontend && npm run build` (build real, sin mocks) | Revert commit; el backlog vuelve a sin barra de filtros, U1 queda intacto y sin consumidores rotos |
| U3 | Fase 3 — el Gantt consume la misma barra (mismas tareas filtradas + expansión de épicas con match) | 3 — `feat(sprint-gantt): consume los filtros compartidos y expande epicas con coincidencia` | N/A — mismo motivo que U2 | `cd frontend && npm run build` | Revert commit; el Gantt vuelve a consumir `allTasks()` sin filtrar, U2 sigue funcional en el backlog |
| U4 | Fase 4 — estados vacíos + textos es-CO + build verde | 4 — `feat(filter-tasks): agrega estados vacios y textos en espanol para los filtros` | N/A — mismo motivo que U2 | `cd frontend && npm run build` | Revert commit; U2/U3 siguen funcionales sin el mensaje de "sin coincidencias" |
| U5 | Fase 5 — suite completa + no regresión + commit final si aplica | 5 — `fix(filtros): cierra hallazgos de la suite completa` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U5 no aporta commit nuevo |

## Fase 0 — Gate: confirmar que 30 y 32 ya están aplicados

- [ ] 0.1 Confirmar en `openspec/changes/30-backlog-sprints-agrupados/state.yaml` y `openspec/changes/32-jerarquia-subtareas/state.yaml` que `phases.apply`, `phases.verify` y `phases.archive` están en `done` y que ambos cambios están mergeados a `preview`. Verify: `git log --oneline preview | rg -i "30-backlog|32-jerarquia"` (o revisar `openspec/changes/archive/` para sus carpetas archivadas).
- [ ] 0.2 Confirmar los seams del 30 en disco: señal `collapsedSections`, función `sectionId(sprint: Sprint | null): string` (`sprint-<uuid>`/`'backlog'`), `tasksBySprint`/`backlogTasks` sobre `allTasks()` en `frontend/src/widgets/project-workspace/project-workspace.component.ts`. Verify: `rg -n "collapsedSections|sectionId|tasksBySprint" frontend/src/widgets/project-workspace/project-workspace.component.ts`. Si falta, DETENER — aplicar primero 30.
- [ ] 0.3 Confirmar los seams del 32 en disco: `include_subtasks: bool` en `backend/app/modules/tasks/router.py`, `is_context: bool = False` en `TaskRead` (`backend/app/modules/tasks/schemas.py`), la "segunda pasada" de padres de contexto en `TaskService.list_tasks` (`backend/app/modules/tasks/service.py`) y su helper de repositorio para traer tareas por ids. Verify: `rg -n "include_subtasks|is_context" backend/app/modules/tasks/{router,schemas,service}.py`. Si falta, DETENER — aplicar primero 32.
- [ ] 0.4 Leer la firma REAL aplicada por 32 de `TaskService.list_tasks`/`TaskRepository.list_for_project` para `assignee_id` (sigue singular, `uuid.UUID | None`, tal como diseñó 32) y el nombre exacto del helper/método que resuelve los padres de contexto (32 no fija un nombre literal en su `design.md`). Verify: leer el código aplicado; actualizar las referencias de nombre de método en la Fase 1 de este documento si difieren de lo aquí asumido, SIN cambiar el contrato de comportamiento (unión OR + `is_context` sobre la unión + sin doble conteo) que exige `specs/tasks/spec.md` de este cambio.

## Fase 1 — Backend: `assignee_id` repetible + contexto sobre la unión (Commit 1)

Extiende el contrato del 32 (hoy `assignee_id` singular con `is_context`) a
`assignee_id` repetible con semántica de unión (OR), igual que ya hace
`label_id` (`tasks/repository.py:98-108`, vía `.in_()`). Contrato exacto:
`specs/tasks/spec.md` (delta MODIFIED + ADDED) de este cambio.

- [ ] 1.1 [RED] Crear `backend/tests/test_task_assignee_multiselect.py` (mismo patrón de fixtures `client`/`tenant`/fixtures de `conftest.py` que `test_task_filters.py`). `test_list_tasks_assignee_id_single_value_still_works_backward_compat`: 1 tarea asignada a A, otra a B; `?assignee_id={A}` sigue devolviendo SOLO la de A (regresión: el cambio de firma de `uuid.UUID | None` a `list[uuid.UUID]` no debe alterar el caso de un solo valor). Hoy pasa igual con la firma actual — este test es la red de seguridad ANTES de tocar `router.py`. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_task_assignee_multiselect.py -k backward_compat` → verde con la firma actual (documenta el comportamiento a preservar).
- [ ] 1.2 [RED] `test_list_tasks_assignee_id_repeated_returns_union_not_intersection`: tareas asignadas a A, B y C respectivamente; `?assignee_id={A}&assignee_id={B}` DEBE devolver solo las de A y B (unión, no intersección), la de C queda fuera. Hoy falla: FastAPI/Pydantic coacciona el segundo `assignee_id` repetido de forma inconsistente con `uuid.UUID | None` (o solo toma el último valor). Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k returns_union_not_intersection` → falla.
- [ ] 1.3 [RED] `test_list_tasks_context_parent_appears_for_multiselect_union`: subtarea asignada a B cuyo padre real está asignado a D (tercer usuario, ajeno a la selección), con `include_subtasks=true`; `?assignee_id={A}&assignee_id={B}&include_subtasks=true` DEBE devolver la subtarea como match y el padre exactamente una vez con `is_context=true`, sin sumar a `meta.total`. Hoy falla: la "segunda pasada" de contexto del 32 solo compara contra un `assignee_id` singular, así que con dos valores repetidos el comportamiento es indefinido/incorrecto (según lo que arroje 1.2). Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k context_parent_appears_for_multiselect_union` → falla.
- [ ] 1.4 [RED] `test_list_tasks_context_parent_not_duplicated_when_parent_also_matches`: padre asignado a A, subtarea asignada a B, ambos bajo `include_subtasks=true`; `?assignee_id={A}&assignee_id={B}` DEBE devolver el padre UNA sola vez con `is_context=false` (es un match real, no contexto) y contarlo en `meta.total`. Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k not_duplicated_when_parent_also_matches`.
- [ ] 1.5 [RED] `test_list_tasks_assignee_id_multiselect_respects_tenant_scoping_auth_and_permissions`: la misma consulta multi-valor sin token responde `401`; contra un proyecto de otra organización (`two_orgs` o patrón equivalente ya usado en `test_task_filters.py`/`test_sprint_backlog_aggregates.py`) responde `404`; un miembro de la organización dueña ve el resultado correcto. Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k tenant_scoping_auth_and_permissions`.
- [ ] 1.6 [GREEN] `backend/app/modules/tasks/router.py`: cambiar `assignee_id: uuid.UUID | None = Query(default=None)` (línea 44) por `assignee_id: list[uuid.UUID] = Query(default_factory=list, description="Repetible; unión (OR) entre asignados.")`; actualizar el docstring de `list_tasks` para documentar la semántica de unión (mismo patrón que `label_id`); pasar `assignee_id=assignee_id` sin cambios al `service.list_tasks(...)` (ahora recibe una lista, posiblemente vacía). Verify: aún sin wiring de servicio — solo compila.
- [ ] 1.7 [GREEN] `backend/app/modules/tasks/service.py`: cambiar la firma de `list_tasks` de `assignee_id: uuid.UUID | None = None` a `assignee_id: Sequence[uuid.UUID] | None = None`; pasar `assignee_id=assignee_id or None` a `self.repo.list_for_project(...)` (lista vacía se normaliza a `None`, preserva "sin filtro" cuando no se selecciona ningún avatar); extender la "segunda pasada" de padres de contexto (32) para que compare contra el CONJUNTO de `assignee_id` recibido en vez de un único valor (mismo criterio: un padre es contexto si NINGUNO de los ids solicitados coincide con su propio `assignee_id`, y ninguna de sus subtareas matcheadas ya lo trae como match real). Verify: mismo comando de 1.2-1.4 → deja de fallar por firma, pendiente del paso 1.8.
- [ ] 1.8 [GREEN] `backend/app/modules/tasks/repository.py`: cambiar `list_for_project(..., assignee_id: uuid.UUID | None = None, ...)` (línea 49) a `assignee_ids: Sequence[uuid.UUID] | None = None`; reemplazar `if assignee_id is not None: stmt = stmt.where(Task.assignee_id == assignee_id)` (líneas 88-89) por `if assignee_ids: stmt = stmt.where(Task.assignee_id.in_(assignee_ids))` (mismo patrón OR ya usado por `label_ids`, sin necesidad de `.distinct()` porque `assignee_id` es columna directa de `Task`, no requiere join). Actualizar el call site de `service.py` (1.7) para pasar `assignee_ids=assignee_id`. Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k "returns_union_not_intersection or backward_compat"` → verde.
- [ ] 1.9 [GREEN] Extender el helper de repositorio que 32 introdujo para traer padres de contexto por ids (identificado en 0.4) para que la resolución de "el padre no matchea NINGUNO de los ids solicitados" opere sobre el conjunto completo de `assignee_ids`, reutilizando el mismo scoping org/proyecto y el mismo criterio de dedup (si el padre ya es un match real, no se reinyecta). Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k "context_parent_appears_for_multiselect_union or not_duplicated_when_parent_also_matches"` → verde.
- [ ] 1.10 Suite dirigida verde + regresión del módulo `tasks` completo (incluye los tests del 32 sobre `is_context`/`include_subtasks` con un solo `assignee_id`, que deben seguir en verde sin cambios de comportamiento). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_task_assignee_multiselect.py backend/tests/test_task_filters.py backend/tests/test_tasks_crud.py backend/tests/test_subtasks.py`

Commit 1: `feat(tasks): permite assignee_id repetible y extiende el contexto de padres a la union de asignados`

## Fase 2 — Frontend: función pura `applyTaskFilters` + widget `task-filter-bar` en el backlog (Commit 2)

- [ ] 2.1 Crear `frontend/src/features/filter-tasks/filter-model.ts`: `export interface TaskFilters { searchText: string; assigneeIds: ReadonlySet<string>; epicIds: ReadonlySet<string>; taskTypes: ReadonlySet<string>; dueFrom: string | null; dueTo: string | null; }`; `export interface HighlightSegment { text: string; match: boolean; }`; `export interface FilterResult { visibleIds: ReadonlySet<string>; matchIds: ReadonlySet<string>; sectionsToExpand: ReadonlySet<string>; highlightQuery: string; }` (contrato exacto de `design.md`).
- [ ] 2.2 Crear `frontend/src/features/filter-tasks/highlight.ts`: `normalizeText(value: string): string` (minúsculas + `.normalize('NFD').replace(/[̀-ͯ]/g, '')` para ignorar tildes) y `buildHighlightSegments(text: string, query: string): HighlightSegment[]` (si `query` vacío, un único segmento `{text, match:false}`; si no, segmenta por la primera coincidencia normalizada, preservando el texto ORIGINAL con tildes en cada segmento — solo la comparación ignora tildes).
- [ ] 2.3 Crear `frontend/src/features/filter-tasks/epic-of.ts`: `resolveEpicId(task: Task, byId: ReadonlyMap<string, Task>): string | null` — sube `parent_task_id` iterativamente (con guarda de ciclo/máximo de saltos, dado que la anidación real es de un solo nivel tras 32) hasta encontrar una tarea con `task_type === 'epic'`; devuelve `null` si no hay épica en la cadena.
- [ ] 2.4 Crear `frontend/src/features/filter-tasks/apply-filters.ts`: `export function applyTaskFilters(tasks: Task[], f: TaskFilters): FilterResult` — función pura, sin dependencias de Angular. Índice `byId` y `bySectionId` (usa `sectionId()` del 30, importado o replicado localmente si el 30 no lo expone como función libre — confirmar en 0.2). Para cada tarea: `matchesSearch` (task_key o título contiene `normalizeText(f.searchText)`, vacío = true), `matchesEpic` (`f.epicIds` vacío = true; si no, `resolveEpicId(task) ∈ f.epicIds` o la propia tarea es la épica seleccionada), `matchesType` (`f.taskTypes` vacío = true; si no, `task.task_type ∈ f.taskTypes`), `matchesDate` (`f.dueFrom`/`f.dueTo` ambos `null` = true; comparación UTC-día sobre `task.due_date`, una tarea sin `due_date` NO matchea un rango activo). `visibleIds` = tareas donde TODAS las condiciones anteriores son verdaderas (AND) — el filtro por asignado NO se re-evalúa aquí (ya viene resuelto del servidor en el set `tasks`). `matchIds` = subconjunto de `visibleIds` con `matchesSearch` verdadero Y `f.searchText` no vacío (para resaltar). `sectionsToExpand` = ids de sección (`sectionId(task)`) que contienen algún elemento de `matchIds`. Predicados vacíos (todos los filtros client-side sin activar) ⇒ `visibleIds` = todas, `matchIds` = vacío, `sectionsToExpand` = vacío.
- [ ] 2.5 Crear `frontend/src/features/filter-tasks/highlight.component.ts`: componente standalone `sol-highlight` con `@Input() text = ''; @Input() query = '';`, plantilla `@for (seg of segments(); track $index) { @if (seg.match) {<mark>{{ seg.text }}</mark>} @else {{{ seg.text }}} }` usando `buildHighlightSegments` en un `computed()` — CERO `[innerHTML]`/`DomSanitizer` (D4).
- [ ] 2.6 Crear `frontend/src/features/filter-tasks/task-filter.store.ts`: clase `TaskFilterStore` con signals `searchText = signal('')`, `assigneeIds = signal<ReadonlySet<string>>(new Set())`, `epicIds = signal<ReadonlySet<string>>(new Set())`, `taskTypes = signal<ReadonlySet<string>>(new Set())`, `dueFrom = signal<string | null>(null)`, `dueTo = signal<string | null>(null)`; setters (`setSearchText`, `toggleAssignee`, `toggleEpic`, `toggleTaskType`, `setDueRange`) que crean un `Set`/valor nuevo (inmutabilidad de signals); `hasActiveFilters = computed(...)`; `clear(): void` resetea TODO a los valores default (incluida `assigneeIds`, que dispara la recarga sin `assignee_id` en el consumidor).
- [ ] 2.7 `frontend/src/entities/workspace/workspace.service.ts`: cambiar `TaskQuery.assignee_id?: string` (línea 25) a `assignee_id?: string | string[]`; en el método `tasks()` (líneas 50-59), reemplazar `if (query.assignee_id) { params = params.set('assignee_id', query.assignee_id); }` por una rama que, cuando `assignee_id` es un array, use `params.append('assignee_id', id)` por cada elemento (HttpParams es inmutable — reasignar en cada `append`), y cuando es un string único preserve el comportamiento actual (`.set(...)`). Si el 32 ya agregó `include_subtasks` a `TaskQuery`/al método `tasks()`, NO duplicar — solo confirmar que sigue serializándose junto al `assignee_id` repetido.
- [ ] 2.8 Crear `frontend/src/widgets/task-filter-bar/task-filter-bar.component.ts` — widget standalone único, inyecta `TaskFilterStore` (provisto por el host, D1): (a) input de búsqueda con debounce ~250ms (`toSignal`/`debounceTime` sobre un `Subject<string>` o `effect` con `setTimeout` cancelable) que llama `store.setSearchText`; (b) fila de avatares desde `members` (input del widget, `@Input() members: Member[] = []`) mostrando hasta N (ej. 6) con inicial (`taskCardInitial`-equivalente), estado seleccionado (anillo/relleno) y `aria-pressed`/`aria-label` con el nombre completo; overflow `+N` como botón que expande un panel app-local (signal `overflowOpen`) con el resto de miembros, cada uno con los mismos atributos `aria-*`; togglear un avatar llama `store.toggleAssignee(id)`; (c) dropdown de épica (`@Input() epics: Task[] = []`, tareas con `task_type==='epic'`) que llama `store.toggleEpic`; (d) dropdown de tipo (`epic`/`story`/`task`/`bug`/`subtask`) que llama `store.toggleTaskType`; (e) selector de rango de fechas (`due_from`/`due_to`) que llama `store.setDueRange`; (f) fila de chips — uno por filtro activo (texto, cada asignado, cada épica, cada tipo, rango de fechas) con botón de cierre individual; (g) botón "Limpiar filtros" (`store.clear()`), visible solo si `store.hasActiveFilters()`; (h) `@Output() assigneeSelectionChanged = new EventEmitter<ReadonlySet<string>>()` — emite (debounced) cuando `assigneeIds` cambia, para que el host dispare la recarga server-side sin que el widget conozca `workspace.service.ts`.
- [ ] 2.9 `frontend/src/widgets/project-workspace/project-workspace.component.ts`: agregar `providers: [TaskFilterStore]` al decorador del componente (D1, scope de proyecto — se resetea al navegar, NO `providedIn:'root'`); montar `<sol-task-filter-bar [members]="members()" [epics]="epicOptions()" (assigneeSelectionChanged)="onAssigneeSelectionChanged($event)" />` sobre la pestaña Backlog; `epicOptions = computed(() => this.allTasks().filter(t => t.task_type === 'epic'))`; `clientFilters = computed<TaskFilters>(() => ({ searchText: this.filterStore.searchText(), assigneeIds: new Set(), epicIds: this.filterStore.epicIds(), taskTypes: this.filterStore.taskTypes(), dueFrom: this.filterStore.dueFrom(), dueTo: this.filterStore.dueTo() }))` (el asignado NO entra aquí — ya viene resuelto por el servidor en `allTasks()`); `filterResult = computed(() => applyTaskFilters(this.allTasks(), this.clientFilters()))`; `effectiveCollapsed = computed(() => new Set([...this.collapsedSections()].filter(id => !this.filterResult().sectionsToExpand.has(id))))` (override NO persistido, D4 — el `Set` de `localStorage` no se reescribe); `onAssigneeSelectionChanged(ids: ReadonlySet<string>)`: debounce ~250ms (un solo `setTimeout` reasignado, cancelando el previo) → `this.loadTasks({ assignee_id: ids.size ? [...ids] : undefined, include_subtasks: true })`. Envolver el título de cada tarjeta de tarea con `<sol-highlight [text]="task.title" [query]="filterResult().highlightQuery" />` cuando `filterResult().matchIds.has(task.id)`, y mostrar el estado vacío (Fase 4) cuando `filterResult().visibleIds.size === 0` y hay algún filtro activo.
- [ ] 2.10 Build verde: Verify: `cd frontend && npm run build`.

Commit 2: `feat(filter-tasks): agrega la barra de filtros compartida y la integra en el backlog`

## Fase 3 — Integración en el Gantt (Commit 3)

- [ ] 3.1 `frontend/src/widgets/sprint-gantt/sprint-gantt.component.ts`: agregar `readonly forceExpandIds = input<ReadonlySet<string>>(new Set())` (opcional); en el `computed()` que arma `GanttGroup[]` (donde hoy se usa `collapsedGroups`, ~línea 412 en adelante), calcular `effectiveCollapsed = computed(() => new Set([...this.collapsedGroups()].filter(id => !this.forceExpandIds().has(id))))` y usarlo en vez de `collapsedGroups()` directamente para decidir qué grupos-épica se renderizan expandidos (override en memoria, NO persistido — el colapso del Gantt ya es solo memoria hoy).
- [ ] 3.2 `frontend/src/widgets/project-workspace/project-workspace.component.ts`: calcular `filteredGanttTasks = computed(() => this.allTasks().filter(t => this.filterResult().visibleIds.has(t.id) || t.is_context))` (visibleIds del filtro client-side UNIDO a los padres de contexto server-side, que nunca deben ocultarse); pasar `<sol-sprint-gantt [tasks]="filteredGanttTasks()" [forceExpandIds]="filterResult().sectionsToExpand" ... />` en el template donde hoy se monta `<sol-sprint-gantt [tasks]="ganttTasks">` (o el binding equivalente actual).
- [ ] 3.3 Confirmar que el toggle de avatares (debounced en 2.9) dispara UNA sola recarga y que los filtros client-side (texto/épica/tipo/fecha) se re-aplican sobre el nuevo `allTasks()` sin refetch adicional (ya cubierto por el `computed()` de 2.9/3.2 al depender de la signal `allTasks`).
- [ ] 3.4 Build verde: Verify: `cd frontend && npm run build`.

Commit 3: `feat(sprint-gantt): consume los filtros compartidos y expande epicas con coincidencia`

## Fase 4 — Estados vacíos + textos es-CO + build verde (Commit 4)

- [ ] 4.1 Estado vacío "sin coincidencias": cuando `filterResult().visibleIds.size === 0` y `filterStore.hasActiveFilters()` es verdadero, mostrar "No hay tareas que coincidan con los filtros" (texto exacto de `specs/frontend-task-filters/spec.md`) tanto en las secciones del backlog como en el área del Gantt (ambas vistas comparten el mismo `filterResult`), en vez de listas/filas vacías sin explicación.
- [ ] 4.2 `frontend/src/assets/i18n/es-CO.json`: bajo un bloque nuevo `workspace.filters` (tuteo formal, mismo patrón que `workspace.backlog`/`workspace.sprints`), agregar: `searchPlaceholder: "Busca por clave o título (ej. SDM-42)"`, `clearFilters: "Limpiar filtros"`, `noMatches: "No hay tareas que coincidan con los filtros"`, `overflowMore: "+{{ count }}"`, `assigneeAria: "Filtra por {{ name }}"`, `assigneeOverflowAria: "Ver más asignados"`, `epicLabel: "Épica"`, `typeLabel: "Tipo"`, `dueRangeLabel: "Rango de fechas"`, `activeFilterChip: "{{ label }}"`. No duplicar claves ya existentes de `workspace.sprints`/`workspace.backlog`.
- [ ] 4.3 Build verde: Verify: `cd frontend && npm run build`.

Commit 4: `feat(filter-tasks): agrega estados vacios y textos en espanol para los filtros`

## Fase 5 — Suite completa + no regresión + commits (Commit 5 condicional)

- [ ] 5.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 5.2 Confirmar que el aislamiento multi-tenant no regresó con `assignee_id` repetible (ya cubierto en 1.5, relectura de cierre). Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k tenant_scoping_auth_and_permissions`
- [ ] 5.3 Confirmar que `meta.total` sigue contando SOLO matches reales (nunca padres de contexto) también bajo selección múltiple (relectura de cierre de 1.3/1.4). Verify: `pytest -q backend/tests/test_task_assignee_multiselect.py -k "context_parent_appears_for_multiselect_union or not_duplicated_when_parent_also_matches"`
- [ ] 5.4 Build de frontend verde (repetir tras cualquier ajuste de las Fases 2-4). Verify: `cd frontend && npm run build`
- [ ] 5.5 Commit final (solo si 5.1-5.3 generaron correcciones no cubiertas por los commits 1-4; caso contrario no aporta commit nuevo).

Commit 5 (solo si 5.5 generó cambios): `fix(filtros): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Fuente única de estado de filtros compartida entre backlog y Gantt (mismo resultado en ambas vistas) · 2.6,2.9,3.2
- Filtro por asignado resuelto en servidor, `assignee_id` repetible (unión OR), backward-compat de un solo valor · 1.1,1.2,1.6,1.7,1.8,2.7,2.9
- Contexto de padres extendido a la unión de asignados, sin duplicar ni sumar a `meta.total` · 1.3,1.4,1.9,5.3
- Aislamiento de tenant y permisos del filtro multi-asignado · 1.5,5.2
- Fila de avatares con overflow "+N" y atributos `aria-*` · 2.8
- Búsqueda resalta y auto-expande sin ocultar (sin narrowing duro) · 2.2,2.4,2.5,2.9
- Filtro por épica derivado de `parent_task_id` (sin `epic_id`) · 2.3,2.4
- Filtros por tipo de tarea y rango de fechas (client-side) · 2.4
- Combinación AND entre todos los filtros (servidor + cliente) · 2.4,2.9
- Chips de filtros activos + acción "Limpiar filtros" · 2.6,2.8
- Estado vacío "No hay tareas que coincidan con los filtros" · 4.1
- Integración Gantt: mismas tareas filtradas + expansión de épicas con match · 3.1,3.2,3.3
- Gate 30+32→33 (seams `collapsedSections`/`sectionId`/`include_subtasks`/`is_context` ya aplicados) · 0.1,0.2,0.3,0.4
- No regresión y commits escalonados en una sola integración · 5.1,5.2,5.3,5.4,5.5

## Risks

- **Presupuesto de revisión superado con certeza** (~950-1150 líneas, `High`): la mayor parte vive en el widget nuevo `task-filter-bar.component.ts` (plantilla completa) y la integración en `project-workspace.component.ts`; se requiere `size:exception` explícito del mantenedor antes de fusionar (ya aceptado por instrucción de este documento).
- **Doble dependencia de secuenciación (30 Y 32)**: a diferencia de 30 (que solo esperaba a 29) o 34 (que solo esperaba a 28), este cambio depende de DOS cambios abiertos simultáneamente. Si cualquiera de los dos sufre ajustes de diseño durante su propio `apply` (nombres de signal/función), la Fase 0 de este documento debe releerse ANTES de iniciar la Fase 1/2, no asumirse por adelantado.
- **Nombre del helper de contexto del 32 no está fijado**: `32/design.md` no da un nombre literal al método/servicio que resuelve los padres de contexto; la Fase 1 de este documento (1.9) asume que existe y es extensible a una lista de ids, pero el nombre exacto se confirma en 0.4 al momento de aplicar, no antes.
- **`assignee_id` vacío vs. ausente**: `assignee_id: list[uuid.UUID] = Query(default_factory=list)` no distingue "el usuario deseleccionó todos los avatares" de "nunca se seleccionó ninguno" — ambos casos producen una lista vacía y DEBEN comportarse como "sin filtro" (todas las tareas), documentado en 1.7/2.6 (`clear()`/deselección total recargan sin `assignee_id`).
- **Sin test runner de frontend**: `frontend/package.json` solo define `build`/`lint`/`watch`; las Fases 2-4 se verifican exclusivamente con `npm run build`, sin cobertura automatizada de `applyTaskFilters`/`buildHighlightSegments` pese a ser funciones puras (mismo gap ya aceptado en 30/34; `design.md` de este cambio lo marca como "vitest opcional NO bloqueante").
- **Fuente de avatares fijada en `members`** (open question de `design.md`, no bloqueante): un asignado que dejó de ser miembro de la organización no tendrá avatar en la fila de filtros aunque sus tareas sigan asignadas a él; aceptado para el alcance de este cambio, confirmable en `verify`.
- **Resaltado en las etiquetas del Gantt fuera de alcance** (open question de `design.md`): el MVP de la Fase 3 resalta solo en las filas/tarjetas del backlog; las etiquetas internas del Gantt no llevan `<sol-highlight>` en este documento.
