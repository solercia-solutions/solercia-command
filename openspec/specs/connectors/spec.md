# connectors Specification

> **Origen**: cambio [14-integration-ports](../../../changes/14-integration-ports/proposal.md)

## Propósito

Modelo de datos de conectores por organización, cuentas conectadas por usuario y credenciales cifradas, junto con el flujo OAuth genérico (`authorize` → callback → intercambio de tokens → cifrado → registro de cuenta) y la sección REST `/api/v1/connectors` con permisos por rol. Consume el núcleo de `integration-ports` (registro de adaptadores, protocolo de adaptador, cifrado) sin conocer el proveedor concreto.

## Alcance propuesto

| Método | Ruta | Propósito | Rol requerido |
|--------|------|-----------|----------------|
| POST | /api/v1/connectors | Crear conector (config de proveedor) | admin\|manager |
| GET | /api/v1/connectors | Listar conectores de la organización | cualquier miembro |
| GET | /api/v1/connectors/{id} | Detalle de un conector | cualquier miembro |
| PATCH | /api/v1/connectors/{id} | Editar conector | admin\|manager |
| DELETE | /api/v1/connectors/{id} | Borrado suave del conector | admin\|manager |
| GET | /api/v1/connectors/{id}/authorize | Inicia el flujo OAuth (genera state + URL del proveedor) | cualquier miembro |
| GET | /api/v1/connectors/oauth/callback | Recibe el callback del proveedor (ruta global; el `state` transporta la referencia al conector), canjea código por tokens | validado por state, no por rol |
| GET | /api/v1/connectors/{id}/accounts | Lista cuentas conectadas del conector | admin\|manager (todas) / miembro (solo propias) |
| DELETE | /api/v1/connected-accounts/{id} | Desconecta una cuenta | dueño de la cuenta o admin\|manager |

Modelos (Pk + Timestamp + SoftDelete + Audit + Tenant salvo donde se indique):

- `Connector`: `organization_id`, `provider`, `scopes`, `status`.
- `ConnectedAccount`: `connector_id`, `user_id`, `organization_id`, `external_account_id`, `status` — único por (`connector_id`, `external_account_id`), NUNCA por (`user_id`, `provider`).
- `ConnectionCredentials` (tabla separada, sin exposición directa vía API): `connected_account_id`, `access_token_enc`, `refresh_token_enc`, `expires_at`.

## Requisitos

### Requirement: Modelo de datos y aislamiento multi-tenant

`Connector`, `ConnectedAccount` y `ConnectionCredentials` DEBEN estar scoped por `organization_id` (directo o vía `connector_id`/`connected_account_id`). Ningún usuario DEBE ver ni gestionar conectores, cuentas o credenciales de otra organización, sin importar su rol.

#### Scenario: Conector de otra organización no es visible
- Dado un conector de la organización A
- Cuando un usuario de la organización B llama `GET /connectors/{id}`
- Entonces la API responde `404`

#### Scenario: Cuenta conectada de otra organización
- Dado una cuenta conectada de la organización A
- Cuando un usuario de la organización B intenta `GET`/`DELETE` sobre ella
- Entonces la API responde `404`

### Requirement: CRUD de conectores con permisos por rol

`POST`/`PATCH`/`DELETE /api/v1/connectors` DEBEN estar gateados a roles `admin` o `manager` (`require_role`). `GET /connectors` y `GET /connectors/{id}` DEBEN ser accesibles a cualquier miembro autenticado de la organización (necesario para que el miembro sepa qué puede conectar). `DELETE` DEBE ser borrado suave.

#### Scenario: Admin crea un conector
- Dado un admin autenticado de la organización
- Cuando envía `POST /connectors` con `provider` y `scopes`
- Entonces se crea el conector con `created_by`/`updated_by` = el admin

#### Scenario: Member no puede crear conectores
- Dado un usuario con rol `member`
- Cuando envía `POST /connectors`
- Entonces la API responde `403`

#### Scenario: Cualquier miembro puede listar conectores
- Dado conectores existentes en la organización
- Cuando un usuario `member` llama `GET /connectors`
- Entonces recibe la lista, sin requerir rol admin/manager

### Requirement: Varias cuentas del mismo proveedor por usuario

Un usuario PUEDE conectar más de una cuenta del mismo proveedor bajo el mismo conector (ej. dos buzones de correo distintos). La unicidad de `ConnectedAccount` DEBE evaluarse por `external_account_id` dentro del conector, NUNCA por la combinación (usuario, proveedor).

#### Scenario: Segunda cuenta del mismo proveedor
- Dado un usuario con una cuenta ya conectada al conector de correo
- Cuando conecta una segunda cuenta externa distinta (`external_account_id` diferente) del mismo conector
- Entonces se crea una SEGUNDA fila `ConnectedAccount` para ese usuario, sin colisión con la primera

#### Scenario: Reconexión de la misma cuenta externa no duplica
- Dado una `ConnectedAccount` existente con un `external_account_id` dado
- Cuando el mismo usuario repite el flujo OAuth para esa MISMA cuenta externa
- Entonces se actualizan sus credenciales en la fila existente, sin crear una fila duplicada

### Requirement: Tipo de credencial del conector (`credential_kind`)

El modelo `Connector` DEBE exponer `credential_kind` (`oauth` | `api_token` | `none`), con `oauth` como valor por defecto. El valor DEBE determinar el flujo de autenticación aplicable: `oauth` usa `authorize`/`callback`; `api_token` usa el registro directo de credenciales; `none` registra un conector sin credencial. El campo DEBE fijarse al crear el conector y NO DEBE cambiarse después sin recrear el conector.

#### Scenario: Conector oauth por defecto
- Dado un admin que crea un conector sin especificar `credential_kind`
- Cuando se persiste
- Entonces `credential_kind` queda en `oauth`

#### Scenario: Conector api_token explícito
- Dado un admin que crea un conector con `credential_kind=api_token`
- Cuando se persiste
- Entonces el conector usa el registro directo de credenciales, no `authorize`/`callback`

#### Scenario: Conector sin credencial
- Dado un admin que crea un conector con `credential_kind=none`
- Cuando se persiste
- Entonces el conector queda activo sin exigir credencial alguna

### Requirement: Extensión del enum `credential_kind` con el valor `none`

El modelo de credenciales de conector DEBE admitir `credential_kind = none`, sumado al conjunto (`oauth`, `api_token`), para conectores cuyo servidor externo no requiere ninguna credencial (ej. un servidor MCP público sin autenticación). Esta extensión NO redefine los valores `oauth`/`api_token`; únicamente agrega `none` como valor adicional del mismo enum.

#### Scenario: Conector registrado con `credential_kind = none`
- Dado un servidor MCP que no exige autenticación
- Cuando se registra el conector con `credential_kind = none`
- Entonces el conector queda activo sin exigir ningún token

#### Scenario: Conector con `credential_kind = none` no persiste credenciales
- Dado un conector con `credential_kind = none`
- Cuando se inspecciona su fila asociada en `ConnectionCredentials`
- Entonces no existe ninguna fila de credenciales para ese conector

### Requirement: Registro de conector con credencial directa (sin flujo `authorize`/`callback`)

Para adaptadores cuyo protocolo declara adquisición directa de credencial (ver `integration-ports`), `POST /api/v1/connectors` DEBE admitir la credencial en el MISMO request de creación: un token estático a cifrar con Fernet (`credential_kind = api_token`) o ninguna credencial (`credential_kind = none`), SIN requerir `GET .../authorize` ni el callback OAuth. El token estático DEBE cifrarse y persistirse en `ConnectionCredentials` con el mismo esquema (Fernet) que los tokens OAuth, y NUNCA DEBE exponerse en respuestas ni en logs.

#### Scenario: Registro exitoso de conector MCP con token estático cifrado
- Dado un admin autenticado que registra un conector MCP con un token bearer estático
- Cuando envía `POST /connectors` con la credencial incluida
- Entonces el conector queda creado y el token queda cifrado en `ConnectionCredentials`, sin pasar por `authorize`/`callback`

#### Scenario: El token estático nunca aparece en la respuesta ni en logs
- Dado un conector MCP registrado con token estático
- Cuando se consulta `GET /connectors/{id}` o se inspeccionan los logs de la aplicación
- Entonces el token, cifrado o en claro, no aparece en ninguno de los dos

#### Scenario: `authorize`/`callback` no aplica a un conector de credencial directa
- Dado un conector cuyo adaptador declara adquisición directa de credencial
- Cuando se intenta `GET /connectors/{id}/authorize` sobre ese conector
- Entonces la API responde un error controlado indicando que ese conector no usa el flujo OAuth

### Requirement: Registro directo de credenciales `api_token` sin flujo OAuth

Para conectores `credential_kind=api_token`, el sistema DEBE exponer una operación de registro directo de credenciales del proveedor (ej. App-Token + user_token de GLPI) sin generar `state` ni redirección de navegador. Las credenciales DEBEN cifrarse antes de persistirse en `ConnectionCredentials`, igual que las credenciales `oauth`, y NUNCA DEBEN exponerse en respuestas ni logs. La operación DEBE estar gateada a roles `admin`/`manager`.

#### Scenario: Admin registra credenciales api_token
- Dado un admin de la organización y un conector `api_token`
- Cuando envía las credenciales del proveedor al endpoint de registro directo
- Entonces se cifran y persisten en `ConnectionCredentials` sin exponerse en la respuesta

#### Scenario: Member no puede registrar credenciales api_token
- Dado un usuario con rol `member`
- Cuando intenta usar el endpoint de registro directo de credenciales
- Entonces la API responde `403`

### Requirement: Inicio del flujo OAuth (authorize)

`GET /api/v1/connectors/{id}/authorize` DEBE generar un `state` (CSRF) único, persistirlo en Redis con TTL asociado al conector y al usuario solicitante, y responder con la URL de autorización del proveedor (construida por el adaptador registrado). DEBE responder `404` si el conector no existe o es de otra organización. Este endpoint SOLO aplica a conectores `credential_kind=oauth`; sobre un conector `api_token` DEBE responder un error controlado indicando que debe usarse el registro directo de credenciales.

#### Scenario: Authorize genera state con TTL y URL del proveedor
- Dado un conector activo `oauth` de la organización del usuario
- Cuando el usuario llama `GET /connectors/{id}/authorize`
- Entonces se persiste un `state` en Redis con TTL y la respuesta incluye la URL de autorización del proveedor

#### Scenario: Authorize sobre conector ajeno o inexistente
- Dado un conector inexistente o de otra organización
- Cuando se llama `GET /connectors/{id}/authorize`
- Entonces la API responde `404` y no se genera ningún `state`

#### Scenario: Authorize sobre conector api_token
- Dado un conector activo con `credential_kind=api_token`
- Cuando se llama `GET /connectors/{id}/authorize`
- Entonces la API responde un error controlado, sin generar `state` ni URL, indicando usar el registro directo de credenciales

### Requirement: Callback exitoso del flujo OAuth

<!-- Errata: Ruta ajustada en design por requisito técnico OAuth (redirect_uri estático). La ruta scoped `GET /connectors/{id}/callback` se reemplaza por la ruta global `GET /api/v1/connectors/oauth/callback`; el `state` transporta la referencia al conector. -->
El callback (ruta global `GET /api/v1/connectors/oauth/callback`) DEBE validar el `state` contra Redis (existe, no vencido, corresponde al conector y usuario esperados) ANTES de canjear el código. Tras un canje exitoso, DEBE cifrar los tokens recibidos, crear o actualizar la `ConnectedAccount` y su `ConnectionCredentials`, y DEBE invalidar (eliminar) el `state` usado para que no pueda reutilizarse.

#### Scenario: Callback válido registra la cuenta y cifra los tokens
- Dado un `state` válido y vigente en Redis para un conector y usuario
- Cuando el proveedor redirige al callback con `code` y ese `state`
- Entonces se crea/actualiza la `ConnectedAccount` con sus credenciales cifradas, y el `state` queda invalidado

#### Scenario: Reutilización del state es rechazada
- Dado un `state` que ya fue consumido por un callback exitoso
- Cuando se reintenta el callback con el mismo `state`
- Entonces la API rechaza la petición sin crear ni actualizar ninguna cuenta

### Requirement: Error y expiración del state en el callback

Si el `state` no existe en Redis (vencido o inválido) o no coincide con el conector/usuario esperado, el callback DEBE responder con un error controlado y NO DEBE crear ni modificar ninguna `ConnectedAccount` ni `ConnectionCredentials`. Si el proveedor reporta un error en el callback (ej. el usuario canceló la autorización), la API DEBE responder un error controlado sin dejar registros a medias.

#### Scenario: State expirado
- Dado un `state` cuyo TTL en Redis ya venció
- Cuando llega un callback con ese `state`
- Entonces la API responde error, sin crear cuenta ni credenciales

#### Scenario: State no coincide (posible manipulación)
- Dado un callback con un `state` que no corresponde al conector/usuario que lo generó
- Cuando se procesa el callback
- Entonces la API rechaza la petición sin registrar nada

#### Scenario: El proveedor reporta error o cancelación
- Dado un callback con un parámetro de error del proveedor (el usuario canceló el consentimiento)
- Cuando se procesa el callback
- Entonces la API responde un error controlado, sin crear cuenta ni credenciales

### Requirement: Cifrado de tokens en reposo y no exposición

`access_token`/`refresh_token` DEBEN cifrarse con Fernet (clave simétrica desde variable de entorno) antes de persistirse en `ConnectionCredentials`. Los tokens (cifrados o en claro) NUNCA DEBEN aparecer en respuestas de la API ni en logs de la aplicación.

#### Scenario: Tokens cifrados en base de datos
- Dado un callback exitoso que registra credenciales
- Cuando se inspecciona la fila de `ConnectionCredentials`
- Entonces `access_token_enc`/`refresh_token_enc` están cifrados, no en texto plano

#### Scenario: Tokens ausentes en la respuesta de la API
- Dado una `ConnectedAccount` con credenciales asociadas
- Cuando se consulta `GET /connectors/{id}/accounts`
- Entonces la respuesta NO incluye el token de acceso ni el de refresco, cifrado o en claro

### Requirement: Listado y desconexión de cuentas conectadas

`DELETE /api/v1/connected-accounts/{id}` DEBE permitir al usuario dueño de la cuenta desconectarla (borrado suave de `ConnectedAccount` y sus `ConnectionCredentials`). Roles `admin`/`manager` DEBEN poder desconectar cuentas de otros miembros de su propia organización.

#### Scenario: Usuario desconecta su propia cuenta
- Dado una `ConnectedAccount` propia del usuario
- Cuando llama `DELETE /connected-accounts/{id}`
- Entonces la cuenta y sus credenciales quedan soft-deleted

#### Scenario: Admin desconecta la cuenta de otro miembro
- Dado una `ConnectedAccount` de un `member` de la misma organización
- Cuando un admin llama `DELETE /connected-accounts/{id}`
- Entonces la cuenta queda desconectada

#### Scenario: Member no puede desconectar la cuenta de otro
- Dado una `ConnectedAccount` de otro `member`
- Cuando un `member` distinto intenta `DELETE /connected-accounts/{id}` sobre ella
- Entonces la API responde `403`

### Requirement: Contratos de API envueltos {data, message, meta}

Toda respuesta exitosa de `/api/v1/connectors` y rutas asociadas DEBE seguir el envelope estándar del backend (`api-conventions`): `data` en recurso único/lista, `meta{total,...}` en listas, `message` en acciones (crear/editar/borrar/desconectar). Los errores DEBEN seguir `{detail, code, status}`.

#### Scenario: Respuesta de creación con message
- Dado un admin que crea un conector
- Cuando `POST /connectors` responde `201`
- Entonces el cuerpo es `{"data": {...}, "message": "..."}`

#### Scenario: Respuesta de listado con meta
- Dado conectores existentes
- Cuando se llama `GET /connectors`
- Entonces el cuerpo es `{"data": [...], "meta": {"total": n}}`

### Requirement: Provisión de credenciales por API token para conectores sin flujo OAuth

Para conectores cuyo proveedor NO usa el baile OAuth `authorize`/`callback` (ej. Jira Cloud con API token), el sistema DEBE exponer una operación que reciba el identificador de cuenta externa y el token, cifre el token con Fernet y cree o actualice la `ConnectedAccount` y su `ConnectionCredentials` con `credential_kind = api_token` (contrato del cambio 17), `access_token_enc` = token cifrado, `refresh_token_enc = null`. Esta operación DEBE estar gateada a roles `admin`/`manager`, DEBE ser scoped a la organización del conector, y el token NUNCA DEBE aparecer en la respuesta ni en logs.

#### Scenario: Admin provee un API token
- GIVEN un conector Jira activo de la organización del admin
- WHEN el admin provee `email` + `api_token`
- THEN se crea/actualiza la `ConnectedAccount` con su `ConnectionCredentials` cifrada, y la respuesta no incluye el token

#### Scenario: Member no puede proveer credenciales por token
- GIVEN un usuario con rol `member`
- WHEN intenta proveer un API token para un conector
- THEN la API responde `403`

#### Scenario: Conector de otra organización
- GIVEN un conector Jira de la organización A
- WHEN un admin de la organización B intenta proveer un token para ese conector
- THEN la API responde `404`

#### Scenario: Reenvío del mismo token no duplica la cuenta
- GIVEN una `ConnectedAccount` ya provista por token para una cuenta externa dada
- WHEN se repite la operación con un token nuevo para la MISMA cuenta externa
- THEN se actualizan las credenciales existentes sin crear una fila duplicada

## Preguntas abiertas para design

- **Visibilidad de `GET /connectors/{id}/accounts` por rol**: el proposal solo confirma "admin/manager configura; member conecta su cuenta"; no especifica si un miembro sin rol admin/manager puede ver cuentas conectadas de OTROS miembros o solo las propias. Este spec asume "solo propias" para member (ver tabla de alcance); el diseño DEBE ratificar esta regla.
- **Método HTTP exacto del callback** (`GET` vs `POST`, según si el proveedor redirige por query string o hace back-channel): el proposal no lo fija; se asume `GET` (patrón estándar de redirect OAuth2 Authorization Code), a confirmar en design.
- **Valores exactos del enum `status`** de `Connector`/`ConnectedAccount` (ej. `active|expired|revoked|error`): el proposal menciona el campo pero no sus valores; el diseño DEBE definir el enum estable.

## Referencias

- `openspec/changes/14-integration-ports/proposal.md`
- `openspec/specs/integration-ports/spec.md` (puertos, registro, adaptador fake, cifrado)
- `openspec/specs/api-conventions/spec.md` (envelope, formato de errores)
- `openspec/specs/multi-tenancy/spec.md` (aislamiento por `organization_id`, `require_role`)
