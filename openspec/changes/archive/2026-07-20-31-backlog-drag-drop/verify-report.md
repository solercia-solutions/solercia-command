```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:e97000836df7d1b0a505640c454dc1ac495a09f4
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 20/20
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:80151bf0a05f30933dc2970c8abf814a24491c32e1f59843f9d61c5394d8edf7
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:b99e8aa89532d64fab0b95dd7a69d92d9844b38603c8f4ebb389935fce04bcc7
```

## Verification Report

**Change**: 31-backlog-drag-drop
**Branch**: `feat/backlog-drag-drop` (HEAD `e970008`)
**Version**: N/A
**Mode**: Strict TDD (backend) + Standard (frontend, no test runner — proyecto-wide, ver WARNING)

## Dictamen: commit de dependencia fuera de alcance

El primer commit de la rama, `5e98b18` (`chore(deps): migra @solercia/ui del
tarball vendido al paquete de npm 0.3.1`), no aparece en `tasks.md` ni en
`design.md`. Cambia `frontend/package.json`
(`"@solercia/ui": "file:./vendor/solercia-ui-0.3.0.tgz"` → `"^0.3.1"`) y
`frontend/src/shared/ui/index.ts` (export nombrado de `SolDrawerComponent`
para resolver una colisión con el drawer publicado).

### (a)/(b) — ¿Era necesario para que compile el cambio 31?

**Experimento real ejecutado** (árbol restaurado al terminar, verificado con
`git status` limpio):

1. `git checkout 5e98b18~1 -- frontend/package.json frontend/package-lock.json frontend/src/shared/ui/index.ts`
   (vuelve al tarball `0.3.0` y al `export *` original, sin el export
   nombrado).
2. `source ~/.nvm/nvm.sh && nvm use 22.22.3 && cd frontend && npm ci` →
   **éxito**, `added 955 packages, and audited 956 packages in 11s`, sin
   errores de resolución.
3. `npm run build` → **éxito**, `Application bundle generation complete.
   [6.822 seconds]`, cero errores TypeScript/Angular, mismos chunks lazy que
   con la dependencia migrada.
4. Árbol restaurado: `git checkout HEAD -- frontend/package.json
   frontend/package-lock.json frontend/src/shared/ui/index.ts`; `git status`
   confirma limpio; se reinstaló con `npm ci` sobre el `package.json` real
   (`^0.3.1`) para dejar `node_modules` consistente con lo commiteado antes
   de correr el build de verificación estándar (más abajo).

**Veredicto (b)**: el build **pasa limpio con el tarball vendido**, sin
tocar nada de `index.ts`. La migración a npm **NO era necesaria** para que
el cambio 31 compile — change 31 no usa `sol-rich-editor` ni selects dentro
de modales/drawers (los dos arreglos que motivan la migración según el
mensaje del commit); es una migración de infraestructura de dependencias
completamente independiente del alcance de "arrastrar historias entre
backlog y sprints".

**Hallazgo — WARNING (alcance)**: `5e98b18` debió ser su propio cambio/PR
(`chore(deps): ...`), revisado y mergeado independientemente del cambio 31.
Al viajar dentro de la misma rama/PR, infla el diff revisable con un cambio
de dependencia + un workaround de colisión de nombres que no tiene relación
funcional con el drag & drop. Recomendación: extraerlo a un cambio SDD
propio (o al menos a un commit/PR separado) en la próxima oportunidad.

### (c) — ¿Es correcto el workaround de `SolDrawerComponent`?

`grep` sobre `frontend/src` confirma que **todo** uso real de
`<sol-drawer>`/`SolDrawerComponent` en la aplicación importa el componente
desde `@shared/ui` (nunca directo desde `@solercia/ui`):

- `src/pages/projects/projects.component.ts` (`<sol-drawer [open] [title]
  size="md" (closed)>`)
- `src/pages/connections/connections.component.ts` (dos usos)
- `src/widgets/project-workspace/project-workspace.component.ts`
  (`<sol-drawer [open] [title] size="lg" [blur]="drawerBlur()" (closed)>`)

El paquete publicado (`node_modules/@solercia/ui/fesm2022/solercia-ui.mjs`)
expone `SolDrawerComponent` con la API `open, title, side, size, variant,
closeable, closeOnBackdrop` — **sin** `blur`. El drawer local
(`src/shared/ui/drawer/drawer.component.ts`) sí expone `blur`.
`project-workspace.component.ts` liga `[blur]="drawerBlur()"`; el `ng
build` (AOT, con chequeo de tipos de plantillas) pasó **limpio** con ese
binding — si el export nombrado no ganara sobre el `export *` y la vista
resolviera el drawer publicado, el compilador AOT habría fallado con
"blur is not a known property of sol-drawer". Esto prueba en tiempo de
compilación, no solo por lectura de código, que el export nombrado
resuelve correctamente al drawer LOCAL en las tres vistas reales.

**Veredicto (c)**: el workaround es **correcto**. Ninguna vista quedó
usando el drawer publicado por accidente; las tres resuelven el drawer
local (API `blur`/`closeOnBackdrop` local, comportamiento sin cambios). El
comentario inline en `index.ts` documenta la razón con precisión.

---

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 27 |
| Tasks complete | 26 |
| Tasks incomplete | 1 (3.4 — merge local a `preview`, diferido al orquestador por instrucción explícita de la invocación de apply; no bloquea verify) |

### Build & Tests Execution

**Backend suite completa** (Prioridad "verificaciones estándar" #1):
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
1345 passed, 1 warning in 373.86s (0:06:13)
```
✅ **1345/1345 passed, 0 failed** — corrida completa e independiente ejecutada por esta verificación (no reutiliza el número reportado por apply sin comprobarlo). Coincide exactamente con lo reportado en `apply-progress` (1337 baseline + 8 tests nuevos de este cambio). El único warning es `SAWarning` preexistente de `alembic/env.py` (ciclos de FK entre `dependencies`/`organizations`/`users`), sin relación con este cambio.

**Suite dirigida** (guard + reorder + no regresión CRUD):
```text
pytest -q backend/tests/test_task_sprint_closed_guard.py backend/tests/test_task_reorder.py backend/tests/test_tasks_crud.py
14 passed in 7.16s
```

**Frontend build** (dependencias reales, `^0.3.1`, tras reinstalar tras el experimento del dictamen):
```text
cd frontend && npm run build
Application bundle generation complete. [6.679 seconds]
▲ [WARNING] bundle initial exceeded maximum budget. Budget 1.00 MB was not met by 416 bytes with a total of 1.00 MB.
Exit code: 0
```
✅ Build verde (mismo warning de presupuesto no bloqueante ya reportado por apply, `maximumError` es 2 MB).

**Frontend lint**:
```text
npm run lint
ESLint: No issues found
Exit code: 0
```

**Backend lint/type-check en archivos cambiados**:
```text
.venv/bin/ruff check app/modules/tasks/ tests/test_task_reorder.py tests/test_task_sprint_closed_guard.py
All checks passed!

.venv/bin/mypy app/modules/tasks/service.py app/modules/tasks/repository.py app/modules/tasks/router.py app/modules/tasks/schemas.py
Success: no issues found in 4 source files
```

**Coverage**: no hay herramienta de cobertura configurada (`pytest.ini`/`pyproject.toml` sin `pytest-cov`; `frontend/package.json` sin `test`) → ➖ No disponible (hallazgo preexistente de todo el repo, no introducido por este cambio).

### Spec Compliance Matrix — `tasks` (backend)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Guard de integridad al asignar `sprint_id` en PATCH | Mover a sprint `draft` se acepta | `test_task_sprint_closed_guard.py::test_patch_task_accepts_draft_and_active_target_sprint` | ✅ COMPLIANT |
| Guard de integridad al asignar `sprint_id` en PATCH | Mover a sprint `active` se acepta | `test_task_sprint_closed_guard.py::test_patch_task_accepts_draft_and_active_target_sprint` | ✅ COMPLIANT |
| Guard de integridad al asignar `sprint_id` en PATCH | Mover hacia `closed` se rechaza (422 `sprint_closed`) | `test_task_sprint_closed_guard.py::test_patch_task_rejects_closed_target_sprint_422` | ✅ COMPLIANT |
| Guard de integridad al asignar `sprint_id` en PATCH | Permisos existentes sin cambio | `test_task_sprint_closed_guard.py::test_patch_task_sprint_guard_respects_permissions_and_org_isolation` | ✅ COMPLIANT |
| Guard de integridad al asignar `sprint_id` en PATCH | Aislamiento de organización se mantiene (spec corregida a 422 `invalid_sprint`, ver Prioridad 2) | `test_task_sprint_closed_guard.py::test_patch_task_sprint_guard_respects_permissions_and_org_isolation` | ✅ COMPLIANT |
| Reordenamiento transaccional `POST /tasks/reorder` | Mover a posición arbitraria reindexa hermanos | `test_task_reorder.py::test_reorder_moves_task_and_reindexes_destination_container` | ✅ COMPLIANT |
| Reordenamiento transaccional `POST /tasks/reorder` | Mover hacia `closed` se rechaza (422 `sprint_closed`) | `test_task_reorder.py::test_reorder_rejects_closed_target_sprint_422` | ✅ COMPLIANT |
| Reordenamiento transaccional `POST /tasks/reorder` | Tarea de otra organización se rechaza (404) | `test_task_reorder.py::test_reorder_rejects_task_from_other_organization_404` | ✅ COMPLIANT |
| Reordenamiento transaccional `POST /tasks/reorder` | Permisos existentes sin cambio | `test_task_reorder.py::test_reorder_respects_existing_permissions` | ✅ COMPLIANT |

**Compliance summary (backend)**: 9/9 escenarios COMPLIANT con test que pasa en runtime.

### Spec Compliance Matrix — `frontend-backlog-dnd`
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Arrastre entre secciones con CDK | Arrastrar una tarjeta entre secciones conectadas | (sin runner FE — lectura de fuente: `cdkDropList`/`cdkDrag` sobre `sectionId()`, líneas 405-442, 529-563) | ⚠️ PARTIAL |
| Reglas de destino aplicadas en la UI | Backlog a sprint `active` permitido | (sin runner FE — `isValidSectionTransition`/`canDropInto`, líneas 2210-2237) | ⚠️ PARTIAL |
| Reglas de destino aplicadas en la UI | Sprint `active` a otro `active` bloqueado | (sin runner FE — misma función, rama `originStatus === 'draft' && targetStatus === 'draft'`) | ⚠️ PARTIAL |
| Reglas de destino aplicadas en la UI | Sprint `draft` a sprint `draft` permitido | (sin runner FE — misma función) | ⚠️ PARTIAL |
| Zona de drop visible durante el arrastre | Resalte de destinos válidos e inválidos | (sin runner FE — `isValidTarget` + bindings `ring-2`/`opacity-40`/`pointer-events-none`, líneas 411-414, 536-539) | ⚠️ PARTIAL |
| Actualización optimista con rollback | Persistencia exitosa | (sin runner FE — `persistReorder`, sin handler `next`: el estado optimista queda como final) | ⚠️ PARTIAL |
| Actualización optimista con rollback | Rollback ante error de servidor | (sin runner FE — `persistReorder` handler `error`: `allTasks.set(snapshot)` + banner `role="alert"` + `loadTasks()`, líneas 2323-2329) | ⚠️ PARTIAL |
| Alternativa de teclado — menú "Mover a…" | Mover una tarjeta por menú sin arrastre | (sin runner FE — `moveTaskTo`, líneas 2365-2381) | ⚠️ PARTIAL |
| Alternativa de teclado — menú "Mover a…" | El menú respeta las mismas reglas de destino | (sin runner FE — `moveTargetsFor` filtra con `isValidSectionTransition`, líneas 2347-2360) | ⚠️ PARTIAL |
| No regresión del modal "mover a sprint" existente | El modal sigue moviendo tareas a sprints abiertos | Backend: `test_patch_task_accepts_draft_and_active_target_sprint` prueba el contrato del mismo endpoint PATCH que consume el modal; sin test FE que ejercite el componente Angular del modal en sí | ⚠️ PARTIAL |
| Textos en español colombiano formal | Tuteo formal en el toast de error | (sin runner FE — `es-CO.json`: `"No se pudo mover la tarjeta. Verifica tu conexión e intenta de nuevo."`, tuteo correcto) | ⚠️ PARTIAL |

**Compliance summary (frontend)**: 0/11 escenarios COMPLIANT con test runtime propio del frontend; 11/11 PARTIAL — implementados correctamente según lectura de fuente + `ng build` (AOT, tipado de plantillas) + `eslint` en verde, pero sin runtime de comportamiento. Causa raíz: `frontend/package.json` no define ningún script `test` (constraint preexistente y de todo el repo, ya señalada y aceptada en los verify de los cambios 28, 29 y 30 — no es deuda nueva de 31; `tasks.md` de este cambio ya lo declara explícitamente como riesgo aceptado con `npm run build` como harness).

**Compliance summary (total)**: 9/20 escenarios COMPLIANT con test runtime, 11/20 PARTIAL (mismo patrón aceptado del repo).

### Correctness (Static + Runtime Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Guard `reject_closed` centralizado en `_verify_sprint` | ✅ Implemented + tested | `service.py:871-908`; activo en `update_task` (línea 441-444, Reconciliación #2) y en `reorder_tasks` (línea 583-585). |
| `POST /tasks/reorder` transaccional | ✅ Implemented + tested | `service.py:555-598`: `_require_task` → `_verify_sprint(reject_closed=True)` → `task.sprint_id = ...` → `reassign_order_for_container` (sin commit) → `_record_history_diff` → `repo.save(task)` (único `db.commit()`, `repository.py:207-212`). Probado en runtime por `test_reorder_is_single_transaction_and_order_not_history_tracked` con spy real sobre `TaskRepository.save` (`call_count == 1`), no una aserción tautológica. |
| `order` no genera `TaskHistory` | ✅ Implemented + tested | `order` fuera de `_HISTORY_TRACKED_FIELDS`; verificado consultando `TaskHistory` directamente tras el reorder (1 sola fila, campo `sprint_id`). |
| Aislamiento de tenant en `reassign_order_for_container` | ✅ Implemented | `repository.py:253-282`: `WHERE Task.id IN (...) AND Task.project_id == project_id AND Project.organization_id == organization_id AND Task.is_active`; ids ajenos al tenant se excluyen en silencio, no se reasignan. |
| `canDropInto`/`isValidSectionTransition` (reglas de destino) | ✅ Implemented | `project-workspace.component.ts:2202-2237`: `backlog`↔`draft`/`active` bidireccional; `sprint↔sprint` solo si ambos `draft`; `closed` falla cerrado (`?? 'closed'` en id desconocido). Coincide exactamente con `constraints` de `state.yaml`. |
| Optimista + rollback | ✅ Implemented | `applyOptimisticReorder`/`persistReorder` (líneas 2290-2330): snapshot inmutable antes del drop, `allTasks.set(snapshot)` + banner `role="alert"` + `loadTasks()` en error — espeja `onKanbanItemMoved` como pedía D4. |
| Menú "Mover a…" accesible | ✅ Implemented | `aria-haspopup="menu"`, `role="menu"`, `role="menuitem"`, `aria-expanded`, `aria-label` (líneas 926-960). |
| Aislamiento del `cdkDrag`/menú respecto al kanban (desviación #2/#3) | ✅ Correcto, verificado | `taskCardTpl` (línea 821) permanece sin `cdkDrag` ni menú embebidos — el wrapper `<div cdkDrag>` y `moveMenuTpl` viven SOLO en la pestaña Backlog (líneas 425-442, 548-563), fuera de `taskCardTpl`. `sol-kanban-board` (línea 222) sigue proyectando `taskCardTpl` puro vía `[cardTemplate]`; su `sol-kanban-card` aplica `CdkDrag` a su propio host (`hostDirectives`, confirmado leyendo `node_modules/@solercia/ui/fesm2022/solercia-ui.mjs`). El build AOT compiló sin conflictos de `cdkDrag` anidado, y la plantilla del tablero no cambió una sola línea — el drag & drop del kanban sigue intacto. |
| Textos es-CO tuteo formal | ✅ Implemented | `es-CO.json`: `"Mover a…"`, `"Backlog"`, `"Este destino no admite esta tarjeta."`, `"Abre el menú Mover a… para {{ title }}"`, `"No se pudo mover la tarjeta. Verifica tu conexión e intenta de nuevo."` — sin voseo, tildes correctas. |
| Review workload budget | ⚠️ Over budget, pre-aceptado | Diff real (excluye docs de `openspec/`): **973 insertions(+) / 14 deletions(-)** en 10 archivos (backend prod ~150, backend tests ~446, frontend prod ~391) — por encima del presupuesto de 400 líneas y de la propia previsión de `tasks.md` (~550-650). Ya resuelto en fase `tasks` con `size:exception` explícito y `Decision needed before apply: No`; no es un hallazgo nuevo. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| D1 — `POST /tasks/reorder`, reindexado por lotes, 1 transacción | ✅ Yes | Implementación idéntica a la especificada; probado por spy real. |
| D2 — Estructura CDK sobre los seams de 30 | ✅ Yes | `cdkDropListGroup`/`cdkDropList`/`cdkDrag`/`cdkDragPlaceholder`/`draggingFrom` tal como diseñado. |
| D3 — Guard server-side mínimo (destino `closed` → 422) | ⚠️ Desviación documentada (no rompe spec) | El texto de `design.md` dice que `update_task` conserva `reject_closed=False`; el código real lo activa también en `update_task` (Reconciliación #2, `tasks.md`). Esto es lo que exige el spec ADDED ya aprobado ("aplica a cualquier consumidor... o el modal existente"), así que el código está alineado con el spec, no con el texto de diseño ahora desactualizado. Ver SUGGESTION. |
| D4 — Optimista + rollback sobre `allTasks` | ✅ Yes | Coincide con `onKanbanItemMoved`; snapshot/rollback/`loadTasks` en error. |
| D5 — Menú "Mover a…" | ✅ Yes, reubicado por aislamiento (Reconciliación #3) | Efecto funcional idéntico al diseñado; vive en `ng-template #moveMenuTpl` separado en vez de "dentro de `taskCardTpl`" (texto literal de D5) por la razón de aislamiento del kanban ya verificada arriba — decisión correcta, documentada. |

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `tasks.md` etiqueta cada tarea backend `[RED]`/`[TEST]`/`[GREEN]` con comando `Verify:` explícito y el fallo que corrige (`200` en vez de `422`, `404` en vez de `200`) — funciona como tabla de evidencia TDD para este cambio (mismo patrón aceptado en el verify de 30). |
| All tasks have tests | ✅ | 9/9 tareas backend con test dedicado (1.1-1.9); tareas frontend (2.x/3.x) sin archivo de test dedicado, consistente con el gap de runner FE de todo el repo. |
| RED confirmed (tests exist) | ✅ | 8 funciones de test existen en `test_task_sprint_closed_guard.py`/`test_task_reorder.py`, confirmadas por lectura directa. |
| GREEN confirmed (tests pass) | ✅ | 14/14 (suite dirigida) y 1345/1345 (suite completa) en ejecución real e independiente de esta verificación. |
| Triangulation adequate | ✅ | `test_patch_task_accepts_draft_and_active_target_sprint` triangula `draft` vs `active` en una función; `test_patch_task_sprint_guard_respects_permissions_and_org_isolation` triangula mismo-org (200) vs cross-org (422); 5 funciones distintas para los 4 escenarios de `reorder` (una función adicional cubre la transaccionalidad). |
| Safety Net for modified files | ✅ | `test_tasks_crud.py` (preexistente) se corrió junto con los tests nuevos (14/14) y forma parte de la suite completa (1345/1345) — sin regresión en los archivos modificados (`service.py`, `repository.py`, `router.py`, `schemas.py`). |

**TDD Compliance**: 6/6 checks passed

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Integration (HTTP vía `AsyncClient` + Postgres real) | 8 nuevos | `test_task_sprint_closed_guard.py`, `test_task_reorder.py` | pytest + pytest-asyncio + httpx |
| Unit | 0 nuevos | — | — |
| E2E | 0 | — | no instalado |
| **Total backend** | **8** | **2** | |

Frontend: 0 tests automatizados de cualquier capa para este cambio (sin runner de test configurado en todo el repo — mismo hallazgo que 28/29/30).

---

### Changed File Coverage
Análisis de cobertura omitido — no hay herramienta de cobertura configurada ni en `backend/pyproject.toml` ni en `frontend/package.json`.

---

### Assertion Quality
Se leyeron completos `test_task_sprint_closed_guard.py` (175 líneas) y `test_task_reorder.py` (273 líneas). Se buscaron tautologías, checks de colección vacía sin caso no-vacío compañero, aserciones solo-de-tipo, ghost loops, smoke-tests, acoplamiento a detalles de implementación y proporción mocks/aserciones.

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real. Cada test llama al endpoint real vía `AsyncClient` contra Postgres de test real (sin mockear lógica de producción, salvo un spy intencional con `wraps=original_save` sobre `TaskRepository.save`, que ejecuta la implementación real, no la reemplaza). Las aserciones de `sprint_id is None`/`order == 0` siempre tienen un caso compañero no-vacío en la misma o una función hermana (`sprint_id == draft_sprint_id`, `order == 1/2/3`). Sin tautologías, sin ghost loops, sin acoplamiento a clases CSS ni conteos de mock.

---

### Quality Metrics
**Linter (backend, `ruff`)**: ✅ No errors — `All checks passed!` sobre `app/modules/tasks/` y los 2 archivos de test nuevos.
**Type Checker (backend, `mypy`)**: ✅ No errors — `Success: no issues found in 4 source files` sobre `service.py`/`repository.py`/`router.py`/`schemas.py`.
**Linter (frontend, `eslint`)**: ✅ No errors — `ESLint: No issues found`.
**Type Checker (frontend, `ng build` AOT)**: ✅ No errors — build verde con tipado de plantillas completo (probó además, por sí solo, la corrección del workaround de `SolDrawerComponent` del dictamen).

### Issues Found

**CRITICAL**: None

**WARNING**:
1. **Commit fuera de alcance `5e98b18`** (dependencia `@solercia/ui`): no necesario para que compile el cambio 31 (comprobado experimentalmente, ver "Dictamen" arriba); viaja en la misma rama sin estar en `tasks.md`/`design.md`. Recomendación: extraerlo a su propio cambio/PR `chore(deps)`.
2. **11/11 escenarios de `frontend-backlog-dnd` sin test runtime propio del frontend** — implementados correctamente según lectura de fuente + `ng build`/`eslint` en verde, pero sin cobertura de comportamiento automatizada (`canDropInto`, rollback, menú "Mover a…"). Causa raíz preexistente y de todo el repo (`frontend/package.json` no define `test`); ya aceptado en los verify de 28/29/30 y en el propio `tasks.md` de este cambio como riesgo conocido. No es deuda nueva introducida por 31, pero sigue siendo un hueco real de regresión para esta área concreta (drag & drop).
3. **Diff real por encima del presupuesto de revisión**: 973+/14- en código (excluye docs), sobre el presupuesto de 400 líneas y por encima incluso de la propia previsión de `tasks.md` (~550-650). Ya resuelto en fase `tasks` con `size:exception` explícito (`Decision needed before apply: No`) — no bloquea, pero amerita atención del revisor humano antes de mergear.

**SUGGESTION**:
1. `design.md` D3 quedó desactualizado: dice que `update_task`/`create_task` conservan `reject_closed=False`, pero el código (correctamente, siguiendo el spec ya aprobado) activa el guard también en `update_task`. Alinear el texto de D3 en la próxima revisión de diseño, tal como ya recomendaba `tasks.md`.
2. Ampliar `_verify_sprint` para diferenciar `404` (sprint inexistente) de `422 invalid_sprint` (sprint de otra organización) queda como mejora futura fuera de este alcance — el efecto protector actual ya es correcto (nunca se reasigna un sprint ajeno).
3. Dado el hallazgo #2 de WARNING, considerar invertir en un test runner de frontend (Karma/Jest/Vitest) antes del próximo cambio que toque estas mismas secciones — el propio `tasks.md` de 31 ya lo señalaba como riesgo heredado de 30.

### Verdict
**PASS WITH WARNINGS**

Backend (`tasks`): 9/9 escenarios COMPLIANT con test que pasa en runtime, suite completa 1345/1345 verde, `ruff`/`mypy` limpios, guard `closed` y `POST /tasks/reorder` transaccional correctamente implementados y probados (incluyendo la transaccionalidad real vía spy, no una aserción de conteo tautológica). Frontend (`frontend-backlog-dnd`): implementación correctamente verificada por lectura de fuente + build AOT + lint en verde, pero sin cobertura runtime propia — mismo patrón ya aceptado del repo (WARNING, no CRITICAL). El commit de dependencia fuera de alcance (`5e98b18`) se probó experimentalmente innecesario para compilar y su workaround de `SolDrawerComponent` se probó correcto — ambos quedan documentados como WARNING de alcance, no como bloqueo. La discrepancia spec/código del guard cross-org (404 vs 422) se corrigió en `specs/tasks/spec.md` durante esta verificación (reconciliación documental pura — comportamiento preexistente sin cambios en este alcance). Nada bloquea `sdd-archive`.

---

## Resolución (orquestador)

El commit `5e98b18` (`chore(deps): migra @solercia/ui del tarball vendido al paquete de npm 0.3.1`) fue extraído de la rama `feat/backlog-drag-drop` a una rama independiente `chore/solercia-ui-npm` para decisión separada, ya que el veredicto experimental concluyó que **NO era necesario** para que el cambio 31 compliara. La rama `feat/backlog-drag-drop` ahora contiene 4 commits con `package.json` revertido al tarball `file:./vendor/solercia-ui-0.3.0.tgz`, y el build se re-verificó verde en ese estado (sin cambios en el comportamiento funcional de este cambio). La rama queda lista para merge a `preview` con el alcance limitado únicamente a arrastre y reordenamiento de tareas.

