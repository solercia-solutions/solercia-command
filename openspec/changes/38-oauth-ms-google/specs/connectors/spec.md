# Delta for connectors

<!-- Causa raíz: `service.py:376` cae en `OAUTH_REDIRECT_ALLOWLIST[0]` (SPA en :4200) como `redirect_uri` por defecto; el front nunca envía `redirect_uri`; el callback real `GET /api/v1/connectors/oauth/callback` (`router.py:245`) no está en esa allowlist. -->

## MODIFIED Requirements

### Requirement: Inicio del flujo OAuth (authorize)

`GET /api/v1/connectors/{id}/authorize` DEBE generar un `state` (CSRF) único con TTL en Redis y responder con la URL de autorización del proveedor. El `redirect_uri` enviado DEBE derivarse de una URL base de callback configurable por entorno (`OAUTH_CALLBACK_BASE_URL`), apuntando SIEMPRE a `GET /api/v1/connectors/oauth/callback`; NUNCA DEBE tomarse de `OAUTH_REDIRECT_ALLOWLIST[0]`, que queda reservada solo para `redirect_to`. DEBE responder `404` si el conector no existe o es de otra organización. Solo aplica a `credential_kind=oauth`; sobre `api_token` DEBE responder un error controlado.
(Previously: `redirect_uri` caía por defecto en `OAUTH_REDIRECT_ALLOWLIST[0]`, una página SPA que nunca canjea el `code`.)

#### Scenario: Authorize genera redirect_uri hacia el callback backend

- Dado un conector activo `oauth` de la organización del usuario
- Cuando llama `GET /connectors/{id}/authorize`
- Entonces el `state` con TTL persiste y `redirect_uri` apunta a `<OAUTH_CALLBACK_BASE_URL>/api/v1/connectors/oauth/callback`, nunca a la allowlist del frontend

#### Scenario: Authorize sobre conector ajeno o inexistente

- Dado un conector inexistente o de otra organización
- Cuando se llama `GET /connectors/{id}/authorize`
- Entonces la API responde `404` y no se genera ningún `state`

#### Scenario: Authorize sobre conector api_token

- Dado un conector activo con `credential_kind=api_token`
- Cuando se llama `GET /connectors/{id}/authorize`
- Entonces la API responde un error controlado, sin generar `state` ni URL

## ADDED Requirements

### Requirement: Redirección final del callback hacia el frontend

Tras un canje exitoso, el callback DEBE redirigir a `redirect_to` (validado contra `OAUTH_REDIRECT_ALLOWLIST`) con indicador de éxito. Ante error (state inválido/vencido, proveedor no configurado, o cancelación del usuario), DEBE redirigir a `redirect_to` con un código estable (`oauth_state_invalid`, `provider_not_registered`, `oauth_provider_error`, `oauth_unexpected_error`) para que el frontend muestre el mensaje es-CO correspondiente, SIN crear ni modificar cuenta o credenciales.

#### Scenario: Canje exitoso redirige con éxito

- Dado un `state` válido y un canje exitoso de código por tokens
- Cuando el callback persiste la cuenta cifrada
- Entonces redirige a `redirect_to` con indicador de éxito

#### Scenario: Proveedor no configurado

- Dado un proveedor sin `client_id`/`client_secret` configurados
- Cuando se procesa el callback
- Entonces redirige con `error=provider_not_registered` y mensaje es-CO accionable

#### Scenario: Usuario canceló la autorización

- Dado un callback con el parámetro de error del proveedor
- Cuando se procesa
- Entonces redirige con `error=oauth_provider_error`, sin crear cuenta ni credenciales

### Requirement: Prueba de conexión post-OAuth (test_connection)

`POST /connectors/{id}/accounts/{account_id}/test` DEBE descifrar las credenciales, refrescar el token si `expires_at` venció, y ejecutar una operación read-only real del adaptador (perfil/calendario en M365 y Google, listado de proyectos en Jira). DEBE responder éxito con detalle de muestra o error accionable, gateado al dueño de la cuenta o a `admin`/`manager` de la organización.

#### Scenario: Prueba exitosa muestra detalle

- Dado una `ConnectedAccount` con token vigente
- Cuando su dueño llama `POST .../test`
- Entonces responde éxito con un detalle de muestra de la operación read-only

#### Scenario: Token vencido se refresca antes de probar

- Dado una `ConnectedAccount` con `expires_at` vencido
- Cuando se llama `POST .../test`
- Entonces el adaptador refresca el token, persiste las credenciales rotadas, y la prueba procede con el token nuevo

#### Scenario: Refresco fallido responde error accionable

- Dado una `ConnectedAccount` cuyo refresco falla (`refresh_token` revocado)
- Cuando se llama `POST .../test`
- Entonces responde un error accionable indicando reconectar, sin sobrescribir credenciales

#### Scenario: Member no puede probar la cuenta de otro

- Dado una `ConnectedAccount` de otro `member` de la misma organización
- Cuando un `member` distinto llama `POST .../test`
- Entonces la API responde `403`

### Requirement: Documentación de variables de entorno OAuth (.env.example)

`backend/.env.example` DEBE existir y documentar `M365_CLIENT_ID`/`M365_CLIENT_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET`, `OAUTH_CALLBACK_BASE_URL` y `OAUTH_REDIRECT_ALLOWLIST` con valores de ejemplo (placeholders), SIN secretos reales.

#### Scenario: .env.example documenta las variables sin secretos reales

- Dado el repositorio backend
- Cuando se inspecciona `backend/.env.example`
- Entonces existe con placeholders para las variables OAuth, sin valores reales

## Referencias

- `openspec/specs/connectors/spec.md` — línea base; CRUD, `credential_kind`, cifrado, permisos y el sink de refresco en lectura quedan intactos
- `openspec/changes/38-oauth-ms-google/proposal.md`
