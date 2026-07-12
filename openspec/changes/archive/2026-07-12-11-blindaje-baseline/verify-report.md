# Verify Report: 11 · Blindaje de la línea base (backfill de tests as-built con TDD)

**Fecha**: 2026-07-12
**Modo de persistencia**: hybrid (archivo + Engram)
**Veredicto final**: **PASS**

## 1. Resumen ejecutivo

31/31 tareas completas, suite in-process en 382 tests verdes (0 fallos), ruff y mypy limpios, contrato de la delta spec `test-coverage-baseline` cubierto por muestreo, y validación black-box contra la imagen reconstruida del backend confirma que el bugfix de producción (commit `40631fa`) quedó horneado. 0 CRITICAL, 0 WARNING, 1 SUGGESTION.

## 2. Completitud de tareas (tasks.md)

| Métrica | Resultado |
|---|---|
| Checkboxes `- [x]` | 31 |
| Checkboxes `- [ ]` sin marcar | 0 |
| Lotes (A–E) commiteados | 5/5 (`66a7198`, `91dfe2f`, `51d76e4`, `9431149`, `bb75d0e`) |
| Bugfix aislado con rollback propio | `40631fa` (`fix(users-admin): excluir usuarios inactivos del listado /admin/users`) |
| Correcciones judgment-day + 4R | `8d311aa` (C1, C2, W1, W2, W3 — confirmadas aplicadas) |
| Checkpoint final (T31) | `cd backend && pytest tests/ -v` reportado verde en apply-progress; re-ejecutado en esta verificación |

Todas las tareas están marcadas y corresponden a commits reales en el log de git (`git log --oneline`: `66a7198` → `8d311aa`). No hay desviación entre tasks.md y el estado del código.

## 3. Suite in-process completa

**Comando**: `cd backend && source <scratchpad>/test_env.sh && .venv/bin/pytest tests/ -q`

```
382 passed, 1 warning in 98.03s (0:01:38)
```

- 0 fallos, 0 errores, 0 skips.
- El único warning es un `SAWarning` preexistente de Alembic sobre ciclos de FK no resolubles al ordenar tablas (`dependencies`, `organizations`, `users`) — no relacionado con el cambio 11, no bloqueante.
- Cifra coincide exactamente con lo esperado: 258 (línea base 01-05) + 106 (apply de los 5 lotes) + 18 (correcciones/tests añadidos en judgment-day) = 382.

## 4. Análisis estático

| Herramienta | Comando | Resultado |
|---|---|---|
| ruff | `.venv/bin/ruff check .` | `All checks passed!` |
| mypy | `.venv/bin/mypy` (config canónica `[tool.mypy] files = ["app"]`) | `Success: no issues found in 145 source files` |

Nota: `mypy` con la configuración canónica del proyecto **no** cubre `backend/tests/` (por diseño, confirmado en apply-progress con `git stash`). Los tipos `object` de `OrgData`/`TwoOrgs` en `conftest.py` no generan error porque `tests/` está fuera de `files = ["app"]`. Esto es una decisión de configuración preexistente al cambio 11, no una brecha introducida por él.

## 5. Contrato contra la delta spec `test-coverage-baseline/spec.md`

4 requisitos, 8 escenarios. Verificación por muestreo (Grep + lectura de los archivos referenciados):

### Requisito 1 — Cobertura por capacidad derivada de los escenarios as-built

Las 11 suites del design existen y colectan tests: `test_auth.py`, `test_users_admin.py`, `test_rbac_catalog.py`, `test_multi_tenancy.py`, `test_projects.py`, `test_tasks_crud.py`, `test_methodology_strategies.py`, `test_alert_engine.py`, `test_notifications_inapp.py`, `test_dashboard_executive.py`, `test_permissions_matrix.py`. 382 tests colectados sin errores de colección (`382 tests collected in 0.36s`). Cumple ambos escenarios (suite verde derivada del spec; convención de rojo documentada en tasks.md y en apply-progress).

### Requisito 2 — Matriz de permisos por endpoint

`test_permissions_matrix.py` confirma vía Grep:
- `test_require_admin_family_rejects_member_and_manager_without_rbac` + `test_require_admin_family_accepts_rbac_admin` → familia `require_admin` (rbac-catalog, users-admin, `PATCH /alert-rules/{id}`, `POST /alerts/evaluate`).
- `test_time_logs_visibility_of_another_user_by_role` parametrizado `[(member,403),(viewer,403),(admin,200),(manager,200)]` → gate inline de `TimeLogService._require_visibility`.
- `test_time_log_edit_delete_forbidden_to_non_owner_regardless_of_role` → dueño estricto.
- `test_projects_and_tasks_crud_has_no_role_gate` y `test_methodology_read_has_no_role_gate` parametrizados con los 4 `MemberRole` → 2xx para todos, documentando el comportamiento vigente sin gate de rol.

Cumple ambos escenarios (admin-only rechaza no-ADMIN; endpoint sin gate acepta cualquier miembro).

### Requisito 3 — Aislamiento entre tenants con fixture de dos organizaciones

`two_orgs` se usa en 8 suites tenant-scoped: `test_alert_engine.py`, `test_dashboard_executive.py`, `test_multi_tenancy.py`, `test_notifications_inapp.py`, `test_projects.py`, `test_rbac_catalog.py`, `test_tasks_crud.py`, `test_users_admin.py`. Las suites excluidas correctamente (`test_auth.py` — no es un listado tenant-scoped; `test_methodology_strategies.py` — unit puro sin BD; `test_permissions_matrix.py` — prueba gates de rol, no aislamiento) coinciden con el diseño.

Acceso directo a recurso ajeno (segundo escenario) fue reforzado en judgment-day: `test_users_admin.py::get_patch_delete_roles_of_other_org_user_returns_404` y 4 equivalentes en `test_rbac_catalog.py`, todos confirmando 404 real (no 200 con dato ajeno). Cumple ambos escenarios.

### Requisito 4 — Cobertura del motor de alertas

`test_alert_engine.py` confirma las 4 estrategias sin `blocked_task`:
- `test_task_overdue_strategy_produces_notification`
- `test_task_at_risk_strategy_produces_notification`
- `test_sprint_at_risk_strategy_produces_notification`
- `test_workload_imbalance_strategy_produces_notification`

`blocked_task` está explícitamente excluida (comentario en el docstring del archivo: "ya cubierta por `test_blocked_task_alert.py` del cambio 04"). Dedup por idempotencia, filtro `enabled`, aislamiento entre orgs, `PATCH /alert-rules/{id}`, `POST /alerts/evaluate` con `require_admin`, y registro/parada del scheduler también están presentes en el archivo (confirmado en apply-progress y por lectura de nombres de test). Cumple ambos escenarios.

**Veredicto de contrato**: 4/4 requisitos y 8/8 escenarios con cobertura de test confirmada por muestreo directo del código (no solo por lo declarado en tasks.md).

## 6. Black-box contra el contenedor reconstruido

**Build**: `docker compose up -d --build backend` — imagen reconstruida desde cero (capas `COPY . .` y `chmod +x docker/entrypoint.sh` re-ejecutadas), contenedor recreado y arrancado (`gestion_proyectos-backend-1 Started`). La imagen es horneada sin volumen montado, por lo que el código corriendo es el de la imagen, no el del filesystem host.

**Login real** (`POST /api/v1/auth/login`, `admin@solercia.com` / `Admin123*` — credenciales del seed en `backend/app/db_init.py`): `HTTP 200`, `access_token` emitido.

| Endpoint | Resultado |
|---|---|
| `GET /api/v1/admin/users` (baseline) | `200`, 4 usuarios activos (`diana`, `carlos`, `admin`, `ana`) |
| `POST /api/v1/admin/users` (usuario de prueba `verify-smoke-11@solercia.com`) | `201` |
| `GET /api/v1/admin/users` (tras crear) | `200`, 5 usuarios, incluye el de prueba |
| `DELETE /api/v1/admin/users/{id}` (soft delete) | `204` |
| `GET /api/v1/admin/users` (tras borrar) | `200`, **4 usuarios**, `smoke_user_present: False` |
| `GET /api/v1/dashboard/executive` | `200`, claves `by_assignee, at_risk, workload, projects_progress, totals, work_gap` presentes |
| `GET /api/v1/alert-rules` | `200`, 5 reglas (`task_overdue`, `task_at_risk`, `sprint_at_risk`, `workload_imbalance`, `blocked_task`) |

**Confirmación explícita del bugfix horneado**: el usuario de prueba soft-borrado desapareció del listado (`meta.total` volvió de 5 a 4, `smoke_user_present: False`), demostrando que `UserRepository.list_by_org` filtra `is_active` en la imagen reconstruida — el commit `40631fa` está efectivamente horneado, no solo presente en el filesystem del host.

No se probó gating de manager por elevación SQL (el seed no trae `manager`); esa cobertura ya está cubierta in-process por `test_permissions_matrix.py` y `test_time_logs.py`, conforme a la instrucción de la tarea.

## 7. Coherencia de state.yaml

Antes de esta verificación:
```yaml
phases:
  ...
  apply: done
  verify: pending
  archive: pending
```

Coherente con el estado real: las 4 fases previas (proposal, spec, design, tasks) están `done`, apply está `done` con evidencia (382 tests, commits reales), y `verify`/`archive` estaban correctamente en `pending`. Se actualiza `verify: done` tras este veredicto PASS.

## 8. Hallazgos

### CRITICAL
Ninguno.

### WARNING
Ninguno. La desviación documentada en T22 (`test_projects.py`: el as-built no expone `PATCH`/`DELETE /projects/{id}`, por lo que el aislamiento R4 se probó solo sobre `GET`) está explícitamente registrada en tasks.md, en el mensaje de commit y en `projects/spec.md` ("Limitaciones y deuda conocida"). No es una brecha de cobertura: la spec de aislamiento habla de "GET/PATCH/DELETE ese recurso por su id" como acciones aplicables cuando existen, y aquí no existen esos verbos en el as-built. No degrada el veredicto.

### SUGGESTION
- **S1**: `pyproject.toml` (`[tool.mypy] files = ["app"]`) excluye `backend/tests/` del chequeo de tipos. Esto es una decisión preexistente al cambio 11 (confirmada con `git stash` en judgment-day), pero como la suite de tests creció ~150 tests en este cambio y usa dataclasses tipadas como `object` (`OrgData`/`TwoOrgs` en `conftest.py`), valdría la pena evaluar en un cambio futuro si conviene tipar `tests/` también — fuera de alcance de este cambio test-only.

## 9. Veredicto final

**PASS**

Evidencia consolidada:
- Suite in-process: 382/382 passed, 0 fallos.
- ruff: limpio. mypy (config canónica): limpio.
- Contrato de la delta spec: 4/4 requisitos, 8/8 escenarios con test confirmado.
- tasks.md: 31/31 completas, coherentes con el log de git.
- Black-box contra imagen reconstruida: login real, smoke de 3 endpoints clave, bugfix `40631fa` confirmado horneado (soft-delete deja de aparecer en el listado tras rebuild sin volumen).
- 0 CRITICAL, 0 WARNING, 1 SUGGESTION (no bloqueante).

`state.yaml`: `verify: pending` → `verify: done`.
