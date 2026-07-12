# Proposal: 07 · Activos de información SDMujer (Asset + AssetLicense + AssetTask + alertas de licencia)

## Intent

CLAUDE.md define la Fase 3 (módulo SDMujer): inventario de activos de información, licencias que vencen y avisos automáticos de vencimiento. Hoy no existe — `assets`/`asset_licenses`/`asset_tasks` no están modelados y el motor de alertas declara `license_expiring`/`license_expired` como deuda pendiente. SDMujer no puede inventariar sus activos ni recibir aviso antes de que caduque una licencia. Este cambio construye el módulo y cierra esas dos estrategias reutilizando el motor as-built.

## Scope

### In Scope
- **CRUD `/api/v1/assets`**: paginación estándar, filtros `?asset_type&status&criticality&responsible_id&category&q` (`q` = búsqueda por nombre), soft delete, auditoría, aislamiento por `organization_id`.
- **AssetLicense (1:N, anidada)**: `POST/GET /api/v1/assets/{id}/licenses` (composición bajo el padre) + `PATCH/DELETE /api/v1/asset-licenses/{id}` (operaciones sobre la licencia individual, patrón comments del repo). Campos CLAUDE.md: `license_key`, `license_type` (perpetual|subscription|trial), `start/expiration_date`, `seats`, `cost`, `auto_renew`.
- **AssetTask (M:N)**: vincular/desvincular tareas existentes (`/api/v1/assets/{id}/tasks`).
- **Alertas `license_expiring`/`license_expired`**: dos estrategias registradas en el registry + seed de AlertRule; destinatario = `responsible_id` (+ admins en la vencida). Reutilizan evaluator/scheduler/dedup SIN modificarlos.
- **Migración Alembic 0010** aditiva con `downgrade`.

### Out of Scope
- Auto-creación de tareas de renovación desde una licencia (solo vínculo manual).
- Recordatorio personal de licencia vía `ReminderRule` (el `params` quedó extensible en 06; se deja como futuro — la señal de licencia es gobernanza de org, no recordatorio personal).
- Email/WebSocket de estas alertas (cambio 08); `frontend/` (frontend-frozen).

## Taxonomía (requisito vinculante — estándar de la industria)

Taxonomía de **dos ejes** anclada a estándares ITAM/SGSI:

- **`asset_type` (enum estable)** derivado de la tipología de activos de ISO/IEC 27005 (primarios + de soporte) intersecada con ITAM (ISO/IEC 19770-1/-3, práctica ITAM de ITIL 4): `hardware`, `software`, `saas_subscription`, `information`, `service`, `certificate`.
  - Se **elimina `license`** del enum del CLAUDE.md: una licencia es un *derecho/entitlement*, no una clase de activo — se modela en `AssetLicense` (ISO/IEC 19770-3 separa el entitlement del activo de software).
  - `document` → `information` (término primario de ISO/IEC 27001:2022 A.5.9 «Inventario de activos de información»).
- **`category` (subtipo opcional, string)** para granularidad ITAM sin migración (hardware → endpoint|servidor|red; software → SO|app_negocio|seguridad). Refleja la estructura «clase + subtipo» de ISO/IEC 27005.

**Referencia citada**: ISO/IEC 27001:2022 Anexo A A.5.9 + ISO/IEC 27005 (tipología primarios/soporte); ISO/IEC 19770-1/-3 e ITIL 4 (práctica ITAM, separación licencia↔activo).

## Permisos
- **Lectura** (GET assets/licenses/tasks): cualquier miembro de la organización (coherente con el modelo de lectura vigente, sin gate granular de `viewer`), tenant-scoped.
- **Escritura** (POST/PATCH/DELETE): `require_admin` — la gestión del inventario y licencias es gobernanza de organización (propiedad de activos ISO 27001), espejo del gate de `PATCH /alert-rules`. Tradeoff: si se quiere que `manager` también gestione, es refinación de RBAC granular futura (deuda `viewer`/roles), fuera de alcance.

## Capabilities

### New Capabilities
- `assets`: inventario de activos (Asset), licencias con vencimiento (AssetLicense 1:N) y vínculo activo↔tarea (AssetTask M:N), con taxonomía estándar y CRUD tenant-scoped.

### Modified Capabilities
- `alert-engine`: dos estrategias nuevas `license_expiring` y `license_expired` vía registry + seed; evaluator/scheduler/dedup intactos.

## Approach

Módulo nuevo `backend/app/modules/assets/` (models, router, service, repository, schemas) con repository pattern y mixins base (Pk+Timestamp+SoftDelete+Audit+Tenant). Las dos estrategias son clases en `backend/app/alerts/strategies/` registradas en `registry._STRATEGIES` (punto de extensión) y sembradas en `db_init.py` como AlertRule por defecto; el evaluador ya itera reglas `enabled` y despacha por `rule_type`, así que su código no se toca. `dedup_key` determinista incluye el umbral (`license_expiring:{license_id}:{lead}`) para permitir avisos escalonados (p. ej. 30/7/1 días) sin duplicar. TDD estricto.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/assets/` | New | Asset+AssetLicense+AssetTask: models, router, service, repository, schemas |
| `backend/app/alerts/strategies/license_expiring.py`, `license_expired.py` | New | Dos estrategias `AlertStrategy` |
| `backend/app/alerts/registry.py` | Modified | Registrar 2 `rule_type` (extensión del dict `_STRATEGIES`) |
| `backend/app/db_init.py` | Modified | 2 AlertRule por defecto (seed idempotente por `rule_type`) |
| `backend/app/main.py` | Modified | Incluir el router de assets |
| `backend/alembic/` | New | Migración 0010: `assets`, `asset_licenses`, `asset_tasks` (con downgrade) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Taxonomía ad-hoc que no cumpla estándar | Med | Enum anclado a ISO 27005/19770/ITIL 4 + `category` para granularidad sin migración |
| Duplicar avisos escalonados de licencia | Med | `dedup_key` incluye el umbral; hereda idempotencia `exists_active` del evaluador |
| Acoplar la alerta y romper las 5 estrategias vigentes | Low | Solo se agregan clases + registro; evaluator/scheduler/dedup sin cambios; TDD |
| Doble evaluación con réplicas (sin lock Redis) | Low | Hereda el TODO de lock del evaluador; guard por dedup |

## Rollback Plan

Cambio aditivo. Revertir el merge y aplicar `downgrade` de la migración 0010 (elimina `assets`, `asset_licenses`, `asset_tasks`). Quitar las 2 entradas de `_STRATEGIES` y del seed deja al evaluador sin esas reglas; las AlertRule sembradas quedan inertes. Las notificaciones de licencia ya emitidas permanecen inertes en la bandeja sin romper el contrato de `notifications-inapp`.

## Dependencies

- `depends_on: 02-contrato-api` — paginación, auditoría y resolución de auth-user para el CRUD.
- Reutiliza línea base as-built (no es dependencia SDD): `alert-engine` (registry/evaluator/scheduler/dedup) y `notifications-inapp` (salida). `06-reminders` es adyacente en el roadmap pero NO es dependencia técnica (la vía `ReminderRule` se deja sin usar).

## Success Criteria

- [ ] CRUD `/api/v1/assets` con paginación, filtros, soft delete, auditoría y aislamiento multi-tenant; tests happy path + error + permisos.
- [ ] AssetLicense anidada (CRUD) y AssetTask vincula/desvincula tareas existentes.
- [ ] `asset_type` implementa la taxonomía estándar (sin `license`; con `information`/`certificate`/`saas_subscription`) + `category` subtipo.
- [ ] `license_expiring` avisa al responsable X días antes (configurable vía `AlertRule.threshold_params`); `license_expired` al vencer; sin duplicar entre corridas.
- [ ] Las 5 estrategias existentes siguen verdes; evaluator/scheduler/dedup sin cambios.
- [ ] Migración 0010 con downgrade probado; suite completa verde (TDD estricto).
