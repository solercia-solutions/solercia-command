# Delta for multi-tenancy

## MODIFIED Requirements

### Requirement: Resolución de empresa activa (antes R2 — resolución de tenant)

El tenant DEBE resolverse en el backend desde el header `X-Organization-Id`, validado contra las membresías del usuario autenticado (`get_current_membership` / `primary_organization_id`); si el header referencia una empresa donde el usuario no es miembro, la resolución DEBE fallar con `403`. Si el header está ausente, DEBE conservarse el comportamiento previo: la primera membresía por `created_at`, sin intervención del cliente.
(Previously: el tenant se resolvía siempre desde la primera membresía por `created_at`, sin que ningún parámetro del cliente pudiera influir en la resolución.)

#### Scenario: Resolución de tenant sin header (comportamiento previo intacto)

- DADO un usuario con una o varias membresías
- CUANDO llama cualquier endpoint de dominio sin el header `X-Organization-Id`
- ENTONCES el scope se toma de su primera membresía por `created_at`, igual que antes de este cambio

#### Scenario: Resolución de tenant con header válido

- DADO un usuario miembro de las empresas X y Y
- CUANDO llama un endpoint de dominio con `X-Organization-Id: Y`
- ENTONCES el scope resuelto es Y, no la primera membresía por `created_at`

#### Scenario: Header de una empresa ajena es rechazado

- DADO un usuario sin membresía en la empresa Z
- CUANDO llama un endpoint de dominio con `X-Organization-Id: Z`
- ENTONCES la resolución falla con `403` y ningún dato de Z se expone

## ADDED Requirements

### Requirement: Unicidad de membresía por empresa y usuario

`organization_members` DEBE tener una restricción única sobre `(organization_id, user_id)`. La migración que la introduce DEBE deduplicar cualquier fila preexistente que viole la unicidad antes de crear la constraint, y DEBE ser reversible (`alembic downgrade` elimina la constraint sin afectar las filas).

#### Scenario: Alta de membresía duplicada es rechazada a nivel de datos

- DADO que el usuario U ya es miembro de la empresa X
- CUANDO se intenta insertar otra fila `(X, U)` en `organization_members`
- ENTONCES la base de datos rechaza la inserción por la restricción única

#### Scenario: La migración deduplica filas previas a la constraint

- DADO filas duplicadas `(organization_id, user_id)` existentes antes de esta migración
- CUANDO se ejecuta `alembic upgrade`
- ENTONCES las duplicadas se consolidan antes de crear la constraint única, sin perder el rol de mayor jerarquía

#### Scenario: La migración es reversible

- DADO la constraint única ya aplicada
- CUANDO se ejecuta `alembic downgrade`
- ENTONCES la constraint se elimina y las filas de `organization_members` permanecen intactas
