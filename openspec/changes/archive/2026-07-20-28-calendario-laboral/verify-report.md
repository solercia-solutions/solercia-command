```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:e7258124a79352edaa9f0802409edd08a75dcc8f9a23d5417231a0cae639e16a
verdict: pass
blockers: 0
critical_findings: 0
requirements: 5/5
scenarios: 18/18
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
test_exit_code: 0
test_output_hash: sha256:41769e490aa099dea88ea651b9614cb245ee3f8f8f216859c2249f22bcf27f66
build_command: cd backend && .venv/bin/ruff check app/modules/work_calendar/ app/modules/organizations/models.py app/modules/projects/models.py app/modules/projects/schemas.py app/main.py tests/test_work_calendar_schemas.py tests/test_work_calendar_resolver.py tests/test_work_calendar_api.py tests/test_migration_work_calendar.py tests/test_projects.py
build_exit_code: 0
build_output_hash: sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f1
```

## Verification Report

**Change**: 28-calendario-laboral
**Rama**: `feat/calendario-laboral` (HEAD `9be4a40`, 5 commits sobre `preview`)
**Versión**: N/A (sin versión de spec explícita)
**Modo**: Strict TDD

### Completitud

| Métrica | Valor |
|---|---|
| Tareas totales (`tasks.md`) | 44 |
| Tareas completas (`- [x]`) | 44 |
| Tareas incompletas (`- [ ]`) | 0 |

Verificado con `rg -c '^\s*- \[x\]'` (44 coincidencias) y `rg -c '^\s*- \[ \]'` (0 coincidencias) sobre `openspec/changes/28-calendario-laboral/tasks.md`.

`state.yaml` (antes de este verify): `phases.apply: done`, `phases.verify: pending` — confirmado por lectura directa del archivo.

### Ejecución de build y tests

**Build (lint, `ruff check`)**: ✅ Passed — `All checks passed!` sobre todos los archivos de producción y test creados/modificados por este cambio (exit 0).

Nota: un `ruff check` más amplio que incluyó `tests/test_cross_tenant_isolation.py` completo reportó 1 `E501` (línea 128, ya existente antes de este cambio — `git diff preview...feat/calendario-laboral -- backend/tests/test_cross_tenant_isolation.py` muestra únicamente 8 líneas agregadas alrededor de la línea 70-78; la línea 128 no forma parte del diff). No es un hallazgo introducido por este cambio.

**Tests**: ✅ 1302 passed, 0 failed, 1 warning (364.54s)
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q
...
1302 passed, 1 warning in 364.54s (0:06:04)
```
Coincide exactamente con lo reportado por apply (1272 baseline + 30 nuevos: 9 schemas, 4 resolver, 13 API, 2 migración, 2 projects).

**`alembic check` (sin diff modelo↔migración)**: ✅ cubierto dentro de la suite completa por `tests/test_migrations_baseline.py::test_alembic_check_reports_no_diff_after_upgrade` (pasó).

**Cabeza Alembic**: `cd backend && DATABASE_URL=... .venv/bin/alembic heads` → `0024 (head)`, una sola cabeza sin bifurcar. `alembic/versions/0024_add_work_calendar.py`: `revision = "0024"`, `down_revision = "0023"` — confirmado por lectura directa del archivo.

**Coverage**: ➖ No disponible (`pytest-cov` no está instalado en el entorno — `ModuleNotFoundError: No module named 'pytest_cov'`).

### Matriz de cumplimiento de especificación

#### Capability `work-calendar` (spec nueva)

| Requirement | Scenario | Test | Resultado |
|---|---|---|---|
| Calendario laboral de la empresa | Cualquier miembro lee el default | `test_work_calendar_api.py::test_get_organization_work_calendar_returns_defaults_for_a_new_org` | ✅ COMPLIANT |
| Calendario laboral de la empresa | Admin edita el calendario | `test_work_calendar_api.py::test_put_organization_work_calendar_as_admin_persists_new_values` | ✅ COMPLIANT |
| Calendario laboral de la empresa | Rol no admin no puede editar | `test_work_calendar_api.py::test_put_organization_work_calendar_rejected_for_non_admin` | ✅ COMPLIANT |
| Calendario laboral de la empresa | Validación rechaza fuera de rango | `test_work_calendar_api.py::test_put_organization_work_calendar_validation_rejects_out_of_range` | ✅ COMPLIANT |
| Override de calendario del equipo (raíz) | Manager sobreescribe en raíz | `test_work_calendar_api.py::test_put_project_work_calendar_as_manager_persists_override_on_root` | ✅ COMPLIANT |
| Override de calendario del equipo (raíz) | Override en no-raíz rechazado | `test_work_calendar_api.py::test_put_project_work_calendar_on_non_root_is_rejected` (422, `code=override_requires_root`) | ✅ COMPLIANT |
| Override de calendario del equipo (raíz) | `null` limpia el override (vuelve a heredar) | `test_work_calendar_api.py::test_put_project_work_calendar_null_clears_override_back_to_inherit` | ✅ COMPLIANT |
| Override de calendario del equipo (raíz) | Rol member no puede sobreescribir | `test_work_calendar_api.py::test_put_project_work_calendar_rejected_for_member` | ✅ COMPLIANT |
| Override de calendario del equipo (raíz) | Validación rechaza fuera de rango | `test_work_calendar_api.py::test_put_project_work_calendar_validation_rejects_out_of_range` | ✅ COMPLIANT |
| Resolución en cascada | Nieto hereda override de la raíz (fin de semana) | `test_work_calendar_resolver.py::test_grandchild_inherits_root_override_with_weekend_days` + `test_work_calendar_api.py::test_get_project_work_calendar_resolved_returns_team_source_for_a_grandchild` | ✅ COMPLIANT |
| Resolución en cascada | Raíz sin override cae a empresa | `test_work_calendar_resolver.py::test_root_without_override_falls_back_to_organization_default` + `test_work_calendar_api.py::test_get_project_work_calendar_resolved_falls_back_to_organization_source` | ✅ COMPLIANT |
| Resolución en cascada | Sin datos resolubles → default global (8h/L-V) | `test_work_calendar_resolver.py::test_resolve_defaults_globally_when_the_organization_has_no_resolvable_calendar` | ✅ COMPLIANT |
| Resolución en cascada | Aislamiento de tenant | `test_work_calendar_resolver.py::test_resolve_never_crosses_organization_id` + `test_work_calendar_api.py::test_get_project_work_calendar_resolved_cross_tenant_returns_404` | ✅ COMPLIANT |
| Mapeo `source` interno→wire (`team`/`organization`/`default`) | Test dedicado de serialización | `test_work_calendar_schemas.py::test_resolved_calendar_serializes_internal_source_to_the_public_wire_value` | ✅ COMPLIANT |
| No regresión y prerrequisito 34/35 | Suite completa en verde | Suite completa (1302 passed, 0 failed) | ✅ COMPLIANT |
| No regresión y prerrequisito 34/35 | Downgrade reversible sin pérdida de datos | `test_migration_work_calendar.py::test_downgrade_removes_the_four_columns_without_losing_rows` | ✅ COMPLIANT |

#### Capability `projects` (delta ADDED)

| Requirement | Scenario | Test | Resultado |
|---|---|---|---|
| Columnas nullable de override en `Project` | Raíz con override expone valores | `test_projects.py::test_get_project_exposes_root_work_calendar_override_values` | ✅ COMPLIANT |
| Columnas nullable de override en `Project` | Hijo nunca expone override propio (detalle + listado) | `test_projects.py::test_get_project_child_always_exposes_null_work_calendar_override` | ✅ COMPLIANT |
| Columnas nullable de override en `Project` | Migración aditiva y reversible | `test_migration_work_calendar.py::test_upgrade_adds_the_four_columns_with_correct_defaults_without_losing_rows` + `test_downgrade_removes_the_four_columns_without_losing_rows` | ✅ COMPLIANT |

**Resumen de cumplimiento**: 18/18 escenarios COMPLIANT (5/5 requirements), todos con test cubriendo y en verde en la ejecución real de la suite completa.

### Correctness (evidencia estática + runtime)

| Requirement | Estado | Notas |
|---|---|---|
| Regla solo-raíz | ✅ Implementado | `WorkCalendarService.set_project_override` rechaza no-raíz con `override_requires_root` (422); `null`/`null` limpia el override. Confirmado por test y por lectura de `router.py`/`service.py`. |
| Permisos: `PUT /organizations/me/work-calendar` solo admin | ✅ Implementado | `router.py:57` usa `Depends(require_admin)`. Test: `rejected_for_non_admin` (manager/member/viewer → 403). |
| Permisos: `PUT /projects/{id}/work-calendar` admin/manager | ✅ Implementado | `router.py:93` usa `Depends(_require_project_calendar_write_role)` = `require_role(admin, manager)`. Test: `rejected_for_member` (member/viewer → 403). |
| Permisos: `GET` (empresa, override, resuelto) abierto a cualquier miembro | ✅ Implementado | Los 3 `GET` usan `Depends(get_current_membership)` sin restricción de rol adicional (`router.py:44,77,117`). |
| Aislamiento organizacional | ✅ Implementado | `WorkCalendarRepository.root_override` filtra por `organization_id`; `resolve()` levanta `project_not_found`/404 si no resuelve. Test dedicado en resolver y en API (`resolved_cross_tenant`). `test_cross_tenant_isolation.py` clasifica `work_calendar` como `TENANT_SCOPED` (línea 80). |
| Seam `resolve(...) -> ResolvedCalendar` sin HTTP | ✅ Implementado | `WorkCalendarResolver.resolve(self, organization_id: UUID, project_id: UUID) -> ResolvedCalendar` es un método puro de clase con DI por constructor (`WorkCalendarRepository`, `organizations` repo) — sin dependencia de FastAPI/HTTP. `test_work_calendar_resolver.py` lo instancia e invoca directamente (sin `client`), probando que 34/35 pueden consumirlo igual. |
| Retrocompatibilidad `GET /projects` | ✅ Implementado | `ProjectRead` agrega `working_hours_per_day`/`working_days` opcionales (`default=None`); ningún campo existente cambió. `test_projects.py` (archivo real; `test_projects_api.py` mencionado en el prompt original no existe en el repo) cubre detalle y listado con hijos en `null`. |
| Retrocompatibilidad general (`organizations`/`projects`) | ✅ Implementado | Suite completa preexistente (1272 tests) sigue en verde dentro de los 1302; `test_org_theme.py`, `test_project_hierarchy_endpoints.py` y el resto de `test_projects.py` corrieron sin modificación de sus aserciones previas. |

### Coherencia (Design)

| Decisión | ¿Seguida? | Notas |
|---|---|---|
| D1 — columnas, no tabla `work_calendar` | ✅ Sí | 2 columnas en `organizations` (NOT NULL+default) + 2 nullable en `projects`. |
| D2 — `working_days` como `postgresql.ARRAY(Integer)` | ✅ Sí | Confirmado en el modelo y en la migración; primera columna `ARRAY` del repo, documentado en el docstring de la migración. |
| D3 — `working_hours_per_day` como `Numeric(4,2)` | ✅ Sí | Confirmado en modelos y migración; serializa como string (`"8.00"`) igual que `TimeLog.hours`, tests envuelven con `float(...)`. |
| D4 — módulo transversal nuevo `work_calendar` | ✅ Sí | No toca `OrganizationRepository`/`ProjectRepository` existentes; consulta las tablas directamente desde su propio repository. |
| D5 — CTE recursivo ascendente (una query) | ✅ Sí | `WorkCalendarRepository.root_override`, acotado por `PROJECT_HIERARCHY_MAX_DEPTH` (mismo guard que `subtree_height`). |
| D6 — `int` plano + validación Pydantic (sin enum `Weekday`) | ✅ Sí | `_normalize_working_days` valida 1-7, sin duplicados, orden ascendente canónico. |
| Reconciliación `CalendarSource` interno → wire `team`/`organization`/`default` | ✅ Sí | `field_serializer` en `ResolvedCalendar` + `_WIRE_SOURCE`; enum interno de `design.md` sin cambios; test dedicado en verde. |
| `CalendarSource` como `enum.StrEnum` puro (no `(str, Enum)`) | ⚠️ Desviación menor de `design.md` (que mostraba `(str, Enum)`) | Documentada explícitamente en el docstring del schema y en `apply-progress`, siguiendo el precedente ya existente `DeliveryPolicy` (`app/notify/ports.py`) para evitar el ruff `UP042`. No afecta el contrato de wire (ambas formas serializan igual vía `field_serializer`). No bloqueante. |

### TDD Compliance

| Check | Resultado | Detalle |
|---|---|---|
| Evidencia TDD reportada | ⚠️ Formato distinto al template | `apply-progress` (Engram, sin archivo en disco) usa el formato narrativo `What/Why/Where/Learned`, no una tabla "TDD Cycle Evidence" con columnas RED/GREEN/TRIANGULATE/SAFETY NET/REFACTOR por tarea. En su lugar, `tasks.md` embebe la etiqueta `[RED]`/`[GREEN]` en el propio ítem de cada tarea (44/44), lo cual sí es verificable. |
| Todas las tareas tienen test | ✅ | 44/44 marcadas `[x]`; cada tarea `[RED]`/`[GREEN]` referencia un archivo/test concreto verificado por lectura directa. |
| RED confirmado (tests existen) | ✅ | Verificado por lectura directa: `test_work_calendar_schemas.py`, `test_work_calendar_resolver.py`, `test_work_calendar_api.py`, `test_migration_work_calendar.py`, adiciones en `test_projects.py` y `test_cross_tenant_isolation.py` — todos existen en el árbol de trabajo. |
| GREEN confirmado (tests pasan) | ✅ | Ejecución real de la suite completa: 1302 passed, 0 failed (reproducido en esta verificación, no solo confiado del reporte de apply). |
| Triangulación adecuada | ✅ | Validación de horas parametrizada (`[0, 25]`), de días parametrizada (`[[], [1,1,2], [0], [8]]`); cascada con 4 casos distintos de resolución (override/organización/global/cross-tenant); permisos con loop sobre 3 roles no-admin y 2 roles no-manager. |
| Safety net en archivos modificados | ✅ | `organizations/models.py`, `projects/{models,schemas}.py`, `main.py` — Fase 1.5/3.16/4.4/5.1 corren la suite dirigida antes de avanzar de fase; confirmado por la suite completa en verde. |

**TDD Compliance**: 5/6 checks en verde estricto; 1 con desviación de formato (no de sustancia) — degradado a WARNING, no CRITICAL, porque la evidencia RED/GREEN/triangulación fue reproducida de forma independiente en esta verificación mediante inspección de archivos y ejecución real de la suite.

---

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---|---|---|
| Unit | 9 | 1 (`test_work_calendar_schemas.py`) | pytest, sin BD (validación Pydantic pura) |
| Integration | 21 | 4 (`test_work_calendar_resolver.py`=4, `test_work_calendar_api.py`=13, `test_migration_work_calendar.py`=2, `test_projects.py`=2) | pytest + Postgres real (`TEST_DATABASE_URL`) + `httpx.AsyncClient` |
| E2E | 0 | 0 | No instalado / no aplica (backend-only, sin navegador) |
| **Total** | **30** | **5** | |

Coincide exactamente con el desglose de `apply_notes` en `state.yaml` (2 migración, 9 schemas, 4 resolver, 13 API, 2 projects).

---

### Changed File Coverage

Coverage analysis skipped — no coverage tool detected (`pytest-cov` no instalado en `.venv`).

---

### Assertion Quality

Auditados los 5 archivos de test nuevos/modificados por este cambio (`test_work_calendar_schemas.py`, `test_work_calendar_resolver.py`, `test_work_calendar_api.py`, `test_migration_work_calendar.py`, adiciones a `test_projects.py`):

- Sin tautologías (`expect(true)`, `assert True`, etc.) — 0 coincidencias.
- Sin loops fantasma sobre colecciones potencialmente vacías — 0 coincidencias.
- Sin tests mock-heavy — 0 usos de `Mock`/`MagicMock`/`monkeypatch` en estos archivos (los dobles de prueba en el resolver son clases stub explícitas, no mocks genéricos, y van acompañadas de aserciones de valor).
- Todas las aserciones verifican valores concretos y variados (horas 6/8/10, días `[6,7]`/`[1..5]`/`[1..7]`, códigos 200/403/422/404, `source` en sus 3 variantes, `null` explícito) — sin aserciones huérfanas de tipo-solo.

**Assertion quality**: ✅ Sin hallazgos — todas las aserciones verifican comportamiento real.

---

### Quality Metrics

**Linter (`ruff check`)**: ✅ Sin errores en los archivos de producción/test que este cambio crea o modifica (`All checks passed!`, exit 0). Hallazgo aparte: 1 `E501` preexistente en `test_cross_tenant_isolation.py:128`, fuera del diff de este cambio — no introducido aquí.

**Type Checker (`mypy`)**: ⚠️ `mypy app/modules/work_calendar/` reporta 2 errores, ambos en `app/modules/organizations/repository.py:90,103` (`Incompatible return value type` en `Sequence[Row[...]]`) — archivo NO tocado por este cambio (`git diff preview...feat/calendario-laboral -- backend/app/modules/organizations/repository.py` está vacío). Preexistente, importado transitivamente por el resolver. Cero errores de mypy en los archivos que este cambio sí crea/modifica.

### Hallazgos

**CRITICAL**: Ninguno.

**WARNING**:
1. `apply-progress` no incluye la tabla "TDD Cycle Evidence" con columnas RED/GREEN/TRIANGULATE/SAFETY NET/REFACTOR que exige el template estricto — usa el formato narrativo `What/Why/Where/Learned`. La sustancia (RED existente, GREEN reproducido, triangulación, safety net) se verificó de forma independiente en esta fase mediante inspección directa de archivos y ejecución real de la suite completa, por lo que no se eleva a CRITICAL.
2. `mypy` reporta 2 errores preexistentes en `app/modules/organizations/repository.py` (no tocado por este cambio) al analizar `app/modules/work_calendar/` por import transitivo. No bloqueante para este cambio; recomendable abrir un ítem de deuda técnica aparte.

**SUGGESTION**:
1. Instalar `pytest-cov` en el entorno de backend para poder reportar cobertura por archivo en futuras verificaciones estrictas (actualmente se omite por completo).
2. `CalendarSource` se implementó como `enum.StrEnum` puro en vez del `(str, Enum)` mostrado literalmente en `design.md` — documentado y justificado (precedente `DeliveryPolicy`), pero vale la pena reflejar esta decisión de vuelta en `design.md` si el cambio se reabre, para que el documento de diseño no quede desactualizado respecto al código final.

### Veredicto

**PASS WITH WARNINGS** — 1302/1302 tests en verde (suite completa reproducida en vivo), 44/44 tareas completas, 18/18 escenarios de spec compilan a test real y pasan, todas las reglas de permisos/solo-raíz/cascada/aislamiento confirmadas por lectura de código + ejecución de test. Los 2 WARNING son de forma/documentación (formato del reporte TDD, deuda de tipos preexistente fuera de este cambio) y no bloquean el archivado.
