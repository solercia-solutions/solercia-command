# Tasks: 15 · Adaptador Microsoft 365 (Graph, solo lectura)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1.600–1.900 (paquete `adapters/microsoft365/` 7 archivos ~470 + fixtures Graph ~320 + `tests/test_adapter_microsoft365.py` ~660 + `config.py`/`db_init.py`/`requirements.txt`/docs ~110) |
| Riesgo de presupuesto (400 líneas) | High acumulado (8 lotes); cada lote individual queda bajo 400 |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote 1 (cliente Graph base) → Lote 2 (cliente Graph resiliencia 401/429) → Lote 3 (OAuth Entra ID + registro) → Lote 4 (correo) → Lote 5 (calendario) → Lote 6 (tareas Planner) → Lote 7 (notas de reunión + degradación) → Lote 8 (frontera solo-lectura + docs + httpx) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, un commit por lote (sin PR) |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Sin migración de BD**: cero cambio de ER (verificado en design.md — reusa `connectors`/`connected_accounts`/`connection_credentials` del 14). Ningún lote toca Alembic ni `docs/diagrams/er-model.md`.

**Precondición de apply**: el apply de este cambio va DESPUÉS del apply del 14 (`app/integrations/` aún no existe en disco a la fecha de este `tasks.md`, verificado). El Lote 1 abre con una tarea de verificación explícita del contrato del 14 en disco.

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Cliente Graph base: `GraphClient` con paginación `@odata.nextLink` + TLS obligatorio + config `M365_*` | 1 — `feat(microsoft365): cliente graph base con paginacion y tls obligatorio` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestGraphClientBase -v` | N/A — pieza interna sin endpoint HTTP propio; verificado con `httpx.MockTransport` in-process | Revert commit; `client.py` es archivo nuevo sin consumidores aún |
| 2 | Cliente Graph resiliencia: `401`→refresh→retry, `429`→`Retry-After`+backoff acotado, `errors.py` (Graph→dominio) | 2 — `feat(microsoft365): resiliencia 401 refresh y 429 backoff del cliente graph` | `cd backend && pytest tests/test_adapter_microsoft365.py -k "TestGraphClientBase or TestGraphClientResilience" -v` | N/A — mismo motivo; secuencia 401/429 simulada con `MockTransport`, `sleep` inyectado sin espera real | Revert commit; amplía `client.py`/crea `errors.py`, sin otros módulos que los importen todavía |
| 3 | Handshake OAuth Entra ID (`authorize_url`/`exchange_code`/`refresh`) + registro import-time del adaptador | 3 — `feat(microsoft365): handshake oauth entra id y registro del adaptador` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestOAuthAndRegistry -v` | `httpx.AsyncClient` contra `GET /connectors/{id}/authorize` (router ya existente del 14) con un conector `provider="microsoft365"` sembrado; verifica el `302` a `login.microsoftonline.com` sin tocar el router del 14 | Revert commit; `oauth.py`/`adapter.py`/`__init__.py` nuevos + 1 línea en `db_init.py`; revertir deja el registro sin `provider="microsoft365"`, `fake` intacto |
| 4 | `MailReaderPort` sobre `/me/messages` | 4 — `feat(microsoft365): lectura de correo via mailreaderport` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestMailPort -v` | N/A — puerto invocado directo por `adapter.port_for(Capability.mail)` (sin endpoint HTTP hasta la ola 22) | Revert commit; agrega rama `mail` en `mappers.py`/`ports.py`, sin romper lotes previos |
| 5 | `CalendarReaderPort` sobre `/me/calendarView` | 5 — `feat(microsoft365): lectura de calendario via calendarreaderport` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestCalendarPort -v` | N/A — mismo motivo que correo | Revert commit; agrega rama `calendar`, independiente de correo |
| 6 | `ExternalTaskReaderPort` sobre `/me/planner/tasks` (solo Planner) | 6 — `feat(microsoft365): lectura de tareas planner via externaltaskreaderport` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestPlannerPort -v` | N/A — mismo motivo | Revert commit; agrega rama `external_tasks`, independiente |
| 7 | `MeetingNotesReaderPort` + degradación `capability_unavailable` sin admin consent | 7 — `feat(microsoft365): notas de reunion con degradacion por consentimiento` | `cd backend && pytest tests/test_adapter_microsoft365.py -k TestMeetingNotesPort -v` | N/A — introspección de `ctx.scopes` ocurre sin red por diseño | Revert commit; agrega rama `meeting_notes`, independiente; degradación queda intacta si se revierte |
| 8 | Frontera solo-lectura estricta + `docs/diagrams/c4-architecture.md` + promoción de `httpx` | 8 — `feat(microsoft365): frontera solo lectura docs c4 y httpx en requirements` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` (suite completa) | N/A — introspección estática de código; VERIFY final cubre la regresión de rutas HTTP existentes del 14 | Revert commit; `requirements.txt`/docs/test de frontera son cambios aislados sin dependientes |

## Lote 1 — Cliente Graph base (Commit 1)

- [x] 1.1 [Preflight] Verificar en disco que `app/integrations/` (14) existe: `ports.py` (`Capability`, `IntegrationAdapter`, 4 puertos read-only + `TicketReaderPort`), `registry.py` (`register_adapter`/`get_adapter`), `dtos.py` (`MailMessage`/`CalendarEvent`/`ExternalTask`/`MeetingNote`/`OAuthTokens`), y que `AccessContext` expone `access_token`/`refresh_token`/`expires_at`. Si `scopes` u `on_tokens_refreshed` NO existen, documentar la degradación (introspección de capacidad depende solo del fallback runtime `403`; refresh sin persistencia se difiere a la ola 22) SIN bloquear el resto de las tareas.
- [x] 1.2 [Foundation] `app/config.py`: agregar `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `M365_TENANT` (default `organizations`), `M365_GRAPH_BASE_URL` (default `https://graph.microsoft.com/v1.0`), `M365_LOGIN_BASE_URL` (default `https://login.microsoftonline.com`), `M365_TIMEOUT_SECONDS`, `M365_MAX_RETRIES`, `M365_DEFAULT_SINCE_DAYS`=30, `M365_CALENDAR_FUTURE_DAYS`=90, `M365_MAX_PAGES`=20, `M365_MAX_LIMIT`=200.
- [x] 1.3 [Fixtures] `tests/fixtures/graph/generic_page_1.json`, `generic_page_2.json` (con `@odata.nextLink` encadenado), `generic_single_page.json` (sin `nextLink`).
- [x] 1.4 RED `backend/tests/test_adapter_microsoft365.py::TestGraphClientBase`: `GraphClient` rechaza esquemas no-https en `M365_GRAPH_BASE_URL`/`M365_LOGIN_BASE_URL`; `paginate()` recorre `@odata.nextLink` completo hasta agotar páginas o `limit`, corta en `M365_MAX_PAGES`; el host de cada request se deriva SOLO de `M365_GRAPH_BASE_URL`, nunca de datos externos. [Threat Matrix: TLS obligatorio, anti-SSRF/host fijo — mitad `client.py`]
- [x] 1.5 VERIFY confirmar T1.4 en ROJO (módulo `client.py` inexistente) antes de GREEN.
- [x] 1.6 GREEN `app/integrations/adapters/microsoft365/client.py`: clase `GraphClient(ctx, *, transport=None, sleep=asyncio.sleep, settings=settings)`; método `paginate(url, *, limit)` sigue `nextLink` con Bearer del `ctx`.
- [x] 1.7 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestGraphClientBase -v` en verde; `ruff check .`/`mypy app` limpios en `client.py`.

## Lote 2 — Cliente Graph resiliencia: 401/429 + errores de dominio (Commit 2)

- [x] 2.1 [Fixtures] `tests/fixtures/graph/unauthorized_401.json`, `throttled_429.json`, `ok_after_retry.json`.
- [x] 2.2 RED `TestGraphClientResilience`: `401` dispara `refresh` una vez y reintenta con éxito; `refresh_token` revocado → error controlado de reconexión sin bucle; `429` honra `Retry-After` (sleep inyectado, sin espera real) con backoff; `429` repetidos más allá de `M365_MAX_RETRIES` → error controlado, no bucle infinito; ningún access/refresh token aparece en `caplog` ni en `str(exception)` de `client.py`. [M365-R3, M365-R7; Threat Matrix: sin fuga de tokens (client), backoff acotado]
- [x] 2.3 VERIFY confirmar T2.2 en ROJO antes de GREEN.
- [x] 2.4 GREEN `.../microsoft365/errors.py`: mapeo Graph→dominio (`capability_unavailable`, `provider_throttled`, `provider_unavailable`, `oauth_token_invalid`).
- [x] 2.5 GREEN `client.py` (ampliar): interceptor `401`→`refresh`→reintento único vía sink opcional `on_tokens_refreshed`; interceptor `429`→`sleep(Retry-After)`+backoff acotado a `M365_MAX_RETRIES`.
- [x] 2.6 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k "TestGraphClientBase or TestGraphClientResilience" -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 3 — OAuth Entra ID + registro del adaptador (Commit 3)

- [x] 3.1 RED `TestOAuthAndRegistry`: `authorize_url` usa `tenant=organizations` por defecto y el de `M365_TENANT` si está configurado; `exchange_code`/`refresh` devuelven `OAuthTokens` con `external_account_id=oid` del id_token; `get_adapter("microsoft365")` retorna la instancia sin editar `ports.py`/`oauth.py`/`registry.py` del 14; `tickets` no aparece en `capabilities`; ningún token en `caplog`/`str(exception)` de `oauth.py`; URLs derivadas solo de `M365_LOGIN_BASE_URL`+tenant, `redirect_uri` validado por el allowlist del 14. [M365-R1, M365-R2; Threat Matrix: sin fuga de tokens (oauth), anti-SSRF/host fijo — mitad `oauth.py`]
- [x] 3.2 VERIFY confirmar T3.1 en ROJO antes de GREEN.
- [x] 3.3 GREEN `.../microsoft365/oauth.py`: constructores de URL `authorize`/`token`/`refresh` sobre `login.microsoftonline.com/{tenant}/oauth2/v2.0/*`.
- [x] 3.4 GREEN `.../microsoft365/adapter.py`: `Microsoft365Adapter` (`provider="microsoft365"`, `capabilities={mail,calendar,external_tasks,meeting_notes}`, `authorize_url`/`exchange_code`/`refresh` con `client_secret`, `port_for` con dict de puertos disponibles).
- [x] 3.5 GREEN `.../microsoft365/__init__.py`: `register_adapter(Microsoft365Adapter(settings))` en import-time.
- [x] 3.6 GREEN `app/db_init.py`: `import app.integrations.adapters.microsoft365` (precedente `adapters.fake`; NO es el núcleo `app/integrations/`).
- [x] 3.7 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestOAuthAndRegistry -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 4 — Correo: `MailReaderPort` (Commit 4)

- [x] 4.1 [Fixtures] `tests/fixtures/graph/mail_page_1.json`, `mail_page_2.json`, `mail_empty.json`.
- [x] 4.2 RED `TestMailPort`: `list_messages(ctx, since, limit)` agrega DTOs de ambas páginas respetando `limit`; sin resultados dentro de `since` → `[]`, no error. [M365-R4 — correo]
- [x] 4.3 VERIFY confirmar T4.2 en ROJO antes de GREEN.
- [x] 4.4 GREEN `.../microsoft365/mappers.py`: `map_mail_message(json) -> MailMessage`.
- [x] 4.5 GREEN `.../microsoft365/ports.py`: `GraphMailReader` sobre `/me/messages` (`$select`/`$top`/`$filter=receivedDateTime ge {since}`, scope `Mail.Read`); wired en `adapter.port_for(Capability.mail)`.
- [x] 4.6 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestMailPort -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 5 — Calendario: `CalendarReaderPort` (Commit 5)

- [x] 5.1 [Fixtures] `tests/fixtures/graph/calendar_page_1.json`, `calendar_empty.json`.
- [x] 5.2 RED `TestCalendarPort`: `list_events` agrega DTOs multi-página respetando `limit`; `startDateTime=since|now-30d`, `endDateTime=now+M365_CALENDAR_FUTURE_DAYS`; sin resultados → `[]`, no error. [M365-R4 — calendario]
- [x] 5.3 VERIFY confirmar T5.2 en ROJO antes de GREEN.
- [x] 5.4 GREEN `mappers.py` (ampliar): `map_calendar_event`.
- [x] 5.5 GREEN `ports.py` (ampliar): `GraphCalendarReader` sobre `/me/calendarView` (scope `Calendars.Read`); wired en `Capability.calendar`.
- [x] 5.6 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestCalendarPort -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 6 — Tareas Planner: `ExternalTaskReaderPort` (Commit 6)

- [x] 6.1 [Fixtures] `tests/fixtures/graph/planner_tasks.json`, `planner_empty.json`.
- [x] 6.2 RED `TestPlannerPort`: `/me/planner/tasks` con tareas → DTOs mapeados; tenant sin grupos/planes → `[]` sin error; filtro `since`/`limit` client-side por `createdDateTime` (Graph no lo soporta en este endpoint). [M365-R5]
- [x] 6.3 VERIFY confirmar T6.2 en ROJO antes de GREEN.
- [x] 6.4 GREEN `mappers.py` (ampliar): `map_external_task` (Planner).
- [x] 6.5 GREEN `ports.py` (ampliar): `GraphExternalTaskReader` (scope `Tasks.Read`); wired en `Capability.external_tasks`; NO implementa Microsoft To Do.
- [x] 6.6 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestPlannerPort -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 7 — Notas de reunión + degradación por consentimiento (Commit 7)

- [ ] 7.1 [Fixtures] `tests/fixtures/graph/transcript_granted.json`, `transcript_content.json`, `no_consent_403.json`.
- [ ] 7.2 RED `TestMeetingNotesPort`: con `OnlineMeetingTranscript.Read.All` en `ctx.scopes` → DTO mapeado del fixture; sin ese scope → `capability_unavailable` **sin red** (introspección antes de llamar); `403 Authorization_RequestDenied` en runtime → también `capability_unavailable`; la degradación no afecta correo/calendario/tareas del mismo adaptador. [M365-R6]
- [ ] 7.3 VERIFY confirmar T7.2 en ROJO antes de GREEN.
- [ ] 7.4 GREEN `mappers.py` (ampliar): `map_meeting_note`.
- [ ] 7.5 GREEN `ports.py` (ampliar): `GraphMeetingNotesReader` sobre `/me/onlineMeetings/{id}/transcripts`+`.../content` (scopes `OnlineMeetingTranscript.Read.All`+`OnlineMeetings.Read`); introspección de `ctx.scopes` (según degradación de T1.1) + captura de `403` vía `errors.py`; wired en `Capability.meeting_notes`.
- [ ] 7.6 VERIFY `cd backend && pytest tests/test_adapter_microsoft365.py -k TestMeetingNotesPort -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 8 — Frontera solo-lectura + docs C4 + `httpx` en runtime (Commit 8)

- [ ] 8.1 RED `TestWriteBoundary`: ninguna llamada HTTP en `client.py`/`ports.py`/`oauth.py` usa verbo `POST`/`PATCH`/`PUT`/`DELETE` hacia Graph (introspección estática sobre los métodos de `httpx` invocados en el paquete). [M365-R8]
- [ ] 8.2 VERIFY confirmar T8.1: si ya está en verde por diseño (ningún puerto implementa escritura), documentarlo explícitamente como guardia de regresión, no como hallazgo nuevo.
- [ ] 8.3 [Docs] `docs/diagrams/c4-architecture.md`: agregar nodo `microsoft365` bajo el componente Integrations/adapters del C3 — mismo commit, obligatorio.
- [ ] 8.4 [Foundation] Verificar si `requirements.txt` ya tiene `httpx>=0.27` (posible promoción del 14/20); si no, moverlo desde `requirements-dev.txt` a `requirements.txt` (el adaptador lo usa en producción, no solo en tests).
- [ ] 8.5 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa sin regresión; `ruff check .`/`mypy app` limpios en `app/integrations/adapters/microsoft365/`.

## Trazabilidad de requisitos

**`adapter-microsoft365`**: M365-R1 Registro del adaptador sin editar el núcleo (1 esc., Lote 3) · M365-R2 Handshake OAuth delegado de Entra ID (1 esc., Lote 3) · M365-R3 Token expirado se refresca vía credenciales del 14 (1 esc., Lote 2) · M365-R4 Lectura de correo y calendario con ventana y paginación (2 esc., Lotes 4–5) · M365-R5 Lectura de tareas Planner sin Microsoft To Do (1 esc., Lote 6) · M365-R6 Notas de reunión con degradación por consentimiento (2 esc., Lote 7) · M365-R7 Backoff ante 429 con Retry-After (1 esc., Lote 2) · M365-R8 Frontera solo-lectura estricta hacia Graph (1 esc., Lote 8).

Total: 8 requisitos, 10 escenarios cubiertos por tareas RED explícitas en los Lotes 1–8.

**Threat Matrix (design.md)**: sin fuga de tokens → Lotes 2 (`client.py`) y 3 (`oauth.py`) · anti-SSRF/host fijo → Lotes 1 (`client.py`) y 3 (`oauth.py`) · TLS obligatorio → Lote 1 · backoff acotado → Lote 2. Las 4 filas quedan cubiertas antes de su producción correspondiente.
