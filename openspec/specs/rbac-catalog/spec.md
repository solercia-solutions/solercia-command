# Spec — Catálogo RBAC (roles, menús y áreas organizacionales)

> **Origen**: línea base as-built (2026-07-11)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Catálogo de control de acceso: roles por organización con grants sobre menús (actividades/navegación) y catálogo de áreas organizacionales (`dependencies`: Dirección, Tecnología, Operaciones…). OJO: `dependencies` son áreas de la entidad, NO dependencias tarea-tarea.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET/POST | /api/v1/admin/roles | Lista y creación de roles |
| GET/PATCH/DELETE | /api/v1/admin/roles/{id} | Detalle, edición y borrado suave |
| PUT | /api/v1/admin/roles/{id}/menus | Reemplaza los grants de menús del rol |
| GET/POST | /api/v1/admin/menus | Lista (plana y en árbol) y creación de menús |
| GET/PATCH/DELETE | /api/v1/admin/menus/{id} | Detalle, edición y borrado suave |
| GET/POST | /api/v1/admin/dependencies | Lista y creación de áreas organizacionales |
| GET/PATCH/DELETE | /api/v1/admin/dependencies/{id} | Detalle, edición y borrado suave |

Modelos:

| Modelo | Campos clave | Mixins |
|--------|--------------|--------|
| Role | code, name | Pk + Tenant + Timestamp + SoftDelete |
| UserRole | user_id, role_id | Tabla de unión |
| RoleMenu | role_id, menu_id | Tabla de unión |
| Menu | name, icon?, path?, parent_id? (árbol), order | Pk + Timestamp + SoftDelete — catálogo GLOBAL, sin tenant |
| Dependency | name, code? | Pk + Tenant + Timestamp + SoftDelete |

## Requisitos

- **R1**: Todos los endpoints del catálogo DEBEN exigir `require_admin` (rol RBAC con `Role.code == 'ADMIN'`).
- **R2**: `PUT /admin/roles/{id}/menus` DEBE reemplazar el conjunto completo de grants (semántica de set).
- **R3**: Los menús DEBEN poder consultarse como lista plana y como árbol anidado por `parent_id` ordenado por `order`.
- **R4**: Los borrados del catálogo DEBEN ser suaves (nunca físicos).

### Escenarios centrales

**R2 — Reemplazo de grants**
- Dado un rol con acceso a los menús M1 y M2
- Cuando un administrador envía `PUT /admin/roles/{id}/menus` con [M3]
- Entonces el rol queda solo con M3 y `GET /auth/me/menus` de sus usuarios refleja el cambio.

**R3 — Árbol de menús**
- Dado menús con relaciones padre-hijo
- Cuando se consulta la vista de árbol
- Entonces los hijos aparecen anidados bajo su `parent_id`, ordenados por `order`.

**R1 — Protección del catálogo**
- Dado un usuario sin rol `ADMIN`
- Cuando llama cualquier endpoint de `/admin/roles`, `/admin/menus` o `/admin/dependencies`
- Entonces la petición es rechazada por autorización.

## Limitaciones y deuda conocida

- Conviven DOS sistemas de roles paralelos: el enum `MemberRole` (admin|manager|member|viewer) en `OrganizationMember` (usado por `require_role`) y el catálogo RBAC `Role`/`UserRole`/`RoleMenu` (usado por `require_admin`). No hay unificación.
- El catálogo de menús es global (sin tenant): un cambio afecta a todas las organizaciones.
- Los permisos granulares por endpoint (viewer/manager/member del CLAUDE.md) NO están aplicados en la mayoría de rutas de dominio.
- CERO tests de roles, menús y dependencies.

## Referencias

- backend/app/modules/roles/ (router.py, service.py, models.py)
- backend/app/modules/menus/
- backend/app/modules/dependencies/
- backend/app/dependencies.py (require_admin, require_role)
