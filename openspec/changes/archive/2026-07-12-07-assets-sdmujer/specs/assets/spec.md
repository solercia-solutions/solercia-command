# assets Specification

## Purpose

Inventario de activos de información de la organización (`Asset`), sus licencias con vencimiento (`AssetLicense`, composición 1:N) y su vínculo con tareas existentes (`AssetTask`, M:N), con taxonomía de dos ejes (`asset_type` enum + `category` subtipo libre) y dos alertas de vencimiento de licencia (`license_expiring`, `license_expired`) sobre el motor de alertas existente.

## Alcance propuesto

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | /api/v1/assets | Crear activo |
| GET | /api/v1/assets | Listar activos (paginado, filtros) |
| GET | /api/v1/assets/{id} | Obtener un activo |
| PATCH | /api/v1/assets/{id} | Editar un activo |
| DELETE | /api/v1/assets/{id} | Borrar (soft) un activo |
| POST | /api/v1/assets/{id}/licenses | Crear licencia del activo |
| GET | /api/v1/assets/{id}/licenses | Listar licencias del activo |
| PATCH | /api/v1/asset-licenses/{id} | Editar una licencia |
| DELETE | /api/v1/asset-licenses/{id} | Borrar (soft) una licencia |
| POST | /api/v1/assets/{id}/tasks | Vincular una tarea existente |
| GET | /api/v1/assets/{id}/tasks | Listar tareas vinculadas |
| DELETE | /api/v1/assets/{id}/tasks/{task_id} | Desvincular una tarea |

Modelo `Asset` (Pk+Timestamp+SoftDelete+Audit+Tenant): `name`, `description?`, `asset_type` (hardware|software|saas_subscription|information|service|certificate), `category?` (string libre), `status` (active|inactive|retired|under_review), `responsible_id` (FK User), `criticality` (critical|high|medium|low), `acquisition_date?`, `location?`, `vendor?`. `AssetLicense` (Pk+Timestamp+SoftDelete+Audit+Tenant, FK `asset_id`): `license_key?`, `license_type` (perpetual|subscription|trial), `start_date`, `expiration_date`, `seats?`, `cost?`, `auto_renew` (bool, default false). `AssetTask` (Pk+Timestamp+Tenant, tabla de unión `asset_id`+`task_id`, único).

## Requirements

### Requirement: Creación de activo con taxonomía validada

`POST /api/v1/assets` DEBE exigir `name` y un `asset_type` perteneciente al enum estable; DEBE estar gateado por `require_admin`.

#### Scenario: Creación válida por admin
- Dado un admin autenticado de la organización
- Cuando envía `POST /assets` con `name` y `asset_type=hardware`
- Entonces se crea el activo con `created_by`/`updated_by` = el admin

#### Scenario: asset_type fuera del enum
- Dado un admin autenticado
- Cuando envía `POST /assets` con `asset_type="license"` (valor eliminado del enum)
- Entonces la API responde `422` y no crea el registro

#### Scenario: Creación rechazada a no-admin
- Dado un usuario sin rol admin
- Cuando envía `POST /assets`
- Entonces la API responde `403`

### Requirement: Consulta de activos por cualquier miembro

`GET /api/v1/assets` DEBE paginar (`?page&size&sort&order`, `meta{total,page,size}`) con filtros combinables `?asset_type&status&criticality&responsible_id&category&q` (`q` = búsqueda por subcadena en el nombre, insensible a mayúsculas; `category` = coincidencia exacta del segundo eje de la taxonomía); `GET /assets/{id}` DEBE responder `404` si no existe, está borrado o es de otra organización. Ambos accesibles a cualquier miembro (sin gate de rol).

#### Scenario: Listado filtrado
- Dado 5 activos `hardware` y 3 `software` en la organización
- Cuando un miembro llama `GET /assets?asset_type=hardware&page=1&size=10`
- Entonces recibe solo los 5 `hardware`, con `meta{total,page,size}`

#### Scenario: Obtención inexistente o ajena
- Dado un activo que no existe o pertenece a otra organización
- Cuando se llama `GET /assets/{id}`
- Entonces la API responde `404`

### Requirement: Edición y borrado de un activo

`PATCH`/`DELETE /api/v1/assets/{id}` DEBEN estar gateados por `require_admin`; `DELETE` DEBE ser soft delete (`is_active=false`, `deleted_at`).

#### Scenario: Edición válida por admin
- Dado un activo propio de la organización
- Cuando un admin envía `PATCH` con nuevos `status`/`criticality`
- Entonces se actualiza y `updated_by` refleja al admin

#### Scenario: Borrado soft
- Dado un activo activo
- Cuando un admin llama `DELETE /assets/{id}`
- Entonces queda `is_active=false` y ya no aparece en `GET /assets`

#### Scenario: Edición rechazada a no-admin
- Dado un usuario sin rol admin
- Cuando envía `PATCH /assets/{id}`
- Entonces la API responde `403`

### Requirement: Licencias anidadas del activo (CRUD)

Las rutas de licencia DEBEN operar bajo el activo padre (composición): `POST/GET /assets/{id}/licenses` y `PATCH/DELETE /asset-licenses/{id}`. La API DEBE rechazar con `422` una `expiration_date` menor o igual a `start_date`. Escritura gateada por `require_admin`; lectura, cualquier miembro.

#### Scenario: Creación válida
- Dado un activo propio
- Cuando un admin envía `POST /assets/{id}/licenses` con `expiration_date` posterior a `start_date`
- Entonces se crea la licencia asociada al activo

#### Scenario: Licencias inaccesibles tras el borrado soft del activo padre
- Dado un activo con licencias que un admin soft-borra vía `DELETE /assets/{id}`
- Cuando cualquier usuario intenta `GET /assets/{id}/licenses` o `PATCH/DELETE /asset-licenses/{id}` sobre sus licencias
- Entonces la API responde `404` (la propagación del borrado ocurre en el service, no solo en la query de alertas)

#### Scenario: Fechas inválidas
- Dado un activo propio
- Cuando un admin envía `POST .../licenses` con `expiration_date <= start_date`
- Entonces la API responde `422`

#### Scenario: Edición y borrado
- Dado una licencia propia
- Cuando un admin la edita (`PATCH`) o la borra (`DELETE`)
- Entonces se actualiza o queda `is_active=false` (soft delete)

#### Scenario: Licencia de activo ajeno
- Dado una licencia de un activo de otra organización
- Cuando se llama `GET/PATCH/DELETE` sobre ella
- Entonces la API responde `404`

### Requirement: Vínculo activo↔tarea con tareas existentes

`POST /api/v1/assets/{id}/tasks` DEBE vincular una tarea EXISTENTE de la MISMA organización (NO DEBE crear tareas); DEBE responder `404` si la tarea no existe o es de otra organización. `GET` lista los vínculos; `DELETE .../tasks/{task_id}` desvincula. Escritura `require_admin`; lectura, cualquier miembro.

#### Scenario: Vínculo válido
- Dado un activo y una tarea de la misma organización
- Cuando un admin llama `POST /assets/{id}/tasks` con el `task_id`
- Entonces el vínculo se crea y aparece en `GET /assets/{id}/tasks`

#### Scenario: Tarea de otra organización
- Dado una tarea que pertenece a otra organización
- Cuando un admin intenta vincularla a un activo propio
- Entonces la API responde `404`

#### Scenario: Desvinculación
- Dado un vínculo activo-tarea existente
- Cuando un admin llama `DELETE /assets/{id}/tasks/{task_id}`
- Entonces el vínculo desaparece de `GET /assets/{id}/tasks`

### Requirement: Aislamiento multi-tenant en activos, licencias y vínculos

Ningún usuario DEBE ver ni gestionar activos, licencias o vínculos de otra organización, independientemente de su rol.

#### Scenario: Activos de otra organización
- Dado activos de la organización A
- Cuando un usuario de la organización B llama `GET /assets`
- Entonces NO recibe activos de la organización A

#### Scenario: Licencia de otra organización
- Dado una licencia de un activo de la organización A
- Cuando un usuario de la organización B intenta `GET/PATCH/DELETE` sobre ella
- Entonces la API responde `404`

#### Scenario: Vínculo de otra organización
- Dado un vínculo activo-tarea de la organización A
- Cuando un usuario de la organización B intenta consultarlo o borrarlo
- Entonces la API responde `404`

### Requirement: Alerta escalonada license_expiring

Para cada licencia activa (no borrada, `auto_renew=false`) con `0 <= días_restantes` hasta `expiration_date`, el evaluador DEBE calcular la **banda vigente**: la MENOR banda `b` de `AlertRule.threshold_params` (por defecto 30/7/1, configurable por organización) tal que `días_restantes <= b`. Si existe banda vigente, DEBE generar UNA sola `Notification` por corrida al `responsible_id` del activo, con `dedup_key` que incluye esa banda (`license_expiring:{license_id}:{banda}`) — jamás candidatos de varias bandas en la misma corrida. Licencias con `auto_renew=true` o de activos/licencias soft-borrados NO DEBEN generar esta alerta.

#### Scenario: Aviso a 30 días
- Dado una licencia activa a 30 días de vencer y la regla `license_expiring` habilitada con umbrales 30/7/1
- Cuando corre el evaluador
- Entonces el responsable del activo recibe UNA notificación

#### Scenario: Re-corrida no duplica
- Dado el aviso de 30 días ya generado
- Cuando el evaluador corre nuevamente sin cruzar el siguiente umbral
- Entonces no se genera una segunda notificación

#### Scenario: Cruce a un umbral distinto sí avisa
- Dado el aviso de 30 días ya generado
- Cuando la licencia llega a 7 días de vencer
- Entonces se genera un NUEVO aviso (`dedup_key` distinto por umbral)

#### Scenario: auto_renew=true no alerta
- Dado una licencia con `auto_renew=true` a 7 días de vencer
- Cuando corre el evaluador
- Entonces NO se genera notificación `license_expiring` para esa licencia

#### Scenario: Descubrimiento tardío dispara solo la banda vigente
- Dado una licencia recién creada a 5 días de vencer y umbrales 30/7/1
- Cuando corre el evaluador por primera vez sobre ella
- Entonces se genera UNA sola notificación con la banda 7 (la menor que contiene 5), nunca las bandas 30 y 7 a la vez

#### Scenario: Salto del día exacto del umbral igual avisa
- Dado una licencia a 25 días de vencer (el evaluador no corrió el día 30 exacto) y umbrales 30/7/1
- Cuando corre el evaluador
- Entonces se genera la notificación de la banda 30 (25 <= 30), sin exigir igualdad exacta con el umbral

### Requirement: Alerta license_expired

Cuando `expiration_date` de una licencia activa (no borrada) ya pasó, el evaluador DEBE generar UNA `Notification` al `responsible_id` del activo Y a los admins de la organización, sin duplicar entre corridas.

#### Scenario: Aviso al vencer
- Dado una licencia activa con `expiration_date` en el pasado
- Cuando corre el evaluador
- Entonces el responsable del activo y los admins de la organización reciben la notificación

#### Scenario: Organización sin admins igual notifica al responsable
- Dado una licencia vencida en una organización SIN ningún miembro con `MemberRole.admin`
- Cuando corre el evaluador
- Entonces el responsable del activo recibe su notificación (la ausencia de admins jamás suprime el aviso al responsable)

#### Scenario: Sin duplicado
- Dado el aviso de vencimiento ya generado para una licencia
- Cuando el evaluador corre nuevamente
- Entonces no se genera una segunda notificación para esa licencia

## Referencias

- Proposal: `openspec/changes/07-assets-sdmujer/proposal.md`
- Patrón espejo: `openspec/specs/alert-engine/spec.md`
- Salida compartida: `openspec/specs/notifications-inapp/spec.md`
