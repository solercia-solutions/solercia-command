# Spec — Multi-tenancy (organizations + membership + filtrado row-level)

> **Origen**: línea base as-built (2026-07-11)

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
- **R2**: El tenant DEBE resolverse en el backend desde el header `X-Organization-Id` validado contra las membresías del usuario autenticado; si el header referencia una empresa donde el usuario no es miembro, la resolución DEBE fallar con `403`. Si el header está ausente, DEBE conservarse el comportamiento previo (primera membresía por `created_at`), sin intervención del cliente.
- **R3**: `MemberRole` DEBE ser la base de `require_role` para autorización por membresía.
- **R4**: El seed inicial DEBE ser idempotente y crear la organización "Solercia" con el usuario `admin@solercia.com` SIN condición, en cada arranque. Los miembros demo (`ana@`, `carlos@`, `diana@`) DEBEN crearse ÚNICAMENTE cuando `settings.SEED_DEMO_DATA` sea `true` (ver capability `data-maintenance`); con el flag en `false` (valor por defecto), la organización "Solercia" y el usuario `admin@solercia.com` existen, pero ningún miembro demo se crea ni se recrea en arranques sucesivos.
- **R5**: `organization_members` DEBE tener una restricción única sobre `(organization_id, user_id)`. La migración que la introduce DEBE deduplicar cualquier fila preexistente que viole la unicidad antes de crear la constraint, y DEBE ser reversible.

### Escenarios centrales

**R1 — Aislamiento row-level**
- Dado dos organizaciones con proyectos propios
- Cuando un miembro de la organización A lista `/projects`
- Entonces solo recibe proyectos con `organization_id` de A.

**R4 — Seed idempotente con miembros demo condicionales**

*Escenario 1: Organización y admin incondicionales*
- DADO una base de datos vacía
- CUANDO la aplicación arranca, sin importar el valor de `SEED_DEMO_DATA`
- ENTONCES existen la organización "Solercia" y `admin@solercia.com` como miembro

*Escenario 2: Miembros demo condicionados al flag*
- DADO `settings.SEED_DEMO_DATA = false`
- CUANDO la aplicación arranca
- ENTONCES NO se crean `ana@`, `carlos@` ni `diana@` como miembros de "Solercia"

*Escenario 3: Restart no revive miembros demo tras la purga*
- DADO una base purgada (sin miembros demo) con `settings.SEED_DEMO_DATA = false`
- CUANDO el backend reinicia
- ENTONCES `organization_members` de "Solercia" contiene únicamente a `admin@solercia.com`

**R2 — Resolución de tenant**
- Dado un usuario con una o varias membresías
- Cuando llama un endpoint de dominio con header `X-Organization-Id` válido
- Entonces el scope se toma de la empresa indicada en el header, validado contra sus membresías
- Cuando llama un endpoint de dominio sin el header
- Entonces el scope se toma de su primera membresía por `created_at`, conservando el comportamiento previo
- Cuando llama con un header de una empresa donde no es miembro
- Entonces la resolución falla con `403` y ningún dato se expone

**R5 — Unicidad de membresía**
- Dado que un usuario U ya es miembro de la empresa X
- Cuando se intenta insertar otra fila `(X, U)` en `organization_members`
- Entonces la base de datos rechaza la inserción por la restricción única

## Limitaciones y deuda conocida

- NO hay middleware de tenant ni schema switching (contrario a lo descrito en CLAUDE.md); el filtrado vive disperso en services/repos.
- `OrganizationMember` no tiene soft delete.

## Cambios respecto a la línea base as-built (2026-07-11)

El cambio 26-admin-empresas introduce:
- CRUD de organizations (router/servicio completo): las organizaciones se pueden crear dinámicamente por cualquier usuario autenticado (bootstrap como admin).
- Resolución de empresa activa por header `X-Organization-Id` con fallback compatible: usuario con varias membresías puede cambiar el scope por request sin reloguearse.
- Selector de empresa activa en el frontend: interfaz para cambiar el scope activo, con persistencia en localStorage.
- Restricción única en `(organization_id, user_id)` con migración reversible (0021).

## Referencias

- backend/app/modules/organizations/models.py
- backend/app/shared/base_model.py (TenantMixin)
- backend/app/dependencies.py (get_current_membership, require_role)
- backend/app/db_init.py (seed_default)
