# organizations-admin Specification

## Purpose

CRUD de empresas, gestión de miembros y resolución de la empresa activa por petición. Cualquier usuario autenticado puede crear una empresa y queda como su `admin` (bootstrap sin superadmin global); el resto de operaciones administrativas queda restringido al rol `admin` de esa empresa. Todas las respuestas usan el envelope vigente (`api-conventions`): `{"data": ...}` en lecturas, `{"data": ..., "message": "..."}` en acciones, `{"data": [...], "meta": {"total": n}}` en listados.

## Endpoints y permisos por rol

| Endpoint | Acción | Rol requerido | Nota |
|---|---|---|---|
| `POST /organizations` | Crear empresa | Cualquier autenticado | Crea membresía `admin` del creador |
| `GET /organizations/{id}` | Leer empresa | Miembro de esa empresa | 404 si no es miembro |
| `PATCH /organizations/{id}` | Actualizar empresa | `admin` de esa empresa | 403 si no es admin |
| `DELETE /organizations/{id}` | Baja lógica | `admin` de esa empresa | soft delete, no física |
| `GET /organizations/{id}/members` | Listar miembros | Miembro de esa empresa | incluye el rol de cada uno |
| `POST /organizations/{id}/members` | Agregar miembro por correo | `admin` de esa empresa | rechaza duplicado (organization_id, user_id) |
| `PATCH /organizations/{id}/members/{member_id}` | Cambiar rol | `admin` de esa empresa | rechaza si deja la empresa sin admin |
| `DELETE /organizations/{id}/members/{member_id}` | Quitar miembro | `admin` de esa empresa | misma protección "sin admin" |
| Endpoint "mis empresas" | Listar empresas del usuario | Cualquier autenticado | cada una con su rol |

## Requirements

### Requirement: Bootstrap de administrador al crear empresa

El sistema DEBE permitir que cualquier usuario autenticado cree una empresa y DEBE crear automáticamente su membresía con rol `admin` en la empresa creada, sin requerir un superadmin global.

#### Scenario: Creación exitosa deja al creador como admin

- DADO un usuario autenticado
- CUANDO crea una empresa con nombre y slug válidos
- ENTONCES la empresa queda creada y el usuario tiene membresía `admin` en ella, sin acceso a otras empresas

#### Scenario: Slug duplicado es rechazado

- DADO una empresa existente con un slug
- CUANDO otro usuario intenta crear una empresa con el mismo slug
- ENTONCES la API responde error de validación y no crea la empresa

### Requirement: Permisos por rol en lectura y escritura de empresa y miembros

El sistema DEBE restringir la lectura de una empresa y de sus miembros a usuarios con membresía en ella (404 si no es miembro), y DEBE restringir su actualización, baja lógica y gestión de miembros al rol `admin` de esa empresa (403 si no es admin).

#### Scenario: No miembro recibe 404 al leer

- DADO un usuario sin membresía en la empresa Y
- CUANDO solicita su detalle o su listado de miembros
- ENTONCES la API responde `404`, sin revelar si la empresa existe

#### Scenario: Rol no admin recibe 403 al escribir

- DADO un usuario con rol `member` en la empresa X
- CUANDO intenta actualizarla, eliminarla o gestionar sus miembros
- ENTONCES la API responde `403` y la empresa permanece intacta

### Requirement: Unicidad de membresía y protección contra empresa sin admin

El sistema DEBE rechazar altas de membresía duplicadas para el mismo par empresa-usuario, y DEBE rechazar cualquier cambio de rol o remoción que deje a la empresa sin ningún miembro con rol `admin`.

#### Scenario: Alta duplicada es rechazada

- DADO un usuario que ya es miembro de la empresa X
- CUANDO un admin intenta agregarlo de nuevo
- ENTONCES la API responde error de conflicto sin duplicar la membresía

#### Scenario: Degradar o remover al único admin es rechazado

- DADO un único admin en la empresa X
- CUANDO intenta cambiar su propio rol a `member` o removerse a sí mismo
- ENTONCES la API responde error y la membresía admin permanece intacta

### Requirement: Resolución de empresa activa por header con fallback compatible

El sistema DEBE resolver la empresa activa de cada petición desde el header `X-Organization-Id`, validado contra las membresías del usuario autenticado; si el header referencia una empresa donde el usuario no es miembro, DEBE responder `403`. Si el header está ausente, DEBE conservar el comportamiento previo (primera membresía por `created_at`).

#### Scenario: Header válido resuelve la empresa activa

- DADO un usuario miembro de las empresas X y Y
- CUANDO llama un endpoint de dominio con `X-Organization-Id: Y`
- ENTONCES la petición opera sobre el scope de Y

#### Scenario: Header de empresa ajena es rechazado

- DADO un usuario sin membresía en la empresa Z
- CUANDO llama un endpoint con `X-Organization-Id: Z`
- ENTONCES la API responde `403`

#### Scenario: Sin header, cae al comportamiento previo

- DADO un usuario con varias membresías y una petición sin el header
- CUANDO llama un endpoint de dominio
- ENTONCES el scope resuelto es su primera membresía por `created_at`

### Requirement: "Mis empresas" y `/auth/me` reflejan la empresa activa resuelta

El sistema DEBE exponer un endpoint que liste todas las empresas del usuario autenticado con su rol en cada una, y `GET /auth/me` DEBE reflejar la empresa activa resuelta para esa petición (header o fallback), no siempre la primera membresía.

#### Scenario: Usuario con varias empresas ve todas con su rol

- DADO un usuario miembro de X (rol `admin`) e Y (rol `member`)
- CUANDO consulta sus empresas
- ENTONCES recibe ambas con el rol correspondiente en cada una

#### Scenario: `/auth/me` cambia según el header enviado

- DADO un usuario miembro de X y Y
- CUANDO llama `/auth/me` con `X-Organization-Id: Y`
- ENTONCES la respuesta refleja el contexto y el rol de Y, no de X
