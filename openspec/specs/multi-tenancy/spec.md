# Spec — Multi-tenancy (organizations + membership + filtrado row-level)

> Línea base as-built (2026-07-11). Documenta el comportamiento existente en el código; no es un diseño futuro.

## Propósito

Aislamiento de datos por organización con estrategia row-level: columna `organization_id` en las entidades tenant-scoped y filtrado en services/repositories a partir de la membresía del usuario autenticado.

## Alcance as-built

Solo modelos — NO existe router ni servicio de organizations:

| Modelo | Campos clave | Mixins |
|--------|--------------|--------|
| Organization | name, slug | Pk + Timestamp + SoftDelete — raíz del tenant |
| OrganizationMember | organization_id, user_id, role (enum MemberRole: admin\|manager\|member\|viewer) | Pk + Timestamp, SIN soft delete |

Mecánica de scope:

- `TenantMixin` (columna `organization_id`) aplicado a: AlertRule, Attachment, TaskComment, Dependency, Notification, Project, Role.
- `get_current_membership` resuelve el tenant del usuario tomando su PRIMERA membresía ordenada por `created_at`.
- Task, Sprint y User NO llevan `organization_id`; su scope se deriva por join (Task/Sprint → Project) o por membresía (User).

## Requisitos

- **R1**: Toda entidad tenant-scoped DEBE llevar `organization_id` (TenantMixin) y toda consulta de dominio DEBE filtrar por la organización de la membresía activa.
- **R2**: El tenant DEBE resolverse en el backend desde el usuario del JWT (vía `get_current_membership`), nunca desde un parámetro del cliente.
- **R3**: `MemberRole` DEBE ser la base de `require_role` para autorización por membresía.
- **R4**: El seed inicial DEBE ser idempotente y crear la organización "Solercia" con sus miembros demo.

### Escenarios centrales

**R1 — Aislamiento row-level**
- Dado dos organizaciones con proyectos propios
- Cuando un miembro de la organización A lista `/projects`
- Entonces solo recibe proyectos con `organization_id` de A.

**R2 — Resolución de tenant**
- Dado un usuario con una membresía
- Cuando llama cualquier endpoint de dominio
- Entonces el scope se toma de su primera membresía por `created_at`, sin intervención del cliente.

## Limitaciones y deuda conocida

- NO hay CRUD de organizations (sin router/servicio): las organizaciones solo nacen por seed.
- NO hay middleware de tenant ni schema switching (contrario a lo descrito en CLAUDE.md); el filtrado vive disperso en services/repos.
- Multi-membresía degenerada: si un usuario pertenece a varias organizaciones, siempre opera sobre la primera; no hay selector de organización.
- `OrganizationMember` no tiene soft delete.
- CERO tests del aislamiento multi-tenant.

## Referencias

- backend/app/modules/organizations/models.py
- backend/app/shared/base_model.py (TenantMixin)
- backend/app/dependencies.py (get_current_membership, require_role)
- backend/app/db_init.py (seed_default)
