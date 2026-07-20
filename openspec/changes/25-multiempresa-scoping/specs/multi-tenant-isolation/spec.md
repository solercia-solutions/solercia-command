# multi-tenant-isolation Specification

## Purpose

Fija como contrato verificable el aislamiento multiempresa por `organization_id`: ninguna operación autenticada de una organización DEBE exponer, modificar ni eliminar entidades de otra, en ningún módulo tenant-scoped. Documenta la superficie compartida por diseño (`menus`, plantillas `system`) para no confundirla con una fuga. No toca la resolución de empresa activa ni el JWT (frontera con el cambio 26).

## Requirements

### Requirement: Aislamiento cross-tenant en operaciones de módulos tenant-scoped

El sistema DEBE garantizar, en cada módulo tenant-scoped listado abajo, que ninguna operación de una organización expone, modifica ni elimina entidades de otra, en listados, detalle, actualización y borrado.

| Grupo | Módulos |
|---|---|
| Proyecto y ejecución | projects, tasks, sprints, boards, dependencies, task_links, checklists, time_logs, activity, labels |
| Colaboración | comments, attachments, notifications, reminders |
| Personas y permisos | users, roles, org_role_templates |
| Búsqueda y panorama | search, dashboard |
| Activos e integraciones | assets, alert_rules, intake, glpi_sync, jira_import, organizations |

#### Scenario: Listado no revela entidades de otra empresa

- DADO organizaciones A y B con entidades sembradas
- CUANDO un usuario de A consulta el listado
- ENTONCES solo aparecen ids de A, ninguno de B

#### Scenario: Detalle de una entidad ajena responde 404

- DADO una entidad que pertenece a B
- CUANDO un usuario de A solicita su detalle por id
- ENTONCES responde 404 (no 403), sin filtrar su existencia

#### Scenario: Actualización y borrado de una entidad ajena son rechazados

- DADO una entidad que pertenece a B
- CUANDO un usuario de A intenta actualizarla o eliminarla
- ENTONCES ambas operaciones fallan y la entidad de B permanece intacta y activa

### Requirement: Superficie global por diseño

El catálogo `menus` y las plantillas `system` de `org_role_templates` SON compartidos por diseño; el sistema NO DEBE tratarlos como fuga y DEBE tener un test que fije ese contrato.

#### Scenario: Catálogo de menús es igual para ambas organizaciones

- DADO organizaciones A y B
- CUANDO cada una consulta el catálogo de menús
- ENTONCES reciben el mismo conjunto de menús `system`

#### Scenario: Plantillas system son visibles para cualquier organización

- DADO una plantilla `system`
- CUANDO otra organización la consulta
- ENTONCES es visible, sin tratarse como fuga

### Requirement: Aislamiento de conectores por organización y por usuario

El sistema DEBE mantener `Connector` único por organización (`UNIQUE(organization_id, provider)`) y `ConnectedAccount` único por usuario; las credenciales cifradas NO DEBEN cruzar organizaciones ni usuarios.

#### Scenario: Connector de una organización no es visible desde otra

- DADO un Connector de A para un proveedor
- CUANDO B consulta sus conectores
- ENTONCES no aparece el de A

#### Scenario: ConnectedAccount de un usuario no es visible por otro

- DADO una ConnectedAccount del usuario X en A
- CUANDO el usuario Y de A consulta sus cuentas
- ENTONCES no ve la cuenta ni las credenciales de X

### Requirement: No regresión y scoping manual sin filtro global

La suite backend DEBE permanecer en verde (≥1158 tests) tras la batería de fuga cross-tenant; el aislamiento sigue siendo manual, consulta por consulta; el sistema NO DEBE introducir un filtro global de tenant en SQLAlchemy salvo que una fuga lo exija.

#### Scenario: Suite completa en verde tras la batería nueva

- DADO la batería de tests de fuga agregada por módulo
- CUANDO se ejecuta la suite completa del backend
- ENTONCES todos pasan, incluidos los ≥1158 preexistentes

#### Scenario: Corrección de una fuga se hace en repository/service

- DADO que un test revela una fuga en un módulo
- CUANDO se corrige
- ENTONCES se filtra por `organization_id` (o join al padre) en repository/service, no con filtro global

### Requirement: Frontera con el cambio 26 (resolución de empresa activa)

Este cambio NO DEBE modificar la resolución de empresa activa, el claim JWT de organización, ni las membresías multiempresa (`app/dependencies.py:128-146`, `app/modules/auth/service.py:34-44`); esa superficie es del cambio 26 (`admin-empresas`).

#### Scenario: Resolución de empresa activa no cambia

- DADO el comportamiento actual (primera membresía por `created_at`)
- CUANDO se aplican las correcciones de scoping de este cambio
- ENTONCES permanece intacta, sin cambios de contrato
