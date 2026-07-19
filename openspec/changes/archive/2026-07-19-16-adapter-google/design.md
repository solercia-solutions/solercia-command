# Design: 16 · Adaptador Google (Gmail/Calendar/Meet, solo lectura)

## Technical Approach

Adaptador `google` en `app/integrations/adapters/google/`, **simétrico** al esqueleto del 15 (mismo cliente/fixtures/errores). Implementa el `IntegrationAdapter` del 14 (contrato del 14) y se **auto-registra** en import-time (precedente `app/notify/registry.py` + `adapters/fake.py`): **cero ediciones al núcleo**. Un único cliente HTTP `httpx.AsyncClient` con transporte inyectable (real en prod, `httpx.MockTransport` en test) sirve OAuth + Gmail + Calendar + Drive con auth `Bearer`. Cada puerto mapea la respuesta cruda a los DTOs frozen del 14. Backend-only, TDD estricto contra fixtures JSON reales. Símbolos `app.integrations.*` referenciados = **contrato del 14** (aún no aplicado en disco).

## Architecture Decisions

| Decisión | Elegida | Alternativa rechazada | Rationale |
|----------|---------|-----------------------|-----------|
| Estructura | `adapters/google/{__init__,adapter,client,oauth,mail,calendar,meeting_notes,mime}.py` — espejo del 15 | Un solo `google.py` monolítico | Máxima simetría estructural con Microsoft; parseo MIME aislado en su módulo |
| Cliente HTTP | `httpx` directo, transporte inyectable (decisión #3) | SDK `google-api-python-client` | Controla el transporte para `MockTransport`; el SDK esconde el HTTP y arrastra dependencias pesadas |
| Parseo de cuerpo | `email`/`base64` de stdlib sobre `payload` MIME (`format=full`) | `format=metadata` (sin cuerpo) | El clasificador (22) necesita `body_text`; Gmail entrega multiparte base64url que hay que decodificar/normalizar |
| Transcripciones Meet | Drive `files.list` "Meet Recordings" + `files.export` (best-effort, decisión #1) | Meet REST API primario | OLA 2 fija Drive; si no hay Doc → lista vacía, nunca error (riesgo Workspace) |
| `external_account_id` | correo de la cuenta (decisión #4) vía `userinfo`/claim `email` del `id_token` | `sub` opaco de OpenID | Identidad estable y legible del `ConnectedAccount`; consistente con `UNIQUE(connector_id, external_account_id)` del 14 |
| Ventana de lectura | `since` default = `now-90d`, `limit` default = `50` | Sin default (traer todo) | Contiene volumen/cuota; `limit=50` alinea con la firma del puerto del 14; se re-alineará al `since/limit` del 15 cuando su design lo fije |
| Verificación | *test users* en MVP (decisión #5) | Verificación + CASA antes del MVP | Restringidos (`gmail.readonly`/`drive.readonly`) exigen CASA anual; test users (≤100) desbloquean dev sin verificación |

## Data Flow

    authorize_url(state,redirect_uri,scopes) → accounts.google.com/o/oauth2/v2/auth
      (access_type=offline, prompt=consent → garantiza refresh_token)
    callback → exchange_code(code) → POST oauth2.googleapis.com/token → OAuthTokens
      + GET userinfo → external_account_id = email
    Lectura → client.get(Bearer) → JSON crudo → mapper → DTO frozen del 14
      401 → refresh() → 1 reintento (oauth_token_invalid si refresh falla)
      429 → backoff(Retry-After si viene, sleep inyectable) ≤ MAX_RETRIES → provider_throttled
      403 rateLimitExceeded/userRateLimitExceeded → backoff (provider_throttled)
      403 permiso Drive → capability_unavailable (Meet best-effort); 5xx → provider_unavailable
      nextPageToken recorrido con tope limit

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/google/__init__.py` | Create | `register_adapter(GoogleAdapter())` import-time (contrato del 14) |
| `app/integrations/adapters/google/adapter.py` | Create | `provider="google"`, `capabilities={mail,calendar,meeting_notes}`, `port_for` |
| `app/integrations/adapters/google/client.py` | Create | `httpx.AsyncClient` Bearer + paginación `nextPageToken` + política de errores |
| `app/integrations/adapters/google/oauth.py` | Create | `authorize_url`/`exchange_code`/`refresh` + `userinfo`→email |
| `app/integrations/adapters/google/{mail,calendar,meeting_notes}.py` | Create | Puertos: Gmail/Calendar/Drive → DTOs |
| `app/integrations/adapters/google/mime.py` | Create | Decodifica multiparte base64url → `body_text`/`snippet` |
| `app/integrations/adapters/google/errors.py` | Create | Taxonomía Google→dominio (**espejo del 15**): `capability_unavailable`, `provider_throttled`, `provider_unavailable`, `oauth_token_invalid` |
| `app/db_init.py` (o `adapters/__init__`) | Modify | `import app.integrations.adapters.google` (registro) — **contrato del 14** |
| `app/config.py` | Modify | `GOOGLE_OAUTH_CLIENT_ID/SECRET`, `GOOGLE_OAUTH_SCOPES` (readonly), `GOOGLE_OAUTH_REDIRECT_URI` |
| `requirements.txt` | Modify | **Añadir `httpx`** — hoy solo está en `requirements-dev.txt`; el adaptador lo usa en runtime |
| `backend/tests/fixtures/google/` | Create | Gmail MIME multiparte, evento Calendar, folder "Meet Recordings" + Doc |
| `docs/diagrams/c4-architecture.md` | Modify | Adaptador `google` como sub-componente en **C3** (Integrations); **mismo commit** |

## Interfaces / Contracts (endpoints exactos)

```python
# client.py — bases; todas GET con Authorization: Bearer <access_token>
GMAIL    = "https://gmail.googleapis.com/gmail/v1/users/me/messages"          # ?q&maxResults&pageToken → list; /{id}?format=full → get
CALENDAR = "https://www.googleapis.com/calendar/v3/calendars/primary/events" # ?timeMin&timeMax&singleEvents=true&orderBy=startTime&pageToken
DRIVE    = "https://www.googleapis.com/drive/v3/files"                        # q="'<folder>' in parents and mimeType='application/vnd.google-apps.document'"; /{id}/export?mimeType=text/plain
AUTHZ    = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN    = "https://oauth2.googleapis.com/token"                              # grant_type=authorization_code | refresh_token
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"                # → email = external_account_id

# errors.py — Google → dominio (espejo del 15)
CAPABILITY_UNAVAILABLE = "capability_unavailable"  # 403 permiso Drive / capacidad no resoluble (Meet best-effort)
PROVIDER_THROTTLED     = "provider_throttled"      # 429 / 403 rateLimitExceeded|userRateLimitExceeded → backoff
PROVIDER_UNAVAILABLE   = "provider_unavailable"    # 5xx
OAUTH_TOKEN_INVALID    = "oauth_token_invalid"     # refresh falla / invalid_grant
```

**Traducción `since`/`limit` por puerto** (defaults `since=now-90d`, `limit=50`):

| Puerto | `since` → | `limit` → |
|--------|-----------|-----------|
| Gmail (`MailReaderPort`) | `q=after:<epoch_segundos>` | `maxResults` |
| Calendar (`CalendarReaderPort`) | `timeMin=<RFC3339>` (`timeMax=now`) | `maxResults` |
| Drive/Meet (`MeetingNotesReaderPort`) | `q += modifiedTime > '<RFC3339>'` | `pageSize` |

**Mapeo → DTO del 14**: Gmail headers (`Subject/From/To/Date`) + `mime.body_text` → `MailMessage` (`threadId` metadato opcional, `external_id`=`id`); evento → `CalendarEvent` (`start/end.dateTime`, `attendees[].email`, `location`); Doc export texto → `MeetingNote.transcript`.

**Refresh (gotcha)**: Google **no** re-emite `refresh_token` en el refresh; si viene ausente, conservar el anterior al construir `OAuthTokens`.

## Testing Strategy

| Layer | Qué | Cómo |
|-------|-----|------|
| Unit — contrato del 14 | Cada puerto devuelve sus DTOs desde fixture (misma forma que el `fake`) | `httpx.MockTransport` → fixtures JSON; cero red |
| Unit — mapeo | MIME multiparte base64url → `body_text`; evento→`CalendarEvent`; Doc→`MeetingNote` | Fixtures reales; casos HTML+texto |
| Unit — OAuth | `exchange_code`/`refresh` → `OAuthTokens`; `external_account_id`=email; **refresh sin `refresh_token` en la respuesta → conserva el anterior** (gotcha Google) | Fixtures token+userinfo; fixture de refresh **sin** `refresh_token` |
| Unit — errores/paginación | 401→refresh→1 reintento (`oauth_token_invalid` si falla); **`429`→backoff respetando `Retry-After` si viene** (`sleep` inyectado, sin espera real) → `provider_throttled`; 403 `rateLimitExceeded`/`userRateLimitExceeded`→backoff; 403 permiso→`capability_unavailable`; 5xx→`provider_unavailable`; `nextPageToken` con tope `limit`; Meet sin Doc→`[]` | `MockTransport` con secuencias (`429`→200, `401`→200); mismos ejes del 15 |
| Seguridad | Tokens jamás en respuestas/logs | Assert de no-fuga (reusa patrón del 14) |

## Threat Matrix

N/A para los ejes formales (routing web, shell, subprocess, automatización VCS/PR, clasificación de ejecutables): el adaptador solo hace HTTP con `httpx`, sin subprocess ni shell. Los riesgos OAuth/token **no se omiten**: van como RED tests de seguridad (no-fuga de tokens, `403 permiso→capability_unavailable`, refresh de un solo reintento). SSRF/redirect ya los cubre el `OAUTH_REDIRECT_ALLOWLIST` del 14.

## Migration / Rollout

Sin migración: reutiliza `connectors`/`connected_accounts`/`connection_credentials` del 14 — **verificado, sin cambio de ER** (`docs/diagrams/er-model.md` no se toca). Aditivo; rollback = revertir el merge (sin el import, `provider="google"` no existe y el 14 queda idéntico).

## Riesgos (adicional al proposal)

| Riesgo | Prob | Mitigación |
|--------|------|------------|
| El correo usado como `external_account_id` puede ser **cambiado por un admin de Workspace**; la identidad estable asumida (decisión #4, se mantiene) deja de coincidir con la cuenta previa | Baja | La reconexión OAuth re-enlaza por el correo **actual** (nuevo `ConnectedAccount` bajo `UNIQUE(connector_id, external_account_id)` del 14); la cuenta previa queda huérfana y se desconecta manualmente. Riesgo visible, no bloqueante |

## Open Questions

- [ ] `since/limit` concretos (`90d`/`50`) a re-alinear cuando aterrice el design del 15.
- [ ] Reclasificación de scopes Google: re-verificar clasificación restringida/sensible **en el apply**.
