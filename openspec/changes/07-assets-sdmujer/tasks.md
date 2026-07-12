# Tasks: 07 · Activos de información SDMujer (Asset + AssetLicense + AssetTask + alertas de licencia)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1400–1600 (3 entidades · módulo CRUD+licencias+vínculos · 2 estrategias de alerta · migración · 3 suites) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote A (módulo `assets`: enums+modelos+migración 0010+CRUD+licencias+vínculos) → Lote B (2 estrategias de alerta+registry+seed+`test_license_alerts`+fix seed 5→7) |
| Estrategia de entrega | commits directos a main por lotes (sin PR), size:exception aceptada por el usuario |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Serialización**: `sdd-apply` de 07 corre ANTES que 08 (orden confirmado). `down_revision` de la migración = head vigente de Alembic al momento de aplicar (verificado hoy: head = `0009`, así que esta migración es `0010`; si otro cambio avanza el head antes del apply de 07, ajustar `down_revision` al head real).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| A | Migración 0010 + enums + módulo `assets` (Asset/AssetLicense/AssetTask: CRUD, licencias anidadas, vínculos) | 1 — `feat(assets): crud de inventario, licencias y vínculos con tareas` | `cd backend && pytest tests/test_assets.py tests/test_asset_licenses.py -v` | N/A — CRUD puro sin integración externa, cubierto por `httpx AsyncClient` | Revert commit + `alembic downgrade -1` (elimina `asset_tasks`/`asset_licenses`/`assets`); sin efecto en otros módulos |
| B | 2 estrategias `license_expiring`/`license_expired` + registry + seed + fix de seed 5→7 | 2 — `feat(assets): alertas de vencimiento de licencia` | `cd backend && pytest tests/test_license_alerts.py tests/test_blocked_task_alert.py -v` | Invocación directa de `strategy.evaluate`/`evaluate_organization` en tests (patrón `test_blocked_task_alert.py`); smoke manual vía `POST /alerts/evaluate` admin (endpoint ya existente, sin cambios) | Revert commit; quitar las 2 entradas de `_STRATEGIES`/`_DEFAULT_ALERT_RULES` deja al evaluador sin esas reglas; notificaciones de licencia ya emitidas quedan inertes (Rollback Plan del proposal) |

## Fase A — Migración + módulo `assets` (Commit 1)

- [x] T01 [Foundation] `app/shared/enums.py`: `AssetType` (hardware|software|saas_subscription|information|service|certificate), `AssetStatus` (active|inactive|retired|under_review), `AssetCriticality` (critical|high|medium|low — enum dedicado, NO reusar `Priority`), `LicenseType` (perpetual|subscription|trial); todos `SAEnum(..., native_enum=False, length=N)` espejo `ReminderStatus`.
- [x] T02 [Foundation] `backend/alembic/versions/0010_add_assets.py`: tablas `assets`, `asset_licenses` (FK `asset_id` CASCADE), `asset_tasks` (FK `asset_id`/`task_id` CASCADE, `UniqueConstraint(asset_id, task_id)`); `down_revision` = head vigente al aplicar (hoy `0009`); `downgrade` elimina las 3 en orden inverso.
- [x] T03 [Foundation] `app/modules/assets/models.py`: `Asset` (Pk+Timestamp+SoftDelete+Audit+Tenant; `name`, `description?`, `asset_type`, `category? String(80)`, `status`, `criticality`, `responsible_id FK users SET NULL?`, `acquisition_date?`, `location?`, `vendor?`); `AssetLicense` (mismos mixins; `asset_id FK CASCADE`, `license_type`, `license_key?`, `start_date`/`expiration_date Date`, `seats?`, `cost Numeric(12,2)?`, `auto_renew bool=False`); `AssetTask` (Pk+Timestamp+**Tenant** — divergencia deliberada de `TaskLabel`, documentada en docstring; `asset_id`/`task_id` FK CASCADE, `UniqueConstraint`); importados en `app/db_init.py` para que `Base.metadata.create_all` (fixture de tests) reconozca las 3 tablas.
- [x] T04 RED `backend/tests/test_assets.py`: R1 (creación válida por admin, `asset_type="license"`→422, creación rechazada a no-admin→403); R2 (listado paginado con filtros `asset_type/status/criticality/responsible_id/category/q`, 404 en inexistente/ajeno); R3 (edición válida, soft-delete desaparece de `GET /assets`, edición rechazada a no-admin→403); R5 (vínculo válido, tarea de otra organización→404, desvinculación); R6 (aislamiento cross-tenant de activos y vínculos). Escrituras vía fixture `rbac_admin` (NO `two_orgs.role=admin`, que no satisface `require_admin`). Confirmar N tests fallando (404/ruta inexistente) antes de T06-T09.
- [x] T05 RED `backend/tests/test_asset_licenses.py`: R4 (creación válida, fechas inválidas `expiration_date<=start_date`→422, edición/borrado, licencia de activo ajeno→404) + escenario de propagación: licencias inaccesibles (`404`) tras `DELETE /assets/{id}` del activo padre, verificado en `GET .../licenses` y `PATCH/DELETE /asset-licenses/{id}`; R6 (licencia cross-tenant). Confirmar fallando.
- [x] T06 GREEN `app/modules/assets/schemas.py`: `AssetCreate/Update/Response`, `AssetLicenseCreate/Update/Response` (valida `expiration_date > start_date`), `AssetTaskLink/Response`. [R1,R4]
- [x] T07 GREEN `app/modules/assets/repository.py`: `AssetRepository` (`SORTABLE_FIELDS`, filtros `asset_type/status/criticality/responsible_id/category` + `q` ILIKE sobre `name`), `AssetLicenseRepository` (scoped por `asset_id`+org), `AssetTaskRepository` (link/list/unlink, hard delete del row). [R2,R4,R5]
- [x] T08 GREEN `app/modules/assets/service.py`: `AssetService` (create/list/get/update/delete; `delete` propaga soft-delete a las licencias del activo EN EL SERVICE); `AssetLicenseService` (CRUD scoped al activo padre, `404` si el padre no existe/está borrado/es ajeno, valida fechas); `AssetTaskService` (vincula solo tareas existentes de la misma organización→`404` si no, lista, desvincula). [R1–R6]
- [x] T09 GREEN `app/modules/assets/router.py`: `POST/GET /assets`, `GET/PATCH/DELETE /assets/{id}`, `POST/GET /assets/{id}/licenses`, `PATCH/DELETE /asset-licenses/{id}`, `POST/GET /assets/{id}/tasks`, `DELETE /assets/{id}/tasks/{task_id}`; lectura `get_current_membership`, escritura `require_admin`. [R1–R6]
- [x] T10 [Integration] `app/main.py`: `include_router(assets_router)`.
- [x] T11 VERIFY `cd backend && pytest tests/test_assets.py tests/test_asset_licenses.py -v` en verde; `ruff check .` y `mypy app` limpios.

## Fase B — Alertas de vencimiento de licencia (Commit 2)

- [x] T12 RED `backend/tests/test_license_alerts.py`: R7 (aviso a 30 días, re-corrida no duplica, cruce a 7 días→nuevo `dedup_key`, `auto_renew=true`→sin alerta, descubrimiento tardío a 5 días→SOLO banda 7, salto del día 30 exacto a 25 días→banda 30) + R8 (aviso al vencer a responsable+admins, organización SIN admins→solo responsable, sin duplicado). Sembrar `expiration_date` relativa a `date.today()`; invocar `strategy.evaluate`/`evaluate_organization` directo (patrón `test_blocked_task_alert.py`); `AlertRule` local por suite. Confirmar fallando (ImportError, estrategia inexistente).
- [x] T13 RED (ajuste) `backend/tests/test_blocked_task_alert.py`: `test_seed_creates_five_rules_including_blocked_task`/`test_reseed_does_not_duplicate_rules` pasan de 5 a 7 `rule_type` (agregar `license_expiring`/`license_expired` al set y `len(rules)==7`). Confirmar fallando junto con T12 (el seed y el registry aún no los conocen).
- [x] T14 GREEN `app/alerts/strategies/license_expiring.py`: `LicenseExpiringStrategy.evaluate` — JOIN `AssetLicense→Asset` filtrando org, ambos `is_active`, `auto_renew=False`; banda vigente = la MENOR `b` de `threshold_params["lead_days"]` tal que `0<=días_restantes<=b`; UNA candidate por licencia por corrida a `responsible_id` (skip si `NULL`, espejo `task_overdue`); `dedup_key="license_expiring:{license_id}:{band}"`. [R7]
- [x] T15 GREEN `app/alerts/strategies/license_expired.py`: `LicenseExpiredStrategy.evaluate` — `expiration_date<hoy`, licencia/activo `is_active`; candidate a `responsible_id` (si no `NULL`) Y una por cada `OrganizationMember.role==admin` (destinatarios INDEPENDIENTES — PROHIBIDO el early-return `if not admins: return []`); `dedup_key="license_expired:{license_id}:{recipient_id}"`. [R8]
- [x] T16 GREEN `app/alerts/registry.py`: registrar `"license_expiring"→LicenseExpiringStrategy`, `"license_expired"→LicenseExpiredStrategy` en `_STRATEGIES`.
- [x] T17 GREEN `app/db_init.py`: agregar `("license_expiring", True, {"lead_days":[30,7,1]})` y `("license_expired", True, {})` a `_DEFAULT_ALERT_RULES`.
- [x] T18 VERIFY `cd backend && pytest tests/test_license_alerts.py tests/test_blocked_task_alert.py -v` en verde (7/7 reglas, alertas sin duplicar).
- [x] T19 VERIFY final `cd backend && pytest tests/ -v` en verde (incluidas las 7 estrategias del motor de alertas + las 3 suites nuevas de `assets`, sin regresión en `test_alert_engine.py`); `ruff check .` y `mypy app` limpios.

## Trazabilidad de requisitos

R1 Creación con taxonomía validada · R2 Consulta por cualquier miembro · R3 Edición/borrado admin · R4 Licencias anidadas CRUD + propagación de borrado · R5 Vínculo activo↔tarea existente · R6 Aislamiento multi-tenant (`specs/assets`). R7 Alerta escalonada `license_expiring` · R8 Alerta `license_expired` (`specs/assets`).
