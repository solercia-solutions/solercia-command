```yaml
schema: gentle-ai.verify-result/v1
verdict: pass
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 15/15
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v
test_exit_code: 1
test_output_hash: sha256:3a3438f1342796c19b4c1008f326843f1c7d671c964f13dabadaf30e8e6be3a7
build_command: cd backend && ruff check . && mypy app
build_exit_code: 0
build_output_hash: sha256:d56acb0407c1283c7767207d5e345474c8f3c3e685bea2637193aad1566fdafa+sha256:2508ce47149e5c8b84197c8418a2a18519ab9be671dacd74503f9af6f96df877
```

> `test_exit_code: 1` refleja las 13 fallas LEGACY preexistentes (ninguna del cambio 16, ninguna toca `app/integrations/adapters/google/`) — ver sección "Build & Tests Execution". `build_output_hash` combina los dos comandos declarados (`ruff` + `mypy`, cada uno con exit 0 y salida limpia).

## Verification Report

**Change**: 16-adapter-google
**Versión spec**: N/A (primer draft del requirement set, capability nueva `google-adapter`)
**Modo**: Strict TDD

### Completeness

| Métrica | Valor |
|---------|-------|
| Tareas totales (`tasks.md`, Lotes 1–6, IDs 1.1–6.7) | 28 |
| Tareas completas `[x]` | 28 |
| Tareas incompletas | 0 |
| Commits del cambio | 7 (`a072828`, `f25b401`, `c6f4745`, `b2f28bc`, `9f95dbf`, `75178ab`, `30fbe9d`) + fix 4R `dae7580` (fuera de `tasks.md`, entregable ratificado por el orquestador) |

`tasks.md` no tiene tareas explícitas para `dae7580` porque es un commit de corrección post-revisión 4R (fuera del ciclo TDD original documentado en `apply-progress`), no una tarea de implementación nueva — coherente con el patrón ya usado en 15-adapter-microsoft365 (`774ca29`).

### Build & Tests Execution

**Build** (`ruff check .` + `mypy app`, backend completo — 228 archivos ruff / 228 archivos mypy): ✅ Passed — "All checks passed!" / "Success: no issues found in 228 source files".

**Tests** (suite completa, ejecución propia e independiente de esta fase de verificación):
```text
811 items collected
13 failed, 798 passed, 1 warning in 188.42s (0:03:08)
```
Las 13 fallas son EXACTAMENTE las 13 legacy preexistentes ya documentadas en el precedente 15-adapter-microsoft365 (verificadas nombre por nombre): `test_upload_and_download_attachment`, `test_upload_rejects_oversized_file`, `test_download_requires_auth`, `test_create_comment_with_mentions`, `test_create_comment_empty_body_rejected`, `test_close_sprint_sums_only_done_tasks`, `test_close_sprint_moves_incomplete_to_backlog`, `test_close_sprint_idempotent_409`, `test_velocity_averages_closed_sprints`, `test_create_subtask_rejects_points`, `test_create_subtask_allows_hours`, `test_create_task_assigns_task_key`, `test_get_task_by_key` — todas por `httpx.LocalProtocolError: Illegal header value b'Bearer '` o `assert 404 == 401` (dependen de un servidor `API_BASE_URL` en vivo con `TEST_AUTH_TOKEN`, ausente en este entorno de ejecución). Ninguna toca `app/integrations/adapters/google/`. **Cero regresión**.

**Aritmética de la evolución**: 15-adapter-microsoft365 cerró en 729 passed/13 failed. 798 − 729 = **69 pruebas nuevas exactas** del cambio 16 (63 del apply original + 6 del fix `dae7580`: 2 en `test_adapter_google_mail.py` + 4 en `test_adapter_google_oauth.py`). Coincide con lo declarado por el orquestador.

**Suite del adaptador Google aislada** (`pytest tests/test_adapter_google_*.py -v`): **69/69 passed** (9 errors + 17 client + 15 oauth + 10 mail + 5 calendar + 5 meeting_notes + 8 registry).

**Coverage**: no se ejecutó herramienta de cobertura dedicada (no detectada en capacidades cacheadas) — informativo, no bloqueante.

### Evidencia del commit de fixes 4R `dae7580`

Confirmado en disco (no solo declarado): `git show dae7580 --stat` → 10 archivos, 307 inserciones/162 eliminaciones.

| # | Hallazgo original (4R) | Corrección verificada en código | Tests nuevos (RED demostrado) |
|---|------------------------|----------------------------------|-------------------------------|
| CRITICAL (seguridad) | `userinfo.email` se aceptaba sin `email_verified`/`verified_email` → secuestro de cuenta conectada por un correo sin verificar | `oauth.py::_fetch_email` ahora exige `payload.get("email_verified", payload.get("verified_email"))` truthy además de `email`; si falta cualquiera de las dos, `oauth_token_invalid()` | `test_unverified_email_is_rejected`, `test_missing_email_field_is_rejected`, `test_verified_email_via_oidc_key_is_accepted`, `test_verified_email_via_legacy_v2_key_is_accepted` (`test_adapter_google_oauth.py`, clase `TestUserinfoEmailVerification`) — 4/4 passed |
| WARNING (resiliencia) | Un fallo puntual de `messages.get` (mensaje borrado entre `list`/`get`) tumbaba TODO el listado de Gmail | `mail.py::GmailMailReader.list_messages` captura `AppException` por mensaje individual, loguea warning sin fuga de token y continúa con el resto (aislamiento N+1) | `test_one_message_get_failure_is_skipped_and_the_rest_still_list` — passed |
| WARNING (config) | `GOOGLE_DEFAULT_LIMIT` declarado en `config.py` pero nunca consumido por ningún puerto | `ports_base.py::_GooglePortBase._bounded_limit` resuelve `GOOGLE_DEFAULT_LIMIT` como default efectivo cuando `limit=None`, ANTES del clamp `GOOGLE_MAX_LIMIT` | `test_google_default_limit_setting_changes_the_effective_default` — passed |
| WARNING/estructura | `mail.py`/`calendar.py`/`meeting_notes.py` duplicaban verbatim `_bounded_limit`/`_page_size`/`_since_or_default`/`_refresh`/`_client` (mismo rol que `_GraphPortBase` del 15, sin consolidar) | Nueva `ports_base.py::_GooglePortBase` (75 líneas) parametrizada por `_base_url_setting`; los 3 puertos ahora heredan de ella, cero código propio duplicado | Cubierto transitivamente por los 69 tests existentes de los 3 puertos (mismo comportamiento, sin regresión) |
| WARNING/limpieza | `_THROTTLE_REASONS` declarado en `client.py` sin usarse desde ahí (vivía también en `errors.py`) | Eliminado el duplicado muerto en `client.py`; `errors.py` sigue siendo la única fuente de la taxonomía `_THROTTLE_REASONS` | N/A — remoción de código muerto, sin cambio de comportamiento |
| SUGGESTION | `verified` faltaba documentarse como criterio explícito de identidad (paralelo a `sso_service.py`) | Docstring de `_fetch_email` cita `sso_service.py:159-160` como precedente del mismo criterio de seguridad | N/A — documental |

**Ubicación exacta de la consolidación estructural verificada por `grep`**: `_bounded_limit`/`_page_size`/`_since_or_default`/`def _refresh`/`def _client` existen ÚNICAMENTE en `ports_base.py` (definición) — `mail.py`/`calendar.py`/`meeting_notes.py` solo contienen LLAMADAS (`self._bounded_limit(...)`, `self._page_size(...)`, `self._since_or_default(...)`), cero redefinición. Confirmado con `rg -n "_bounded_limit|_page_size|_since_or_default|def _refresh|def _client" app/integrations/adapters/google/*.py`.

### Spec Compliance Matrix

| Requisito | Escenario | Test(s) | Resultado |
|-----------|-----------|---------|-----------|
| GA-R1 Registro y protocolo uniforme | El adaptador aparece por su provider | `test_get_adapter_returns_google_instance_without_editing_the_core` | ✅ COMPLIANT |
| GA-R1 (íd.) | Capacidad no declarada queda excluida | `test_external_tasks_capability_is_not_declared` | ✅ COMPLIANT |
| GA-R2 Handshake OAuth → OAuthTokens | Canje de código devuelve el correo como identidad | `test_exchange_code_returns_tokens_with_the_email_as_external_account_id` (+ `test_verified_email_via_oidc_key_is_accepted`/`_via_legacy_v2_key_is_accepted` del fix) | ✅ COMPLIANT |
| GA-R2 (íd.) | Scopes solicitados son de solo lectura | `test_authorize_url_only_ever_contains_readonly_scopes` | ✅ COMPLIANT |
| GA-R3 Resiliencia — 401 | 401 dispara refresh y reintento único | `test_401_triggers_refresh_once_and_retries_successfully` | ✅ COMPLIANT |
| GA-R3 (íd.) — 429 | 429 respeta backoff | `test_429_honors_retry_after_and_succeeds` (+ techo: `test_429_retry_after_beyond_the_ceiling_sleeps_at_most_the_max`) | ✅ COMPLIANT |
| GA-R4 Gmail + MIME | Mensaje multiparte se decodifica a texto plano | `test_multipart_message_prefers_the_plain_text_part` | ✅ COMPLIANT |
| GA-R4 (íd.) | Labels no se traducen a carpeta | `test_labels_are_never_exposed_as_a_folder_field_on_mail_message` | ✅ COMPLIANT |
| GA-R5 Calendar API | since/limit acotan la consulta | `test_since_and_limit_translate_to_time_min_time_max_and_max_results` | ✅ COMPLIANT |
| GA-R6 Meet/Drive best-effort | Transcripción disponible se exporta | `test_transcript_available_is_exported_and_mapped` | ✅ COMPLIANT |
| GA-R6 (íd.) | Sin transcripción del organizador, degrada sin error | `test_no_recordings_folder_degrades_to_empty_list_without_error`, `test_folder_exists_but_no_docs_degrades_to_empty_list` | ✅ COMPLIANT |
| GA-R7 Capacidad no disponible | Falta de permiso Drive se reporta como capacidad no disponible | `test_no_permission_on_the_organizer_drive_raises_capability_unavailable` (+ `test_meeting_notes_failure_does_not_touch_mail_or_calendar_fixtures`) | ✅ COMPLIANT |
| GA-R8 Frontera solo lectura | Sin método de escritura en el adaptador | `test_client_and_every_port_never_call_a_write_http_verb`, `test_oauth_module_posts_only_to_the_token_endpoint_never_to_a_data_api`, `test_no_port_declares_more_than_its_one_read_method` | ✅ COMPLIANT |
| GA-R9 Transporte inyectable, cero red en CI | Pruebas del adaptador corren sin red | Estructural: los 69 tests del paquete usan `httpx.MockTransport`; `requirements.txt` no declara `google-api-python-client`/`google-auth` | ✅ COMPLIANT |
| GA-R10 Google Tasks fuera de corte | external_tasks ausente de capabilities | `test_declared_capabilities_are_exactly_mail_calendar_and_meeting_notes` | ✅ COMPLIANT |

**Resumen de cumplimiento**: 15/15 escenarios COMPLIANT — 10/10 requisitos con cobertura de test en verde.

### Seguridad (evidencia adicional)

- **Email sin verificar rechazado, ambas variantes de clave**: `_fetch_email` exige `email_verified` (OIDC, clave del `GOOGLE_USERINFO_BASE_URL` por defecto) O `verified_email` (userinfo v2 legacy) truthy — ambas cubiertas por test explícito, y el caso "ninguna de las dos presente" también (`test_missing_email_field_is_rejected` usa un payload sin `email`).
- **Scopes solo lectura**: `test_authorize_url_only_ever_contains_readonly_scopes` + `test_authorize_url_assembles_default_readonly_scopes_when_none_given` confirman que `authorize_url` nunca emite un scope de escritura (`gmail.readonly`/`calendar.readonly`/`drive.readonly` únicamente).
- **No fuga de tokens**: `test_no_token_leaks_in_caplog_or_exception_message` (client.py, con `caplog` a nivel `DEBUG`) y `test_no_token_leaks_in_caplog_or_exception_message_for_oauth` (oauth.py) — ambos assert explícito `"super-secret-*-token" not in caplog.text`.
- **Frontera solo lectura (guard AST)**: `_called_http_verbs()` usa `ast.parse`+`ast.walk` sobre `inspect.getsource(module)` filtrando `ast.Call` con `func` `ast.Attribute` cuyo `.attr` esté en `{get,post,put,patch,delete}` — evita falsos positivos de texto (`dict.get()` vs verbo HTTP). Confirmado con grep independiente: el único verbo de escritura en todo el paquete es `oauth.py`'s `.post(...)` contra `GOOGLE_TOKEN_BASE_URL` (nunca `GOOGLE_GMAIL_BASE_URL`/`GOOGLE_CALENDAR_BASE_URL`/`GOOGLE_DRIVE_BASE_URL`).

### Resiliencia (evidencia adicional)

- **Gotcha del refresh**: `test_refresh_without_a_new_refresh_token_keeps_the_previous_one` confirma que si Google no re-emite `refresh_token` en la respuesta (comportamiento frecuente documentado en design.md), el `OAuthTokens` resultante CONSERVA el `refresh_token` usado para pedir el refresh.
- **Backoff con techo**: `test_429_retry_after_beyond_the_ceiling_sleeps_at_most_the_max` — un `Retry-After` abusivo (3600s) nunca hace dormir al cliente más del techo configurado (`GOOGLE_MAX_BACKOFF_SECONDS`, `sleep` inyectado, sin espera real).
- **403 cuota vs permisos**: `errors.py::_THROTTLE_REASONS = {rateLimitExceeded, userRateLimitExceeded}` distingue cuota (→ `provider_throttled`, reintenta con backoff) de cualquier OTRA razón de `403` (→ `capability_unavailable`, sin permiso genuino) — `test_403_rate_limit_exceeded_maps_to_provider_throttled`/`test_403_drive_permission_denied_maps_to_capability_unavailable` cubren ambos caminos.
- **Aislamiento por mensaje (Gmail)**: `test_one_message_get_failure_is_skipped_and_the_rest_still_list` (fix `dae7580`) — un `404` puntual en `messages.get` se omite con warning logueado, el resto del listado se devuelve intacto.
- **Degradación best-effort de Drive**: `test_no_recordings_folder_degrades_to_empty_list_without_error` (sin carpeta) y `test_folder_exists_but_no_docs_degrades_to_empty_list` (carpeta sin Doc) devuelven `[]` sin error; `test_meeting_notes_failure_does_not_touch_mail_or_calendar_fixtures` confirma que la falla de `meeting_notes` no afecta las otras 2 capacidades del mismo adaptador en la misma sesión de prueba.

### Estructura — consolidación `_GooglePortBase`

Confirmada sin duplicación residual (ver tabla de evidencia del fix arriba). `ports_base.py` centraliza `_bounded_limit`/`_page_size`/`_since_or_default`/`_refresh`/`_client`; los tres puertos (`GmailMailReader`, `GoogleCalendarReader`, `DriveMeetingNotesReader`) heredan de `_GooglePortBase` y solo declaran `_base_url_setting` + su método público único (`list_messages`/`list_events`/`list_notes`). `test_no_port_declares_more_than_its_one_read_method` usa `vars(port_cls)` (namespace propio de la clase, no hereda de `_GooglePortBase`) para confirmar que cada puerto expone exactamente UN método público — compatible con la herencia introducida por el fix.

### Docs (C4)

- **C1 (contexto)**: `System_Ext(gws, "Google Workspace (Gmail/Calendar/Drive)", ...)` presente; el flujo del conector `provider=google` documentado en modo lectura únicamente.
- **C3 (componentes)**: nodo `i_google` bajo `app/integrations/adapters/google/` actualizado a **10 módulos** (`__init__`/`adapter`/`oauth`/`client`/`ports_base`/`mail`/`calendar`/`meeting_notes`/`mime`/`errors`) — confirmado contra el filesystem real (`ls app/integrations/adapters/google/*.py` → 10 archivos exactos). El fix `dae7580` corrigió el conteo de "9 módulos" (versión pre-fix) a "10 módulos" al agregar `ports_base.py`.
- **Ortografía**: "OAuth 2.0 estándar" (antes "estandar", corregido en `dae7580`) — verificado con tildes correctas en todo el bloque agregado/modificado; sin ocurrencias de palabras españolas sin tilde en las secciones tocadas (`rg` contra el diccionario de errores comunes → 0 coincidencias).
- **ER-model sin cambio**: `git diff --stat a072828^..dae7580 -- docs/diagrams/er-model.md` vacío — confirma "sin cambio de ER" de design.md.

### Correctness (Static Evidence)

| Requisito | Estado | Nota |
|-----------|--------|------|
| Registro import-time sin tocar el núcleo | ✅ Implementado | `__init__.py` → `register_adapter(GoogleAdapter())`; `db_init.py` importa `app.integrations.adapters.fake`, `app.integrations.adapters.google`, `app.integrations.adapters.microsoft365` — registro TRIPLE confirmado, ningún archivo del núcleo (`ports.py`/`oauth.py`/`registry.py` del 14) tocado |
| Handshake OAuth Google | ✅ Implementado | `oauth.py` — `authorize_url`/`exchange_code`/`refresh` sobre `accounts.google.com`/`oauth2.googleapis.com`/`openidconnect.googleapis.com` |
| `email_verified` obligatorio | ✅ Implementado (fix `dae7580`) | `oauth.py::_fetch_email` — antes aceptaba `email` sin verificar (CRITICAL de seguridad), ahora exige `email_verified`/`verified_email` truthy |
| Refresh 401→retry único | ✅ Implementado | `client.py` — un solo reintento, `oauth_token_invalid` si el refresh falla |
| Backoff 429/403-cuota + techo | ✅ Implementado | `GOOGLE_MAX_RETRIES` + `GOOGLE_MAX_BACKOFF_SECONDS` |
| Gmail MIME multiparte | ✅ Implementado | `mime.py` decodifica base64url multiparte a texto plano |
| Aislamiento por mensaje en Gmail | ✅ Implementado (fix `dae7580`) | `mail.py::list_messages` captura `AppException` por `messages.get` individual |
| Calendar since/limit | ✅ Implementado | `calendar.py` — `timeMin`/`maxResults` |
| Meet/Drive best-effort | ✅ Implementado | `meeting_notes.py` — sin carpeta/Doc → `[]`; `403` real → `capability_unavailable` |
| Frontera solo lectura | ✅ Implementado | Guard AST + verificación manual — único `POST` es OAuth hacia el token endpoint |
| `GOOGLE_DEFAULT_LIMIT` cableado | ✅ Implementado (fix `dae7580`) | `ports_base.py::_bounded_limit` — antes declarado en `config.py` sin consumir |
| `_GooglePortBase` consolidada | ✅ Implementado (fix `dae7580`) | Cero duplicación residual, confirmado por grep |
| `external_tasks`/`tickets` no declarados | ✅ Implementado | `GoogleAdapter.capabilities == {mail, calendar, meeting_notes}` exacto |

### Coherence (Design)

| Decisión | ¿Seguida? | Nota |
|----------|-----------|------|
| Estructura espejo del 15 (`{__init__,adapter,client,oauth,mail,calendar,meeting_notes,mime,errors}.py`) | ✅ Sí, con extensión ratificada | El fix `dae7580` agrega `ports_base.py` — desviación DOCUMENTADA (mismo rol que `_GraphPortBase` del 15, que el design original no anticipó), no rompe ningún escenario |
| `httpx` inyectable, sin SDK oficial | ✅ Sí | `requirements.txt` sin `google-api-python-client`/`google-auth` |
| Parseo MIME con stdlib (`email`/`base64`) | ✅ Sí | `mime.py` |
| Transcripciones Meet vía Drive, best-effort | ✅ Sí | `meeting_notes.py` |
| `external_account_id` = correo vía `userinfo` (decisión #4) | ✅ Sí, endurecida | Ahora exige `email_verified`/`verified_email` — endurecimiento de seguridad sobre la decisión original, no una desviación de la decisión en sí |
| Ventana `since`/`limit` (decisión de negocio: 30 días, no 90) | ✅ Sí | `GOOGLE_DEFAULT_SINCE_DAYS=30`, `GOOGLE_DEFAULT_LIMIT=50` — ratificado por el orquestador en tasks.md (ventana unificada con el 15) |
| Sin migración, sin cambio de ER | ✅ Sí | `git diff --stat` vacío sobre `er-model.md` |
| **Desviación #1**: `errors.py` (Lote 1) escrito antes que su test | ⚠️ Documentada | Única violación de RED-first del cambio (`apply-progress`), test escrito y verde inmediatamente después; a partir del Lote 2 RED→GREEN estricto confirmado con `ModuleNotFoundError`/`ImportError`. WARNING, no CRITICAL — no afecta el resultado final |
| **Desviación #2**: 5ª taxonomía `provider_request_failed` no listada en spec/design originales | ⚠️ Documentada | Instrucción explícita del orquestador (endurecimiento 4R del 15, distingue 4xx no reintentable de 5xx) |
| **Desviación #3**: `error_for_response` standalone en `errors.py` (más puro que el 15) | ⚠️ Documentada | Decisión para permitir un RED test standalone real en Lote 1 |
| **Desviación #4**: paginación `nextPageToken` opaco (no URL completa) → anti-SSRF estructural, no host-check en runtime como el `GraphHostMismatchError` del 15 | ⚠️ Documentada | Cubierta con `test_pagination_never_follows_a_response_supplied_host_only_a_token`; el vector que motiva el host-check del 15 no existe en Google (nunca sigue una URL de la respuesta) |
| **Desviación #5**: `GOOGLE_OAUTH_REDIRECT_URI` declarado en `config.py` pero nunca consumido | ⚠️ Documentada intencionalmente | El protocolo del 14 siempre recibe `redirect_uri` explícito del caller; el setting queda como referencia operativa (mismo patrón que `OAUTH_REDIRECT_ALLOWLIST`), documentado en el docstring de `config.py` — NO es un bug, es consumo diferido por diseño |
| **Desviación #6**: `external_account_id` vía `userinfo` (round-trip extra) en vez de leer `email` del `id_token` | ⚠️ Documentada, ahora con verificación | Decisión original para mantener un ÚNICO camino de resolución de identidad (`exchange_code` y `refresh` comparten `_fetch_email`); el fix `dae7580` refuerza esta misma ruta con `email_verified`, sin introducir un segundo camino |
| **Desviación #7**: volumen real (~3.880 inserciones) por encima del forecast (~1.400–1.800) | ⚠️ Documentada | Incluye ~600 líneas de proposal/design/spec nunca antes comprometidas + ~30 fixtures; cada commit individual autónomo y bajo revisión de calidad; `size:exception` ya aceptado por el orquestador cubre el agregado |
| **Nueva (post-fix)**: consolidación `_GooglePortBase` no prevista en el design original | ⚠️ Documentada, ratificada | Ver tabla de evidencia del fix — reduce duplicación sin cambiar comportamiento, mismo patrón que `_GraphPortBase` del 15 |

### Revisión 4R (recibo nativo)

Lineage `review-c9f1c291e63540ee` — confirmado en `.git/gentle-ai/review-transactions/v2/review-c9f1c291e63540ee/review-receipt.json`: `risk_level: high`, `selected_lenses: [review-risk, review-resilience, review-readability, review-reliability]`, `terminal_state: "escalated"`.

**Limitación conocida, señalada explícitamente por el orquestador**: el recibo permanece `escalated` porque el CRITICAL de seguridad (`email_verified`) disparó escalamiento durante la revisión — el commit de corrección `dae7580` llegó DESPUÉS del recibo y no lo reabre ni lo revalida automáticamente (los recibos son inmutables/vinculados al contenido revisado en su momento). Esta verificación (sdd-verify) confirmó independientemente, contra el código y los tests EN DISCO tras `dae7580`, que las 6 correcciones (incl. el CRITICAL) están implementadas y probadas en verde — pero **no sustituye ni reabre el ciclo de revisión nativo**. Antes de `pre-commit`/`pre-push`/`pre-pr`/`release` sobre este contenido, la acción de mantenedor correspondiente (revalidación o nuevo `review/start` explícito) sigue pendiente según el protocolo de recibos — **riesgo para el orquestador, no bloqueante para este verify de specs/tests**.

### Issues Found

**CRITICAL**: Ninguno (el único CRITICAL detectado por la revisión 4R —`email_verified`— está corregido y probado en verde, confirmado independientemente en esta fase).

**WARNING**:
1. El recibo nativo de revisión 4R (`review-c9f1c291e63540ee`) permanece en `terminal_state: escalated` porque el fix `dae7580` es posterior al recibo — requiere acción explícita de mantenedor (revalidación o nuevo `review/start`) antes de los gates `pre-commit`/`pre-push`/`pre-pr`/`release` sobre este contenido. No es un defecto de código; es un estado de proceso pendiente.
2. 7 desviaciones de diseño documentadas en `apply-progress` (ver tabla "Coherence (Design)") — ninguna rompe un escenario de spec, todas están explícitamente documentadas en docstrings/código, pero `design.md` no se actualizó para reflejar el as-built (incl. la nueva `ports_base.py` del fix). Recomendación: actualizar `design.md` en un futuro pase de mantenimiento de documentación (no bloquea archive).

**SUGGESTION**:
1. `test_pagination_never_follows_a_response_supplied_host_only_a_token` es el único test que prueba explícitamente la ausencia de vector anti-SSRF vía respuesta — sería valioso un comentario cruzado en `client.py` señalando este test como su prueba de regresión formal (ya existe parcialmente en el docstring de `errors.py`/`ports_base.py`, pero no en `client.py` mismo).

### Verdict

**PASS**

0 CRITICAL, 2 WARNING (1 de proceso/recibo de revisión — no de código; 1 documental sobre `design.md` desactualizado), 1 SUGGESTION. 798/811 tests en verde (13 fallas legacy idénticas, cero regresión, 798−729=69 pruebas nuevas exactas confirmadas), 15/15 escenarios de spec COMPLIANT con test real, 28/28 tareas de `tasks.md` coherentes con el código, el CRITICAL de seguridad de la revisión 4R (`email_verified`) corregido y probado en verde (4 tests nuevos), aislamiento por mensaje en Gmail probado, `GOOGLE_DEFAULT_LIMIT` cableado y probado, `_GooglePortBase` consolidada sin duplicación residual (confirmado por grep), ruff+mypy limpios, frontera solo-lectura confirmada por guard AST + inspección manual, degradación best-effort de Drive aislada por capacidad, ER-model sin cambio, C4 actualizado (C1+C3, 10 módulos, ortografía correcta), registro triple (fake+microsoft365+google) confirmado en `db_init.py`. Único riesgo pendiente: el recibo nativo de revisión permanece `escalated` por ser anterior al fix — requiere acción explícita de mantenedor antes de gates de commit/push/PR/release, no bloquea este verify de specs/tests.
