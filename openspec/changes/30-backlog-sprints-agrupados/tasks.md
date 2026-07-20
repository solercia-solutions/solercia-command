# Tasks: 30 · Backlog con sprints agrupados (secciones colapsables estilo Jira)

## Gate de secuenciación

Este documento asume que **29-sprint-borrador** ya está completamente cerrado
(apply + verify + archive + merge a `preview`): el estado `draft`,
`POST /sprints/{id}/start`, `sprintBadgeClass()` con la rama `draft` y el mapa
estado→acción de la Fase 5 de 29 (`canStartSprint`, `startSprint`,
`openAddDates`) deben existir en el árbol de trabajo antes de iniciar la Fase 1
de aquí. `apply` de 30 NO debe arrancar mientras el ciclo de 29 siga abierto.

Nota sobre referencias de línea: los números citados en la Fase 2 corresponden
al estado actual del repositorio (**antes** de aplicar 29). La Fase 5 de 29
modifica bloques cercanos (formulario de creación de sprint, badge, botones de
acción); reverificar los números exactos en `apply` tras el merge de 29 — los
nombres de función/signal citados no cambian.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~480–520 (producción ~85–95: `sprints/repository.py` ~20, `sprints/schemas.py` ~12, `sprints/service.py` ~35, `sprints/router.py` ~8, frontend `workspace.model.ts` ~15 + `workspace.service.ts` ~2 + `project-workspace.component.ts` ~150–210 (plantilla + signals + computed + localStorage) + `es-CO.json` ~20; tests ~160–200: `test_sprint_backlog_aggregates.py`) |
| 400-line budget risk | High — cerca o por encima del presupuesto, principalmente por la reestructuración de plantilla en `project-workspace.component.ts`; sin migración ni datos tocados |
| Chained PRs recommended | No — instrucción explícita recibida: single-pr, merge local a `preview`. Partir backend (agregados) y frontend (consumo) en PRs separados dejaría un PR intermedio sin valor visible (agregados sin consumidor, o consumo de un contrato que no existe todavía) |
| Suggested split | Single PR con 4 commits escalonados: Fase 1 agregados backend → Fase 2 secciones colapsables frontend → Fase 3 estados vacíos + textos es-CO → Fase 4 suite completa |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |
| Decision needed before apply | No — alcance, gate de secuenciación con 29 y estrategia ya resueltos explícitamente en este documento |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U1 | Fase 1 — consulta agrupada única (`aggregate_tasks_by_sprint`), `SprintListItem`/`BacklogAggregate` aditivos, `meta.backlog` | 1 — `feat(sprints): agrega agregados de historias y horas por sprint y backlog en la lista` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_sprint_backlog_aggregates.py` | Pytest contra Postgres real de test | Revert commit; `SprintRead`/`burndown`/`close` no se tocaron, el listado vuelve a no exponer agregados |
| U2 | Fase 2 — secciones colapsables en la pestaña Backlog (cabecera servidor, cuerpo `allTasks()`, ids estables, colapso localStorage) | 2 — `feat(project-workspace): reorganiza el backlog en secciones colapsables por sprint` | N/A — sin runner de tests configurado en `frontend/package.json` | `cd frontend && npm run build` (build real, sin mocks) | Revert commit; la pestaña Backlog vuelve a la lista plana previa, el backend de U1 queda intacto y sin consumidores rotos |
| U3 | Fase 3 — estados vacíos (sin sprints / backlog vacío / sprint sin historias) + textos es-CO nuevos | 3 — `feat(project-workspace): agrega estados vacios y textos en espanol para el backlog agrupado` | N/A — mismo motivo que U2 | `cd frontend && npm run build` | Revert commit; U2 sigue funcional sin los mensajes vacíos (solo listas en blanco) |
| U4 | Fase 4 — suite completa + no regresión + commit final si aplica | 4 — `fix(sprints): cierra hallazgos de la suite completa` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U4 no aporta commit nuevo |

## Fase 1 — Backend: agregados en la lectura de sprints (Commit 1)

- [ ] 1.1 [RED] Crear `backend/tests/test_sprint_backlog_aggregates.py` (fixtures `client`/`tenant`/`user`/`two_orgs` de `conftest.py`, mismo patrón de `test_sprint_close.py`). `test_list_sprints_reports_story_count_and_hours_sum_never_null`: sprint A con 2 tareas activas (`estimation_hours=2`, `3`) más una tercera con `is_active=False` (eliminada) en la misma sprint; sprint B recién creado sin tareas. `GET /projects/{id}/sprints` → el ítem de A tiene `story_count == 2`, `estimation_hours_sum == 5`; el de B tiene `story_count == 0`, `estimation_hours_sum == 0` (nunca `null`). Hoy falla: `SprintRead` no define esos campos → `KeyError` al leer la respuesta. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_sprint_backlog_aggregates.py -k reports_story_count_and_hours_sum_never_null` → falla.
- [ ] 1.2 [RED] `test_list_sprints_meta_includes_backlog_aggregate_with_and_without_tasks`: proyecto con 2 tareas sin sprint (4h y 1h) → `meta.backlog == {"story_count": 2, "estimation_hours_sum": 5}`; otro proyecto sin tareas sueltas → `meta.backlog == {"story_count": 0, "estimation_hours_sum": 0}`. Hoy falla: `build_list_meta` no incluye la clave `backlog` → `KeyError`. Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k meta_includes_backlog_aggregate`.
- [ ] 1.3 [RED] `test_list_sprints_aggregates_respect_tenant_scoping_auth_and_permissions`: un `member` lista su proyecto y ve los agregados nuevos; la misma solicitud sin token responde `401`; la misma solicitud contra un proyecto de `two_orgs` (otra organización) responde `404`. Hoy falla la rama propia (agregados ausentes); 401/404 ya pasan hoy y quedan como red de seguridad. Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k tenant_scoping_auth_and_permissions`.
- [ ] 1.4 [RED] `test_aggregate_tasks_by_sprint_called_exactly_once_regardless_of_sprint_count`: proyecto con 3 sprints + tareas sueltas de backlog; usar `unittest.mock` para envolver `SprintRepository.aggregate_tasks_by_sprint` con un spy (`monkeypatch`/`AsyncMock` con `wraps`) y afirmar `call_count == 1` tras `GET /projects/{id}/sprints` (prueba D1: una sola consulta `GROUP BY` cubre todos los sprints y el backlog, no N+1). Hoy falla: el método no existe → `AttributeError`. Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k called_exactly_once`.
- [ ] 1.5 [GREEN] `backend/app/modules/sprints/repository.py`: agregar `async def aggregate_tasks_by_sprint(self, organization_id, project_id) -> dict[uuid.UUID | None, tuple[int, float]]` — `select(Task.sprint_id, func.count(Task.id), func.coalesce(func.sum(Task.estimation_hours), 0)).join(Project, ...).where(Task.project_id == project_id, Project.organization_id == organization_id, Task.is_active.is_(True)).group_by(Task.sprint_id)`; construir el `dict` con `{row.sprint_id: (row[1], float(row[2])) for row in result}` (clave `None` = fila del backlog). Verify: aún sin wiring — solo compila.
- [ ] 1.6 [GREEN] `backend/app/modules/sprints/schemas.py`: agregar `class SprintListItem(SprintRead): story_count: int = 0; estimation_hours_sum: float = 0.0` y `class BacklogAggregate(BaseModel): story_count: int = 0; estimation_hours_sum: float = 0.0`. `SprintRead` no se toca (D2).
- [ ] 1.7 [GREEN] `backend/app/modules/sprints/service.py`: cambiar `list_sprints` para que, tras `repo.list_for_project`, llame **una sola vez** a `self.repo.aggregate_tasks_by_sprint(organization_id, project_id)`; construir `items: list[SprintListItem]` usando `aggregates.get(sprint.id, (0, 0.0))` por cada sprint; construir `backlog = BacklogAggregate(story_count=..., estimation_hours_sum=...)` desde `aggregates.get(None, (0, 0.0))`; devolver `(items, total, backlog)` (nueva firma de retorno, 3-tupla). Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py` → verde.
- [ ] 1.8 [GREEN] `backend/app/modules/sprints/router.py`: actualizar `list_sprints` para desempacar `sprints, total, backlog = await service.list_sprints(...)` y responder `{"data": sprints, "meta": {**build_list_meta(pagination, total), "backlog": backlog}}`. Verify: mismo comando de 1.7 → verde end-to-end vía HTTP.
- [ ] 1.9 [TEST] Guarda de contrato (D2, ya verde tras 1.5–1.8, sin RED previo — documenta el invariante): `test_sprint_read_burndown_and_close_payloads_unchanged_by_aggregates` confirma que `GET .../burndown` y `POST /sprints/{id}/close` NO incluyen `story_count`/`estimation_hours_sum` en sus respuestas (los agregados viven solo en `SprintListItem`/`meta.backlog`, no en `SprintRead`). Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k unchanged_by_aggregates`.
- [ ] 1.10 Suite dirigida verde + regresión de módulos vecinos: Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_sprint_backlog_aggregates.py backend/tests/test_sprint_close.py`

Commit 1: `feat(sprints): agrega agregados de historias y horas por sprint y backlog en la lista`

## Fase 2 — Frontend: secciones colapsables en la pestaña Backlog (Commit 2)

- [ ] 2.1 `frontend/src/entities/workspace/workspace.model.ts`: agregar `export interface SprintListItem extends Sprint { story_count: number; estimation_hours_sum: number; }` y `export interface BacklogAggregate { story_count: number; estimation_hours_sum: number; }`; cambiar `SprintListResponse` (líneas 115-117) a `{ data: SprintListItem[]; meta: { total: number; backlog: BacklogAggregate } }`.
- [ ] 2.2 `frontend/src/entities/workspace/workspace.service.ts`: sin cambio de método — el endpoint `sprints()` (líneas 103-107) ya devuelve el envelope completo; dejar constancia explícita de que NO se agrega un endpoint dedicado (alternativa descartada en D1), solo se beneficia de los tipos de 2.1 al compilar.
- [ ] 2.3 `frontend/src/widgets/project-workspace/project-workspace.component.ts` línea 933: cambiar `sprints = signal<Sprint[]>([])` a `sprints = signal<SprintListItem[]>([])`; agregar `backlogAggregate = signal<BacklogAggregate>({ story_count: 0, estimation_hours_sum: 0 })`.
- [ ] 2.4 `loadSprints()` (líneas 1198-1201): en `next`, además de `this.sprints.set(res.data ?? [])`, agregar `this.backlogAggregate.set(res.meta?.backlog ?? { story_count: 0, estimation_hours_sum: 0 })`; en `error`, resetear `backlogAggregate` al mismo default.
- [ ] 2.5 Ids estables y orden de secciones (D4/D7): agregar `sectionId(sprint: Sprint | null): string` → `sprint ? \`sprint-${sprint.id}\` : 'backlog'`; agregar `showClosedSprints = signal(false)`; agregar `openSprintSections = computed(() => [...activos, ...draft ordenados asc por created_at])` (filtra `status === 'active'` y `status === 'draft'` de `sprints()`, concatenados, draft ordenado con `localeCompare` sobre `created_at`); agregar `closedSprints = computed(() => this.sprints().filter(s => s.status === 'closed'))`.
- [ ] 2.6 Agrupación del cuerpo sin fetch extra (D3/D7): agregar `tasksBySprint = computed<Map<string, Task[]>>(() => { const map = new Map<string, Task[]>(); for (const t of this.allTasks()) { if (t.sprint_id) { (map.get(t.sprint_id) ?? map.set(t.sprint_id, []).get(t.sprint_id)!).push(t); } } return map; })`; reutilizar `backlogTasks()` ya existente (líneas 1023-1025) como cuerpo de la sección `backlog`, sin duplicar el filtro.
- [ ] 2.7 Colapso persistido en localStorage (D6, espeja `readPersistedCollapsed`/`persistCollapsed` de `frontend/src/widgets/layout-shell/ui/layout-shell.component.ts:169-184`): agregar `collapsedSections = signal<Set<string>>(new Set())`; funciones de módulo `readPersistedSections(projectId: string): Set<string>` (clave `` `sp-backlog-sections-${projectId}` ``, `JSON.parse` a array, `try/catch` retorna `new Set()`) y `persistSections(projectId: string, ids: Set<string>): void` (`JSON.stringify([...ids])`, `try/catch` silencioso); hidratar `collapsedSections` cuando cambia `projectId()` (mismo punto donde hoy se dispara `loadSprints()`, ~línea 1175); método `toggleSection(id: string): void` que alterna el id en una copia nueva del `Set` y llama `persistSections(this.projectId(), this.collapsedSections())`.
- [ ] 2.8 Reemplazar el bloque `@if (activeTab() === 'backlog')` (plantilla líneas 312-343): `@for (sprint of openSprintSections(); track sprint.id)` renderiza una cabecera `[id]="sectionId(sprint)"` con nombre, fechas (`dateLabel`) o "Sin fechas", badge (`sprintBadgeClass`, ya extendido por 29 para `draft`), `sprint.story_count`, `sprint.estimation_hours_sum`, botón de acción según D5 (`draft` sin fechas → "Añadir fechas" vía `openAddDates(sprint)` de 29; `draft` con fechas → "Iniciar sprint" vía `startSprint(sprint)`/`canStartSprint(sprint)` de 29; `active` → "Completar sprint" vía el modal de cierre existente, líneas 701-796) y un botón de colapso (`toggleSection(sectionId(sprint))`); cuerpo `@if (!collapsedSections().has(sectionId(sprint)))` iterando `tasksBySprint().get(sprint.id) ?? []` con el mismo `ng-template *ngTemplateOutlet="taskCardTpl"` (línea 337); tras las secciones abiertas, si `showClosedSprints()` es verdadero, renderizar `closedSprints()` como secciones de solo lectura sin botón de acción (D5); enlace "Ver sprints cerrados (N)" (`closedSprints().length`) que alterna `showClosedSprints`; al final, sección `backlog` fija (`[id]="'backlog'"`) con cabecera desde `backlogAggregate()` y cuerpo `backlogTasks()` reutilizando `taskCardTpl`.
- [ ] 2.9 Build verde: Verify: `cd frontend && npm run build`.

Commit 2: `feat(project-workspace): reorganiza el backlog en secciones colapsables por sprint`

## Fase 3 — Estados vacíos + textos es-CO + build verde (Commit 3)

- [ ] 3.1 Estado vacío "sin sprints": cuando `openSprintSections().length === 0 && closedSprints().length === 0`, ocultar el enlace "Ver sprints cerrados" y mostrar un mensaje breve (`text.backlogNoSprintsYet()`) antes de la sección Backlog fija (que sigue visible siempre).
- [ ] 3.2 Estado vacío de la sección Backlog: reemplazar el mensaje genérico actual (`text.backlogEmpty()`, línea 328) por el mismo texto reutilizado como cuerpo de la sección Backlog cuando `backlogTasks().length === 0`.
- [ ] 3.3 Estado vacío por sprint sin historias: dentro de cada sección de sprint abierta, si `(tasksBySprint().get(sprint.id) ?? []).length === 0`, mostrar un mensaje corto (`text.sprintSectionEmpty()`) en vez de una lista en blanco.
- [ ] 3.4 `frontend/src/assets/i18n/es-CO.json`: bajo un bloque nuevo `workspace.backlog` (mismo patrón que `workspace.sprints`) agregar, en tuteo formal: `noSprintsYet: "Todavía no hay sprints; el backlog se muestra abajo."`, `sprintSectionEmpty: "Este sprint no tiene historias todavía."`, `viewClosedSprints: "Ver sprints cerrados ({{ count }})"`, `hideClosedSprints: "Ocultar sprints cerrados"`, `collapseAria: "Colapsa la sección {{ name }}"`, `expandAria: "Expande la sección {{ name }}"`, `storyCount: "{{ count }} historias"`, `hoursSum: "{{ hours }} h"`. No duplicar claves ya existentes en `workspace.sprints` (`addDates`, `start`, `statusDraft` de 29) — reutilizarlas.
- [ ] 3.5 Build verde: Verify: `cd frontend && npm run build`.

Commit 3: `feat(project-workspace): agrega estados vacios y textos en espanol para el backlog agrupado`

## Fase 4 — Suite completa + no regresión + commits (Commit 4 condicional)

- [ ] 4.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 4.2 Relectura de cierre del contrato D2 (ya cubierto en 1.9): `SprintRead`, `burndown`, `close` y `PATCH /sprints/{id}` (incluido `/start` de 29) no cambiaron de forma tras los agregados. Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k unchanged_by_aggregates`
- [ ] 4.3 Relectura de cierre de aislamiento multi-tenant y permisos (ya cubierto en 1.3). Verify: `pytest -q backend/tests/test_sprint_backlog_aggregates.py -k tenant_scoping_auth_and_permissions`
- [ ] 4.4 Build de frontend verde (repetir tras cualquier ajuste de Fase 2-3). Verify: `cd frontend && npm run build`
- [ ] 4.5 Commit final (solo si 4.1-4.3 generaron correcciones no cubiertas por los commits 1-3; caso contrario no aporta commit nuevo).

Commit 4 (solo si 4.5 generó cambios): `fix(sprints): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Agregados por sprint y por Backlog en la lista (nunca `null`, tareas eliminadas excluidas) · 1.1,1.2,1.5,1.6,1.7,1.8
- Permisos de la lectura de agregados (mismo modelo del módulo, aislamiento de tenant) · 1.3
- Consulta agrupada única, no N+1 (D1) · 1.4
- `SprintRead`/`burndown`/`close` intactos (D2, additive-only) · 1.9,4.2
- Orden, visibilidad y estados vacíos del Backlog agrupado (`active`→`draft`→Backlog, `closed` oculto por defecto) · 2.5,2.8,3.1,3.2,3.3
- Cabecera de sección y acción contextual (nombre, fechas, badge, conteo, suma, botón por estado) · 2.8
- Persistencia del colapso por proyecto y sección (localStorage, default expandido) · 2.7
- Ids estables por sección (seam drag & drop 31) · 2.5,2.8
- No regresión del listado y acciones existentes, suite en verde · 1.10,4.1,4.3,4.4

## Risks

- **Estimación cercana al presupuesto de revisión** (~480–520 líneas, `High`): la mayor parte vive en la reestructuración de plantilla de `project-workspace.component.ts` (Fase 2); si en `apply` crece más de lo previsto, considerar `size:exception` explícito del mantenedor antes de fusionar (ya aceptado por instrucción de este documento).
- **Líneas de referencia previas a 29**: los números citados en la Fase 2 pueden desplazarse tras el merge de 29 (su Fase 5 toca bloques cercanos); los nombres de función/signal son la referencia estable, no el número de línea exacto.
- **Divergencia cabecera vs. cuerpo** (riesgo #1 de la propuesta): mitigado por diseño — la cabecera SIEMPRE lee `story_count`/`estimation_hours_sum` del servidor (2.8), el cuerpo solo agrupa `allTasks()` ya cargado (2.6) sin recomputar el conteo; ningún test debe comparar `tasksBySprint().get(id)!.length` contra `story_count` como si fueran la misma fuente.
- **Sin test runner de frontend**: `frontend/package.json` solo define `build`/`lint`/`watch`; las Fases 2-3 se verifican exclusivamente con `npm run build`, sin cobertura automatizada de UI para las secciones colapsables ni el colapso persistido.
- **`showClosedSprints` en memoria, no persistido**: a diferencia del colapso por sección (2.7), el toggle "Ver sprints cerrados" no se guarda en `localStorage` en este documento (no especificado por `proposal.md`/`design.md`); se reinicia a oculto en cada carga de la pestaña — aceptable para el alcance de 30, puede revisarse si el usuario lo pide en `apply`.
