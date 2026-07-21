```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:39d4f747daab01146fad616c355453c12889786c-c4475d44d92d4e89c9c37d849eb19e9da3b582f0-51d622e1f09f8050ed3a3055183056cf1cd5d622
verdict: fail
blockers: 1
critical_findings: 1
requirements: 3/3
scenarios: 10/11
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:058e4cda98be6753d83901dec8c96a19c1a316dc3741bd8913a677555adb4c7c
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:74318d82a6f537d601d7ff306885daf21baa4658576e9a92b39c5715d65df6b8
```

## Verification Report

**Change**: 32-jerarquia-subtareas
**Rama**: `feat/jerarquia-subtareas`
**Versión**: N/A (delta MODIFIED sobre la capability `tasks`)
**Modo**: Strict TDD

### Completeness

| Métrica | Valor |
|---------|-------|
| Tareas totales (tasks.md) | 30 |
| Tareas completas | 30 |
| Tareas incompletas | 0 |
| Commits reportados y verificados en el árbol real | 3 (`39d4f74`, `c4475d4`, `51d622e`) |

`git show --stat` confirma los tres commits en `feat/jerarquia-subtareas` con los archivos y deltas de línea reportados por `apply-progress` (backend: 5 archivos, +400/-2; frontend: 4 archivos, +252/-51; docs: 2 archivos).

### Build & Tests Execution

**Build**: ✅ Passed
```text
$ cd frontend && npm run build
Application bundle generation complete. [6.365 seconds]
Output location: frontend/dist/frontend
```

**Tests**: ✅ 1352 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
$ cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
1352 passed, 1 warning in 382.46s (0:06:22)
```
(warning pre-existente de Alembic/SQLAlchemy sobre orden cíclico de FKs, ajeno a este cambio)

`backend/tests/test_task_hierarchy.py` ejecutado en aislamiento (7/7 verdes):
```text
tests/test_task_hierarchy.py::test_default_listing_stays_top_level_only_no_regression PASSED
tests/test_task_hierarchy.py::test_include_subtasks_true_returns_top_level_and_subtasks_flat PASSED
tests/test_task_hierarchy.py::test_assignee_filter_surfaces_subtask_of_foreign_parent_without_include_subtasks PASSED
tests/test_task_hierarchy.py::test_context_parent_not_duplicated_when_it_also_matches_assignee PASSED
tests/test_task_hierarchy.py::test_meta_total_excludes_context_parent PASSED
tests/test_task_hierarchy.py::test_is_context_defaults_false_without_assignee_filter PASSED
tests/test_task_hierarchy.py::test_hierarchy_and_context_respect_tenant_scoping_and_auth PASSED
7 passed in 4.48s
```

**Coverage**: ➖ No hay herramienta de cobertura configurada en el proyecto — no evaluado (no bloqueante).

---

### PRIORIDAD 1 — Regla innegociable (padre de contexto por `assignee_id`)

Verificada con dureza por lectura de código real (`backend/app/modules/tasks/service.py:67-156`, `repository.py:42-155`, `schemas.py:149-153`, `router.py:44-121`) y por los 7 tests nombrados de `test_task_hierarchy.py`, todos verdes:

| Regla de producto | Evidencia de código | Test que la prueba | Resultado |
|---|---|---|---|
| Subtarea asignada al usuario filtrado SIEMPRE aparece, aunque el padre sea de otro | `service.py:124-128` — `top_level_only` se apaga también cuando `assignee_id is not None` (misma 1ª pasada) | `test_assignee_filter_surfaces_subtask_of_foreign_parent_without_include_subtasks` | ✅ COMPLIANT |
| El padre acompaña con `is_context: true` | `service.py:132-155` — 2ª pasada `missing_parent_ids` → `repo.get_by_ids` → `_to_read(..., is_context=True)` | mismo test anterior (`ids_to_row[parent_of_b["id"]]["is_context"] is True`) | ✅ COMPLIANT |
| Si el padre TAMBIÉN matchea por sí mismo → `is_context: false`, sin duplicar | `service.py:134-140` — `missing_parent_ids` excluye por construcción todo `parent_task_id` ya presente en `matched_ids` (dedup automático, no hay lógica ad hoc de "borrar duplicado") | `test_context_parent_not_duplicated_when_it_also_matches_assignee` (`len(parent_rows) == 1`, `is_context is False`) | ✅ COMPLIANT |
| Padres de contexto NO cuentan en `meta.total` | `service.py:111-130` — `total` se captura del `repo.list_for_project` ANTES de anexar `context_parents`; nunca se recalcula tras la 2ª pasada | `test_meta_total_excludes_context_parent` (`meta.total == 3`, `len(data) == 4`) | ✅ COMPLIANT |
| Padres de contexto NO cuentan en los agregados por sprint del cambio 30 (`story_count`, `estimation_hours_sum`) | `backend/app/modules/sprints/repository.py:240-265` — `aggregate_tasks_by_sprint` es una query `GROUP BY sprint_id` totalmente independiente de `TaskService.list_tasks`; no filtra por `assignee_id`, no conoce `is_context` | Verificado ARQUITECTÓNICAMENTE (lectura de código, independencia de query confirmada); **NO existe un test runtime que combine explícitamente padre-de-contexto + agregado de sprint en el mismo caso** (`test_sprint_backlog_aggregates.py` no referencia `parent_task_id`/`is_context`) | ⚠️ PARTIAL — ver hallazgo WARNING-1 |
| La regla actúa siempre que `assignee_id` esté presente, sin requerir `include_subtasks` | `service.py:132-133` — el `if assignee_id is not None:` que dispara la 2ª pasada es independiente de `include_subtasks` | `test_assignee_filter_surfaces_subtask_of_foreign_parent_without_include_subtasks` (se llama SIN `include_subtasks`) | ✅ COMPLIANT |

**Veredicto Prioridad 1**: la regla innegociable está completa y correctamente implementada en el backend, con tests nombrados para cada punto salvo el cruce exacto "padre de contexto + agregado de sprint", que queda probado solo por independencia arquitectónica de la query (ver WARNING-1). No es CRITICAL: la query de agregados no toca en ningún punto `assignee_id`/`is_context`/`parent_task_id`, así que no hay mecanismo posible de fuga — pero al no tener test runtime dedicado, no cumple el listón estricto de "todo escenario de spec probado en runtime".

---

### PRIORIDAD 2 — Interacción con drag & drop del cambio 31 (CRÍTICO)

**Hallazgo CRITICAL-1 — Los padres de contexto siguen registrados como ítems arrastrables ante Angular CDK, aunque `cdkDragDisabled`, y desincronizan los índices de reordenamiento.**

`apply-progress` reporta que se añadió `topLevelOf()` aplicado a `[cdkDropListData]` (líneas 420, 563) y a `moveTaskTo()` (línea 2558-2561) para evitar que las subtareas desincronizaran los índices de CDK. Esa corrección es **correcta pero incompleta**: cubre el caso de las filas de subtarea (`subtaskRowTpl`, sin directiva `cdkDrag`), pero **no cubre el caso de las filas de padre-de-contexto**, que SÍ siguen llevando `cdkDrag` (solo con `[cdkDragDisabled]="row.isContext"`) dentro del mismo `cdkDropList` de la sección.

Evidencia verificada en el código real de Angular CDK instalado (`frontend/node_modules/@angular/cdk/fesm2022/drag-drop.mjs`, v22.0.5):

- `CdkDropList.addItem()` (línea 3050-3056) agrega CUALQUIER `CdkDrag` hijo a `this._unsortedItems`, sin filtrar por `disabled`.
- `CdkDropList.getSortedItems()` (línea 3067-3072) devuelve `Array.from(this._unsortedItems)` ordenado por posición en el DOM — de nuevo, sin excluir los deshabilitados.
- `DropListRef.withItems()`/`_activeDraggables` (línea 1568-1590) recibe exactamente ese array; `_cacheItemPositions()` (línea 1615-1627) mide la posición de TODOS los `_activeDraggables`.
- `DropListRef.getItemIndex()` (línea 1592-1594) — usado para computar `event.currentIndex`/`event.previousIndex` en cada `drop()` (línea 1964-1977) — busca la posición dentro de esa misma lista completa (deshabilitados incluidos).

Es decir: `cdkDragDisabled` solo impide que ESE ítem inicie su propio arrastre; NO lo excluye de la cuenta de posiciones que CDK usa para calcular `currentIndex`/`previousIndex` de los DEMÁS ítems que sí se arrastran a su alrededor.

En `project-workspace.component.ts`, tanto la sección Backlog (líneas 441-475) como cada sección de sprint (líneas 581-615) renderizan **todas** las filas de `sectionRows(...)` — incluidas las de padre-de-contexto — con:

```html
@if (row.parent; as parent) {
  <div cdkDrag [cdkDragData]="parent" [cdkDragDisabled]="row.isContext" ...>
    ...
  </div>
}
```

mientras que `[cdkDropListData]="topLevelOf(...)"` (líneas 420, 563) excluye esos mismos padres-de-contexto del array de datos (correctamente, porque `topLevelOf` filtra por `parent_task_id == null` sobre la lista de la SECCIÓN, y el padre de contexto no pertenece a esa sección). El resultado: el DOM de la sección tiene **más** elementos `cdkDrag` registrados que elementos en el array `[cdkDropListData]`, cada vez que esa sección contiene al menos una subtarea cuyo padre real vive en otra sección o sprint (`sectionRows()`, segundo bucle, líneas 1632-1642) — exactamente el escenario que `design.md` D4 documenta como INTENCIONAL ("Subtarea con padre en OTRA sección").

**Alcance real, no un caso de borde teórico**: este cruce de secciones no depende del filtro `assignee_id` del backend (que hoy ni siquiera se envía desde `loadTasks()` — confirmado, `workspace.tasks(this.projectId(), { include_subtasks: true })`, sin `assignee_id`). Basta con que una subtarea tenga un `sprint_id` distinto al de su padre — y no existe ninguna regla, en backend (`TaskService.create_task`, `service.py:255-330`) ni en frontend, que ate el `sprint_id` de una subtarea al de su padre. Es decir, el escenario está disponible con datos de uso normal, no solo con la futura fila de avatares (33).

**Consecuencia**: cuando el usuario arrastra una tarjeta real hasta el final de una sección que contiene al menos un padre-de-contexto (algo tan común como "mover la última tarjeta al fondo de la lista"), o arrastra entre dos secciones donde la de destino tiene padres-de-contexto, `event.currentIndex`/`event.previousIndex` reportados por CDK cuentan también esas filas deshabilitadas. `onTaskDropped` (línea 2443-2468) y `moveTaskTo` (línea 2549-2569) aplican esos índices directamente sobre `[...event.container.data]` (el array `topLevelOf`, más pequeño), vía `moveItemInArray`/`transferArrayItem`, y el resultado se persiste con `POST /tasks/reorder` (`ordered_task_ids`, línea 2501-2506) sin ninguna corrección posterior. El desalineamiento puede escribir un `order`/`sprint_id` que no corresponde a la posición visual que el usuario indicó — el mismo riesgo de "corromper el orden de las tareas en la base" que se pidió evaluar.

**No hay ningún test que lo hubiera detectado**: `tasks.md` documenta explícitamente "Sin test runner de frontend" — la Fase 2 se verificó solo con `npm run build`, que no ejecuta ninguna interacción de arrastre real ni puede detectar un desalineamiento de índices en tiempo de ejecución.

**Fix recomendado** (no aplicado — reportar, no corregir): excluir estructuralmente la directiva `cdkDrag` de las filas de contexto, en vez de solo deshabilitarla — mismo patrón ya usado correctamente para `subtaskRowTpl`:

```html
@if (row.parent; as parent) {
  @if (!row.isContext) {
    <div cdkDrag [cdkDragData]="parent" ...> ...taskCardTpl... ...moveMenuTpl... </div>
  } @else {
    <ng-container *ngTemplateOutlet="taskCardTpl; context: { $implicit: parent, isContext: true }" />
  }
}
```

Esto elimina por completo el registro del padre-de-contexto ante `CdkDropList`, en vez de confiar en `[cdkDragDisabled]`, que no ofrece esa garantía.

**Verificación del resto de puntos que sí pasan índices o listas a CDK** (los otros 3 pedidos explícitamente):

| Punto | Usa `topLevelOf()`/excluye subtareas correctamente | Nota |
|---|---|---|
| `[cdkDropListData]` (drop handler) | ✅ Sí, líneas 420, 563 | Correcto para subtareas; NO corrige el caso de padre-de-contexto (ver CRITICAL-1) |
| `cdkDropListEnterPredicate`/`canDropInto` | ➖ N/A — opera a nivel de SECCIÓN completa (`isValidSectionTransition`, líneas 2394-2421), no de fila individual; no participa en el cálculo de índices | Sin hallazgos |
| Menú "Mover a…" | ✅ Sí — `moveTaskTo()` usa `topLevelOf(...)` en ambos destinos (línea 2558-2561); el menú mismo está excluido de las filas de contexto (`@if (!row.isContext) { moveMenuTpl }`, líneas 458-462, 598-602) | Correcto y consistente con el guard de no-arrastrable |
| `POST /tasks/reorder` (`ordered_task_ids`) | ⚠️ Recibe el array ya potencialmente corrupto desde `onTaskDropped`/`persistReorder` (línea 2495-2514) — el problema nace ANTES, en el cálculo de índices de CDK, no en esta llamada | Ver CRITICAL-1 |

---

### Spec Compliance Matrix

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Filtros combinables | Combinación simultánea de filtros | `test_task_filters.py::test_combined_filters_match_all_criteria_simultaneously` | ✅ COMPLIANT |
| Filtros combinables | `label_id` acepta múltiples valores | `test_task_filters.py::test_label_id_multiple_values_uses_or_semantics_without_duplicates` | ✅ COMPLIANT |
| Filtros combinables | Filtro de texto sobre título/descripción | `test_task_filters.py::test_q_filter_matches_title_or_description` | ✅ COMPLIANT |
| Filtros combinables | Filtro de rango de fechas | `test_task_filters.py::test_due_date_range_filters_tasks_within_bounds` | ✅ COMPLIANT |
| Filtros combinables | Listado por defecto sigue plano (no regresión board/Gantt) | `test_task_hierarchy.py::test_default_listing_stays_top_level_only_no_regression` | ✅ COMPLIANT |
| Filtros combinables | `include_subtasks` incluye subtareas planas | `test_task_hierarchy.py::test_include_subtasks_true_returns_top_level_and_subtasks_flat` | ✅ COMPLIANT |
| Filtros combinables | Subtarea de padre ajeno visible al filtrar por asignado | `test_task_hierarchy.py::test_assignee_filter_surfaces_subtask_of_foreign_parent_without_include_subtasks` | ✅ COMPLIANT |
| Filtros combinables | Padre que también matchea no se duplica | `test_task_hierarchy.py::test_context_parent_not_duplicated_when_it_also_matches_assignee` | ✅ COMPLIANT |
| Campo aditivo `is_context` | `is_context=false` fuera de contexto | `test_task_hierarchy.py::test_is_context_defaults_false_without_assignee_filter` | ✅ COMPLIANT |
| Campo aditivo `is_context` | Total y agregados no se inflan por contexto | `test_task_hierarchy.py::test_meta_total_excludes_context_parent` (solo la mitad de `meta.total`; `story_count` sin test dedicado) | ⚠️ PARTIAL |
| Permisos y aislamiento | Aislamiento de tenant con `include_subtasks`+`assignee_id` | `test_task_hierarchy.py::test_hierarchy_and_context_respect_tenant_scoping_and_auth` | ✅ COMPLIANT |

**Compliance summary**: 10/11 escenarios COMPLIANT, 1/11 PARTIAL. 3/3 requirements con cobertura de al menos un escenario compliant.

### Assertion Quality

Revisado `backend/tests/test_task_hierarchy.py` completo (7 tests): sin tautologías, sin loops fantasma sobre colecciones potencialmente vacías, sin asserts que no ejerciten código de producción real. Cada test hace al menos una llamada HTTP real (`client.get`/`client.post`) y asserta sobre valores concretos (ids, booleanos `is_context`, `meta.total`, status codes) — no solo `toBeDefined`/tipo.

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| `include_subtasks` levanta `top_level_only`, listado plano, orden `order asc, created_at asc` | ✅ Implementado | `service.py:124-128`; sin campo `subtasks` anidado, verificado por test |
| Regla innegociable server-side (padre de contexto) | ✅ Implementado | Ver tabla Prioridad 1 |
| Campo aditivo `is_context` default `false`, `TaskRead` intacto | ✅ Implementado | `schemas.py:149-153`, aditivo, no rompe consumidores previos |
| Aislamiento multi-tenant sin cambio | ✅ Implementado | `repository.get_by_ids` siempre hace `join(Project).where(organization_id=...)`, nunca cruza tenant |
| Kanban y Gantt siguen usando solo tareas raíz | ✅ Implementado | `topLevelTasks()` (línea 1568-1570) usado por `kanbanColumns()` (línea 1699-1708) y `ganttTasks()` (línea 1381-1386); `allTasks()` directo eliminado de ambos |
| Padre de contexto atenuado, clicable solo a detalle, no editable desde la fila | ✅ Implementado | `taskCardTpl` línea 869-877: `(click)="isContext ? openTaskDrawer(task) : openEdit(task)"`, `[class.opacity-60]` |
| Padre de contexto no arrastrable | ⚠️ Parcial | `[cdkDragDisabled]` impide que ÉL se arrastre, pero no lo excluye del cálculo de índices de sus vecinos — ver CRITICAL-1 |
| Padre de contexto excluido del menú "Mover a…" | ✅ Implementado | `@if (!row.isContext) { moveMenuTpl }` en ambas secciones |
| Retrocompatibilidad sin `include_subtasks` ni `assignee_id` | ✅ Implementado | `test_default_listing_stays_top_level_only_no_regression` verde; misma condición `top_level_only` que hoy cuando ambos parámetros están ausentes |
| `frontend/package.json` sigue con `file:./vendor/solercia-ui-0.3.0.tgz` | ✅ Confirmado | Sin migración de dependencia colada en la rama |
| `tasks.md` 30/30, `state.yaml` apply: done | ✅ Confirmado | Verificado por lectura directa de ambos archivos |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — listado plano con `include_subtasks`, jerarquía compuesta en cliente | ✅ Sí | Sin árbol anidado en la respuesta; agrupación por `parent_task_id` en `sectionRows()` |
| D2 — padres de contexto resueltos SOLO en backend | ✅ Sí | 2ª pasada server-side, única fuente de verdad |
| D3 — agregados del 30 invariantes bajo filtro | ✅ Sí (arquitectónicamente) | Query independiente confirmada; falta test runtime dedicado (WARNING-1) |
| D4 — render de sección, padre de contexto atenuado, doble render intencional | ⚠️ Parcial | El render y el comentario "doble render intencional" están correctos (línea 1594-1599); pero D4 asume implícitamente que el doble render es inocuo para CDK, lo cual esta verificación refuta (CRITICAL-1) |
| D5 — orden por `Task.order` entre hermanos | ✅ Sí | Backend ordena `order asc, created_at asc`; sin cambios de ese contrato |

### Issues Found

**CRITICAL**:
1. **CRITICAL-1 — Los padres de contexto siguen registrados ante `CdkDropList` pese a `cdkDragDisabled`, desincronizando los índices de arrastre/reordenamiento en secciones con subtareas cruzadas.** Ver análisis completo en "PRIORIDAD 2" arriba. Reachable con datos de uso normal (subtarea con `sprint_id` distinto al del padre), sin necesitar el filtro `assignee_id`. Sin ningún test que lo detecte (no hay runner de frontend). Riesgo: corrupción silenciosa de `order`/`sprint_id` en `POST /tasks/reorder`. Archivos: `frontend/src/widgets/project-workspace/project-workspace.component.ts` líneas 441-475, 581-615 (render), 1581-1583 (`topLevelOf`), 2443-2514 (`onTaskDropped`/`persistReorder`).

**WARNING**:
1. **WARNING-1** — El escenario de spec "Total y agregados no se inflan por contexto" (mitad `story_count`/`estimation_hours_sum`) no tiene un test runtime dedicado que combine explícitamente padre-de-contexto + agregado de sprint; solo está probado por independencia arquitectónica de la query (`aggregate_tasks_by_sprint`, `sprints/repository.py:240-265`, que nunca toca `assignee_id`/`is_context`/`parent_task_id`). Bajo riesgo real (la independencia de la query es sólida y verificada), pero no cumple el listón estricto de "todo escenario probado en runtime". Recomendado: agregar un caso a `test_sprint_backlog_aggregates.py` o `test_task_hierarchy.py` que cree un padre-de-contexto dentro de un sprint y verifique `story_count` sin inflar.
2. **WARNING-2** — Ausencia total de test runner de frontend (ya documentada como riesgo aceptado en `tasks.md`, no es un hallazgo nuevo de esta verificación, pero es la razón directa por la que CRITICAL-1 llegó hasta `apply` sin detectarse). Recomendado priorizar para 33 o un cambio de tooling dedicado.

**SUGGESTION**:
1. Considerar, junto con el fix de CRITICAL-1, agregar una prueba de humo manual o Cypress/Playwright mínima que arrastre una tarjeta en una sección con padre-de-contexto y confirme que `ordered_task_ids` enviado al backend coincide con el orden visual — cerraría tanto CRITICAL-1 como WARNING-2 para este flujo específico.

### Verdict

**FAIL**

Backend (Prioridad 1, la regla innegociable) está completo, correcto y probado con dureza — 1352/1352 tests verdes, incluidos los 7 nuevos de `test_task_hierarchy.py`, cada uno nombrado exactamente para un punto de la regla de negocio. Sin embargo, la corrección de Prioridad 2 reportada por `apply` (`topLevelOf()`) es **incompleta**: no cubre el caso de padres de contexto que quedan registrados como ítems de arrastre deshabilitados dentro de `CdkDropList`, lo que puede desincronizar los índices de reordenamiento y corromper el orden persistido de tareas — confirmado por lectura del código fuente real de Angular CDK instalado, no por especulación. Este hallazgo bloquea el archivo del cambio hasta que se corrija (excluir estructuralmente `cdkDrag` de las filas de contexto, no solo deshabilitarlo) y se re-verifique.
