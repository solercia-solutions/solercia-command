# adapter-microsoft365 Specification

> **Origen**: cambio [15-adapter-microsoft365](../../../15-adapter-microsoft365/proposal.md)
> **Depende de** (no se redefine aquí): `openspec/changes/14-integration-ports/specs/integration-ports/spec.md`, `openspec/changes/14-integration-ports/specs/connectors/spec.md` (puertos, registro, protocolo de adaptador, cifrado, modelo Connector/ConnectedAccount/ConnectionCredentials)

## Propósito

Primer adaptador real sobre el núcleo hexagonal del 14: Microsoft Graph, **solo lectura**, autorización **delegada** (Entra ID/Azure AD). Implementa `MailReaderPort`, `CalendarReaderPort`, `ExternalTaskReaderPort` (solo Planner) y `MeetingNotesReaderPort` (con degradación). `TicketReaderPort` queda fuera de este adaptador (lo cubren 17–18). Cero cambios al núcleo del 14; ninguna operación de escritura hacia Graph.

## Ubicación

`backend/app/integrations/adapters/microsoft365.py` (o paquete equivalente), auto-registrado en import-time con `provider="microsoft365"`, mismo precedente que `adapters/fake.py`.

## Requisitos

### Requirement: Registro del adaptador sin editar el núcleo
El adaptador `microsoft365` DEBE implementar el protocolo de adaptador del 14 y auto-registrarse en `registry.py` en import-time bajo `provider="microsoft365"`, sin modificar `ports.py`, `oauth.py` ni `registry.py`. DEBE declarar únicamente correo, calendario, tareas externas y notas de reunión; NO DEBE declarar la capacidad de tickets.

#### Scenario: Registro sin tocar el núcleo ni declarar tickets
- Dado el módulo del adaptador `microsoft365` importado por la aplicación
- Cuando el núcleo consulta el registro por `provider="microsoft365"`
- Entonces obtiene la instancia sin que se haya editado ningún archivo del núcleo
- Y `tickets` no aparece entre sus capacidades declaradas

### Requirement: Handshake OAuth delegado de Entra ID
El adaptador DEBE implementar `authorize_url`, `exchange_code` y `refresh` contra `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/*`, con `tenant=organizations` por defecto y configurable por variable de entorno. DEBE solicitar solo scopes delegados (`openid profile email offline_access User.Read` + los de cada capacidad); NO DEBE solicitar permisos de aplicación en esta ola.

#### Scenario: Tenant por defecto y override por configuración
- Dado ningún override de tenant
- Cuando el núcleo pide `authorize_url`
- Entonces la URL usa `organizations`
- Y si hay un tenant fijo por variable de entorno, la URL usa ese tenant en su lugar

### Requirement: Token expirado se refresca vía credenciales del 14
Antes de cada llamada a Graph, el adaptador DEBE verificar la vigencia del token (vía las credenciales del 14) y, si venció, DEBE refrescarlo con `refresh` antes de reintentar la llamada original, sin intervención del llamador. Si el `refresh_token` está revocado, DEBE responder un error controlado indicando reconexión, sin caerse.

#### Scenario: Refresco automático o error controlado
- Dado un `access_token` vencido para una cuenta conectada
- Cuando el adaptador necesita leer una capacidad de Graph
- Entonces refresca el token primero y completa la llamada original
- Y si el `refresh_token` está revocado, responde error controlado de reconexión

### Requirement: Lectura de correo y calendario con ventana y paginación
El adaptador DEBE implementar `MailReaderPort` sobre `/me/messages` (scope `Mail.Read`) y `CalendarReaderPort` sobre `/me/calendarView`/`/me/events` (scope `Calendars.Read`), aceptando `since`/`limit` de cada puerto y devolviendo los DTOs del 14. DEBE recorrer `@odata.nextLink` hasta agotar páginas o alcanzar `limit`, sin exponer paginación de Graph en los DTOs.

#### Scenario: Resultados dentro de la ventana, multi-página
- Dado un fixture de Graph con resultados en dos páginas dentro de `since`
- Cuando se invoca el puerto con `since`/`limit`
- Entonces devuelve los DTOs agregados de ambas páginas, respetando `limit`

#### Scenario: Sin resultados en la ventana
- Dado un fixture sin mensajes/eventos dentro de `since`
- Cuando se invoca el puerto
- Entonces devuelve una lista vacía, no un error

### Requirement: Lectura de tareas Planner (sin Microsoft To Do)
El adaptador DEBE implementar `ExternalTaskReaderPort` SOLO sobre `/me/planner/tasks` y `/planner/plans/{id}/tasks` (scope `Tasks.Read`). NO DEBE implementar Microsoft To Do en este cambio (extensión futura fuera de alcance). Si el tenant no tiene Planner/Grupos M365, DEBE devolver lista vacía, NUNCA error.

#### Scenario: Tenant con y sin Planner
- Dado un fixture de `/me/planner/tasks` con tareas
- Cuando se invoca el puerto
- Entonces devuelve los DTOs mapeados de Planner
- Y si el tenant no tiene grupos/planes, devuelve lista vacía sin lanzar error

### Requirement: Notas de reunión con degradación por falta de consentimiento
El adaptador DEBE implementar `MeetingNotesReaderPort` sobre `/me/onlineMeetings/{id}/transcripts` (+ `/content`), usando SOLO permisos delegados (`OnlineMeetingTranscript.Read.All` + `OnlineMeetings.Read`); NO DEBE intentar el modo de permiso de aplicación en esta ola. Si el tenant no otorgó el admin consent requerido, `meeting_notes` DEBE degradar a "no disponible" y responder `capability_unavailable`, sin afectar correo, calendario ni tareas.

#### Scenario: Consentimiento otorgado
- Dado un tenant con admin consent para transcripciones
- Cuando se invoca `MeetingNotesReaderPort`
- Entonces devuelve el DTO de transcripción mapeado del fixture

#### Scenario: Consentimiento no otorgado degrada sin afectar el resto
- Dado un tenant sin admin consent para `OnlineMeetingTranscript.Read.All`
- Cuando se invoca `MeetingNotesReaderPort`
- Entonces responde `capability_unavailable`
- Y correo, calendario y tareas del mismo adaptador siguen funcionando

### Requirement: Backoff ante 429 con Retry-After
Ante una respuesta `429` de Graph, el adaptador DEBE honrar el header `Retry-After` (esperar al menos ese tiempo) antes de reintentar, y DEBE aplicar backoff ante 429 repetidos en vez de reintentar de inmediato o en bucle infinito.

#### Scenario: Retry-After se respeta y agotamiento controlado
- Dado que Graph responde `429` con `Retry-After: N`
- Cuando el adaptador reintenta
- Entonces espera al menos `N` y completa la llamada al recibir éxito
- Y si los 429 se repiten más allá del límite de reintentos, responde error controlado en vez de bloquearse

### Requirement: Frontera solo-lectura estricta hacia Graph
El adaptador `microsoft365` NUNCA DEBE invocar un endpoint de escritura de Graph (enviar correo, crear/editar evento, crear/editar tarea, responder) en ninguna capacidad.

#### Scenario: Ninguna capacidad invoca escritura
- Dado el código del adaptador `microsoft365`
- Cuando se revisan las llamadas HTTP que realiza
- Entonces ninguna es `POST`/`PATCH`/`PUT`/`DELETE` hacia Graph

## Referencias
- `openspec/changes/15-adapter-microsoft365/proposal.md`
- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md`
- `openspec/changes/14-integration-ports/specs/connectors/spec.md`
