# google-adapter Specification

> **Origen**: cambio [16-adapter-google](../../proposal.md)

## Propósito

Adaptador `google` que implementa tres puertos read-only del núcleo `integration-ports` (14) —`MailReaderPort`, `CalendarReaderPort`, `MeetingNotesReaderPort`— contra Gmail, Calendar y Drive (transcripciones de Meet), reutilizando `IntegrationAdapter`, `OAuthTokens` y el registro import-time del 14 sin editar el núcleo. Es la contraparte del adaptador Microsoft 365 (15): ambos comparten el mismo contrato de puerto donde la semántica coincide.

## Ubicación

`backend/app/integrations/adapters/google/`: `__init__.py` (registro import-time), `adapter.py` (`provider="google"`, `capabilities`, `port_for`), `oauth.py` (authorize/exchange/refresh + userinfo→correo), `client.py` (transporte `httpx` inyectable + Bearer/paginación/errores), `mail.py`, `calendar.py`, `meeting_notes.py` (mapeo API→DTO), `mime.py` (parseo MIME base64url) y `errors.py` (taxonomía de errores). Registro vía import en `app/db_init.py` (precedente `adapters/fake.py`). (Errata: layout alineado al design por decisión del orquestador)

## Mapeo capacidad → API → scope

| Puerto (14) | API Google | Scope | Endpoint de lectura |
|---|---|---|---|
| `MailReaderPort` | Gmail API | `gmail.readonly` | `users.messages.list`/`get` |
| `CalendarReaderPort` | Calendar API | `calendar.readonly` | `events.list` (`timeMin`/`timeMax`) |
| `MeetingNotesReaderPort` | Drive API + Docs export | `drive.readonly` | `files.list` ("Meet Recordings") + `files.export` |

`ExternalTaskReaderPort`/`TicketReaderPort`: sin implementación Google (ver requisito de Tasks).

## Requisitos

### Requirement: Registro y protocolo de adaptador uniforme

El adaptador `google` DEBE registrarse en `registry.py` en import-time (`register_adapter`) sin editar `ports.py`, `oauth.py` ni otro archivo del núcleo, y DEBE declarar `provider="google"` y `capabilities={mail, calendar, meeting_notes}` (`Capability` del 14).

#### Scenario: El adaptador aparece por su provider
- Dado el módulo del adaptador Google importado en el arranque
- Cuando el núcleo llama `get_adapter("google")`
- Entonces obtiene la instancia registrada sin que se haya editado ningún archivo del núcleo

#### Scenario: Capacidad no declarada queda excluida
- Dado el adaptador con `capabilities={mail, calendar, meeting_notes}`
- Cuando el núcleo pide `port_for(Capability.external_tasks)`
- Entonces el adaptador no expone ese puerto

### Requirement: Handshake OAuth de Google mapeado a OAuthTokens

`authorize_url`, `exchange_code` y `refresh` DEBEN operar contra los endpoints OAuth 2.0 de Google con scopes exclusivamente `*.readonly`, devolviendo `OAuthTokens` cuyo `external_account_id` es el correo de la cuenta Google conectada.

#### Scenario: Canje de código devuelve el correo como identidad
- Dado un `code` válido de autorización de Google
- Cuando el adaptador ejecuta `exchange_code`
- Entonces devuelve `OAuthTokens` con `external_account_id` igual al correo autenticado

#### Scenario: Scopes solicitados son de solo lectura
- Dado la URL generada por `authorize_url`
- Cuando se inspeccionan sus scopes
- Entonces todos son `gmail.readonly`/`calendar.readonly`/`drive.readonly`; ninguno de escritura

### Requirement: Resiliencia ante errores transitorios de la API de Google

Ante `401` por token vencido, el adaptador DEBE invocar `refresh` y reintentar la operación una vez con el token renovado. Ante `429` o cuota excedida, DEBE aplicar backoff (respetando `Retry-After` si el proveedor lo envía) antes de reintentar.

#### Scenario: 401 dispara refresh y reintento único
- Dado un `access_token` vencido
- Cuando una lectura a Gmail/Calendar/Drive responde `401`
- Entonces el adaptador renueva el token vía `refresh` y reintenta la operación una única vez

#### Scenario: 429 respeta backoff
- Dado que la API responde `429`
- Cuando el adaptador procesa la respuesta
- Entonces espera el intervalo de backoff (o `Retry-After`) antes de reintentar

### Requirement: Lectura de correo vía Gmail con parseo MIME

`MailReaderPort.list_messages` DEBE listar mensajes vía Gmail API y decodificar el payload MIME (base64url, multiparte) a `MailMessage.body_text`/`snippet`. Labels y `threadId` de Gmail son metadato interno del adaptador; `MailMessage` NO expone carpeta (divergencia frente a `mailFolders` de Graph).

#### Scenario: Mensaje multiparte se decodifica a texto plano
- Dado un mensaje Gmail con payload MIME multiparte (HTML+texto, base64url)
- Cuando el adaptador lo mapea a `MailMessage`
- Entonces `body_text` contiene el texto decodificado, sin base64 ni MIME crudo

#### Scenario: Labels no se traducen a carpeta
- Dado un mensaje Gmail con varias labels asignadas
- Cuando se mapea a `MailMessage`
- Entonces el DTO no expone ningún campo de carpeta; las labels quedan fuera del contrato común

### Requirement: Lectura de calendario vía Calendar API

`CalendarReaderPort.list_events` DEBE consultar `events.list` acotado por `timeMin`/`timeMax` derivados de `since`/`limit`, mapeando cada evento a `CalendarEvent` (organizador, asistentes, horario).

#### Scenario: since/limit acotan la consulta
- Dado `since` y `limit` provistos al puerto
- Cuando el adaptador consulta `events.list`
- Entonces traduce `since` a `timeMin` y limita los eventos devueltos según `limit`

### Requirement: Transcripciones de Meet vía Drive (best-effort)

`MeetingNotesReaderPort.list_notes` DEBE buscar en Drive la carpeta "Meet Recordings" y exportar el Doc de transcripción a `MeetingNote.transcript`. Como la transcripción depende de que el organizador la haya activado y de permisos sobre su Drive, la ausencia de Doc DEBE devolverse como lista vacía, nunca como error.

#### Scenario: Transcripción disponible se exporta
- Dado un Doc de transcripción accesible en "Meet Recordings"
- Cuando el adaptador lista notas de reunión
- Entonces devuelve `MeetingNote` con `transcript` poblado desde el export del Doc

#### Scenario: Sin transcripción del organizador, degrada sin error
- Dado que el organizador no activó/compartió la transcripción
- Cuando el adaptador no encuentra el Doc esperado en Drive
- Entonces devuelve una lista vacía, sin lanzar error

### Requirement: Capacidad no disponible declarada explícitamente

Cuando el adaptador no puede resolver una capacidad declarada por causa ajena al dato (ej. sin permiso sobre el Drive del organizador para `meeting_notes`), DEBE señalarlo como `capability_unavailable` en lugar de fallar de forma silenciosa o genérica, sin afectar las demás capacidades.

#### Scenario: Falta de permiso Drive se reporta como capacidad no disponible
- Dado que la cuenta conectada carece de permiso sobre el Drive del organizador
- Cuando se invoca `MeetingNotesReaderPort`
- Entonces el adaptador responde `capability_unavailable` para esa cuenta, sin afectar mail/calendar

### Requirement: Frontera de solo lectura estricta

El adaptador Google NO DEBE declarar ni exponer ninguna operación de escritura hacia Gmail, Calendar o Drive (enviar correo, crear evento, modificar archivo).

#### Scenario: Sin método de escritura en el adaptador
- Dado el adaptador Google completo
- Cuando se revisan sus métodos públicos
- Entonces ninguno crea, edita ni envía datos hacia Google; solo lectura y el handshake OAuth

### Requirement: Transporte HTTP inyectable sin SDK — cero red en CI

El adaptador DEBE usar `httpx` con transporte inyectable (stub con fixtures en pruebas, real en producción) y NO DEBE depender del SDK oficial de Google. Las pruebas de contrato, mapeo DTO y OAuth DEBEN correr contra fixtures.

#### Scenario: Pruebas del adaptador corren sin red
- Dado el transporte stub cargado con fixtures de Gmail/Calendar/Drive
- Cuando se ejecuta la suite del adaptador Google
- Entonces ninguna prueba realiza una llamada de red real

### Requirement: Google Tasks fuera del primer corte

El adaptador Google NO DEBE declarar la capacidad `external_tasks` en este cambio; `ExternalTaskReaderPort` queda sin implementación Google hasta una extensión futura, agregable sin editar el núcleo.

#### Scenario: external_tasks ausente de las capacidades declaradas
- Dado el adaptador Google registrado
- Cuando se inspeccionan sus `capabilities`
- Entonces `external_tasks` no está incluida

## Referencias

- `openspec/changes/16-adapter-google/proposal.md`
- `openspec/changes/14-integration-ports/specs/integration-ports/spec.md` (puertos, registro, protocolo de adaptador — contrato consumido, no redefinido)
- `openspec/changes/14-integration-ports/specs/connectors/spec.md` (CRUD/OAuth/cifrado ya cubiertos por el núcleo)
- `openspec/changes/14-integration-ports/design.md` (DTOs/`ports.py` reales: `MailMessage`, `CalendarEvent`, `MeetingNote`, `OAuthTokens`, `Capability`)
- `openspec/changes/15-adapter-microsoft365/proposal.md` (adaptador hermano — simetría de puertos correo/calendario/transcripciones; divergencias documentadas arriba)
