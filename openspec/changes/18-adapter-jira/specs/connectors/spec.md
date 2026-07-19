# Delta for connectors

> **Origen**: cambio [18-adapter-jira](../../proposal.md)
> Este delta CONSUME el contrato `credential_kind` (`oauth`/`api_token`) del cambio **17-adapter-glpi** — 18 NO redefine ese campo ni su enum, solo usa el valor `api_token` para provisionar credenciales de Jira. Si el 17 aún no ha aplicado ese delta al archivar, esta operación queda bloqueada hasta que `credential_kind` exista en el modelo.

## ADDED Requirements

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

## Referencias

- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (modelo base, cifrado Fernet, flujo OAuth)
- `openspec/changes/17-adapter-glpi/proposal.md` (dueño del delta `credential_kind`)
- `openspec/changes/18-adapter-jira/proposal.md`
