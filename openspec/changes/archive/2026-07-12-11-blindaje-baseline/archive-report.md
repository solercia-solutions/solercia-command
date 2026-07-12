# Archive Report: 11 · Blindaje de la línea base

**Cambio**: 11-blindaje-baseline  
**Fechas**: Proposal 2026-07-05 → Archive 2026-07-12  
**Modo**: hybrid (filesystem + Engram)  
**Veredicto final**: ✅ **ARCHIVED** — ciclo SDD completo, todos los artefactos fusionados

---

## Resumen ejecutivo

El cambio 11 compreta la línea base de pruebas de la gestion_proyectos: backfill de TDD estricto en 10 capacidades críticas (auth, users-admin, rbac-catalog, multi-tenancy, projects, tasks, methodology-strategies, alert-engine, notifications-inapp, dashboard-executive), matriz de permisos transversal por endpoint y aislamiento multi-tenant verificado con fixture de dos organizaciones. El bugfix `40631fa` (usuarios soft-borrados en listado) fue destapado por el test RED, corregido mínimo, y confirmado horneado en black-box con contenedor reconstruido. Suite final: **382 tests** (258 base + 106 apply + 18 judgment-day), 0 CRITICAL, 0 WARNING, 1 SUGGESTION (no bloqueante). Archivado con deuda documentada.

---

## Completitud de ciclo SDD

| Fase | Artefacto | Estado | Detalles |
|------|-----------|--------|----------|
| **Proposal** | `proposal.md` | ✅ Done | Intent, scope, approach, risks, rollback |
| **Spec** | `specs/test-coverage-baseline/spec.md` | ✅ Done | Delta spec (nueva capacidad): 4 requisitos, 8 escenarios, contrato de cobertura as-built |
| **Design** | `design.md` | ✅ Done | TDD estricto, fixtures de dos orgs, matriz parametrizada, decisiones de arquitectura 1–7, data flow |
| **Tasks** | `tasks.md` | ✅ Done (31/31) | Lotes A–E, 31 tareas completas (checkbox `[x]`), commits reales (`66a7198` → `8d311aa`) |
| **Apply** | 5 commits + 1 bugfix | ✅ Done | Lotes A–E: 106 tests nuevos inyectados; `40631fa` bugfix (`fix(users-admin): excluir usuarios inactivos`); judgment-day: `8d311aa` (C1+C2+W1+W2+W3 resueltos, +18 tests) |
| **Verify** | `verify-report.md` | ✅ PASS | 382/382 tests verdes, ruff/mypy limpios, contrato delta spec verificado por muestreo, black-box en contenedor reconstruido |
| **Archive** | `archive-report.md` (este archivo) | ✅ Done | Fusión de delta spec, actualización de trazabilidad, cierre documentado |

---

## Trazabilidad de tareas (31/31)

### Lote A — conftest + multi-tenancy + auth

| Tarea | Commit | Tests nuevos | Resultado |
|-------|--------|--------------|-----------|
| T01–T07 (conftest fixtures + multi-tenancy + auth) | `66a7198` | ~18 | ✅ Verde |

### Lote B — rbac-catalog + usuarios-admin + matriz

| Tarea | Commit | Tests nuevos | Resultado |
|-------|--------|--------------|-----------|
| T08–T14 (rbac-catalog, users-admin, matriz permisos) | `91dfe2f` + `40631fa` (bugfix) | ~30 | ✅ Verde (incluye corrección bug soft-delete) |

### Lote C — alert-engine

| Tarea | Commit | Tests nuevos | Resultado |
|-------|--------|--------------|-----------|
| T15–T19 (4 estrategias, evaluador, dedup, scheduler) | `51d76e4` | ~14 | ✅ Verde |

### Lote D — methodology-strategies + projects + tasks

| Tarea | Commit | Tests nuevos | Resultado |
|-------|--------|--------------|-----------|
| T20–T26 (methodology, projects, tasks CRUD) | `9431149` | ~24 | ✅ Verde |

### Lote E — notifications-inapp + dashboard-executive

| Tarea | Commit | Tests nuevos | Resultado |
|-------|--------|--------------|-----------|
| T27–T31 (notifications, dashboard, checkpoint final) | `bb75d0e` | ~20 | ✅ Verde, 258→364 tests (antes correcciones JD) |

### Correcciones Judgment-Day

| Tipo | Commits | Tests adicionales | Resultado |
|------|---------|-------------------|-----------|
| Review 4R (CRITICAL×2 resueltos) | `8d311aa` | +18 | ✅ Verde, suite final 382/382 |

**Total tareas**: 31/31 completadas · **Total commits de contenido**: 6 (5 lotes + 1 bugfix aislado) · **Total tests**: 258 + 106 (apply) + 18 (JD) = **382**

---

## Verificación de cobertura

### Requisito 1 — Cobertura por capacidad derivada de escenarios as-built

Todas las 10 capacidades objetivo tienen suites verdes:

| Capacidad | Suite | Escenarios cubiertos | Tests |
|-----------|-------|----------------------|-------|
| auth | `test_auth.py` | R1–R5 (login, refresh, logout, me, menus) | 8 |
| users-admin | `test_users_admin.py` | R1–R4 (CRUD, roles, soft-delete) | 8 |
| rbac-catalog | `test_rbac_catalog.py` | R1–R4 (roles, menus, grants, borrado) | 12 |
| multi-tenancy | `test_multi_tenancy.py` | R1–R4 (row-level, resolución, MemberRole, seed) | 10 |
| projects | `test_projects.py` | R1, R3, R4 (scrum, velocity, aislamiento) | 6 |
| tasks | `test_tasks_crud.py` | R2, R3, R4 (status válido, progreso, filtros) | 8 |
| methodology-strategies | `test_methodology_strategies.py` | R1–R4 (4 estrategias, 422) | 10 |
| alert-engine | `test_alert_engine.py` | R1–R4 (4 estrategias, evaluador, dedup, scheduler) | 14 |
| notifications-inapp | `test_notifications_inapp.py` | R1–R4 (listado, dedup, unread-count, status) | 6 |
| dashboard-executive | `test_dashboard_executive.py` | R1–R4 + work_gap (by_assignee, at_risk, workload, performance) | 6 |

**Matriz de permisos**: `test_permissions_matrix.py` (parametrizado, 15+ tests)  
**Aislamiento multi-tenant**: fixture `two_orgs` utilizado en 8 suites tenant-scoped

**Veredicto**: Requisito 1 ✅ Cumplido — 4/4 requisitos del spec verificados por muestreo directo

### Requisito 2 — Matriz de permisos (comportamiento vigente)

✅ Verificado:
- `require_admin` (RBAC ADMIN) en rbac-catalog, users-admin, alert-rules, evaluate → `rbac_admin` 2xx, member/manager 403
- Dueño estricto en time-logs PATCH/DELETE
- `MemberRole` admin|manager en GET /users/{id}/time-logs
- CRUD projects/tasks sin gate de rol → 4 MemberRole 2xx

### Requisito 3 — Aislamiento multi-tenant

✅ Verificado:
- Listado no cruza orgs (tasks, projects, users-admin, alerts, notifications)
- Acceso directo a recurso ajeno → 404 (reforzado en judgment-day con 4 escenarios adicionales)

### Requisito 4 — Cobertura alert-engine (4 estrategias + motor)

✅ Verificado:
- `task_overdue`, `task_at_risk`, `sprint_at_risk`, `workload_imbalance` (cada una con test)
- `blocked_task` explícitamente excluida (ya cubierta por cambio 04)
- Dedup idempotente confirmado (2ª corrida → 0 nuevas notificaciones)
- Scheduler registro + parada sin timing real

---

## Artefactos archivados

| Artefacto | Ruta de destino | Contenido |
|-----------|-----------------|----------|
| Proposal | `openspec/changes/archive/2026-07-12-11-blindaje-baseline/proposal.md` | Intent, scope, approach, risks, rollback |
| Spec (delta) | `openspec/specs/test-coverage-baseline/spec.md` (FUSIONADA a viva) | 4 requisitos, 8 escenarios |
| Design | `openspec/changes/archive/2026-07-12-11-blindaje-baseline/design.md` | TDD estricto, fixtures, matriz, 7 decisiones |
| Tasks | `openspec/changes/archive/2026-07-12-11-blindaje-baseline/tasks.md` | 31/31 tareas, lotes A–E, checkpoint final |
| Verify Report | `openspec/changes/archive/2026-07-12-11-blindaje-baseline/verify-report.md` | PASS, 382 tests, 0 CRITICAL, 1 SUGGESTION |
| State | `openspec/changes/archive/2026-07-12-11-blindaje-baseline/state.yaml` | `verify: done`, `archive: done` |

---

## Fusión de delta spec

**Acción**: La delta spec `openspec/changes/11-blindaje-baseline/specs/test-coverage-baseline/spec.md` es una **nueva capacidad** (no una modificación de una existente). Se copió directamente a:

```
openspec/specs/test-coverage-baseline/spec.md
```

Con línea de trazabilidad agregada:
```
> **Origen**: cambio 11-blindaje-baseline
```

**Actualización de trazabilidad**: `openspec/specs/README.md` actualizado con:
- Entrada en tabla de capacidades (fila `test-coverage-baseline | [link] | 11-blindaje-baseline`)
- Entrada en detalle del mapeo (cambio 11 → `test-coverage-baseline.md` nueva)
- Sección de cambios en curso: cambio 11 **removido** (ya archivado)

---

## Actualización de progreso

### openspec/AVANCE.md cambios:

1. **Línea de "Última actualización"**: 2026-07-12 con descripción del cierre de cambio 11
2. **Mapa visual (mermaid)**:
   - Nodo C11 agregado: `"11 · Blindaje baseline<br/>backfill TDD + permisos + aislamiento"`
   - Conexión: `C01 --> C11` (depende de 01-fundacion-tdd)
   - Clasificación: `class C11 done` (🟩)
3. **Tabla del roadmap**: Fila 11 insertada con specs `test-coverage-baseline` (nueva)
4. **Estadística de tests**: De 258 a **382** (258 + 106 apply + 18 judgment-day)
5. **Sección "Aún pendiente"**: Deuda documentada ahora registra:
   - Bug pre-existente `get_in_org` sin filtro `is_active` (corregido en 40631fa)
   - Tie-break de `created_at` en `get_current_membership` (comportamiento correcto, no documentado)
   - Viewer sin gate de rol (comportamiento vigente documentado, fuera de alcance)
   - mypy excluye tests (decisión preexistente, reevaluar en cambios futuros)

---

## Bugfix documentado

**Descripción**: Durante T10 RED, el test destapó un defecto real: `UserRepository.list_by_org` no filtraba `is_active=True`, devolviendo usuarios soft-borrados.

**Corrección**: Commit `40631fa` (`fix(users-admin): excluir usuarios inactivos del listado /admin/users`)
- Cambio mínimo: `query.filter(User.is_active == True)` agregado
- Rollback: revertir el commit elimina el filtro
- Delta spec: **No requiere** (cambio de comportamiento es transparente al contrato; usuarios inactivos siempre fueron borrados lógicamente, solo no estaban filtrados en el listado)
- Verificación black-box: confirmado horneado en imagen reconstruida (usuario soft-borrado desaparece del listado tras DELETE)

---

## Riesgos y deuda

### CRITICAL
✅ Ninguno — 0 CRITICAL en verify-report

### WARNING
✅ Ninguno — 0 WARNING en verify-report

### SUGGESTION
⚠️ S1 (no bloqueante): `pyproject.toml` (`[tool.mypy] files = ["app"]`) excluye `backend/tests/`. Con el crecimiento de ~150 tests nuevos tipados con dataclasses en cambio 11, futuro trabajo podría tipar `tests/` también.

### Deuda registrada (pre-existente, documentada, no blockeante)
- **get_in_org sin filtro is_active**: pre-SDD, corregida en commit `40631fa` del cambio 11
- **Tie-break created_at en get_current_membership**: comportamiento determinista correcto, razón no documentada en código
- **Viewer sin gate de rol**: acceso permitido a todos los miembros, comportamiento documentado en matriz de permisos; enderezamiento pendiente (roadmap)
- **mypy config**: excluye tests por diseño, reevaluar tras crecimiento de suites tipadas

---

## Trazabilidad de observaciones Engram

**Topic keys de artefactos SDD archivados** (para búsqueda y auditoría):
- `sdd/11-blindaje-baseline/proposal` → Engram observation ID: [recuperar con mem_search]
- `sdd/11-blindaje-baseline/spec` → Engram observation ID: [recuperar con mem_search]
- `sdd/11-blindaje-baseline/design` → Engram observation ID: [recuperar con mem_search]
- `sdd/11-blindaje-baseline/tasks` → Engram observation ID: [recuperar con mem_search]
- `sdd/11-blindaje-baseline/verify-report` → Engram observation ID: [recuperar con mem_search]
- `sdd/11-blindaje-baseline/archive-report` → Este archivo (topic_key de este mem_save)

**Pasos de recuperación**: En futuras sesiones, `mem_search("sdd/11-blindaje-baseline", project: "gestion_proyectos")` devuelve todos los artefactos. Para contenido completo, usar `mem_get_observation(id)`.

---

## Confirmación de cierre

✅ **Tareas**: 31/31 checkbox `[x]` — sin stale unchecked  
✅ **Tests**: 382/382 PASS in-process, 0 fallos, ruff/mypy limpios  
✅ **Black-box**: Login real + 3 smoke endpoints en contenedor reconstruido  
✅ **Bugfix**: Confirmado horneado (soft-delete efectivo tras rebuild)  
✅ **Specs fusionadas**: `test-coverage-baseline` integrada en viva, trazabilidad actualizada  
✅ **Trazabilidad**: Cambio 11 en `openspec/specs/README.md` y `openspec/AVANCE.md`  
✅ **State.yaml**: `archive: pending` → `archive: done`, `verify: pending` → `verify: done`  

---

## Conclusión

El cambio 11-blindaje-baseline es un ciclo SDD completo y exitoso. La línea base de la gestion_proyectos queda blindada con:
- **10 capacidades críticas** con cobertura TDD estricto
- **Matriz de permisos** documentada y verificada por endpoint
- **Aislamiento multi-tenant** probado con fixture de dos orgs
- **Bugfix real** (soft-delete) destapado, corregido y confirmado horneado
- **Suite de 382 tests** totalmente verde

El cambio está archivado, su delta spec fusionada a las specs vivas, y la trazabilidad completamente actualizada para futuros cambios SDD (06-10).

**Próximo paso recomendado**: Cambio 06-reminders, según el roadmap de AVANCE.md
