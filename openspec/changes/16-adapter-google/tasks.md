# Tasks: 16 · Adaptador Google (Gmail/Calendar/Meet, solo lectura)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1.400–1.800 (fixtures+config+errors ~370 + client ~290 + oauth ~180 + mime/mail ~260 + calendar/meeting_notes ~300 + adapter/registro/docs ~152) |
| Riesgo de presupuesto (400 líneas) | High (agregado del cambio; cada lote individual queda por debajo de 400) |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote 1 (fixtures+config+errores) → Lote 2 (client.py) → Lote 3 (oauth.py) → Lote 4 (mime+mail) → Lote 5 (calendar+meeting_notes) → Lote 6 (adapter+registro+docs+VERIFY final) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, un commit por lote (sin PR) |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota de tamaño por lote**: a diferencia del 14 (donde 2 lotes superaban 400 líneas individualmente), aquí cada lote queda estimado por debajo de 400 líneas; el riesgo High es del **agregado** del cambio (~1.400–1.800 líneas en 6 commits). `delivery_strategy: exception-ok` ya cubre la entrega sin PR; no requiere pregunta adicional antes del apply. Lote 1 es el más cercano al límite (~370) por la cantidad de fixtures — si crece, dividir fixtures de errores en un lote propio.

**Orden serializado 14→15→16**: el apply de este cambio va DESPUÉS del apply de 14 y 15. El Lote 1 incluye una tarea explícita de verificación de precondiciones (existencia de `app/integrations/` y de `httpx` en `requirements.txt`) antes de escribir código nuevo.

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Fixtures Gmail/Calendar/Drive (incl. MIME multiparte y refresh sin `refresh_token`) + `config.py` + `errors.py` | 1 — `feat(google-adapter): fixtures configuracion y taxonomia de errores` | `cd backend && pytest tests/test_adapter_google_errors.py -v` | N/A — sin endpoint HTTP propio en este lote; fixtures y mapeo de errores puros | Revert commit; `tests/fixtures/google/` y `errors.py` nuevos y aislados |
| 2 | `client.py`: Bearer, 401→refresh→retry, 429/403 backoff, paginación | 2 — `feat(google-adapter): cliente http con reintentos y paginacion` | `cd backend && pytest tests/test_adapter_google_client.py -v` | `client.get()` invocado directamente en tests contra `httpx.MockTransport` con fixtures encadenadas (401→200, 429→200) | Revert commit; `client.py` nuevo, sin consumidores fuera del paquete |
| 3 | `oauth.py`: `authorize_url`/`exchange_code`/`refresh` de Google | 3 — `feat(google-adapter): handshake oauth con external_account_id por correo` | `cd backend && pytest tests/test_adapter_google_oauth.py -v` | `oauth.exchange_code`/`refresh` invocados contra fixtures token+userinfo (sin HTTP real) | Revert commit; `oauth.py` nuevo, sin consumidores fuera del paquete |
| 4 | `mime.py`+`mail.py`: Gmail → `MailMessage` | 4 — `feat(google-adapter): lectura de gmail con parseo mime multiparte` | `cd backend && pytest tests/test_adapter_google_mail.py -v` | `MailReaderPort.list_messages` invocado contra fixture Gmail multiparte vía `MockTransport` | Revert commit; `mime.py`/`mail.py` nuevos, sin consumidores fuera del paquete |
| 5 | `calendar.py`+`meeting_notes.py`: Calendar/Drive → `CalendarEvent`/`MeetingNote` | 5 — `feat(google-adapter): lectura de calendar y transcripciones meet best-effort` | `cd backend && pytest tests/test_adapter_google_calendar.py tests/test_adapter_google_meeting_notes.py -v` | `CalendarReaderPort.list_events`/`MeetingNotesReaderPort.list_notes` contra fixtures vía `MockTransport` | Revert commit; ambos módulos nuevos, sin consumidores fuera del paquete |
| 6 | `adapter.py`+`__init__.py`+registro en `db_init.py`+docs C4+VERIFY final | 6 — `feat(google-adapter): registro import-time del adaptador google` | `cd backend && pytest tests/test_adapter_google_registry.py -v` | `get_adapter("google")` invocado tras el import de arranque (mismo patrón de prueba del registro del 14); VERIFY final `pytest tests/ -v` (suite completa, incl. 14/15) | Revert commit; sin el import en `db_init.py`, `provider="google"` no existe y el núcleo queda idéntico |

## Lote 1 — Fixtures + config + errors.py (Commit 1)

- [x] 1.1 [Foundation] Verificar que `app/integrations/` (14) y el adaptador `microsoft365` (15) ya existen en disco (orden serializado 14→15→16); verificar si `httpx` ya está en `backend/requirements.txt` (promovido por el apply del 14/15) — si NO está, agregarlo en este lote.
- [x] 1.2 [Foundation] Crear fixtures en `backend/tests/fixtures/google/`: mensaje Gmail MIME multiparte HTML+texto base64url (`gmail_message_multipart.json`) + lista paginada (`nextPageToken`); evento Calendar con organizador/asistentes + lista paginada; carpeta "Meet Recordings" + Doc de transcripción exportado, y lista vacía (sin Doc, organizador sin transcripción); token exchange + userinfo; refresh CON `refresh_token` y refresh SIN `refresh_token` (gotcha explícito del design); respuestas 401, 429 con `Retry-After`, 403 `rateLimitExceeded`, 403 permiso Drive denegado, 500.
- [x] 1.3 [Foundation] `app/config.py`: agregar `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_SCOPES` (readonly), `GOOGLE_OAUTH_REDIRECT_URI`, `GOOGLE_DEFAULT_SINCE_DAYS=30`, `GOOGLE_DEFAULT_LIMIT=50`, `GOOGLE_MAX_RETRIES` (ventana unificada con el 15: 30 días, no 90, por decisión ratificada del orquestador).
- [x] 1.4 [Foundation] `app/integrations/adapters/google/errors.py`: taxonomía Google→dominio (`capability_unavailable`, `provider_throttled`, `provider_unavailable`, `oauth_token_invalid`), espejo del 15.
- [x] 1.5 RED `backend/tests/test_adapter_google_errors.py`: `401`→`oauth_token_invalid`; `429` y `403 rateLimitExceeded/userRateLimitExceeded`→`provider_throttled`; `403` permiso Drive→`capability_unavailable`; `5xx`→`provider_unavailable`. [GA-R3, GA-R7]
- [x] 1.6 VERIFY confirmar T1.5 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_errors.py -v` en verde.

## Lote 2 — client.py: transporte HTTP + reintentos + paginación (Commit 2)

- [x] 2.1 [Foundation] `app/integrations/adapters/google/client.py`: `httpx.AsyncClient` con transporte inyectable, header `Authorization: Bearer`, paginación por `nextPageToken`/`pageToken` con tope `limit`.
- [x] 2.2 RED `backend/tests/test_adapter_google_client.py`: toda request incluye `Authorization: Bearer`; `401`→invoca `refresh`→reintenta la operación una única vez (`oauth_token_invalid` si el refresh falla); `429`→backoff respetando `Retry-After` (`sleep` inyectado, sin espera real); `403 rateLimitExceeded/userRateLimitExceeded`→backoff; `5xx`→`provider_unavailable`; `nextPageToken` se recorre hasta agotar o alcanzar `limit`; ningún token en logs ni en `str(exception)`. [GA-R3, GA-R9]
- [x] 2.3 VERIFY confirmar T2.2 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_client.py -v` en verde; `ruff check .`/`mypy app` limpios en `client.py`.

## Lote 3 — oauth.py: handshake OAuth de Google (Commit 3)

- [x] 3.1 [Foundation] `app/integrations/adapters/google/oauth.py`: `authorize_url(state, redirect_uri, scopes)`, `exchange_code(code, redirect_uri) -> OAuthTokens` (GET `userinfo`→`external_account_id`=email), `refresh(refresh_token) -> OAuthTokens`.
- [x] 3.2 RED `backend/tests/test_adapter_google_oauth.py`: `authorize_url` solo contiene scopes `*.readonly`; `exchange_code` con `code` válido devuelve `OAuthTokens.external_account_id`=correo autenticado; `refresh` con `refresh_token` en la respuesta devuelve `OAuthTokens` actualizado; `refresh` SIN `refresh_token` en la respuesta (fixture del gotcha) conserva el `refresh_token` anterior en el `OAuthTokens` resultante. [GA-R2]
- [x] 3.3 VERIFY confirmar T3.2 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_oauth.py -v` en verde.

## Lote 4 — mime.py + mail.py: Gmail (Commit 4)

- [ ] 4.1 [Foundation] `app/integrations/adapters/google/mime.py`: decodifica `payload` MIME multiparte base64url (`email`/`base64` de stdlib) a texto plano normalizado.
- [ ] 4.2 [Foundation] `app/integrations/adapters/google/mail.py`: `MailReaderPort.list_messages` vía `users.messages.list`/`get` (`q=after:<epoch>`, `maxResults`), mapea headers (`Subject/From/To/Date`) + `mime.body_text` a `MailMessage`.
- [ ] 4.3 RED `backend/tests/test_adapter_google_mail.py`: mensaje multiparte (HTML+texto) decodifica a `body_text` sin base64/MIME crudo; labels de Gmail no se exponen como campo de carpeta en `MailMessage`; `since`/`limit` se traducen a `q=after:<epoch_segundos>`/`maxResults`. [GA-R4]
- [ ] 4.4 VERIFY confirmar T4.3 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_mail.py -v` en verde.

## Lote 5 — calendar.py + meeting_notes.py: Calendar + Drive/Meet (Commit 5)

- [ ] 5.1 [Foundation] `app/integrations/adapters/google/calendar.py`: `CalendarReaderPort.list_events` vía `events.list` (`timeMin`/`timeMax` desde `since`, `maxResults` desde `limit`), mapea a `CalendarEvent` (organizador, asistentes, horario).
- [ ] 5.2 RED `backend/tests/test_adapter_google_calendar.py`: `since`/`limit` acotan `timeMin`/`maxResults`; evento mapea organizador/asistentes/horario a `CalendarEvent`. [GA-R5]
- [ ] 5.3 [Foundation] `app/integrations/adapters/google/meeting_notes.py`: `MeetingNotesReaderPort.list_notes` — busca la carpeta "Meet Recordings" en Drive (`files.list`), exporta el Doc (`files.export`, `mimeType=text/plain`) a `MeetingNote.transcript`.
- [ ] 5.4 RED `backend/tests/test_adapter_google_meeting_notes.py`: Doc de transcripción accesible→`MeetingNote.transcript` poblado; sin Doc (organizador sin transcripción activada/compartida)→lista vacía, sin error; sin permiso sobre el Drive del organizador→`capability_unavailable`, sin afectar mail/calendar. [GA-R6, GA-R7]
- [ ] 5.5 VERIFY confirmar T5.2/T5.4 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_calendar.py tests/test_adapter_google_meeting_notes.py -v` en verde.

## Lote 6 — adapter.py + registro + docs + VERIFY final (Commit 6)

- [ ] 6.1 [Foundation] `app/integrations/adapters/google/adapter.py`: `provider="google"`, `capabilities={mail,calendar,meeting_notes}` (sin `external_tasks`), `port_for(capability)`.
- [ ] 6.2 [Foundation] `app/integrations/adapters/google/__init__.py`: `register_adapter(GoogleAdapter())` en import-time.
- [ ] 6.3 [Foundation] `app/db_init.py`: `import app.integrations.adapters.google` (registro, sin editar ningún archivo del núcleo del 14).
- [ ] 6.4 RED `backend/tests/test_adapter_google_registry.py`: `get_adapter("google")` devuelve la instancia sin que se haya editado ningún archivo del núcleo; `port_for(Capability.external_tasks)` no expone puerto (capacidad no declarada); ningún método público del adaptador crea/edita/envía datos hacia Google (frontera solo lectura); `capabilities` no incluye `external_tasks`. [GA-R1, GA-R8, GA-R10]
- [ ] 6.5 VERIFY confirmar T6.4 en ROJO antes de GREEN; luego `cd backend && pytest tests/test_adapter_google_registry.py -v` en verde.
- [ ] 6.6 [Docs] `docs/diagrams/c4-architecture.md`: agregar el adaptador `google` como sub-componente en C3 (Integrations), junto al `microsoft365` ya documentado por el 15 — mismo commit.
- [ ] 6.7 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa sin regresión (incl. 14/15); `ruff check .`/`mypy app` limpios en `app/integrations/adapters/google/`.

## Trazabilidad de requisitos

**`google-adapter`**: GA-R1 Registro y protocolo de adaptador uniforme (2 esc.) · GA-R2 Handshake OAuth de Google mapeado a `OAuthTokens` (2 esc.) · GA-R3 Resiliencia ante errores transitorios de la API de Google (2 esc.) · GA-R4 Lectura de correo vía Gmail con parseo MIME (2 esc.) · GA-R5 Lectura de calendario vía Calendar API (1 esc.) · GA-R6 Transcripciones de Meet vía Drive best-effort (2 esc.) · GA-R7 Capacidad no disponible declarada explícitamente (1 esc.) · GA-R8 Frontera de solo lectura estricta (1 esc.) · GA-R9 Transporte HTTP inyectable sin SDK — cero red en CI (1 esc.) · GA-R10 Google Tasks fuera del primer corte (1 esc.).

Total: 10 requisitos, 15 escenarios cubiertos por tareas RED explícitas en los Lotes 1–6.
