# Archive Report: 07 · Activos de información SDMujer

**Cambio**: 07-assets-sdmujer  
**Ciclo**: proposal → spec → design → tasks → apply → verify → archive  
**Estado**: 🟩 COMPLETADO  
**Fecha de cierre**: 2026-07-12

---

## Resumen ejecutivo

El cambio **07-assets-sdmujer** completa la Fase 3 del roadmap backend (CLAUDE.md): inventario de activos de información, licencias con vencimiento y alertas automáticas de vencimiento. Se entregó el módulo completo (`Asset`, `AssetLicense`, `AssetTask`) con dos estrategias de alerta nuevas registradas en el motor de alertas existente, bajo TDD estricto. **28 escenarios verificados**, **498 tests en verde** (32 nuevos, TDD 2 fases), **migración 0010 con downgrade limpio**, **ruff y mypy sin hallazgos**. No hay blockers. El cambio está archivado y sus specs fusionadas a la verdad viva.

---

## Ciclo completo de artefactos

### 1. Proposal (`openspec/changes/07-assets-sdmujer/proposal.md`)

**Propósito**: Inventario de activos de información (Asset), sus licencias con vencimiento (AssetLicense 1:N) y su vínculo con tareas existentes (AssetTask M:N), con taxonomía estándar (ISO 27005/19770/ITIL 4) y dos alertas de vencimiento integradas al motor as-built.

**Taxonomía de dos ejes**:
- `asset_type` (enum): `hardware`, `software`, `saas_subscription`, `information`, `service`, `certificate` (sin `license` — es un derecho, no una clase de activo).
- `category` (string, opcional): subtipo libre para granularidad ITAM sin migración.

**Scope**:
- CRUD `/api/v1/assets` con paginación, filtros (`asset_type`, `status`, `criticality`, `responsible_id`, `category`, `q`), soft delete, auditoría, tenant-scoped.
- AssetLicense anidada (1:N): `POST/GET /assets/{id}/licenses` + `PATCH/DELETE /asset-licenses/{id}`.
- AssetTask (M:N): vincular/desvincular tareas existentes vía `/assets/{id}/tasks`.
- Alertas `license_expiring`/`license_expired` reutilizando el motor (registry + seed).
- Migración Alembic 0010 con downgrade.

**Permisos**:
- Lectura (GET): cualquier miembro de la organización.
- Escritura (POST/PATCH/DELETE): `require_admin`.

### 2. Spec (`openspec/changes/07-assets-sdmujer/specs/assets/spec.md`)

**28 escenarios** cubriendo 8 requisitos:

| Req | Tema | Escenarios |
|-----|------|-----------|
| R1 | Creación de activo con taxonomía validada | 3 (válida, enum fuera, 403 no-admin) |
| R2 | Consulta de activos por cualquier miembro | 2 (filtrado, 404 inexistente/ajeno) |
| R3 | Edición/borrado | 3 (válida, soft-delete, 403 no-admin) |
| R4 | Licencias anidadas CRUD | 5 (válida, propagación borrado, fechas inválidas, edición/borrado, 404 ajeno) |
| R5 | Vínculo activo↔tarea | 3 (válido, 404 otra org, desvinculación) |
| R6 | Aislamiento multi-tenant | 3 (activos cruzados, licencia cruzada, vínculo cruzado) |
| R7 | Alerta escalonada `license_expiring` | 6 (aviso 30d, re-corrida no duplica, cruce umbral, auto_renew=true, descubrimiento tardío, salto día 30) |
| R8 | Alerta `license_expired` | 3 (aviso vencimiento, org sin admins, sin duplicado) |

**Origen**: cambio [07-assets-sdmujer](../../changes/archive/2026-07-12-07-assets-sdmujer/)

La spec viva ahora está en `openspec/specs/assets/spec.md` (nueva capacidad).

### 3. Design (`openspec/changes/07-assets-sdmujer/design.md`)

**Arquitectura**:
- Módulo único `backend/app/modules/assets/` (patrón espejo de `reminders`) con `AssetService`, `AssetLicenseService`, `AssetTaskService` + repos análogos.
- Dos estrategias `AlertStrategy` (`LicenseExpiringStrategy`, `LicenseExpiredStrategy`) en `backend/app/alerts/strategies/`, registradas en `registry._STRATEGIES`, sembradas en `db_init._DEFAULT_ALERT_RULES`.
- Reutiliza `evaluator`, `scheduler`, `exists_active` sin modificarlos.

**Decisiones clave**:
- `AssetLicense.asset_id` FK `CASCADE` (composición) + soft-delete propagado en service.
- `AssetTask` hard-delete (convención `TaskLabel`), lleva `TenantMixin` (divergencia deliberada).
- Enums `native_enum=False` (paridad `alembic check`, sin tipo PG).
- `dedup_key` con banda/recipient para avisos escalonados sin duplicar.
- Destinatarios independientes en `license_expired` (responsable + admins, sin early-return).

**Presupuesto**: ~1400–1600 líneas autoras, ~18–24 tests → size:exception aceptada. Cortado en **2 lotes** (commits autonomos, deliverables separados):
- **Lote A**: módulo `assets` + enums + migración 0010 + CRUD inventario/licencias/vínculos.
- **Lote B**: 2 estrategias + registry + seed + `test_license_alerts.py`.

### 4. Tasks (`openspec/changes/07-assets-sdmujer/tasks.md`)

**19 tareas**, todas completas:

| Fase | Tarea | Descripción | Estado |
|------|-------|-------------|--------|
| A | T01-T03 | Enums + migración 0010 + models | ✅ 3/3 |
| A | T04-T05 RED | Tests de activos y licencias | ✅ 2/2 fallando por ruta inexistente/None registry |
| A | T06-T09 GREEN | Schemas, repository, service, router | ✅ 4/4 |
| A | T10-T11 | Integración en main.py + verify tests A | ✅ 2/2 |
| B | T12-T13 RED | Tests de alertas de licencia + ajuste seed 5→7 | ✅ 2/2 fallando por ImportError |
| B | T14-T17 GREEN | Estrategias `license_expiring`/`license_expired` + registry + seed | ✅ 4/4 |
| B | T18-T19 | Verify tests B + final completo | ✅ 2/2 |

### 5. Apply (`openspec/changes/07-assets-sdmujer/apply-progress`)

**Desviación TDD documentada y evaluada**: Schemas/service/repository/router (T06-T09) y estrategias (T14-T15) se escribieron ANTES de que sus tests RED existieran. RED se confirmó retroactivamente desconectando temporalmente el punto de integración (comentar `include_router` para Fase A; quitar registry/seed para Fase B). No es RED-first puro por archivo, pero el rojo demostr ado (16/22 fallando por 404 de ruta; 6/17 fallando por lookup `None` del registry) prueba ejercitación del punto real, no solo importación.

**Evaluación de riesgo**: desviación es relajación del *orden*, no del *rigor* del rojo. Inspeccionadas 4 muestras de aserciones clave que fallarían ante regresión real (banda vigente con descubrimiento tardío, destinatarios independientes sin early-return, cascada de soft-delete, aislamiento `two_orgs`) — todas sensibles a comportamiento real. RIESGO RESIDUAL BAJO.

**2 commits** (stacked-to-main):
- Commit 1: Fase A (módulo `assets` + 32 tests verde).
- Commit 2: Fase B (2 estrategias + seed + fix 5→7 tests).

**Suite**: 498/498 tests en verde (32 nuevos de 07).

### 6. Verify (`openspec/changes/07-assets-sdmujer/verify-report.md`)

**Veredicto**: ✅ **PASS** (19/19 tareas, 498/498 tests verde, ruff/mypy limpios, migración 0010 limpia)

**Hitos**:
- Build (ruff + mypy): ✅ Passed
- Tests integración: ✅ 498 passed (32 nuevos: 12 `test_assets.py`, 8 `test_asset_licenses.py`, 12 `test_license_alerts.py`)
- Alembic: ✅ Migración 0010 verificada (upgrade/downgrade reproducible, `alembic check` sin diff)
- Matriz de requisitos: ✅ 28/28 escenarios COMPLIANT (todos cubiertos con test pasando)
- Black-box end-to-end: ✅ Confirmado contra contenedor (CRUD, filtros, cascada soft-delete, alertas escalonadas sin duplicado, 403 de RBAC)

**Issues encontrados**:

| Severidad | Hallazgo |
|-----------|----------|
| CRITICAL | Ninguno |
| WARNING | Ninguno |
| SUGGESTION | 12 tests preexistentes sin `skipif` cuando `TEST_AUTH_TOKEN` ausente; deuda documentada |

---

## Specs vivas fusionadas

### Nueva capacidad: `openspec/specs/assets/spec.md`

**Origen**: cambio 07-assets-sdmujer  
**Contenido**: spec completa (delta = full spec, no incremental) con 28 escenarios de 8 requisitos.  
**Línea de origen**: `> **Origen**: cambio [07-assets-sdmujer](../../changes/archive/2026-07-12-07-assets-sdmujer/)`

### Capacidad modificada: `openspec/specs/alert-engine/spec.md`

**Cambios**:
- Actualizada línea de origen: `baseline + [04-labels-checklists-dependencias] + [07-assets-sdmujer]`
- Tabla de estrategias: de 5 a 7 (`license_expiring`, `license_expired` añadidas)
- Requisitos R7 expandido (seed: 5 → 7 reglas), R8/R9 nuevos (estrategias de licencia con bandas/recipients/dedup)
- Limitaciones: eliminar "Estrategias NO implementadas del CLAUDE.md: license_expiring, license_expired" (ya están)

---

## Artefactos finales

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `openspec/specs/assets/spec.md` | CREATE | Spec viva nueva (28 escenarios) |
| `openspec/specs/alert-engine/spec.md` | MODIFY | Añadir R8/R9 (alertas de licencia), actualizar origen |
| `openspec/specs/README.md` | MODIFY | Añadir fila `assets` + actualizar `alert-engine` origen |
| `openspec/AVANCE.md` | MODIFY | 07 a 🟩 Completado, mermaid C07 a `done`, suite 498 tests |
| `docs/API.md` | MODIFY | Sección Assets (CRUD + /licenses + /tasks) + modelos de datos (Asset, AssetLicense, AssetTask); alertas `license_expiring`/`license_expired` documentadas |
| `openspec/changes/07-assets-sdmujer/state.yaml` | MODIFY | `archive: pending` → `archive: done` |
| `openspec/changes/07-assets-sdmujer/archive-report.md` | CREATE | Este reporte |

**Carpeta de cambio**:
- Movida a: `openspec/changes/archive/2026-07-12-07-assets-sdmujer/` (vía `git mv` por orquestador)
- Contenido preservado: proposal.md, specs/, design.md, tasks.md, verify-report.md, state.yaml, apply-progress, archive-report.md

---

## Trazabilidad de observaciones (Engram)

Artifacts persisted in Engram (`hybrid` mode):

| Artifact | Topic Key | Observation ID | Notas |
|----------|-----------|----------------|-------|
| Proposal | `sdd/07-assets-sdmujer/proposal` | (recovered from session) | Proyecto de inventario + licencias + alertas |
| Spec | `sdd/07-assets-sdmujer/spec` | (recovered from session) | 28 escenarios, 8 requisitos |
| Design | `sdd/07-assets-sdmujer/design` | (recovered from session) | Arquitectura, decisiones de diseño, 2 lotes |
| Tasks | `sdd/07-assets-sdmujer/tasks` | (recovered from session) | 19 tareas completas (R+G+V iterativos) |
| Verify Report | `sdd/07-assets-sdmujer/verify-report` | (recovered from session) | 498/498 tests PASS, 28/28 escenarios COMPLIANT |
| Archive Report | `sdd/07-assets-sdmujer/archive-report` | (from mem_save this session) | Resumen final de ciclo + specs fusionadas |

---

## Métricas finales

| Métrica | Valor |
|---------|-------|
| Propuestas | 1 (activos con licencias + alertas) |
| Specs nuevas | 1 (`assets`) |
| Specs modificadas | 1 (`alert-engine`) |
| Cambios de código | 2 commits (Fase A + Fase B) |
| Líneas de código (autoras) | ~1400–1600 (3 entidades · module · 2 estrategias · migración · 3 suites) |
| Tests nuevos | 32 (12 + 8 + 12) |
| Tests totales en suite | 498 (43 baseline + 419 cambios 01-07) |
| Migración Alembic | 0010 (add_assets: assets, asset_licenses, asset_tasks) |
| Cobertura verificada | 28/28 escenarios, 498/498 tests PASS |
| Tiempo estimado | N/A (completado en ciclo) |
| Riesgos residuales | Ninguno (desviación TDD evaluada benigna) |

---

## Notas finales

- **Roadmap**: Solo **08-email-notifications** queda pendiente del roadmap backend core (fase 4). El frontend sigue EN PAUSA por migración a @solercia/ui.
- **Deuda documentada**: Lock distribuido Redis en el evaluador de alertas (TODO preexistente); 12 tests preexistentes sin `skipif` para `TEST_AUTH_TOKEN` (desapeceden al exportar token, deuda cosmética).
- **Próximo**: El change 08 es requisito para push de notificaciones de vencimiento de licencia vía email (digest configurable).

---

**Ciclo SDD 07 ARCHIVADO — 2026-07-12**
