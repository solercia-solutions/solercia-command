# Tasks: 31 · Backlog drag & drop (arrastrar historias entre backlog y sprints)

## Gate de secuenciación

Este documento asume que **30-backlog-sprints-agrupados** está completamente
cerrado (apply + verify + archive + merge a `preview`), lo que a su vez exige
que **29-sprint-borrador** también lo esté (30 depende de 29). Hoy (verificado
por grep) NO existen en el árbol `sectionId`/`openSprintSections`/
`tasksBySprint`/`collapsedSections` en `project-workspace.component.ts`, ni el
estado `draft` en `sprints/models.py` — los seams `sprint-<uuid>`/`backlog` y
el estado `draft` que este documento consume son productos de 29/30. `apply`
de 31 NO debe arrancar mientras ese ciclo siga abierto.

## Reconciliación aplicada (orquestador)

1. **Instruida**: `design.md` (D1) introdujo `POST /tasks/reorder` sin delta
   paralelo en spec. Se añadió a `specs/tasks/spec.md` el requisito ADDED
   "Reordenamiento transaccional vía `POST /tasks/reorder`" con 4 escenarios
   (reindexa hermanos; destino `closed` → 422 `sprint_closed`; tarea de otra
   organización → 404; permisos sin cambio). `state.yaml` actualizado:
   `capabilities.modified: [tasks]`.
2. **Detectada durante esta fase**: el primer requisito ADDED ya existente en
   `specs/tasks/spec.md` ("Guard de integridad al asignar `sprint_id` en
   PATCH") exige que `PATCH /tasks/{id}` rechace un destino `closed`, y su
   nota explícita dice que el guard "aplica a cualquier consumidor del
   endpoint... o el modal existente". Sin embargo `design.md` D3 dice
   literalmente que `update_task`/`create_task` **conservan el default
   `False`** (solo `reorder_tasks` recibe `reject_closed=True`) — el modal
   (que usa `PATCH`) quedaría sin protección, contradiciendo el spec ya
   aprobado. No se encontró ningún test existente que dependa del
   comportamiento actual (permitir `closed` vía PATCH), así que la alternativa
   de design ("churn de tests") no aplica. Fase 1.1–1.5 abajo implementa el
   guard **también** en `update_task` para satisfacer el spec tal como está
   escrito; se recomienda alinear `design.md` D3 con este resultado en la
   próxima revisión de diseño.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~550–650 (backend producción ~120: `service.py` ~65, `repository.py` ~35, `schemas.py` ~8, `router.py` ~20; backend tests ~300: `test_task_sprint_closed_guard.py` ~100, `test_task_reorder.py` ~200; frontend producción ~230: `project-workspace.component.ts` ~190, `workspace.model.ts`/`workspace.service.ts` ~20, `es-CO.json` ~18) |
| 400-line budget risk | High — el volumen de tests backend (TDD estricto, 5 escenarios de reorder + 2 del guard PATCH) y la integración CDK en la plantilla suman por encima del presupuesto |
| Chained PRs recommended | No — instrucción explícita recibida: single-pr, merge local a `preview`. Backend (guard+reorder) sin frontend consumidor no aporta valor demostrable; frontend sin el endpoint no compila contra un backend real |
| Suggested split | Single PR con 2 commits: Fase 1 backend (guard PATCH + `POST /tasks/reorder`, TDD) → Fase 2 frontend (CDK + optimista/rollback + "Mover a…") |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |
| Decision needed before apply | No — alcance, gate con 30/29 y estrategia ya resueltos explícitamente en este documento |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|-------------------|
| U1 | Fase 1 — guard `closed` en PATCH + `POST /tasks/reorder` transaccional | 1 — `feat(tasks): agrega guard de sprint cerrado y reordenamiento transaccional` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_task_sprint_closed_guard.py backend/tests/test_task_reorder.py` | Pytest contra Postgres real de test | Revert commit; `PATCH /tasks/{id}` vuelve a aceptar cualquier estado de sprint, `POST /tasks/reorder` desaparece; ningún otro endpoint se toca |
| U2 | Fase 2 — CDK DragDrop sobre las secciones de 30, reglas de destino, optimista/rollback, menú "Mover a…" | 2 — `feat(project-workspace): agrega arrastrar y soltar entre backlog y sprints` | N/A — sin runner de tests configurado en `frontend/package.json` (mismo hallazgo que 30) | `cd frontend && npm run build` (build real, sin mocks) | Revert commit; la vista de 30 vuelve a solo el modal para mover sprint/backlog, U1 queda intacto y sin consumidores rotos |
| U3 | Fase 3 — suite completa + no regresión | 3 (condicional) — `fix(tasks): cierra hallazgos de la suite completa` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U3 no aporta commit nuevo |

## Fase 1 — Backend: guard `closed` + `POST /tasks/reorder` (Commit 1)

- [x] 1.1 [RED] Crear `backend/tests/test_task_sprint_closed_guard.py` (fixtures `client`/`tenant`/`user`/`two_orgs`). `test_patch_task_rejects_closed_target_sprint_422`: tarea en Backlog + sprint del mismo proyecto con `status="closed"` (seed directo) → `PATCH /tasks/{id}` `{"sprint_id": <closed>}` hoy responde `200` (`_verify_sprint` solo valida existencia) → debe responder `422` `code=sprint_closed`, tarea conserva su `sprint_id` anterior. Verify: `pytest -q backend/tests/test_task_sprint_closed_guard.py -k rejects_closed_target_sprint`.
- [x] 1.2 [TEST] Mismo archivo, ya verde hoy (documenta no-regresión, spec Escenarios 1/2): `test_patch_task_accepts_draft_and_active_target_sprint`.
- [x] 1.3 [TEST] Mismo archivo, ya verde hoy (spec Escenarios 4/5): `test_patch_task_sprint_guard_respects_permissions_and_org_isolation` — `member` reasigna su propio sprint `draft`; `sprint_id` de `two_orgs.b` vía token de `two_orgs.a` → **422 `invalid_sprint`** (desviación documentada: `specs/tasks/spec.md` describe `404`, pero `_verify_sprint` — sin cambios en este alcance, D3 solo añade el guard de `closed` — ya responde `422` para cualquier sprint no encontrado en el org/proyecto del solicitante, sin distinguir "no existe" de "otra organización"; el resultado protector es el mismo, aislamiento preservado. Ampliar el guard para diferenciar 404 queda fuera de alcance de esta reconciliación).
- [x] 1.4 [GREEN] `backend/app/modules/tasks/service.py`: `_verify_sprint` (línea 822) recibe `reject_closed: bool = False`; si `sprint.status == "closed"` y `reject_closed` → `AppException("No puedes mover tareas a un sprint cerrado.", code="sprint_closed", status_code=422)`. En `update_task` (línea 440-444), la rama `if "sprint_id" in changes` pasa `reject_closed=True` (reconciliación #2). `create_task` conserva el default `False` (sin requisito de spec sobre creación). Verify: 1.1–1.3 verdes.
- [x] 1.5 [RED] Crear `backend/tests/test_task_reorder.py`. `test_reorder_moves_task_and_reindexes_destination_container`: sprint `draft` con tareas `[A,B,C]` (`order` 0,1,2) + tarea `D` en Backlog → `POST /tasks/reorder` `{task_id: D, sprint_id: <draft>, ordered_task_ids: [A,D,B,C]}` hoy `404` (ruta no existe) → debe responder `200`, `D.sprint_id == draft`, `order` de `A,D,B,C == 0,1,2,3`. Verify: `pytest -q backend/tests/test_task_reorder.py -k reindexes_destination_container`.
- [x] 1.6 [RED] Mismo archivo: `test_reorder_rejects_closed_target_sprint_422` — destino `closed` → `422 sprint_closed`, tarea conserva `sprint_id`/`order` previos, sin tocar a los demás ids del arreglo. Verify: `pytest -q backend/tests/test_task_reorder.py -k rejects_closed_target_sprint`.
- [x] 1.7 [RED] Mismo archivo: `test_reorder_rejects_task_from_other_organization_404` — `task_id` de `two_orgs.b` con token de `two_orgs.a` → `404`, sin ninguna reasignación. Verify: `pytest -q backend/tests/test_task_reorder.py -k rejects_task_from_other_organization`.
- [x] 1.8 [RED] Mismo archivo: `test_reorder_respects_existing_permissions` — `member` reordena dentro de su proyecto (200); sin token → `401` (mismo modelo del módulo). Verify: `pytest -q backend/tests/test_task_reorder.py -k respects_existing_permissions`.
- [x] 1.9 [RED] Mismo archivo: `test_reorder_is_single_transaction_and_order_not_history_tracked` — spy (`monkeypatch`/`AsyncMock` con `wraps`) sobre `TaskRepository.save` para `call_count == 1`; tras el reorder, `TaskHistory` tiene exactamente 1 fila nueva (por `sprint_id`), ninguna por `order` (D1, `order` fuera de `_HISTORY_TRACKED_FIELDS`). Verify: `pytest -q backend/tests/test_task_reorder.py -k single_transaction_and_order_not_history_tracked`.
- [x] 1.10 [GREEN] `backend/app/modules/tasks/schemas.py`: `class TaskReorder(BaseModel): task_id: uuid.UUID; sprint_id: uuid.UUID | None = None; ordered_task_ids: list[uuid.UUID]`.
- [x] 1.11 [GREEN] `backend/app/modules/tasks/repository.py`: `async def reassign_order_for_container(self, organization_id, project_id, ordered_task_ids: list[uuid.UUID]) -> None` — `select(Task).join(Project,...).where(Task.id.in_(ordered_task_ids), Task.project_id == project_id, Project.organization_id == organization_id, Task.is_active.is_(True))`; por cada id en `ordered_task_ids`, `task.order = índice` (no comitea; el caller cierra la transacción).
- [x] 1.12 [GREEN] `backend/app/modules/tasks/service.py`: `async def reorder_tasks(self, organization_id, task_id, sprint_id, ordered_task_ids, *, actor_id=None) -> TaskRead` — `task = await self._require_task(...)`; `project = await self._require_project(..., task.project_id)`; snapshot `{"sprint_id": task.sprint_id}`; `await self._verify_sprint(organization_id, task.project_id, sprint_id, reject_closed=True)`; `task.sprint_id = sprint_id`; `await self.repo.reassign_order_for_container(organization_id, task.project_id, ordered_task_ids)`; `await self._record_history_diff(organization_id, task, snapshot, actor_id=actor_id)`; `task = await self.repo.save(task)` (1 commit cubre el cambio de `sprint_id` + el reindexado en memoria). Verify: 1.5–1.9 verdes.
- [x] 1.13 [GREEN] `backend/app/modules/tasks/router.py`: `@router.post("/tasks/reorder")` con `get_current_membership`, `get_actor_id`, payload `TaskReorder` → `service.reorder_tasks(membership.organization_id, payload.task_id, payload.sprint_id, payload.ordered_task_ids, actor_id=actor_id)` → `{"data": task}`. Verify: mismo comando de 1.12 end-to-end vía HTTP.
- [x] 1.14 Suite dirigida verde: `pytest -q backend/tests/test_task_sprint_closed_guard.py backend/tests/test_task_reorder.py backend/tests/test_tasks_crud.py`

Commit 1: `feat(tasks): agrega guard de sprint cerrado y reordenamiento transaccional`

## Fase 2 — Frontend: CDK DragDrop + optimista/rollback + "Mover a…" (Commit 2)

- [x] 2.1 `frontend/src/entities/workspace/workspace.model.ts`: agregar `export interface TaskReorderPayload { task_id: string; sprint_id: string | null; ordered_task_ids: string[]; }`.
- [x] 2.2 `frontend/src/entities/workspace/workspace.service.ts`: agregar `reorderTasks(payload: TaskReorderPayload) { return this.http.post<TaskItemResponse>(\`${this.base}/tasks/reorder\`, payload); }` (mismo patrón que `updateTask`/`sprints`).
- [x] 2.3 `frontend/src/widgets/project-workspace/project-workspace.component.ts`: importar `DragDropModule` y envolver las secciones (cabeceras + Backlog de 30) en un `cdkDropListGroup`; cada sección declara `cdkDropList [id]="sectionId(sprint)"` (reutiliza `sectionId`/`'backlog'` de 30), `[cdkDropListData]="tasksBySprint().get(sprint.id) ?? []"` (o `backlogTasks()`), `[cdkDropListEnterPredicate]="canDropInto(sectionId(sprint) | 'backlog')"`.
- [x] 2.4 Tarjetas: agregar `cdkDrag [cdkDragData]="task"` **en un wrapper nuevo alrededor de `taskCardTpl`, NO dentro de `taskCardTpl` mismo** (desviación documentada — ver Reconciliación #3 abajo); agregar `*cdkDragPlaceholder` (fila punteada visible durante el arrastre, spec "Zona de drop visible").
- [x] 2.5 Reglas de destino (D2/spec `frontend-backlog-dnd`): agregar `draggingFrom = signal<string | null>(null)`; `(cdkDragStarted)="draggingFrom.set(sectionId(origen))"`, `(cdkDragEnded)="draggingFrom.set(null)"`; `canDropInto(targetId: string): (drag) => boolean` implementa: backlog↔sprint (`draft`|`active`) permitido en ambas direcciones; sprint↔sprint solo si origen y destino son ambos `draft`; los `closed` no se renderizan (30) por lo que nunca son origen/destino. `isValidTarget(id)` deriva las clases (resaltado válido / atenuado-`pointer-events-none` inválido) durante `draggingFrom()`.
- [x] 2.6 `(cdkDropListDropped)="onTaskDropped($event, sectionId(destino))"`: `const snapshot = this.allTasks()`; aplica `transferArrayItem`/`moveItemInArray` sobre las listas derivadas y `this.allTasks.update(...)` fijando el nuevo `sprint_id` y `order` (índice) de los ítems del contenedor destino (optimista); construye `ordered_task_ids` desde el orden final del contenedor y llama `this.workspace.reorderTasks({ task_id, sprint_id, ordered_task_ids }).subscribe({ error: () => { this.allTasks.set(snapshot); this.dragDropError.set(this.i18n.translate('workspace.errors.taskReorder')); this.loadTasks(); } })` (espeja `onKanbanItemMoved`, línea 1264; usa el banner `role="alert"` existente en vez de un "toast" — ver Reconciliación #3).
- [x] 2.7 Menú "Mover a…" **en un `ng-template #moveMenuTpl` separado, proyectado junto a `taskCardTpl` (no dentro de él)** — mismo motivo de aislamiento que 2.4: botón/dropdown (`aria-haspopup="menu"`, `role="menu"`) que lista los destinos válidos de esa tarjeta según `canDropInto`; al elegir uno, invoca `reorderTasks` con `ordered_task_ids = destino + [task.id]` (anexa al final) y aplica el mismo patrón optimista/rollback de 2.6.
- [x] 2.8 `frontend/src/assets/i18n/es-CO.json`: bajo `workspace.backlog` (existente de 30) agregar en tuteo formal: `moveTo: "Mover a…"`, `moveToBacklog: "Backlog"`, `dropInvalid: "Este destino no admite esta tarjeta."`, `moveToAria: "Abre el menú Mover a… para {{ title }}"` (aria-label del botón, no prevista explícitamente en el documento pero necesaria para accesibilidad), `errors.taskReorder: "No se pudo mover la tarjeta. Verifica tu conexión e intenta de nuevo."`.
- [x] 2.9 Build verde: `cd frontend && npm run build` (warning de presupuesto de bundle, 416 bytes sobre 1 MB — no bloqueante, `maximumError` es 2 MB). `npm run lint` también verde.

### Reconciliación #3 (aplicada durante Fase 2, hallazgo de implementación)

`taskCardTpl` NO es exclusivo de la vista Backlog: `sol-kanban-board`
(`@solercia/ui`) también lo proyecta como `[cardTemplate]` dentro de
`sol-kanban-card`, cuyo HOST ya aplica `CdkDrag` vía `hostDirectives`
(verificado leyendo `node_modules/@solercia/ui/fesm2022/solercia-ui.mjs`).
Agregar `cdkDrag`/el menú "Mover a…" DIRECTO en `taskCardTpl` anidaría un
`cdkDrag` dentro de otro `cdkDrag` cuando el tablero kanban renderiza esa
MISMA plantilla — riesgo real de regresión sobre el drag & drop del tablero
que ya funciona (fuera de alcance de este cambio, boundary explícito
"Fuera de alcance: DnD del board kanban"). Implementación real: un `<div
cdkDrag>` nuevo envuelve cada `*ngTemplateOutlet="taskCardTpl"` SOLO en la
vista Backlog (30), y el menú "Mover a…" vive en un `ng-template
#moveMenuTpl` separado proyectado junto a él — `taskCardTpl` queda
byte-idéntico a como lo dejó el cambio 30. Efecto funcional idéntico al
pedido por design.md D2/D5; cambia solo DÓNDE vive el marcado.

Adicionalmente, `backlogTasks()`/`tasksBySprint()` (30) no ordenaban por
`task.order` — solo preservaban el orden de `allTasks()` tal como llega del
backend. Sin un `.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))` en ambos
computed, la actualización optimista (D4) mutaba el campo `order` de cada
tarea pero la tarjeta NO se movía visualmente hasta el siguiente
`loadTasks()` — se agregó ese sort (no state en tasks.md/design.md, detalle
de implementación necesario para cumplir el requisito "reubicar la tarjeta
de inmediato").

Por último, no existe ningún componente/servicio de "toast" en este
repositorio ni en `@solercia/ui` (verificado por búsqueda antes de
implementar). El "toast de error en español" del requisito se implementó
reutilizando el patrón YA establecido en este mismo archivo (`tasksError`,
`modalError`, etc.): un signal (`dragDropError`) + un banner `role="alert"`
en la pestaña Backlog — mismo comportamiento funcional (mensaje de error
visible en español), sin introducir un componente nuevo fuera de alcance.

Commit 2: `feat(project-workspace): agrega arrastrar y soltar entre backlog y sprints`

## Fase 3 — Suite completa + no regresión (Commit 3 condicional)

- [ ] 3.1 Suite completa del backend sin regresión: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 3.2 Build de frontend verde (repetir tras cualquier ajuste de Fase 2): `cd frontend && npm run build`
- [ ] 3.3 Commit final (solo si 3.1 generó correcciones no cubiertas por los commits 1-2; caso contrario no aporta commit nuevo).
- [ ] 3.4 Merge local a `preview` (single-pr, sin PR encadenado).

Commit 3 (solo si 3.3 generó cambios): `fix(tasks): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Guard `closed` en `PATCH /tasks/{id}` (draft/active aceptados, closed 422, permisos, aislamiento) · 1.1,1.2,1.3,1.4
- Reordenamiento transaccional `POST /tasks/reorder` (reindexa hermanos, closed 422, aislamiento, permisos, 1 transacción sin spam de historial) · 1.5,1.6,1.7,1.8,1.9,1.10,1.11,1.12,1.13
- Arrastre entre secciones con CDK sobre ids estables de 30 · 2.3,2.4
- Reglas de destino en la UI (backlog↔draft/active; sprint↔sprint solo draft; nunca closed) · 2.5
- Zona de drop visible (resaltar válidos, atenuar inválidos) · 2.4,2.5
- Actualización optimista con rollback + toast en español · 2.6
- Alternativa de teclado "Mover a…" · 2.7
- No regresión del modal existente (mismo endpoint, guard aplica igual) · 1.4 (PATCH sigue siendo su ruta de persistencia)
- Textos es-CO formal tuteo · 2.8
- Suite en verde (backend + build frontend) · 1.14,3.1,3.2

## Risks

- **Conflicto spec/design sobre el alcance del guard `closed`** (ver Reconciliación #2): esta fase resuelve implementando el guard en `update_task` además de `reorder_tasks`, en línea con el spec ya aprobado; se recomienda que `design.md` D3 se actualice para reflejarlo y evitar que una futura relectura del diseño revierta el guard del PATCH.
- **Sin test runner de frontend** (mismo hallazgo que 30): `frontend/package.json` solo define `build`/`lint`/`watch`; Fase 2 se verifica solo con `npm run build`, sin cobertura automatizada de `canDropInto`/rollback — validar manualmente contra los escenarios de `specs/frontend-backlog-dnd/spec.md` antes de mergear.
- **`ordered_task_ids` confía en el orden recibido del cliente**: el repositorio valida tenant (`organization_id`+`project_id`) pero no re-verifica que cada id pertenezca YA al contenedor destino antes del drop; un payload manual con ids ajenos al destino reindexaría igual (mismo nivel de confianza que el `PATCH` existente hoy — endurecimiento server-side queda fuera de alcance, igual que en la propuesta).
- **Estimación cercana o por encima del presupuesto de revisión** (~550–650 líneas, `High`): concentrado en los tests backend (TDD estricto de 8 escenarios) y la plantilla CDK del frontend; aceptado como `size:exception` por instrucción explícita de este documento.
