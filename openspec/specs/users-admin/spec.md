# Spec — Administración de usuarios (users-admin)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

CRUD administrativo de usuarios de la plataforma y asignación de su conjunto de roles RBAC. Todo el módulo exige rol de administrador.

## Alcance as-built

| Método | Ruta | Propósito |
|--------|------|-----------|
| GET | /api/v1/admin/users | Lista de usuarios |
| POST | /api/v1/admin/users | Crea usuario (201) |
| GET | /api/v1/admin/users/{id} | Detalle de usuario |
| PATCH | /api/v1/admin/users/{id} | Actualización parcial |
| DELETE | /api/v1/admin/users/{id} | Borrado suave (204) |
| PUT | /api/v1/admin/users/{id}/roles | Reemplaza el conjunto de roles RBAC del usuario |

Modelo `User` (Pk + Timestamp + SoftDelete; SIN TenantMixin — el scope de tenant se resuelve vía `OrganizationMember`):

| Campo | Descripción |
|-------|-------------|
| email | Único, credencial de login |
| primer_nombre, segundo_nombre | Nombres |
| primer_apellido, segundo_apellido | Apellidos |
| dependency_id | FK a `dependencies` (área organizacional) |
| hashed_password | Hash bcrypt |

## Requisitos

- **R1**: Todos los endpoints del módulo DEBEN exigir `require_admin` (usuario con rol RBAC de código `ADMIN`).
- **R2**: La creación DEBE responder 201 y almacenar la contraseña únicamente como hash bcrypt.
- **R3**: `DELETE` DEBE ser borrado suave (`is_active`/`deleted_at`) y responder 204; nunca borrado físico.
- **R4**: `PUT /{id}/roles` DEBE reemplazar el conjunto completo de roles del usuario (semántica de set, no de append).

### Escenarios centrales

**R1 — Acceso restringido**
- Dado un usuario autenticado sin rol `ADMIN`
- Cuando llama cualquier endpoint de `/admin/users`
- Entonces la petición es rechazada por autorización.

**R3 — Borrado suave**
- Dado un usuario existente
- Cuando un administrador llama `DELETE /admin/users/{id}`
- Entonces responde 204, el registro conserva su fila y deja de aparecer en la lista.

**R4 — Reemplazo de roles**
- Dado un usuario con los roles A y B
- Cuando un administrador envía `PUT /{id}/roles` con solo el rol C
- Entonces el usuario queda únicamente con el rol C.

## Limitaciones y deuda conocida

- Sin paginación: la lista devuelve todos los usuarios.
- Sin auditoría `created_by`/`updated_by`.
- El scope multi-tenant del usuario depende de `OrganizationMember`; el modelo no tiene `organization_id` propio.
- CERO tests del módulo.

## Referencias

- backend/app/modules/users/ (router.py, service.py, repository.py, models.py, schemas.py)
- backend/app/db_init.py (seed del admin y usuarios demo)
