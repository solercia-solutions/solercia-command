# Design: 26 · Administración de empresas y empresa activa

## Technical Approach

Empresa activa resuelta por request desde el header `X-Organization-Id`, aprovechando que `get_current_membership` (`dependencies.py:128-146`) ya consulta la membresía en cada llamada. El resolver deja de tomar "la primera por `created_at`" y pasa a: header presente + válido + es membresía del usuario → esa membresía; header presente pero no es membresía (o UUID inválido) → **403**; header ausente → primera membresía (retrocompat con los 1158 tests y clientes actuales). El módulo `organizations/` se extiende con CRUD + miembros sin tocar las rutas de theme existentes. Frontend FSD: store de empresa activa (signal + localStorage), header inyectado por el interceptor, y **recarga completa** de la app al cambiar. Autorización sobre `{id}` es *target-scoped* (membresía en la empresa de la ruta), no la del header. Migración 0021 añade unique `(organization_id, user_id)` con deduplicación previa.

## Architecture Decisions

### Decisión 1: resolución de empresa activa (header validado, fallback compatible)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Header `X-Organization-Id`; `get_current_membership` recibe `Request`, consulta `WHERE user_id AND organization_id`; ausente → primera por `created_at`** | Stateless, cambio instantáneo sin rotar token; fallback conserva TODOS los tests y el WS actuales | **Elegida** |
| Claim de empresa en el JWT | Exige `/auth/refresh` + reconectar socket en cada cambio | Rechazada |
| `User.active_organization_id` persistido | Acopla el cambio entre dispositivos y agrega escritura | Rechazada |

Header con UUID malformado o de una empresa ajena → **403** (`not_a_member`), nunca 404 ni 200 (no confirma existencia; alinea con el contrato de 25).

### Decisión 2: autorización sobre `{id}` es target-scoped, con `MemberRole.admin`

`require_role(MemberRole.admin)` valida la membresía **activa** (header), no la empresa de la ruta. Para CRUD sobre `/organizations/{id}` se añade `require_org_admin(id)`: carga la membresía del caller en la empresa de la ruta y exige `role == admin` (404 si no es miembro, 403 si no es admin). Se usa `MemberRole.admin` (autoridad de membresía) y **no** el RBAC catalog (`require_admin`, reservado a menús/theme): el bootstrap otorga `MemberRole.admin`, así que es el gate coherente.

### Decisión 3: migración 0021 — unique con dedup segura, reversible

`revises 0020`. `upgrade()`: elimina duplicados conservando la fila más antigua por `(organization_id, user_id)` (`MIN(created_at)`), luego crea `uq_organization_members_org_user`. `OrganizationMember` no tiene hijos → borrar duplicados es seguro. `downgrade()`: `drop_constraint`. Sin dedup, filas previas romperían la constraint (riesgo del proposal).

### Decisión 4: bootstrap en una transacción, sin superadmin global

`POST /organizations`: cualquier autenticado crea empresa **y** su `OrganizationMember(role=admin)` en el mismo commit. Tradeoff documentado: no hay consola cross-tenant; crear una empresa no da acceso a otras — solo administras donde eres `admin`.

### Decisión 5: frontend — recarga completa tras el switch (vs. reset selectivo)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **`setActiveOrg(id)` → persiste `sp-active-org` → `window.location.reload()`** | Bootstrap re-corre íntegro (theme `GET /me/theme`, menús, `/auth/me`, datos de página y futuro WS) con el header nuevo; cero fuga de estado | **Elegida** |
| Reset selectivo de stores | Frágil: hay que enumerar cada store y se rompe al agregar dominios | Rechazada |

**Gotcha crítico**: `sp-active-org` debe limpiarse en `clearSession()`/logout. Si no, tras login de otro usuario en el mismo navegador el header apunta a una empresa ajena → **403 en toda la sesión**. El interceptor omite el header en `/auth/login|refresh|logout` (igual que `Authorization`).

## Data Flow

    Angular request ─► authInterceptor: + Authorization + X-Organization-Id (store)
         │
         ▼
    get_current_membership(Request): header? ─► valida membresía ─► 403 si ajena
         │  (ausente → primera por created_at)
         ▼
    /auth/me · /auth/me/menus · CRUD · WS  ─► scope = empresa activa
         │
    switch: setActiveOrg ─► localStorage ─► reload ─► bootstrap re-corre con header

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/dependencies.py` | Modify | `get_current_membership(Request)` lee/valida header; nuevo `require_org_admin(id)` |
| `backend/app/modules/organizations/service.py` | Modify | + `OrganizationService` (CRUD/bootstrap) y `OrganizationMemberService` |
| `backend/app/modules/organizations/repository.py` | Modify | list/create/update/soft-delete + membership queries (`get_membership`, `list_mine`) |
| `backend/app/modules/organizations/router.py` | Modify | + CRUD, `/mine`, `/{id}/members`; theme intacto |
| `backend/app/modules/organizations/schemas.py` | Create | `OrganizationCreate/Update/Read`, `MemberCreate/UpdateRole/Read` |
| `backend/app/realtime/router.py` | Modify | `_resolve_organization_id` acepta hint de empresa activa (query/subprotocol), valida membresía (1008 si ajena), fallback primera |
| `backend/alembic/versions/0021_unique_org_member.py` | Create | dedup + unique `(organization_id, user_id)`, reversible |
| `frontend/src/entities/organization/organizations.service.ts` | Create | CRUD + members + `mine()` |
| `frontend/src/entities/organization/organization.model.ts` | Create | tipos `Organization`, `OrganizationMember` |
| `frontend/src/features/organizations/active-org.store.ts` | Create | signal + `sp-active-org`; `setActiveOrg()` → reload |
| `frontend/src/features/auth/auth.interceptor.ts` | Modify | inyecta `X-Organization-Id` (omite endpoints de auth) |
| `frontend/src/features/auth/auth.service.ts` | Modify | limpia `sp-active-org` en `clearSession()` |
| `frontend/src/features/manage-organizations/**` | Create | páginas admin (CRUD + miembros) |
| `frontend/src/widgets/header/ui/header.component.ts` | Modify | selector de empresa activa (lista `mine()`) |
| `frontend/src/pages/admin/admin.routes.ts` | Modify | ruta lazy `organizations` |

## Interfaces / Contracts

```python
async def get_current_membership(request, db, user) -> OrganizationMember  # header X-Organization-Id
async def require_org_admin(organization_id, db, user) -> OrganizationMember  # target-scoped

# GET  /organizations/mine        -> [{organization, role}]  (miembro)
# POST /organizations             -> bootstrap: org + creador admin (autenticado)
# GET/PATCH/DELETE /organizations/{id}          (require_org_admin excepto GET=miembro)
# GET/POST/PATCH/DELETE /organizations/{id}/members/{user_id}   (require_org_admin)
```

Header ausente ⇒ comportamiento idéntico al actual (los tests de aislamiento de 25 siguen verdes sin header). Envoltura `{data}` como el resto de módulos.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (dep) | header válido/ausente/ajeno/malformado; `require_org_admin` | `two_orgs` + `make_member` por rol; assert membresía/403 |
| Integration | CRUD + members: happy + error + permisos por rol (TDD) | `client` con/sin `X-Organization-Id` |
| Integration | bootstrap crea creador `admin` en un commit | `POST /organizations` → assert membership |
| Migration | dedup conserva la más antigua; unique aplica; reversible | siembra duplicados → upgrade/downgrade |
| Regresión | 1158 tests sin header y aislamiento de 25 verdes | suite completa |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. La falsificación del header es autorización de dominio: mitigada validando la membresía en el resolver (Decisión 1) y target-scoped en `{id}` (Decisión 2).

## Migration / Rollout

Migración 0021 (dedup + unique). Rollback: `alembic downgrade` elimina la constraint; sin header el resolver vuelve a "primera membresía", así que revertir no rompe sesiones activas.

## Forecast de tamaño (para sdd-tasks)

Backend ~260–320 (resolver + `require_org_admin` ~60, service/repo/schemas CRUD+members ~150, migración ~50, WS ~20) + tests ~250; frontend ~250–320 (store ~50, service/model ~90, páginas admin ~140, selector ~40, interceptor/auth ~20). `400-line budget risk: High`. `Decision needed before apply: Yes`. `Chained PRs recommended: Yes` — cortar: (1) backend resolver+migración+CRUD/members (autónomo, aísla la invariante), (2) frontend store+interceptor+switcher, (3) páginas admin.

## Open Questions

- [ ] Ninguna bloqueante. Baja de miembros = baja dura de la fila (MVP; soft delete diferido). Códigos exactos de error (`not_a_member` vs `forbidden`) los fija el spec.
