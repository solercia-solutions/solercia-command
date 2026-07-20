# Tasks: 34 · Estimación normalizada (w/d/h → horas con calendario laboral)

## Reconciliación aplicada (orquestador)

1. **Nombres de las funciones puras** — `design.md` §Interfaces/Contracts fija
   `parse_estimation(text, calendar) -> Decimal` y
   `format_estimation(hours, calendar) -> str` (más `seconds_to_hours`,
   `InvalidEstimationError`); `specs/estimation/spec.md` usa `estimate_to_hours`/
   `format_hours` en su prosa. Este `tasks.md` usa los nombres de `design.md`
   (instrucción explícita del orquestador); la nomenclatura de la spec queda
   superada por el contrato de `design.md`, sin reabrirse en `apply`.
2. **Precondición dura**: `app/modules/work_calendar/` (resolver + schemas) NO
   existe todavía en disco (`state.yaml` de 28: `apply: pending`). La Fase 0 de
   este documento verifica su existencia ANTES de tocar cualquier archivo de
   este cambio; si falta, `apply` de 34 se detiene y corre primero
   `28-calendario-laboral`.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~580–750 (producción ~220–290: `work_calendar/estimation.py` ~90-110, `tasks/{schemas,service}.py` ~95-135, frontend `workspace.model.ts`+`task-modal.component.ts`+`project-workspace.component.ts`+`estimation.ts` ~35-50; tests ~360-460: `test_estimation.py` ~140-180, `test_tasks_estimation.py` ~220-280) |
| 400-line budget risk | High — el cambio completo supera el presupuesto de revisión con certeza, aunque no requiere migración |
| Chained PRs recommended | No — instrucción explícita: single-pr, merge local a `preview` (mismo patrón que 25/27/28: commits escalonados dentro de una sola integración) |
| Suggested split | Fase 0 gate 28→34 → Fase 1 funciones puras + tests unitarios → Fase 2 integración en `TaskService` (precedencia/vacío/422) → Fase 3 `estimation_display` sin N+1 → Fase 4 frontend (task-modal + `estimation.ts`) → Fase 5 suite completa + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U0 | Fase 0 — confirmar que `work_calendar` (28) ya está aplicado en disco | (sin commit propio) | `ls backend/app/modules/work_calendar/{resolver,schemas}.py` | N/A — solo lectura de disco | N/A |
| U1 | Fase 1 — `parse_estimation`/`format_estimation`/`seconds_to_hours` puras en `work_calendar/estimation.py` | 1 — `feat(estimation): agrega el parser y formateador de estimaciones en work_calendar` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_estimation.py` | Pytest, funciones puras (sin BD) | Revert commit; módulo nuevo sin consumidores todavía |
| U2 | Fase 2 — `estimation_input` en `TaskCreate`/`TaskUpdate` con precedencia/vacío/422 | 2 — `feat(tasks): agrega estimation_input con precedencia sobre estimation_hours` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py` | Pytest contra Postgres real de test | Revert commit; `estimation_hours` numérico sigue funcionando igual que hoy |
| U3 | Fase 3 — `estimation_display` en `_to_read`, calendario memoizado por proyecto | 3 — `feat(tasks): expone estimation_display calculado sin N+1` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py backend/tests/test_tasks_pagination.py` | Ídem | Revert commit; campo transitorio adicional, sin efecto en persistencia |
| U4 | Fase 4 — frontend: `task-modal` envía string crudo, `estimation.ts` deja de ser fuente de verdad | 4 — `feat(task-modal): el frontend deja de convertir w/d/h localmente` | `cd frontend && npx jest --testPathPattern task-modal` (o el runner configurado; confirmar en `package.json`) | `cd frontend && npm run build` (build real, sin mocks) | Revert commit; el backend sigue aceptando `estimation_hours` numérico como antes |
| U5 | Fase 5 — suite completa verde + commit final si aplica | 5 — `fix(estimacion): cierra hallazgos de la suite completa` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; si no hubo hallazgos, U5 no aporta commit nuevo |

## Fase 0 — Precondición: 28-calendario-laboral ya aplicado

- [ ] 0.1 Confirmar que `backend/app/modules/work_calendar/resolver.py` (`WorkCalendarResolver`) y `backend/app/modules/work_calendar/schemas.py` (`ResolvedCalendar`, `CalendarSource`) existen en disco. Verify: `ls backend/app/modules/work_calendar/{resolver,schemas}.py`. Si falta cualquiera de los dos, DETENER este cambio y aplicar primero `28-calendario-laboral`.
- [ ] 0.2 Leer la firma real aplicada de `WorkCalendarResolver.resolve(organization_id, project_id) -> ResolvedCalendar` y los campos de `ResolvedCalendar` (`working_hours_per_day`, `working_days`, `source`). Verify: coinciden con el contrato usado en las Fases 1-3 de este documento; si 28 aplicó con ajustes, actualizar las referencias antes de escribir código nuevo.

## Fase 1 — Funciones puras en `work_calendar/estimation.py` (Commit 1)

- [ ] 1.1 [RED] Crear `backend/tests/test_estimation.py`. Gramática: `"2w 3d 4h"` con calendario A (8h, `working_days=[1,2,3,4,5]`) → `Decimal("60")`; `"1.5d"` → `Decimal("12")`; `"1d 2d"` (unidad repetida) → `InvalidEstimationError`; `"4h 3d"` (orden invertido) → `InvalidEstimationError`; `"3x"` y `"-2h"` (unidad desconocida / negativo) → `InvalidEstimationError`. Hoy falla: `app.modules.work_calendar.estimation` no existe. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_estimation.py` → error de import.
- [ ] 1.2 [GREEN] Crear `backend/app/modules/work_calendar/estimation.py`: `class InvalidEstimationError(ValueError)`; `parse_estimation(text: str, calendar: ResolvedCalendar) -> Decimal` — regex de token `^(\d+(\.\d+)?)([wdh])$` (case-insensitive), split por espacios, orden estricto `w→d→h` sin repetidos (rank creciente en una sola pasada), aritmética exclusivamente `Decimal` (`1d = calendar.working_hours_per_day`; `1w = len(calendar.working_days) × calendar.working_hours_per_day`); cualquier fallo levanta `InvalidEstimationError` con mensaje claro. No maneja cadena vacía (responsabilidad del service, D3). Verify: mismo comando de 1.1 → verde para los casos de gramática.
- [ ] 1.3 [RED] En el mismo archivo: formateo — `format_estimation(Decimal("6"), calendario_8h)` → `"6h"`; `Decimal("26")` → `"3d 2h"`; `format_estimation(Decimal("60"), calendario_8h_5dias)` → `"1w 2d 4h"`; `Decimal("40")` (exacto a 1 semana) → `"1w"` (sin `0d 0h`). Verify: `pytest -q backend/tests/test_estimation.py -k format_estimation` → falla (función no existe).
- [ ] 1.4 [GREEN] Implementar `format_estimation(hours: Decimal, calendar: ResolvedCalendar) -> str`: rollup a la mayor unidad alcanzada (`1w = len(working_days) × working_hours_per_day`; `1d = working_hours_per_day`), resto en unidades menores, omite componentes en cero, resto decimal se muestra tal cual (`"2.5h"`). Verify: mismo comando de 1.3 → verde.
- [ ] 1.5 [RED] Contrato de ida y vuelta con dos calendarios distintos: calendario A (8h, `working_days=[1,2,3,4,5]`) — `format_estimation(parse_estimation("1w 2d 4h", A), A) == "1w 2d 4h"` y el total en horas es `60`; calendario B (10h, `working_days=[1..7]`, 7 días) — `format_estimation(parse_estimation("1w", B), B) == "1w"` con total `70`, distinto del resultado de A para el mismo texto. Verify: `pytest -q backend/tests/test_estimation.py -k round_trip` → falla si algún redondeo/rollup no preserva el total (test escrito antes de tocar la implementación de 1.2/1.4 si aún no cubre ambos calendarios).
- [ ] 1.6 [GREEN] Ajustar `parse_estimation`/`format_estimation` si el paso 1.5 expone un caso de redondeo o rollup no cubierto por 1.2/1.4 (p. ej. `working_days` con longitud distinta de 5). Verify: mismo comando de 1.5 → verde.
- [ ] 1.7 [RED] `seconds_to_hours(9000) == Decimal("2.5")`; `seconds_to_hours(0) == Decimal("0")`. Verify: `pytest -q backend/tests/test_estimation.py -k seconds_to_hours` → falla (función no existe).
- [ ] 1.8 [GREEN] Implementar `seconds_to_hours(seconds: int) -> Decimal` (`Decimal(seconds) / Decimal(3600)`, sin gramática — seam 40/41). Verify: mismo comando de 1.7 → verde.
- [ ] 1.9 [RED→GREEN] `test_estimation_module_does_not_import_tasks`: inspeccionar `app.modules.work_calendar.estimation.__dict__`/AST de imports y afirmar que ninguno referencia `app.modules.tasks` (frontera de reutilización, spec R5). Verify: `pytest -q backend/tests/test_estimation.py -k does_not_import_tasks`.
- [ ] 1.10 Suite dirigida verde: Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_estimation.py`

Commit 1: `feat(estimation): agrega el parser y formateador de estimaciones en work_calendar`

## Fase 2 — Integración en `TaskService` (create/update) (Commit 2)

- [ ] 2.1 [RED] Crear `backend/tests/test_tasks_estimation.py` (usa `client`/`tenant`/fixtures de `conftest.py`; configura el calendario del proyecto vía `PUT /organizations/me/work-calendar` u override de proyecto raíz, endpoints de 28). `test_create_task_with_estimation_input_converts_to_hours`: calendario 8h/`[1..5]`, `POST /projects/{id}/tasks` con `estimation_input="2d 4h"` → `201`, `estimation_hours == 20`. Hoy falla: `TaskCreate` no acepta `estimation_input` (422 por campo no reconocido, o el campo se ignora silenciosamente). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py -k converts_to_hours` → falla.
- [ ] 2.2 [RED] `test_estimation_input_takes_precedence_over_estimation_hours_numeric`: `POST` con `estimation_input="1d"` y `estimation_hours=100` a la vez (calendario 8h/día) → persiste `estimation_hours == 8`, ignora el `100`. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k takes_precedence`.
- [ ] 2.3 [RED] `test_estimation_input_empty_string_clears_existing_estimation`: tarea con `estimation_hours=16`, `PATCH /tasks/{id}` con `estimation_input=""` → `estimation_hours` queda `null`. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k clears_existing`.
- [ ] 2.4 [RED] `test_estimation_input_invalid_grammar_returns_422_and_persists_nothing`: `POST` y `PATCH` con `estimation_input="3x"` y `"4h 3d"` → `422` en ambos casos, la tarea no se crea / no cambia (assert vía `GET` posterior). Verify: `pytest -q backend/tests/test_tasks_estimation.py -k invalid_grammar`.
- [ ] 2.5 [RED] `test_estimation_hours_numeric_only_still_accepted_without_conversion`: `POST` solo con `estimation_hours=12` (sin `estimation_input`) → `201`, `estimation_hours == 12` sin pasar por el parser (retrocompat, spec "estimation_hours numérico directo sigue siendo válido"). Verify: `pytest -q backend/tests/test_tasks_estimation.py -k numeric_only`.
- [ ] 2.6 [RED] `test_patch_estimation_input_on_task_of_other_org_returns_404` (mismo patrón que el resto de endpoints de detalle de `tasks`, usando la fixture `two_orgs` si existe o el patrón equivalente del archivo): miembro de la organización A intenta `PATCH /tasks/{id}` de la organización B con `estimation_input` → `404`, nada se persiste. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k other_org`.
- [ ] 2.7 [GREEN] `backend/app/modules/tasks/schemas.py`: añadir `estimation_input: str | None = Field(default=None, max_length=60)` a `TaskCreate` y `TaskUpdate` (junto a `estimation_hours`); añadir `estimation_display: str | None = None` a `TaskRead` (junto a `estimation_hours`). Verify: import de `test_tasks_estimation.py` deja de fallar por campo desconocido.
- [ ] 2.8 [GREEN] `backend/app/modules/tasks/service.py`: importar `work_calendar.estimation.{parse_estimation, InvalidEstimationError}` y `work_calendar.resolver.WorkCalendarResolver` a nivel de módulo (sin ciclo — `work_calendar` no importa `tasks`, mismo criterio ya usado para `projects`). Añadir `self._cal_cache: dict[uuid.UUID, ResolvedCalendar] = {}` en `__init__` y `async def _resolve_calendar(self, organization_id, project_id) -> ResolvedCalendar` memoizado por `project_id` (vida = instancia de `TaskService`, una por request). Añadir `_apply_estimation_input(calendar, raw_input, fallback_hours) -> float | None`: `stripped = raw_input.strip()`; vacío → `None` (limpia); no vacío → `float(parse_estimation(stripped, calendar))`, capturando `InvalidEstimationError` y re-lanzando `AppException(mensaje claro, code="invalid_estimation_input", status_code=422)`. Verify: aún sin wiring en create/update — solo compila e importa.
- [ ] 2.9 [GREEN] En `create_task`: tras resolver `project`, `calendar = await self._resolve_calendar(organization_id, project_id)`; si `data.estimation_input is not None`, `estimation_hours = self._apply_estimation_input(calendar, data.estimation_input, data.estimation_hours)` (precedencia: ignora `data.estimation_hours` si `estimation_input` viene); si no, `estimation_hours = data.estimation_hours` (comportamiento actual, sin cambios). Pasar ese valor resuelto a `Task(..., estimation_hours=estimation_hours)` en lugar de `data.estimation_hours` directo. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k "converts_to_hours or takes_precedence or numeric_only"` → verde.
- [ ] 2.10 [GREEN] En `update_task`: extender el bloque `if "estimation_points" in changes or "estimation_hours" in changes:` para incluir `"estimation_input" in changes`; cuando `"estimation_input" in changes` y su valor no es `None`, resolver el calendario del proyecto de la tarea y calcular `next_hours` vía `_apply_estimation_input` ANTES de `self._validate_estimation(...)` (para que un input inválido siga respondiendo 422 sin tocar `task.estimation_hours`); cuando `estimation_input` está ausente o es `None`, mantener la resolución actual de `next_hours` desde `changes.get("estimation_hours", task.estimation_hours)`. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k "clears_existing or invalid_grammar or other_org"` → verde.
- [ ] 2.11 Suite dirigida verde: Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py backend/tests/test_tasks_crud.py`

Commit 2: `feat(tasks): agrega estimation_input con precedencia sobre estimation_hours`

## Fase 3 — `estimation_display` sin N+1 (Commit 3)

- [ ] 3.1 [RED] `test_get_task_exposes_estimation_display`: tarea con `estimation_hours=26` en proyecto con calendario 8h/día → `GET /tasks/{id}` incluye `estimation_display == "3d 2h"`. Hoy falla: el campo no se calcula (queda `None`/ausente). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py -k exposes_estimation_display` → falla.
- [ ] 3.2 [RED] `test_task_without_estimation_has_null_display`: tarea con `estimation_hours=None` → `estimation_display is None` en detalle y en listado, sin error. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k null_display`.
- [ ] 3.3 [RED] `test_list_tasks_resolves_calendar_once_per_response`: proyecto con 20 tareas con `estimation_hours` distintos; instrumentar un spy/contador sobre `WorkCalendarResolver.resolve` (monkeypatch) antes de `GET /projects/{id}/tasks` y afirmar que se invoca exactamente UNA vez para toda la respuesta. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k resolves_calendar_once`.
- [ ] 3.4 [RED] `test_list_subtasks_and_get_by_key_also_expose_estimation_display`: `GET /tasks/{id}/subtasks` y `GET /tasks/{key}` (formato `CODIGO-N`) también incluyen `estimation_display` calculado, sin duplicar la resolución del calendario dentro de la misma llamada. Verify: `pytest -q backend/tests/test_tasks_estimation.py -k also_expose_estimation_display`.
- [ ] 3.5 [GREEN] `backend/app/modules/tasks/service.py`: convertir `_to_read` de `@staticmethod` a método de instancia (o parámetro explícito) que reciba `calendar: ResolvedCalendar | None` y setee `read.estimation_display = format_estimation(task.estimation_hours, calendar) if task.estimation_hours is not None and calendar is not None else None` — usar el `Decimal` crudo de `task.estimation_hours` (columna ORM), NO el valor ya coercionado a `float` por `TaskRead`. Actualizar los call sites: `list_tasks` resuelve el calendario UNA vez antes del loop de `_to_read`; `get_task`/`get_task_by_key`/`list_subtasks` resuelven una vez por llamada; `create_task`/`update_task`/`move_task_column` reutilizan el `calendar` ya resuelto en el propio método (evitar una segunda resolución en la misma request). Verify: mismo comando de 3.1-3.4 → verde.
- [ ] 3.6 Suite dirigida verde: Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_tasks_estimation.py backend/tests/test_tasks_crud.py backend/tests/test_tasks_pagination.py`

Commit 3: `feat(tasks): expone estimation_display calculado sin N+1`

## Fase 4 — Frontend: `task-modal` deja de convertir localmente (Commit 4)

- [ ] 4.1 `frontend/src/entities/workspace/workspace.model.ts`: añadir `estimation_display?: string | null` a la interfaz `Task`; añadir `estimation_input?: string | null` a `CreateTaskPayload` y `UpdateTaskPayload` (junto a `estimation_hours`, que se conserva para retrocompat de otros flujos como la creación rápida de subtareas en `task-detail.service.ts`).
- [ ] 4.2 `frontend/src/widgets/task-modal/task-modal.component.ts`: en `ngOnInit` (línea 359), reemplazar `formatOriginalEstimate(existing.estimation_hours)` por `existing.estimation_display ?? ''` al hidratar el control `original_estimate` (el backend ya formatea con el calendario real del proyecto). En `onSubmit()` (líneas 415-434), dejar de invocar `parseOriginalEstimate` para calcular `estimation_hours`: solo validar que el texto no esté vacío cuando el usuario escribió algo (la gramática la valida el backend, que responde 422 si es inválida); emitir el texto recortado como `estimation_input` en `TaskFormResult` en lugar de `estimation_hours` numérico. Actualizar la interfaz `TaskFormResult` (línea 42): `estimation_input: string | null` en vez de `estimation_hours: number | null`. Quitar el import de `parseOriginalEstimate` si queda sin uso en este archivo (`formatOriginalEstimate` sigue en uso para la hidratación de lectura si `estimation_display` viniera vacío en algún caso legado — confirmar con 4.4).
- [ ] 4.3 `frontend/src/widgets/project-workspace/project-workspace.component.ts` (líneas 1336, 1351): actualizar el mapeo de `TaskFormResult` → `CreateTaskPayload`/`UpdateTaskPayload` para enviar `estimation_input: result.estimation_input` en lugar de `estimation_hours: result.estimation_hours`.
- [ ] 4.4 `frontend/src/shared/lib/estimation.ts`: actualizar el comentario de cabecera para reflejar que `parseOriginalEstimate`/`formatOriginalEstimate` ya NO son la fuente de verdad de `task-modal` (el backend convierte/formatea con el calendario real). NO eliminar las funciones: `task-detail-panel.component.ts` y `sprint-gantt.component.ts` siguen invocándolas para su propia UI (fuera del alcance de esta Fase — ver Risks). Verify: `grep -rn "parseOriginalEstimate\|formatOriginalEstimate" frontend/src` sigue resolviendo a usos válidos tras 4.2.
- [ ] 4.5 Build verde: Verify: `cd frontend && npm run build` (o el comando de build configurado en `package.json`) sin errores de tipos por los campos renombrados/añadidos.

Commit 4: `feat(task-modal): el frontend deja de convertir w/d/h localmente`

## Fase 5 — Suite completa + commits (Commit 5 condicional)

- [ ] 5.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 5.2 Confirmar que el aislamiento cross-tenant no regresó tras exponer `estimation_input`/`estimation_display`. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_cross_tenant_isolation.py -k "tasks or estimation"` (confirmar el nombre exacto del archivo con `ls backend/tests/ | rg cross_tenant`).
- [ ] 5.3 Confirmar que el historial automático de cambios (`TaskHistory`) sigue registrando `estimation_hours` sin importar si el cambio llegó vía `estimation_input` o numérico directo (campo ya incluido en `_HISTORY_TRACKED_FIELDS`, sin cambios de código esperados — solo confirmación). Verify: `pytest -q backend/tests/ -k "history and estimation"` (o el archivo de historial equivalente).
- [ ] 5.4 Build de frontend verde (repetir tras cualquier ajuste de las Fases 2-4). Verify: `cd frontend && npm run build`.
- [ ] 5.5 Commit final (solo si 5.1/5.2/5.3 generaron correcciones no cubiertas por los commits 1-4; en caso contrario no aporta commit nuevo).

Commit 5 (solo si 5.5 generó cambios): `fix(estimacion): cierra hallazgos de la suite completa`

## Trazabilidad de requisitos

- Gramática del texto de estimación (válida, decimales, unidad repetida/orden invertido/desconocida/negativo rechazados) · 1.1,1.2
- Conversión a horas con calendario del proyecto (`1d=hpd`, `1w=len(days)×hpd`, dos calendarios distintos) · 1.1,1.2,1.5
- Formateo por unidad mayor con resto (solo horas, días+resto, semanas+días+horas, exacto omite ceros) · 1.3,1.4
- Contrato de ida y vuelta estable entre calendarios · 1.5,1.6
- Frontera de reutilización — módulo puro sin importar `tasks` · 1.9
- Seam Jira (segundos, sin gramática) · 1.7,1.8
- Estimación por texto con precedencia sobre el valor numérico (crear/actualizar, vacío limpia, inválido 422, retrocompat numérico, aislamiento de tenant) · 2.1,2.2,2.3,2.4,2.5,2.6,2.7,2.8,2.9,2.10
- Campo calculado `estimation_display` (detalle, listado sin N+1, subtareas/por-clave, `null` sin estimación) · 3.1,3.2,3.3,3.4,3.5
- Frontend deja de fijar 8h/5d como fuente de verdad en `task-modal` · 4.1,4.2,4.3,4.4,4.5
- Gate 28→34 (módulo `work_calendar` aplicado antes de iniciar) · 0.1,0.2
- No regresión y commits escalonados en una sola integración · 5.1,5.2,5.3,5.4,5.5

## Risks

- **Superficies frontend fuera de alcance de la Fase 4**: `task-detail-panel.component.ts` (líneas 571, 768-799, edición inline de `estimation_hours`) y `sprint-gantt.component.ts` (línea 744) siguen usando `formatOriginalEstimate`/`parseOriginalEstimate` con el factor local 8h/5d — el mismo drift que este cambio busca eliminar persiste en esas dos superficies. La Fase 4 de este documento cubre exclusivamente `task-modal` + `shared/lib/estimation.ts` por instrucción explícita del alcance recibido; se recomienda decidir si se amplía esta Fase o se abre un fast-follow antes de dar por cerrado el cambio.
- **Precedencia con `estimation_input: null` explícito** (distinto de campo ausente y de cadena vacía): la spec solo define el comportamiento de "ausente" (usa `estimation_hours`) y "vacío" (limpia); un `null` explícito en el PATCH no está cubierto por ningún escenario de la spec — este documento lo trata igual que "ausente" (2.10); si el equipo prefiere que `null` también limpie, es una decisión a validar antes del `apply`.
- **Naming spec vs. design** (ver Reconciliación aplicada): si `apply` o `verify` leen `specs/estimation/spec.md` de forma literal, puede generar confusión porque menciona `estimate_to_hours`/`format_hours`; ya reconciliado a favor de `design.md` en este documento.
