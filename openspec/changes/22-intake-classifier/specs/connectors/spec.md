# Delta for connectors

> **Origen**: cambio [22-intake-classifier](../../proposal.md). Capacidad existente definida por [14-integration-ports](../../../14-integration-ports/specs/connectors/spec.md).

## ADDED Requirements

### Requirement: Persistencia de credenciales rotadas tras refresco en lectura (sink)

Cuando un puerto de lectura del 14 se invoca sobre una cuenta cuyo token de acceso está vencido (`expires_at` pasado), el adaptador DEBE ejecutar su intercambio de refresco (`refresh`) ANTES de leer, y el sistema DEBE cifrar y persistir las credenciales rotadas resultantes en `ConnectionCredentials` (mismo mecanismo de cifrado Fernet que el callback OAuth), actualizando `expires_at`. Esta persistencia DEBE ocurrir de forma transparente al llamador del puerto (ej. `intake-items` durante un pull), sin requerir una llamada adicional del usuario.

#### Scenario: Token vencido se refresca y persiste antes de leer

- Dado una `ConnectedAccount` cuyo `expires_at` ya venció
- Cuando `intake-items` invoca el puerto de lectura para esa cuenta
- Entonces el adaptador refresca el token, las nuevas credenciales cifradas quedan persistidas en `ConnectionCredentials`, y la lectura procede con el token nuevo

#### Scenario: Refresco fallido no persiste credenciales corruptas

- Dado una `ConnectedAccount` cuyo refresco de token falla (ej. `refresh_token` revocado por el proveedor)
- Cuando se intenta leer a través del puerto
- Entonces las credenciales existentes NO se sobrescriben, la cuenta queda marcada en un estado de error recuperable, y el `IntakeRun` de esa cuenta cierra con `status=error`

#### Scenario: Token vigente no dispara refresco

- Dado una `ConnectedAccount` cuyo `expires_at` aún no vence
- Cuando se invoca el puerto de lectura para esa cuenta
- Entonces no se ejecuta `refresh` ni se modifica `ConnectionCredentials`

## Referencias

- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (requisito "Cifrado de tokens en reposo y no exposición" — mismo mecanismo de cifrado reutilizado aquí; cierra la "Open Question" de renovación de tokens dejada por el 14)
- `openspec/changes/22-intake-classifier/proposal.md`
