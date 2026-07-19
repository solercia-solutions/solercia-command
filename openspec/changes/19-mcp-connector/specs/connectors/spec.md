# Delta for connectors

> Origen: cambio [19-mcp-connector](../../proposal.md). Extiende el modelo de [14-integration-ports/connectors](../../../14-integration-ports/specs/connectors/spec.md). El valor `credential_kind = oauth|api_token` es propiedad del delta del cambio [17-adapter-glpi](../../../17-adapter-glpi/proposal.md); este delta solo AGREGA `none` sobre ese mismo enum (la spec del 17 aún está pendiente al momento de escribir esta).

## ADDED Requirements

### Requirement: Extensión del enum `credential_kind` con el valor `none`

El modelo de credenciales de conector DEBE admitir `credential_kind = none`, sumado al conjunto (`oauth`, `api_token`) que aporta el cambio 17-adapter-glpi, para conectores cuyo servidor externo no requiere ninguna credencial (ej. un servidor MCP público sin autenticación). Esta extensión NO redefine los valores `oauth`/`api_token`; únicamente agrega `none` como valor adicional del mismo enum.

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

## Referencias
- `openspec/changes/19-mcp-connector/proposal.md`
- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (base)
- `openspec/changes/17-adapter-glpi/proposal.md` (dueño de `credential_kind = oauth|api_token`; coordinación, spec del 17 aún pendiente)
