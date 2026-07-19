# Delta for connectors

> **Origen**: cambio [17-adapter-glpi](../../proposal.md) sobre [14-integration-ports](../../../14-integration-ports/specs/connectors/spec.md)

## ADDED Requirements

### Requirement: Tipo de credencial del conector (`credential_kind`)

El modelo `Connector` DEBE exponer `credential_kind` (`oauth` | `api_token`), con `oauth` como valor por defecto. El valor DEBE determinar el flujo de autenticación aplicable: `oauth` usa `authorize`/`callback`; `api_token` usa el registro directo de credenciales. El campo DEBE fijarse al crear el conector y NO DEBE cambiarse después sin recrear el conector.

#### Scenario: Conector oauth por defecto
- Dado un admin que crea un conector sin especificar `credential_kind`
- Cuando se persiste
- Entonces `credential_kind` queda en `oauth`

#### Scenario: Conector api_token explícito
- Dado un admin que crea un conector con `credential_kind=api_token`
- Cuando se persiste
- Entonces el conector usa el registro directo de credenciales, no `authorize`/`callback`

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

## MODIFIED Requirements

### Requirement: Inicio del flujo OAuth (authorize)

`GET /api/v1/connectors/{id}/authorize` DEBE generar un `state` (CSRF) único, persistirlo en Redis con TTL asociado al conector y al usuario solicitante, y responder con la URL de autorización del proveedor (construida por el adaptador registrado). DEBE responder `404` si el conector no existe o es de otra organización. Este endpoint SOLO aplica a conectores `credential_kind=oauth`; sobre un conector `api_token` DEBE responder un error controlado indicando que debe usarse el registro directo de credenciales.
(Previously: no distinguía tipo de credencial porque solo existía `oauth`)

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

## Referencias

- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (spec base)
- `openspec/changes/17-adapter-glpi/proposal.md`
