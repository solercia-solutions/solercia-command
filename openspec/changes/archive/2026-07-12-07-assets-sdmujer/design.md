# Design: 07 · Activos de información SDMujer (Asset + AssetLicense + AssetTask + alertas de licencia)

## Technical Approach

Dos piezas backend: (1) módulo nuevo `app/modules/assets/` (`router → service → repository`, patrón idéntico a `reminders`) con **tres entidades cohesivas** — `Asset`, `AssetLicense` (composición 1:N), `AssetTask` (M:N) — CRUD tenant-scoped, paginación/soft-delete/auditoría de 02, lectura por miembro (`get_current_membership`) y escritura `require_admin`; (2) dos estrategias `AlertStrategy` (`license_expiring`, `license_expired`) en `app/alerts/strategies/`, registradas en `registry._STRATEGIES` y sembradas en `db_init._DEFAULT_ALERT_RULES`, reutilizando `evaluator`/`scheduler`/`exists_active` SIN tocarlos. Todo en UTC; taxonomía de dos ejes (`asset_type` enum + `category` string). TDD estricto por invocación directa de `strategy.evaluate`/`evaluate_organization`. Depende de 02.

## Architecture Decisions

### Un solo módulo para las tres entidades

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Un módulo `assets/` con `AssetService`/`AssetLicenseService`/`AssetTaskService` + repos análogos | Un solo agregado, cero fragmentación; espejo exacto de `reminders` (Reminder+ReminderRule) | **Elegida** |
| Módulo `assets/` + `licenses/` separados | La licencia no existe sin su activo (composición) → separar rompe el agregado y duplica scoping | Rechazada |

### FK y borrado de las entidades hijas

| Relación | ondelete | Borrado operativo |
|----------|----------|-------------------|
| `AssetLicense.asset_id → assets` | **CASCADE** (la licencia es composición, no sobrevive al activo — a diferencia de `Reminder.task_id=SET NULL`) | soft: `DELETE /assets/{id}` marca `is_active=False` y arrastra sus licencias en el service |
| `AssetTask.asset_id`/`task_id` | **CASCADE** ambas | **hard delete** del row al desvincular — precedente `TaskLabel` (join puro: `Pk+Timestamp`, `UniqueConstraint`, SIN `SoftDeleteMixin`; OJO: `TaskLabel` real NO lleva `TenantMixin` — `AssetTask` DIVERGE deliberadamente añadiéndolo para scoping directo por organización sin joins) |

**Rationale**: `AssetTask` es asociación pura sin semántica de recorrido (a diferencia de `TaskDependency`, que sí es soft por la detección de ciclos), así que aplica la convención `Role/UserRole/TaskLabel`; el hard-delete evita el gotcha del `UniqueConstraint(asset_id, task_id)` bloqueando el re-vínculo tras un soft-delete.

### Enums `native_enum=False` (sin tipo PG)

`AssetType` (`hardware|software|saas_subscription|information|service|certificate`), `AssetStatus` (`active|inactive|retired|under_review`), `AssetCriticality` (`critical|high|medium|low` — enum **dedicado**, no reusar `Priority`: separación de dominio), `LicenseType` (`perpetual|subscription|trial`) en `app/shared/enums.py`, todos `SAEnum(..., native_enum=False, length=N)` — espejo exacto de `ReminderStatus`: se renderizan como `VARCHAR`, no generan tipo PG, paridad `alembic check` garantizada. `category`: `String(80)` nullable (segundo eje, granularidad sin migración).

### `dedup_key` con recipient y banda de umbral

| Estrategia | `dedup_key` | Destinatarios |
|-----------|-------------|---------------|
| `license_expiring` | `license_expiring:{license_id}:{band}` — **banda vigente = la MENOR band b de los leads tal que `0 <= days_left <= b`**; UNA sola candidate por corrida (jamás varias bandas a la vez; descubrimiento tardío a 5 días → solo band 7; salto del día exacto, p. ej. 25 días → band 30 porque 25<=30) | `responsible_id` (si NULL → skip, como `task_overdue`) |
| `license_expired` | `license_expired:{license_id}:{recipient_id}` | `responsible_id` **+ cada** `OrganizationMember.role==admin` — **cada destinatario es independiente**: org sin admins → solo responsable; responsable NULL → solo admins; PROHIBIDO copiar el early-return `if not admins: return []` de workload_imbalance (allí es correcto porque TODOS los destinatarios son admins; aquí suprimiría el aviso al responsable) |

**Rationale**: incluir `band` permite avisos escalonados (30→7→1) sin duplicar entre corridas; incluir `recipient_id` en la vencida evita que el aviso del primer admin suprima al resto (lección de `workload_imbalance`). Admins se resuelven con `select(OrganizationMember).where(role==MemberRole.admin)` — patrón as-built de `workload_imbalance`. `auto_renew=True`, licencias/activos `is_active=False` no generan candidatos.

## Data Flow

    scheduler → evaluate_organization(db, org) → AlertRule(enabled).rule_type
      → get_strategy("license_expiring"/"license_expired").evaluate(db, org, threshold_params)
        · JOIN AssetLicense→Asset WHERE org, ambos is_active, auto_renew=False
        · expiring: banda vigente = min{b ∈ leads : 0 <= days_left <= b} → UNA candidate a responsible con esa banda
        · expired:  expiration_date < today → candidate a responsible + una por admin (independientes)
      → exists_active(dedup_key)? no → Notification.create → commit
    CRUD  /assets · POST/GET /assets/{id}/licenses · PATCH/DELETE /asset-licenses/{id} · /assets/{id}/tasks
          → service (admin write / member read; el soft-delete del asset propaga a sus licencias) → repository (org-scoped)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/assets/{models,schemas,repository,service,router}.py` | Create | Asset+AssetLicense+AssetTask; 3 services/repos; `SORTABLE_FIELDS`; filtros `asset_type/status/criticality/responsible_id/category/q` (`q` = ILIKE sobre name); rutas de licencias: POST/GET anidadas + PATCH/DELETE planas `/asset-licenses/{id}` |
| `app/alerts/strategies/license_expiring.py`, `license_expired.py` | Create | Dos `AlertStrategy` (firma `evaluate(db, org, threshold_params)`) |
| `alembic/versions/0010_add_assets.py` | Create | 3 tablas, `down_revision="0009"`, `downgrade` limpio (drop inverso) |
| `app/shared/enums.py` | Modify | `AssetType`, `AssetStatus`, `AssetCriticality`, `LicenseType` |
| `app/alerts/registry.py` | Modify | Registrar 2 `rule_type` en `_STRATEGIES` |
| `app/db_init.py` | Modify | Import de modelos (metadata) + 2 entradas en `_DEFAULT_ALERT_RULES` |
| `app/main.py` | Modify | `include_router(assets_router)` |
| `tests/test_blocked_task_alert.py` | Modify | **Requerido**: `test_seed_creates_five_rules`/`test_reseed` asumen 5 reglas — pasan a 7 y agregan los 2 `rule_type` al set |

## Interfaces / Contracts

```python
# Asset:        Pk+Timestamp+SoftDelete+Audit+Tenant · asset_type SAEnum(native_enum=False),
#   category String(80)?, status AssetStatus, criticality AssetCriticality,
#   responsible_id FK users SET NULL?, vendor String?, location String?, acquisition_date Date?
# AssetLicense: mismos mixins · asset_id FK assets CASCADE, license_type LicenseType,
#   license_key String?, start_date/expiration_date Date, seats Int?, cost Numeric(12,2)?, auto_renew bool=False
# AssetTask:    Pk+Timestamp+Tenant (join TaskLabel) · asset_id/task_id FK CASCADE,
#   UniqueConstraint(asset_id, task_id)
_DEFAULT_ALERT_RULES += [("license_expiring", True, {"lead_days": [30, 7, 1]}),
                         ("license_expired", True, {})]
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | formato `dedup_key` (band/recipient, sin colisión); `require_admin` 403 en escritura; validación de fechas/enum en schema | pytest sin BD |
| Integration `test_assets.py`/`test_asset_licenses.py` | CRUD paginado + filtros + soft-delete + auditoría; aislamiento cross-tenant con `two_orgs`; **escritura exige RBAC admin vía `rbac_admin(session,org,user)`** (OJO: `two_orgs` siembra `OrganizationMember.role=admin`, que NO satisface `require_admin`); lectura solo con membresía; licencia anidada CRUD; vincular/desvincular task existente | `client` ASGI + fixtures 01 |
| Integration `test_license_alerts.py` | expiring notifica al responsable dentro de banda; expired al responsable **+ admins**; `auto_renew=True`/soft-borrados no notifican; re-run no duplica; registry + seed idempotente | sembrar `expiration_date` relativa a `date.today()` e invocar `strategy.evaluate`/`evaluate_organization` directo (patrón `test_blocked_task_alert.py`); AlertRule local por suite |

## Threat Matrix

N/A — no hay routing, shell, subprocess, automatización VCS/PR ni clasificación de ejecutables. El scheduler es asíncrono in-process (heredado, sin cambios). El único riesgo de integración es el doble disparo multi-réplica, cubierto por `dedup_key` + `exists_active` y con el TODO de lock Redis heredado del evaluador.

## Migration / Rollout

Migración aditiva `0010` (`down_revision="0009"`); enums inline `sa.Enum(native_enum=False, length=N)` (sin tipo PG). Rollback: `downgrade` elimina `asset_tasks`, `asset_licenses`, `assets`; quitar las 2 estrategias del registry + seed deja las AlertRule inertes; notificaciones ya emitidas permanecen inertes sin romper `notifications-inapp`.

## Presupuesto (líneas / tests)

~1400–1600 líneas autoras (módulo de 3 entidades + 2 estrategias + migración + 3 suites) y ~18–24 tests → excede el budget de 400 (**size:exception aceptada**). `sdd-tasks` debe cortar en **2 lotes** con verificación y rollback autónomos: **Lote A** — módulo `assets` + enums + migración 0010 + `main` (deliverable: CRUD inventario/licencias/vínculos verde); **Lote B** — 2 estrategias + registry + seed + `test_license_alerts.py` + fix de los tests de seed (deliverable: alertas de licencia verdes). El corte espeja las 2 capabilities (assets new / alert-engine modified).

## Open Questions

- [x] Módulo único vs. separado — RESUELTO: único (espejo `reminders`).
- [x] `AssetTask` soft vs hard delete — RESUELTO: hard (convención `TaskLabel`).
- [x] Destinatarios admin de `license_expired` — RESUELTO: `OrganizationMember.role==admin` (patrón `workload_imbalance`).
