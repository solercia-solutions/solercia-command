# Proposal: 16 · Adaptador Google (solo lectura sobre los puertos del 14)

## Intent

La plataforma ya tiene el núcleo hexagonal solo-lectura y los conectores OAuth del cambio **14-integration-ports**. Este cambio agrega el **primer adaptador real de Google**: implementa los puertos del 14 contra Gmail, Google Calendar y las transcripciones de reuniones de Meet (guardadas en Drive), en **solo lectura**. El requerimiento de negocio (OLA 2, ítem 2b) exige que Outlook y Gmail **compartan interfaces** cuando la semántica coincida; aquí se verifica contra los puertos del 14 y se **documentan las divergencias reales** entre Microsoft Graph y las APIs de Google. Se registra en import-time como el adaptador `fake`: **cero ediciones al núcleo del 14**. Entregable **backend-only**.

## Scope

### In Scope
- Adaptador `google` en `backend/app/integrations/adapters/google/` que se **auto-registra** (precedente del `fake` del 14).
- Implementación de **3 puertos read-only**: `MailReaderPort` (Gmail), `CalendarReaderPort` (Calendar), `MeetingNotesReaderPort` (Meet vía Drive + Docs).
- **Handshake OAuth de Google** (`authorize_url` / `exchange_code` / `refresh`) con scopes de solo lectura, mapeado a `OAuthTokens` (`external_account_id` = correo de la cuenta).
- **Mapeo API Google → DTO agnóstico del 14** (`MailMessage`, `CalendarEvent`, `MeetingNote`).
- **Fixtures + transporte HTTP inyectable** para pruebas sin red en CI.
- **Documentación de divergencias** con el adaptador Microsoft (15).

### Out of Scope
- Escritura hacia Google (enviar correo, crear evento) — los puertos del 14 son read-only.
- **Google Tasks** (evaluado abajo; diferido con justificación).
- Cambios al núcleo del 14 (puertos, registro, OAuth genérico, cifrado, DTOs) — se **consumen**, no se redefinen.
- Almacenamiento/clasificación de insumos (cambio 22). Tickets/casos (no aplica a Google).
- Meet REST API como fuente primaria (se documenta como alternativa; primario = Drive). Frontend.

## Capabilities

### New Capabilities
- `google-adapter`: adaptador solo-lectura del proveedor Google sobre los puertos del 14 — mapeo capacidad→API→scope, DTOs, OAuth de Google y divergencias con el adaptador Microsoft.

### Modified Capabilities
- None. (No cambia requisitos de `integration-ports` ni `connectors`; los implementa.)

## Approach

### Mapeo capacidad → API Google → scope

| Puerto del 14 | API Google | Lectura | Scope | Clasificación Google |
|---|---|---|---|---|
| `MailReaderPort` | Gmail API | `users.messages.list`/`get` | `gmail.readonly` | **Restringido** (verificación + evaluación CASA) |
| `CalendarReaderPort` | Calendar API | `events.list` (`timeMin`/`timeMax`) | `calendar.readonly` | **Sensible** (verificación) |
| `MeetingNotesReaderPort` | Drive API (+ Docs export) | `files.list` ("Meet Recordings") + `files.export` | `drive.readonly` | **Restringido** (verificación + CASA) |
| `ExternalTaskReaderPort` | (sin equivalente Planner) | — | — | Fuera del primer corte (ver Google Tasks) |
| `TicketReaderPort` | N/A | — | — | No aplica a Google |

Adaptador declara `provider="google"`, `capabilities={mail, calendar, meeting_notes}`. Transporte HTTP async inyectable (fixtures en test, real en prod). Reutiliza `connectors`/`connected_accounts`/`connection_credentials` del 14 — **sin migración ni tablas nuevas**.

### Divergencias Microsoft Graph (15) ↔ Google (16)

| Eje | Graph | Google | Efecto en el puerto |
|---|---|---|---|
| Organización de correo | Carpetas (`mailFolders`) jerárquicas | **Etiquetas** (labels): varias por mensaje, sin carpeta única | El DTO no expone carpeta; el filtro por "ubicación" diverge → detalle interno del adaptador |
| Hilos | `conversationId` | `threadId` (hilo nativo) | Cabe como metadato opcional; `external_id` es la identidad |
| Cuerpo del mensaje | `body.content` (JSON limpio) | **payload MIME base64url**, requiere parseo de partes | Google decodifica/normaliza MIME → `body_text`/`snippet` |
| Transcripciones | `onlineMeetings/transcripts` u OneDrive | **Meet las guarda como Google Doc en Drive "Meet Recordings"**; sin endpoint "meeting notes" directo | Google: buscar en Drive + exportar Doc → `MeetingNote.transcript` |
| Tareas | Planner (`/planner/tasks`) | Sin Planner; Google Tasks es lista **personal**, no tablero de equipo | Google no declara `external_tasks` en el primer corte |

### Google Tasks — decisión

**Fuera del primer corte.** Google Tasks (`tasks.readonly`) es una lista de pendientes personal atada al usuario, no un tablero de proyecto como Planner; no alimenta la vista ejecutiva (carga por persona a nivel de proyecto) como sí lo hace Planner. Mapea a `ExternalTaskReaderPort` pero aporta poco valor y suma otro scope. Se difiere; se añade luego **sin tocar el núcleo** (registro import-time).

### Estrategia de pruebas (sin red en CI)

- **Fixtures** JSON de respuestas reales en `backend/tests/fixtures/google/`: mensaje Gmail MIME multiparte (base64url, HTML+texto), evento Calendar con asistentes, carpeta "Meet Recordings" + Doc de transcripción.
- **Transporte HTTP inyectable** (stub) que devuelve esos fixtures → cero red en CI; el adaptador real solo añade el transporte HTTP mockeado.
- Pruebas de **contrato del 14** reutilizadas (misma forma que el `fake`); pruebas de **mapeo DTO** (MIME→`MailMessage`, evento→`CalendarEvent`, Doc→`MeetingNote`); **OAuth** de Google simulado (`exchange_code`/`refresh` contra fixtures → `OAuthTokens`).

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `backend/app/integrations/adapters/google/` | New | Adaptador: `authorize_url`/`exchange_code`/`refresh` + puertos mail/calendar/meeting_notes |
| `backend/app/db_init.py` (o `adapters/__init__`) | Modified | Import del adaptador Google para auto-registro import-time |
| `backend/app/config.py` | Modified | `GOOGLE_OAUTH_CLIENT_ID/SECRET`, scopes readonly, `redirect_uri` (env) |
| `backend/tests/fixtures/google/` | New | Payloads Gmail/Calendar/Drive/Docs para pruebas sin red |
| `backend/requirements.txt` | Modified (posible) | Cliente HTTP/SDK Google si se decide en design (preferir `httpx` para controlar el transporte inyectable) |

## Risks

| Riesgo | Prob | Mitigación |
|---|---|---|
| **Verificación de app Google + evaluación CASA** para scopes restringidos (`gmail.readonly`, `drive.readonly`): semanas/meses de proceso + costo anual de evaluación de seguridad de terceros; bloquea el uso con usuarios externos | **Alta** | Declararlo como **riesgo operativo**; en dev/interno usar *test users* (hasta 100) sin verificación; iniciar verificación temprano; evaluar `drive.file`/Meet API para reducir el alcance restringido |
| Transcripciones de Meet dependen de config del tenant (transcripción activada, edición Workspace) y de permisos sobre el Drive del organizador | Med | `meeting_notes` es *best-effort*; si no hay Doc, devolver vacío sin error; documentar prerequisito Workspace |
| Parseo MIME de Gmail frágil (multiparte, codificaciones, adjuntos) | Med | Fixtures con casos reales; normalizar a `body_text` |
| Google reclasifica scopes/políticas | Low | Re-verificar la clasificación de scopes contra la política vigente **en el apply** |
| Filtro label/folder diverge entre Outlook y Gmail | Low | El DTO no expone carpeta; los filtros de ubicación quedan fuera del contrato común del primer corte |

## Rollback Plan

Adaptador aislado y aditivo. Rollback = revertir el merge; sin el import de registro, el proveedor `google` no existe y el núcleo del 14 queda idéntico. **Sin migración** (reutiliza las tablas del 14). Cero impacto en flujos existentes.

## Dependencies

- **14-integration-ports** aplicado (puertos, registro import-time, OAuth genérico, cifrado Fernet, DTOs). Contrato base obligatorio.
- Proyecto de Google Cloud con OAuth client + scopes readonly habilitados (config/env).
- Cliente HTTP async (preferir `httpx`) o SDK de Google — a decidir en design.

## Success Criteria

- [ ] Adaptador `google` registrado import-time **sin editar** el núcleo del 14.
- [ ] Implementa `MailReaderPort`, `CalendarReaderPort`, `MeetingNotesReaderPort` contra fixtures; pasa las pruebas de contrato del 14.
- [ ] OAuth de Google (`authorize`/`exchange_code`/`refresh`) mapeado a `OAuthTokens` con `external_account_id`; solo scopes readonly.
- [ ] Divergencias Graph↔Google documentadas (labels/folders, threads, MIME, ubicación de transcripciones).
- [ ] Decisión de Google Tasks (fuera del primer corte) justificada.
- [ ] **Cero llamadas de red en CI** (transporte HTTP mockeado + fixtures).
- [ ] Riesgo operativo de verificación/CASA declarado.

## Ronda de preguntas de propuesta

> No pude preguntar en vivo (ejecutor delegado). Supuestos a ratificar antes de spec/design:

1. **Meet primario vía Drive**: se asume Drive + Docs export (`drive.readonly`) como fuente primaria de transcripciones —según OLA 2— en lugar del Meet REST API. ¿Se ratifica, o se prefiere el Meet API para reducir el scope restringido de Drive?
2. **Google Tasks**: se asume **fuera** del primer corte (lista personal, no Planner). ¿Se ratifica el diferimiento?
3. **Cliente HTTP**: se asume `httpx` directo (transporte inyectable para fixtures) sobre el SDK oficial de Google. ¿Se confirma en design?
4. **`external_account_id`**: se asume el correo de la cuenta Google como identidad estable de `ConnectedAccount`. ¿Se confirma?
5. **Alcance de verificación**: para el MVP/interno se asume operar con *test users* de Google sin verificación completa de la app. ¿Se acepta esa frontera operativa?
