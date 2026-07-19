# Design: 15 · Adaptador Microsoft 365 (Graph, solo lectura)

## Technical Approach

Un paquete adaptador `app/integrations/adapters/microsoft365/` que implementa el `IntegrationAdapter` del 14 (**contrato del 14**) y se auto-registra en import-time, precedente exacto de `adapters/fake.py`. Cero ediciones al núcleo (`ports.py`/`registry.py`/`oauth.py`/`crypto.py` del 14): el adaptador consume esas piezas tal cual. El núcleo del 14 sigue orquestando `authorize`/`callback` y delega en el adaptador vía `get_adapter("microsoft365")`. Toda salida a Graph pasa por un `GraphClient` (httpx) inyectable → cero red en CI. TDD estricto contra fixtures JSON de respuestas Graph reales + `httpx.MockTransport`.

## Mapeo capacidad → endpoint Graph → scope delegado

| Capacidad | Puerto (14) | Endpoint Graph (GET, base `graph.microsoft.com/v1.0`) | Scope delegado | Admin consent |
|-----------|-------------|-------------------------------------------------------|----------------|---------------|
| Correo | `MailReaderPort` | `/me/messages?$select&$top&$filter=receivedDateTime ge {since}` | `Mail.Read` | No |
| Calendario | `CalendarReaderPort` | `/me/calendarView?startDateTime&endDateTime&$top` | `Calendars.Read` | No |
| Tareas Planner | `ExternalTaskReaderPort` | `/me/planner/tasks` | `Tasks.Read` | No (exige pertenecer al plan) |
| Notas Teams | `MeetingNotesReaderPort` | `/me/onlineMeetings/getAllTranscripts` [as-built; ver sección "As-Built Notes"] | `OnlineMeetingTranscript.Read.All` (+`OnlineMeetings.Read`) | **Sí** |

Base OIDC/refresh: `openid profile email offline_access User.Read`. OAuth: `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/{authorize,token}`, `tenant=organizations` (config `M365_TENANT`).

## Architecture Decisions

### Scopes de transcripciones son opt-in por conector (no en el set por defecto)

**Choice**: el set de scopes por defecto del conector EXCLUYE `OnlineMeetingTranscript.Read.All`; solo se añade si el admin del tenant lo consiente. **Alternativa rechazada**: incluir el `.All` siempre. **Rationale**: un scope `.All` sin admin consent hace fallar TODO el `authorize` (AADSTS65001), tumbando correo/calendario/tareas. Mantenerlo opt-in aísla la degradación.

### Detección de `meeting_notes` no concedido por introspección de scopes (sin red)

**Choice**: el `MeetingNotesReaderPort` verifica `OnlineMeetingTranscript.Read.All in ctx.scopes` (el 14 persiste `scopes` en `ConnectionCredentials`) ANTES de llamar; si falta → `capability_unavailable` sin red. Fallback en runtime: `403 Authorization_RequestDenied` también mapea a `capability_unavailable`. **Rationale**: falla barato y determinista; el 403 cubre el caso "scope presente pero *application access policy* de Teams ausente".

### Refresh dentro del adaptador (401 → refresh → retry once)

**Choice**: el `GraphClient` intercepta `401` una vez: llama `adapter.refresh(refresh_token)` (**firma lista del 14**, este es su primer consumidor), reintenta con el nuevo access token. La persistencia de tokens rotados se hace vía un `on_tokens_refreshed` opcional en `AccessContext`. **Alternativa rechazada**: orquestar refresh en `oauth.py` del 14 (viola "cero cambios al núcleo"). **Rationale**: el 14 difirió explícitamente el wiring a los adaptadores; vive aquí. *Dependencia de contrato*: si el `AccessContext` del 14 aún no expone el sink, el refresh igual sirve la lectura en memoria y la persistencia queda como follow-up del consumidor (ola 22).

### Flujo confidential-client (client_secret), PKCE diferido

**Choice**: Authorization Code con `client_secret` (cliente confidencial backend). **Alternativa**: PKCE (mencionado en el proposal). **Rationale**: `authorize_url(state, redirect_uri, scopes)` y `exchange_code(code, redirect_uri)` del 14 NO enhebran `code_verifier`; PKCE exigiría que el `state_store` del 14 persista el verifier → cambio al núcleo, fuera de alcance. El `state` (anti-CSRF, single-use en Redis) + `client_secret` dan protección equivalente. PKCE = follow-up del 14.

### `external_account_id` = claim `oid` del id_token

**Choice**: `oid` (object id inmutable) como `external_account_id`; `userPrincipalName` como `display_name`. **Rationale**: el `UNIQUE(connector_id, external_account_id)` del 14 y "reconexión no duplica" exigen un id estable; el UPN cambia. El proposal decía UPN; se ajusta por estabilidad. Evita un `GET /me` extra (el `openid` scope ya devuelve id_token).

### Defaults de `since`/`limit` (decisión ratificada #4)

`limit`=50 (`$top`), tope `MAX_LIMIT`=200. `since` None → últimos `M365_DEFAULT_SINCE_DAYS`=30 (correo, notas). Calendario: `startDateTime=since|now-30d`, `endDateTime=now+M365_CALENDAR_FUTURE_DAYS`=90d (alertas miran lo próximo). Planner: sin filtro temporal en Graph → `limit` y `since` (por `createdDateTime`) client-side. Tope de paginación `M365_MAX_PAGES`=20.

## Data Flow

    OAuth (núcleo 14):  oauth.build_authorize → adapter.authorize_url(state,redirect,scopes) → 302 Entra ID
      callback → adapter.exchange_code(code,redirect) → OAuthTokens(oid, access, refresh, expires_at, scopes)
    Lectura (ola 22):  adapter.port_for(cap).list_*(ctx, since, limit)
      → GraphClient: Bearer → 401?refresh+retry → 429?sleep(Retry-After)+backoff → seguir @odata.nextLink (≤MAX_PAGES/limit)
      → mappers.<cap>(json) → list[DTO del 14]

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/microsoft365/__init__.py` | Create | `register_adapter(Microsoft365Adapter(settings))` import-time |
| `.../microsoft365/adapter.py` | Create | `provider`, `capabilities={mail,calendar,external_tasks,meeting_notes}`, `authorize_url`/`exchange_code`/`refresh`, `port_for` |
| `.../microsoft365/oauth.py` | Create | URLs y payloads Entra ID (authorize/token/refresh) |
| `.../microsoft365/client.py` | Create | `GraphClient` httpx: Bearer, 401→refresh→retry, 429 backoff, paginación nextLink; `transport`+`sleep` inyectables |
| `.../microsoft365/mappers.py` | Create | Graph JSON → `MailMessage`/`CalendarEvent`/`ExternalTask`/`MeetingNote` |
| `.../microsoft365/ports.py` | Create | 4 impls de puerto (cada una envuelve `GraphClient`+mapper) |
| `.../microsoft365/errors.py` | Create | Graph → dominio: `capability_unavailable`, `provider_throttled`, `provider_unavailable`, `oauth_token_invalid` |
| `app/db_init.py` | Modify | `import app.integrations.adapters.microsoft365` (registro; precedente fake — NO es el núcleo `integrations/`) |
| `app/config.py` | Modify | `M365_CLIENT_ID/SECRET/TENANT`, `M365_GRAPH_BASE_URL`, `M365_LOGIN_BASE_URL`, timeouts, `MAX_RETRIES`, `DEFAULT_SINCE_DAYS`, `CALENDAR_FUTURE_DAYS`, `MAX_PAGES`, `MAX_LIMIT` |
| `requirements.txt` | Modify | **`httpx>=0.27` promovido a runtime** (hoy solo en `requirements-dev.txt`; el adaptador lo usa en producción) |
| `tests/fixtures/graph/*.json` | Create | Respuestas reales mail/calendar/planner/transcripts + páginas nextLink + 429/401 |
| `tests/test_adapter_microsoft365.py` | Create | Contrato, oauth, refresh, 429, capability, registro |
| `docs/diagrams/c4-architecture.md` | Modify | C1: sistema externo **Microsoft Graph**; C3: adaptador `microsoft365` bajo Integrations |

**ER-model NO cambia**: este cambio no crea tablas (usa `connectors`/`connected_accounts`/`connection_credentials` del 14). `docs/diagrams/er-model.md` queda intacto — declarado explícitamente.

## Interfaces / Contracts

```python
# app/integrations/adapters/microsoft365/adapter.py
class Microsoft365Adapter:                     # implementa IntegrationAdapter (contrato del 14)
    provider = "microsoft365"
    capabilities = frozenset({Capability.mail, Capability.calendar,
                              Capability.external_tasks, Capability.meeting_notes})
    def authorize_url(self, state, redirect_uri, scopes) -> str: ...
    async def exchange_code(self, code, redirect_uri) -> OAuthTokens: ...  # oid, scopes concedidos
    async def refresh(self, refresh_token) -> OAuthTokens: ...             # primer consumidor de la firma del 14
    def port_for(self, capability) -> object: ...

# client.py — inyectable para CI sin red
class GraphClient:
    def __init__(self, ctx, *, transport=None, sleep=asyncio.sleep, settings=settings): ...
    async def paginate(self, url, *, limit) -> list[dict]: ...  # sigue @odata.nextLink ≤ MAX_PAGES
```

`AccessContext` requerido del 14 (**contrato**): `access_token`, `refresh_token`, `expires_at`, `scopes: tuple[str,...]` (para introspección de capacidad), y opcional `on_tokens_refreshed` (sink de persistencia tras refresh).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit | Cada puerto: fixture Graph → DTOs del 14; mappers | `httpx.MockTransport` + fixtures `tests/fixtures/graph/` |
| Unit | 401 → `refresh` → retry → éxito; token rotado invoca el sink | MockTransport secuencial (401 luego 200) |
| Unit | 429 con `Retry-After` respeta backoff; `sleep` inyectado (no espera real) | MockTransport 429→200; `sleep` no-op captura la espera |
| Unit | `meeting_notes` sin scope → `capability_unavailable` **sin red**; 403 runtime → igual | ctx sin scope; MockTransport 403 |
| Unit | Tenant sin Planner → `[]` (capacidad activa, sin datos, nunca error) | fixture `{"value": []}` |
| Unit | Paginación completa vía `@odata.nextLink`; corte en `MAX_PAGES`/`limit` | fixtures encadenados |
| Unit | `get_adapter("microsoft365")` retorna la instancia sin editar el núcleo | misma prueba de registro del 14 |
| Security | Ningún access/refresh token en logs ni en el texto de excepciones; respuestas crudas con tokens jamás loggeadas | assert sobre `caplog` y `str(exc)` |

## Threat Matrix

N/A para los ejes formales (routing/shell, subprocess, automatización VCS/PR, clasificación de ejecutables): no hay ninguno. Los riesgos propios de la frontera de red/OAuth NO se omiten y se cubren con RED tests:

| Requisito | Test RED |
|-----------|----------|
| Sin fuga de tokens | ningún token en `caplog` ni en `str(exception)` de client/oauth |
| Anti-SSRF/host fijo | URLs derivadas de `M365_GRAPH_BASE_URL`/`M365_LOGIN_BASE_URL` + rutas del adaptador; host jamás desde datos externos; `redirect_uri` validado por el allowlist del 14 |
| TLS obligatorio | `GraphClient` rechaza esquemas no-https en base URLs |
| Backoff acotado | 429 respeta `Retry-After` y se detiene en `MAX_RETRIES` (no bucle infinito) |

## Migration / Rollout

Sin migraciones (aditivo, reusa tablas del 14). El adaptador se registra en import-time; sin `M365_CLIENT_ID/SECRET` queda inerte (patrón `EMAIL_ENABLED`): `authorize`/`exchange` lanzan error de config claro, las lecturas no arrancan. Rollback = revertir el merge → `provider="microsoft365"` desaparece del registro.

## As-Built Notes

### Desviación: endpoint de transcripciones (`getAllTranscripts`)

Design.md/tasks.md mencionaban un flujo per-reunión (`/me/onlineMeetings/{id}/transcripts`), que requeriría primero obtener la lista de reuniones del usuario. Durante el apply, se detectó que Graph no ofrece un endpoint directo para "listar todas mis reuniones sin filtro previo" a través de scopes delegados (exigiría `OnlineMeetings.ReadAll` o un ciclo de querys costoso). El as-built optó por `/me/onlineMeetings/getAllTranscripts`, un endpoint alternativo que devuelve un estado paginado de transcripciones sin necesidad de enumerar reuniones primero, manteniendo la misma cobertura de escenarios de spec (ambos escenarios de M365-R6 pasan). Esto queda documentado en el docstring de `ports.py::GraphMeetingNotesReader` y no rompe ningún requisito. **Clasificación**: WARNING documental en verify-report, no CRITICAL.

### Desviación: Planner `assignee` y `url`

- **assignee**: Planner devuelve una lista de `oid`s de asignados; el as-built mapea el primero. Graph no devuelve el email del oid sin usar `$expand`, que está fuera del presupuesto del lote. Si la ola 22 (clasificador/wiring del engine) necesita resolver oid→email, puede hacerlo mediante una llamada adicional a `GET /directoryObjects/{id}`. **Clasificación**: SUGGESTION en verify-report (mejora futura, no bloqueante).
- **url**: Planner v1.0 no expone un `webUrl` para las tareas. Si es necesario en futuras olas, puede introducirse cuando Planner v2.0 esté disponible. **Clasificación**: documentado, no bloqueante.

## Open Questions

- [ ] `AccessContext` del 14 (apply pendiente): confirmar que expone `scopes` y el sink `on_tokens_refreshed`. Si el sink falta, la persistencia de tokens rotados se difiere al consumidor (ola 22); la lectura no se bloquea.
- [ ] PKCE: requiere que el `state_store` del 14 persista `code_verifier` (cambio al núcleo). Diferido; se usa confidential-client + `client_secret`.
- [ ] Ola 22 (resolución oid→email para Planner): confirmado que es follow-up fuera de alcance del 15.
- [ ] Wiring del sink `on_tokens_refreshed` a persistencia real en BD: confirmado que es follow-up del 22.
