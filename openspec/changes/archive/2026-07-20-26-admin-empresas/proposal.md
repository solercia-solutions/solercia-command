# Proposal: 26 · Administración de empresas y empresa activa

## Intent

Hoy no existe empresa activa ni gestión de empresas. `get_current_membership` (`dependencies.py:128`) y `primary_organization_id` (`auth/service.py:34`) toman siempre la PRIMERA membresía por `created_at`: un usuario con varias empresas queda atrapado en una y no puede cambiar. Las empresas solo nacen por seed (sin CRUD ni gestión de miembros). Este cambio habilita el patrón boki multi-empresa: administrar empresas, pertenecer a varias con roles distintos y cambiar la empresa activa refrescando todo el contexto (proyectos, menús, dashboards, notificaciones).

## Scope

### In Scope
- Backend: CRUD de empresas (`/organizations`) y gestión de miembros (`/organizations/{id}/members`: alta, baja, cambio de rol).
- Resolución de empresa activa por header `X-Organization-Id` validado contra la membresía; reemplaza el "primera por created_at" en `get_current_membership`/`primary_organization_id` (fallback compatible si falta el header).
- Migración: unique `(organization_id, user_id)` en `organization_members`.
- Permisos por rol en cada endpoint (TDD): admin de la empresa administra empresa y miembros; cualquier autenticado crea empresa y queda como su `admin` (bootstrap, sin superadmin global).
- Frontend: selector de empresa activa en el layout shell, entidad/servicio `organization`, store de empresa activa (signal + localStorage), interceptor que inyecta el header y refresco de contexto al cambiar (reset de stores de proyectos/tareas/dashboard/notificaciones, recarga de menús y reconexión WebSocket).

### Out of Scope
- Superadmin global / consola cross-tenant (no existe hoy).
- Soft delete de membresías (se evalúa en design; MVP: baja dura de la fila de asociación).
- Claim de empresa activa en el JWT con rotación de token (alternativa documentada, no elegida).
- Endurecimiento del scoping por módulo (lo cubre el cambio 25).
- Harness de pruebas de frontend.

## Capabilities

### New Capabilities
- `organizations-admin`: CRUD de empresas + gestión de miembros + resolución de empresa activa (backend).
- `frontend-org-switcher`: selector de empresa activa y refresco de contexto (frontend).

### Modified Capabilities
- `multi-tenancy`: R2 pasa de "primera membresía por created_at" a "empresa activa validada contra membresía"; nueva unicidad `(organization_id, user_id)`.

## Approach

Empresa activa vía header `X-Organization-Id`: stateless, cambio instantáneo, sin rotar token; aprovecha que `get_current_membership` ya consulta la membresía por request. El resolver valida que el header sea una membresía del usuario (403 si no pertenece) y cae en la primera membresía si falta (retrocompatible). Alternativas descartadas para el MVP: claim en JWT (exige refresh al cambiar y reconectar el socket) y `User.active_organization_id` persistido (pega el cambio entre dispositivos y agrega escritura). Backend con Repository + `require_role(MemberRole.admin)` por empresa. Frontend FSD: `entities/organization/`, `features/manage-organizations/`, selector en `widgets/header`, y un store de empresa activa que orquesta el reseteo.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/organizations/` | Modified | router/service/repository/schemas de CRUD + miembros |
| `backend/app/dependencies.py` | Modified | resolución de empresa activa desde header |
| `backend/app/modules/auth/service.py` | Modified | `primary_organization_id` respeta empresa activa |
| `backend/alembic/` | New | migración unique (org,user) |
| `frontend/src/entities/organization/` | Modified | servicio CRUD + miembros |
| `frontend/src/features/manage-organizations/` | New | páginas de administración |
| `frontend/src/widgets/header/` | Modified | selector de empresa activa |
| `frontend/src/features/auth/` | Modified | interceptor inyecta header; store de empresa activa |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Header falsificable (acceder a empresa ajena) | Alta | Validar el header contra membresía en el resolver; 403 si no pertenece |
| Cambio de empresa deja stores/WS con datos de la anterior | Media | Store de empresa activa resetea dominios y reconecta WebSocket |
| Solapamiento de spec con el cambio 25 | Media | Orden: 25 (scoping) antes de 26; el delta de 26 se limita a resolución + unicidad |
| Bootstrap sin superadmin abusable | Media | Solo tocas empresas donde eres admin; crear una no da acceso a otras |
| Filas (org,user) duplicadas previas rompen la unique | Media | La migración deduplica antes de crear la constraint |

## Rollback Plan

Revertir los commits de backend/frontend; `alembic downgrade` elimina la constraint. Sin el header, el resolver vuelve al comportamiento "primera membresía", así que la reversión no rompe sesiones activas.

## Dependencies

- `25-multiempresa-scoping`: el endurecimiento del aislamiento por `organization_id` debe aterrizar antes; 26 asume que cada módulo ya filtra por la empresa resuelta.

## Success Criteria

- [ ] CRUD de empresas y gestión de miembros con permisos por rol (TDD: happy path + error + permisos).
- [ ] Un usuario en dos empresas cambia la activa y ve datos de la nueva (proyectos, menús, dashboards).
- [ ] Header inválido o de una empresa ajena devuelve 403.
- [ ] Unique `(organization_id, user_id)` aplicada y reversible.
- [ ] Cambiar de empresa resetea stores y reconecta WebSocket sin fuga de la anterior.

## Proposal question round

Supuestos a validar (aprobables en automático): (1) empresa activa por header `X-Organization-Id`, no claim JWT ni campo persistido; (2) cualquier autenticado crea empresa y queda como su admin, sin superadmin global; (3) MVP con baja dura de membresías (soft delete diferido a design); (4) 26 depende de 25 ya aplicado.
