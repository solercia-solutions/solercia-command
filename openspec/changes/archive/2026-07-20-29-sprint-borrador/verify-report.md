```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:2d83e52e962dfd94a1535a26eb6522721540d98d69c294145b165d80d7c446f
verdict: pass
blockers: 0
critical_findings: 0
requirements: 5/6
scenarios: 5/6
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:ef1f6a9a1bc8ba68e9a401e4854aeaf533155fee4440506cd6ed0829d2a99040
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:08461e2bcaf0683f1c71e410d4d866efec300bc214bde17ae175925ae1625797
```

# Verification Report: 29 · Sprint borrador (creación con solo nombre + autonombre)

**Change**: 29-sprint-borrador
**Rama**: `feat/sprint-borrador` (HEAD `3d79fcf`)
**Mode**: Full artifact set (proposal, specs, design, tasks) — Strict TDD activo
**Verdict**: **PASS WITH WARNINGS**

## Completeness

| Ítem | Estado |
|------|--------|
| Tareas completadas | 46/46 (100%) — `tasks.md` sin casillas `[ ]` pendientes |
| Commits de apply | 6 (`5456ecb` naming, `c403399` draft creation, `3367f67` start+guarda, `4d58f2c` suggested-name, `77fca04` frontend, `3d79fcf` docs de cierre) |
| `state.yaml` (antes de este reporte) | `phases.apply: done`, `phases.verify: pending` |
| Migración | Ninguna — `git diff --stat preview...feat/sprint-borrador -- backend/alembic` vacío, confirma `constraints: no-schema-migration-status-is-freeform-string` |
| Alcance | Backend `sprints/*` + frontend `entities/workspace`, `widgets/project-workspace`, `assets/i18n/es-CO.json` — 13 archivos, 1289 inserciones / 78 eliminaciones (`git diff --stat`) |

## Build / Tests — evidencia de ejecución real

| Comando | Resultado |
|---------|-----------|
| `cd backend && TEST_DATABASE_URL=... pytest -q` (suite completa) | **1332 passed**, 1 warning preexistente (SAWarning de ciclos FK en `alembic/env.py`, no relacionado), 0 failed — coincide exactamente con lo reportado por apply (1302→1332, +30) |
| `source ~/.nvm/nvm.sh && nvm use 22.22.3 && cd frontend && npm run build` | **Exit 0** — `Application bundle generation complete`, sin errores ni warnings en el log completo |

## Spec Compliance Matrix

| Requirement | Escenario | Test cubriendo | Estado |
|-------------|-----------|-----------------|--------|
| Creación en borrador sin fechas | Con/sin nombre; metodología no habilitada rechaza | `test_create_sprint_without_name_and_without_dates_is_draft_with_autoname`, `test_create_sprint_with_empty_string_name_also_uses_autoname`, `test_create_sprint_still_rejects_project_without_sprints_enabled` (`test_sprint_draft_creation.py`) | ✅ COMPLIANT |
| Autonombre sugerido del próximo sprint | Consecutivo con separador y año | `test_next_name_increments_trailing_run_with_separator`, `test_next_name_preserves_zero_padding`, `test_next_name_without_previous_uses_project_code`, `test_next_name_without_previous_and_without_code_defaults_to_sprint_one` (`test_sprint_naming.py`, 9 casos) + `test_suggested_name_matches_next_sprint_name_given_last_sprint` (`test_sprint_suggested_name.py`) | ✅ COMPLIANT |
| Inicio de sprint exige fechas presentes | Sin fechas no inicia; con fechas sí; sin reinicio | `test_start_sprint_without_dates_returns_422_spanish_and_stays_draft`, `test_start_sprint_with_both_dates_transitions_to_active`, `test_start_sprint_already_active_returns_409`, `test_start_sprint_already_closed_returns_422` (`test_sprint_start.py`) | ✅ COMPLIANT |
| Permisos y aislamiento de tenant | Happy path, sin auth, tenant ajeno | `test_start_sprint_of_other_org_returns_404`, `test_start_sprint_not_found_returns_404`, `test_suggested_name_of_other_org_returns_404`, `test_suggested_name_requires_auth` | ✅ COMPLIANT |
| UI del flujo de sprint borrador | Creación liviana e inicio condicionado | Sin test automatizado (frontend sin runner) — verificado por inspección de código + `npm run build` en verde, conforme al harness declarado explícitamente en `tasks.md` U5 (`Runtime harness: cd frontend && npm run build`) | ⚠️ PARTIAL |
| No regresión sobre sprints existentes | Suite en verde con sprints previos intactos | `test_sprint_close.py` (11 tests preexistentes, sin modificar, en verde dentro de la suite completa) + `test_create_sprint_with_both_dates_is_active_backwards_compatible` | ✅ COMPLIANT |

**Compliance summary**: 5/6 escenarios COMPLIANT en runtime; 1/6 PARTIAL (UI, ver Issues).

## Verificaciones puntuales pedidas por el orquestador

1. **Suite completa** — ✅ 1332 passed, 0 failed (coincide con lo reportado por apply).
2. **Tabla de verdad del autonombre** — ✅ Cubierta por 9 tests unitarios nombrados en `test_sprint_naming.py`: `PANDORA 2026-1→2026-2` (`test_next_name_increments_trailing_run_with_separator`), `Sprint 9→10` (`test_next_name_increments_simple_trailing_number`), `Velocidad→2` (`test_next_name_without_trailing_number_suffixes_two`), `S-09→S-10` con padding (`test_next_name_preserves_zero_padding`), fallback con `code` (`test_next_name_without_previous_uses_project_code`), fallback sin `code` (`test_next_name_without_previous_and_without_code_defaults_to_sprint_one`).
3. **Guarda de fechas** — ✅ Ambos caminos probados y en verde: `POST /sprints/{id}/start` (`test_start_sprint_without_dates_returns_422_spanish_and_stays_draft`) y `PATCH /sprints/{id}` con `status=active` directo (`test_patch_status_active_on_draft_without_dates_returns_422_and_stays_draft`), ambos con `detail == "El sprint necesita fecha de inicio y fin antes de iniciarse."` (es-CO formal).
4. **Retrocompatibilidad** — ✅ `test_create_sprint_with_both_dates_is_active_backwards_compatible` (ambas fechas → `active`); `test_create_sprint_with_only_one_date_is_still_draft` (una fecha → `draft`); `test_sprint_close.py` (suite existente, 11 tests, sin modificar, en verde).
5. **`suggested-name` antes de `{sprint_id}`** — ✅ Confirmado por lectura de `router.py`: `GET /projects/{project_id}/sprints/suggested-name` (línea 65) declarado antes de `GET /projects/{project_id}/sprints/{sprint_id}/burndown` (línea 83), con comentario explícito documentando la salvaguarda.
6. **Strategy `sprints_enabled` sin `if methodology ==`** — ✅ `grep -rn "methodology ==" backend/app/modules/sprints/` no arroja código nuevo (única coincidencia es el docstring de `_require_sprints_enabled` describiendo la regla). El único punto de lectura sigue siendo `get_strategy(project.methodology).sprints_enabled` dentro de `_require_sprints_enabled`.
7. **Aislamiento organizacional** — ✅ `sprints` ya está en el bucket `TENANT_SCOPED` de `test_cross_tenant_isolation.py` (meta-test `test_all_modules_are_classified`), cubierto ahí para `list`/`update`. Los endpoints NUEVOS (`/start`, `suggested-name`) no se agregaron a esa batería central, pero SÍ tienen cobertura dedicada equivalente en sus propios archivos: `test_start_sprint_of_other_org_returns_404`, `test_start_sprint_not_found_returns_404` (`test_sprint_start.py`) y `test_suggested_name_of_other_org_returns_404`, `test_suggested_name_requires_auth` (`test_sprint_suggested_name.py`). Anotado como nota, no como hallazgo — la cobertura existe, solo vive en otro archivo.
8. **Frontend** — ✅ Confirmado por lectura: botón "Crear sprint" liviano con `name` opcional y precarga de sugerencia (`project-workspace.component.ts` — efecto lazy que llama `suggestedSprintName` cuando `activeTab() === 'sprints'` y el control sigue `pristine`); badge "Borrador" (`sprintBadgeClass()` + `workspace.sprints.statusDraft`); modal "Añadir fechas" (`addDatesOpen`, `openAddDates`, `confirmAddDates`, líneas 802-810 y 1589-1614); botón "Iniciar sprint" deshabilitado sin ambas fechas con tooltip (`canStartSprint()`, `[disabled]="!canStartSprint(sprint) || startingSprintId() === sprint.id"`, `startDisabledTooltip`). `npm run build` verde (exit 0, sin errores).
9. **`tasks.md` 46/46 y `state.yaml` apply: done** — ✅ Confirmado por lectura directa de ambos archivos antes de esta verificación.

## TDD Compliance

| Check | Resultado | Detalle |
|-------|-----------|---------|
| TDD Evidence reportada | ⚠️ Formato distinto, sustancia presente | `apply-progress` (Engram) no trae una tabla literal "TDD Cycle Evidence"; la evidencia RED/GREEN vive en `tasks.md` (cada tarea etiquetada `[RED]`/`[GREEN]`/`[RED→GREEN]` con comando `Verify:` explícito), formato consistente con cambios previos de este repo (25/27/28/34) |
| Todas las tareas tienen tests | ✅ | 4/4 archivos nuevos de test (`test_sprint_naming.py`, `test_sprint_draft_creation.py`, `test_sprint_start.py`, `test_sprint_suggested_name.py`) |
| RED confirmado (archivos existen) | ✅ | 4/4 verificados en el filesystem |
| GREEN confirmado (tests pasan) | ✅ | 30/30 tests nuevos pasan dentro de la corrida completa (1332 passed) |
| Triangulación adecuada | ✅ | Autonombre: 9 casos; guarda de fechas: 3 vías (`/start`, `PATCH` directo, `PATCH` sin `status`); permisos: 404/401 explícitos por endpoint nuevo |
| Safety Net (archivos modificados) | ✅ | `service.py`/`router.py`/`schemas.py`/`repository.py` modificados; `test_sprint_close.py` (11 tests preexistentes) corrido dentro de la suite completa, en verde tras el reordenamiento de `update_sprint` |

**TDD Compliance**: 5/6 checks pasados (1 nota de formato, no de sustancia).

## Assertion Quality Audit

Archivos escaneados: `test_sprint_naming.py` (9 tests), `test_sprint_draft_creation.py` (6), `test_sprint_start.py` (9), `test_sprint_suggested_name.py` (6) = 30 tests.

- Sin tautologías (`assert True`, `expect(true).toBe(true)`) — 0 coincidencias.
- Todas las aserciones verifican comportamiento real: status codes, `code`/`detail` exactos, transiciones de `status`, contenido de `name` calculado — ninguna aserción huérfana de llamada a producción.
- Sin ghost loops sobre colecciones potencialmente vacías.
- Sin acoplamiento a detalles de implementación (clases CSS, conteos de mocks) en el backend.

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real.

## Coherence (Design)

| Decisión | ¿Seguida? | Notas |
|----------|-----------|-------|
| D1 — `next_sprint_name` pura, sin I/O, tabla de verdad completa | ✅ Sí | `naming.py` sin imports de SQLAlchemy ni de `app`; algoritmo idéntico al documentado |
| D2 — Endpoint de sugerencia reutilizando `POST` + nuevo `GET` | ✅ Sí, con reconciliación documentada | `design.md` nombraba `next-name`/`SprintNextName`; `spec.md` e instrucción del orquestador fijaron `suggested-name`/`SprintSuggestedName` — reconciliación explícita en `tasks.md` §1, no es drift silencioso |
| D3 — `_ALLOWED_STATUSES`, `/start` con 404/409/422 | ✅ Sí, con reconciliación documentada | `code=sprint_already_closed` para el 422 de "ya cerrado" decidido en `tasks.md` §2 (reutiliza el nombre del 409 de `/close`, distinguible por `status_code`+endpoint) — riesgo aceptado y documentado en `tasks.md` Risks |
| D4 — Frontend: acciones por estado (draft/active/closed) | ✅ Sí | Confirmado por lectura: 3 ramas de botones (`draft`→Añadir fechas+Iniciar; `active`→Cerrar; `closed`→Reactivar) |
| D5 — Seams para cambio 30 (`SprintStatus` incluye `draft`, `sprintBadgeClass()` reutilizable) | ✅ Sí | `SprintStatus = 'draft' \| 'active' \| 'closed'` en `workspace.model.ts` |

## Issues Found

**CRITICAL**: Ninguno.

**WARNING**:
1. **UI sin cobertura automatizada de comportamiento** — el flujo de sprint borrador en el frontend (`project-workspace.component.ts`) solo se verifica con `npm run build` (compilación/type-check estricto de Angular), no con un test de comportamiento en tiempo de ejecución, porque `frontend/package.json` no define un runner de tests (`test`), solo `build`/`lint`/`watch`. Esto es una limitación de infraestructura preexistente en todo el repo (mismo patrón aceptado en el cambio 34), documentada explícitamente en `tasks.md` como el harness de verificación de la Fase 5 — no es deuda nueva introducida por este cambio, pero sigue siendo un hueco real de cobertura si un regresión de comportamiento (no de tipos) se introduce ahí en el futuro.
2. **`sprint_already_closed` con dos significados** (`tasks.md` Reconciliación #2, riesgo ya documentado por el propio equipo de `apply`): el mismo `code` se usa en `close_sprint` (409, "ya cerrado, no se puede volver a cerrar") y en `start_sprint` (422, "cerrado, no se puede iniciar"). Distinguibles por `status_code`+endpoint, pero un cliente que solo mire `code` sin `status_code` podría confundir ambos casos.
3. **Meta-test de aislamiento tenant no extendido a los endpoints nuevos** — `test_cross_tenant_isolation.py` (la batería central) no agregó `test_start_sprint_of_other_org_returns_404`/`suggested-name` a su propio archivo; la cobertura de aislamiento para `/start` y `suggested-name` existe pero vive en `test_sprint_start.py`/`test_sprint_suggested_name.py` en vez de la batería central. Funcionalmente cubierto, organizacionalmente disperso.

**SUGGESTION**:
1. **Reactivar un sprint `closed` vía `PATCH status=active`** ahora también pasa por la guarda de fechas nueva (3.9); no hay ningún test explícito para "reactivar un `closed` que quedó sin fechas" — caso de borde de baja probabilidad (un sprint `closed` casi siempre tuvo ambas fechas al haber sido `active` antes), ya anotado como riesgo aceptado en `tasks.md`.

## Verdict

**PASS WITH WARNINGS** — Los 6 requisitos ADDED de `specs/sprints/spec.md` están trazados a implementación; 5/6 respaldados por tests que corrieron en verde en esta verificación (no solo inspección estática), 1/6 (UI) verificado por inspección de código + build en verde, con el hueco de cobertura de comportamiento documentado explícitamente como decisión de infraestructura preexistente, no como deuda nueva. Suite completa: 1332 passed, 0 failed (exit 0). Frontend build: exit 0, sin errores. `tasks.md` 46/46. Sin migración. Sin `if methodology ==` nuevo. Guarda de fechas confirmada en ambos mecanismos de transición (`/start` y `PATCH` directo). Ningún hallazgo CRITICAL bloquea el archivo del cambio.
