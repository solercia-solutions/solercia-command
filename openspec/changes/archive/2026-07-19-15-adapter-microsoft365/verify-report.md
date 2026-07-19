```yaml
schema: gentle-ai.verify-result/v1
verdict: pass
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 10/10
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v
test_exit_code: 1
test_output_hash: sha256:67d4c035b94b5acc67bb4ee594e8863b94b693fc119a6bec6a8bb6cef02cb9e3
build_command: cd backend && ruff check app && mypy app
build_exit_code: 0
build_output_hash: sha256:6a16561c69af70e74adbf2f06c7b76907f9ccfb25e436f82af160a860b389af1
```

> `test_exit_code: 1` refleja las 13 fallas LEGACY preexistentes (ninguna del cambio 15) — ver sección "Build & Tests Execution".

## Verification Report

**Change**: 15-adapter-microsoft365
**Versión spec**: N/A (primer draft del requirement set)
**Modo**: Strict TDD

### Completeness

| Métrica | Valor |
|---------|-------|
| Tareas totales (tasks.md, IDs 1.1–8.5) | 49 |
| Tareas completas `[x]` | 49 |
| Tareas incompletas | 0 |

**Nota de conteo**: `apply-progress` (Engram #1694) y el contexto de esta fase de verificación citan "39/39 tareas" — el conteo real de IDs numerados en `tasks.md` es **49/49**, todos `[x]`. Es un desajuste de reporte en el apply previo, no un defecto de implementación: cada uno de los 49 ítems está verificado contra el código real más abajo. No bloquea (WARNING documental, no CRITICAL).

### Build & Tests Execution

**Build** (`ruff check app` + `mypy app`, paquete completo, no solo el adaptador): ✅ Passed — "All checks passed!" / "Success: no issues found".

**Tests** (suite completa, 2 corridas independientes para confirmar determinismo):
```text
Corrida 1: 13 failed, 729 passed, 1 warning in 188.79s (0:03:08)
Corrida 2: 13 failed, 729 passed, 1 warning in 188.26s (0:03:08)
```
Las 13 fallas son EXACTAMENTE las 13 legacy preexistentes documentadas en `apply-progress` (verificado nombre por nombre en ambas corridas): `test_upload_and_download_attachment`, `test_upload_rejects_oversized_file`, `test_download_requires_auth`, `test_create_comment_with_mentions`, `test_create_comment_empty_body_rejected`, `test_close_sprint_sums_only_done_tasks`, `test_close_sprint_moves_incomplete_to_backlog`, `test_close_sprint_idempotent_409`, `test_velocity_averages_closed_sprints`, `test_create_subtask_rejects_points`, `test_create_subtask_allows_hours`, `test_create_task_assigns_task_key`, `test_get_task_by_key`. Ninguna toca `app/integrations/adapters/microsoft365/`. Cero regresión.

**Suite del adaptador aislada** (`pytest tests/test_adapter_microsoft365.py -v`, sin `TEST_DATABASE_URL`): 45 passed, 1 skipped (`test_authorize_route_redirects_to_entra_id_for_a_microsoft365_connector` — harness de runtime del Lote 3, requiere DB; se ejecuta y pasa dentro de la suite completa con `TEST_DATABASE_URL` seteado — confirmado en las 729 del total). Con `TEST_DATABASE_URL` seteado: **46/46 passed** (40 originales del apply + 6 nuevos del fix 774ca29).

**Aritmética de la evolución**: baseline pre-apply 683/13 → post-apply (Engram #1694) 723/13 (+40 tests nuevos) → post-fix 774ca29 729/13 (+6 tests nuevos). 723 + 6 = 729. ✅ Coincide exactamente con lo declarado por el orquestador.

**Alembic**: `test_alembic_check_reports_no_diff_after_upgrade` — ✅ passed (ejecutado con `TEST_DATABASE_URL`). Cero diff — confirma "ER-model NO cambia" de design.md. `docs/diagrams/er-model.md` sin cambios en el rango `7ac8da2^..774ca29` (`git diff --stat` vacío).

**Coverage**: no se ejecutó herramienta de cobertura dedicada (no detectada en capacidades cacheadas) — informativo, no bloqueante.

### Evidencia del commit de fixes `774ca29`

Confirmado en disco (no solo declarado): `git show 774ca29 --stat` → 8 archivos, 293 inserciones/32 eliminaciones, incluye 161 líneas nuevas en `test_adapter_microsoft365.py` (6 tests nuevos, todos verificados PASSED arriba):

| # | Test nuevo | Cubre |
|---|-----------|-------|
| 1 | `test_4xx_other_than_401_403_429_raises_a_non_retryable_domain_error` | `provider_request_failed` (4xx≠401/403/429, no reintentable) + logging sin fuga de token |
| 2 | `test_5xx_raises_the_retryable_provider_unavailable_error` | `provider_unavailable` (5xx, reintentable) + logging |
| 3 | `test_429_retry_after_beyond_the_ceiling_sleeps_at_most_the_max` | `M365_MAX_BACKOFF_SECONDS` clamp (`Retry-After` abusivo de 3600s → duerme máx. 30s) |
| 4 | `test_authorize_url_assembles_default_delegated_scopes_when_none_given` | `scopes=[]` nunca produce `scope=` vacío; ensambla `DEFAULT_DELEGATED_SCOPES` sin `.All` |
| 5 | `test_authorize_url_respects_explicit_scopes_when_the_caller_passes_some` | Scopes explícitos se respetan tal cual, sin mezclar con el default |
| 6 | `test_list_tasks_returns_empty_list_when_graph_denies_planner_access` | `403` real de Graph en Planner → `[]`, nunca error (spec M365-R5) |

Verificado en código real (no solo en el diff): `client.py._log_error_response` loguea status+body truncado (200 chars) sin tocar `Authorization`; `client.py._retry_after_seconds` aplica `min(seconds, M365_MAX_BACKOFF_SECONDS)`; `oauth.py.DEFAULT_DELEGATED_SCOPES`/`_effective_scopes` implementados y usados en `authorize_url`; `ports.py.GraphExternalTaskReader.list_tasks` captura `AppException` con `code == "capability_unavailable"` y degrada a `[]`. Ortografía del docs fix (`c4-architecture.md`, "via/autorizacion/organizacion/reunion" → "vía/autorización/organización/reunión") confirmada en el diff.

### Spec Compliance Matrix

| Requisito | Escenario | Test(s) | Resultado |
|-----------|-----------|---------|-----------|
| M365-R1 Registro sin editar el núcleo | Registro sin tocar el núcleo ni declarar tickets | `TestOAuthAndRegistry::test_get_adapter_returns_microsoft365_instance_without_editing_the_core`, `::test_tickets_capability_is_not_declared` | ✅ COMPLIANT |
| M365-R2 Handshake OAuth delegado | Tenant por defecto y override por configuración | `TestOAuthAndRegistry::test_authorize_url_uses_organizations_tenant_by_default`, `::test_authorize_url_uses_the_configured_tenant_override` | ✅ COMPLIANT |
| M365-R3 Refresco de token vencido | Refresco automático o error controlado | `TestGraphClientResilience::test_401_triggers_refresh_once_and_retries_successfully`, `::test_revoked_refresh_token_raises_controlled_error_without_looping` | ✅ COMPLIANT |
| M365-R4 Correo/calendario, ventana+paginación | Resultados dentro de la ventana, multi-página | `TestMailPort::test_list_messages_aggregates_dtos_from_two_pages_respecting_limit`, `TestCalendarPort::test_list_events_aggregates_dtos_from_two_pages_respecting_limit` | ✅ COMPLIANT |
| M365-R4 (íd.) | Sin resultados en la ventana | `TestMailPort::test_list_messages_returns_empty_list_without_error`, `TestCalendarPort::test_list_events_returns_empty_list_without_error` | ✅ COMPLIANT |
| M365-R5 Tareas Planner (sin To Do) | Tenant con y sin Planner | `TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window`, `::test_list_tasks_returns_empty_list_when_tenant_has_no_plans`, `::test_list_tasks_returns_empty_list_when_graph_denies_planner_access` (fix) | ✅ COMPLIANT |
| M365-R6 Notas de reunión, degradación | Consentimiento otorgado | `TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto` | ✅ COMPLIANT |
| M365-R6 (íd.) | Consentimiento no otorgado degrada sin afectar el resto | `TestMeetingNotesPort::test_missing_scope_degrades_to_capability_unavailable_without_network`, `::test_runtime_403_also_degrades_to_capability_unavailable`, `::test_meeting_notes_degradation_does_not_affect_other_capabilities` | ✅ COMPLIANT |
| M365-R7 Backoff ante 429 | Retry-After se respeta y agotamiento controlado | `TestGraphClientResilience::test_429_honors_retry_after_and_succeeds`, `::test_429_beyond_max_retries_raises_controlled_error`, `::test_429_retry_after_beyond_the_ceiling_sleeps_at_most_the_max` (fix) | ✅ COMPLIANT |
| M365-R8 Frontera solo-lectura | Ninguna capacidad invoca escritura | `TestWriteBoundary::test_client_and_ports_never_call_a_graph_write_verb`, `::test_oauth_module_posts_only_to_the_login_endpoint_never_to_graph`, `::test_this_guard_documents_a_regression_boundary_not_a_new_finding` | ✅ COMPLIANT |

**Resumen de cumplimiento**: 10/10 escenarios COMPLIANT — 8/8 requisitos con cobertura de test en verde.

### Frontera solo-lectura (guardia AST + grep propio)

`_called_http_verbs()` en `tests/test_adapter_microsoft365.py` usa `ast.parse` + `ast.walk` sobre `inspect.getsource(module)`, filtrando `ast.Call` cuyo `func` es `ast.Attribute` con `.attr` en `{get,post,put,patch,delete}` — evita falsos positivos de texto (p. ej. `dict.get()` vs `httpx_client.get()`, ambos comparten nombre pero el filtro real son los verbos de ESCRITURA). Verificado con grep independiente (`rg "\.(post|put|patch|delete)\("` sobre el paquete): el ÚNICO verbo de escritura en todo `adapters/microsoft365/` es `oauth.py:140` (`http_client.post(endpoint, data=data)`), dirigido exclusivamente a `M365_LOGIN_BASE_URL` (Entra ID `/token`), nunca a `M365_GRAPH_BASE_URL`. `client.py`/`ports.py` no contienen ningún verbo de escritura. Frontera confirmada tanto por el guard automatizado como por inspección manual independiente.

### Degradaciones (capacidad aislada)

- **Transcripciones sin consent**: `GraphMeetingNotesReader.list_notes` introspecciona `_MEETING_NOTES_SCOPE not in ctx.scopes` ANTES de red (sin llamada HTTP) → `capability_unavailable()`; fallback en runtime, `403` real de Graph → mismo mapeo vía `GraphClient._get` (`status_code == 403` → `capability_unavailable()`). `test_meeting_notes_degradation_does_not_affect_other_capabilities` confirma que correo/calendario/tareas del MISMO adaptador siguen funcionando en la misma sesión de prueba. ✅ Verificado.
- **Planner 403**: `GraphExternalTaskReader.list_tasks` captura `AppException` con `code == "capability_unavailable"` (mapeado desde el `403` de `GraphClient`) y degrada a `[]` — nunca propaga error (spec.md, "NUNCA error"). Verificado con `no_consent_403.json` real vía `MockTransport`. ✅ Verificado.
- Ambas degradaciones son estrictamente por capacidad — ninguna toca las otras 3 capacidades del mismo adaptador, confirmado por test explícito para meeting_notes y por diseño (try/except acotado al propio método) para Planner.

### Persistencia real del refresh de tokens (`on_tokens_refreshed`)

`GraphClient._refresh_tokens` invoca `ctx.on_tokens_refreshed(new_tokens)` cuando el sink está presente (confirmado por `test_401_triggers_refresh_once_and_retries_successfully`, que verifica `sink_calls[0].access_token == "fresh-access-token"` sobre un sink FAKE inyectado en el test). Búsqueda exhaustiva de `AccessContext(` en todo `app/` (excluyendo `tests/`): **cero coincidencias** — `AccessContext` solo se construye en 3 archivos de test (`test_adapter_microsoft365.py`, `test_integration_fake_adapter.py`, `test_integration_ports_contract.py`). No existe ningún router/servicio de producción que construya un `AccessContext` con un `on_tokens_refreshed` real apuntando a `connectors`/`connected_accounts`.

**Conclusión**: el sink se invoca correctamente (mecanismo probado), pero NO hay wiring de producción a persistencia todavía — no aplica el patrón de dos sesiones independientes porque no existe ningún flujo real que escriba. Esto coincide exactamente con lo declarado en `design.md` ("Open Questions": *"si el sink falta, la persistencia de tokens rotados se difiere al consumidor, ola 22"*) y en `apply-progress`. Se declara como **diseño esperado y correctamente documentado**, no como hallazgo.

### Correctness (Static Evidence)

| Requisito | Estado | Nota |
|-----------|--------|------|
| Registro import-time sin tocar el núcleo | ✅ Implementado | `__init__.py` llama `register_adapter(Microsoft365Adapter())`; `ports.py`/`oauth.py`/`registry.py` del 14 sin diff |
| Handshake OAuth Entra ID | ✅ Implementado | `oauth.py` — `authorize`/`token` sobre `M365_LOGIN_BASE_URL/{tenant}/oauth2/v2.0/*` |
| `id_token` sin reverificación de firma | ✅ Aceptado (lente de riesgo) | Llamada servidor-a-servidor TLS directa; identidad viene del `state` ligado al caller autenticado, no del token — documentado en docstring de `oauth.py` |
| Refresh 401→retry único | ✅ Implementado | `client.py._get` — `used_refresh` evita bucle |
| Backoff 429 acotado + clamp | ✅ Implementado | `_retry_after_seconds` con `min(..., M365_MAX_BACKOFF_SECONDS)` (fix 774ca29) |
| Mail/Calendar paginación + ventana | ✅ Implementado | `paginate()` sigue `@odata.nextLink` con `M365_MAX_PAGES` |
| Planner solo, sin To Do, degradación 403→[] | ✅ Implementado | `GraphExternalTaskReader` + captura `capability_unavailable` (fix 774ca29) |
| Meeting notes degradación por consentimiento | ✅ Implementado | Introspección `ctx.scopes` sin red + `403`→`capability_unavailable` |
| Frontera solo-lectura | ✅ Implementado | Guard AST + verificación manual — único `POST` es OAuth hacia login, nunca Graph |
| Manejo 4xx/5xx global + logging sin fuga | ✅ Implementado | `errors.provider_request_failed` (4xx≠401/403/429) vs `provider_unavailable` (5xx); `_log_error_response` trunca body, nunca loguea `Authorization` |
| Scopes por defecto nunca vacíos | ✅ Implementado | `DEFAULT_DELEGATED_SCOPES` + `_effective_scopes` (fix 774ca29); `.All` de transcripciones excluido del default (ADR #1) |

### Coherence (Design)

| Decisión | ¿Seguida? | Nota |
|----------|-----------|------|
| Scopes de transcripción opt-in (no en default) | ✅ Sí | `DEFAULT_DELEGATED_SCOPES` excluye `OnlineMeetingTranscript.Read.All` |
| Detección de `meeting_notes` por introspección sin red | ✅ Sí | `if _MEETING_NOTES_SCOPE not in ctx.scopes: raise ... ` antes de cualquier `await client.*` |
| Refresh dentro del adaptador (401→refresh→retry once) | ✅ Sí | `client.py._refresh_tokens`, sink opcional `on_tokens_refreshed` |
| Confidential-client (`client_secret`), PKCE diferido | ✅ Sí | `oauth.py._post_token` usa `client_secret`; sin `code_verifier` |
| `external_account_id` = claim `oid` | ✅ Sí | `oauth._tokens_from_payload` usa `oid`, nunca UPN |
| Defaults `since`/`limit` (decisión #4) | ✅ Sí | `M365_DEFAULT_SINCE_DAYS=30`, `M365_CALENDAR_FUTURE_DAYS=90`, `M365_MAX_PAGES=20`, `M365_MAX_LIMIT=200` en `config.py` |
| **Desviación**: endpoint de transcripciones | ⚠️ Documentada | design.md/tasks.md mencionan `/me/onlineMeetings/{id}/transcripts` per-reunión; el as-built usa `/me/onlineMeetings/getAllTranscripts` porque Graph no ofrece un "listar todas mis reuniones" sin filtro previo — evita un flujo multi-hop fuera del presupuesto del lote. Documentado explícitamente en el docstring de `ports.py`/`GraphMeetingNotesReader` y en `apply-progress`. No rompe ningún escenario de spec (ambos escenarios de M365-R6 pasan). WARNING, no CRITICAL. |
| **Desviación**: Planner `assignee`/`url` | ⚠️ Documentada | `assignee` = primer oid de `assignments` (no email, Graph no lo da sin `$expand`); `url` siempre `None` (Planner v1.0 no expone `webUrl`). Documentado en docstring de `mappers.map_external_task`. No rompe M365-R5 (el spec no exige email ni URL). SUGGESTION — mejora futura fuera de alcance de este cambio. |
| C4 C3: nodo `microsoft365` bajo Integrations/adapters | ✅ Sí | `i_ms365` anidado en `subgraph integrations_e["app/integrations (change 14)"]`, junto a `i_ports`/`i_registry`/`i_fake` |
| ER-model sin cambio | ✅ Sí | `git diff --stat 7ac8da2^..774ca29 -- docs/diagrams/er-model.md` vacío; `test_alembic_check_reports_no_diff_after_upgrade` verde |

### Revisión 4R (recibo nativo)

Lineage `review-3cd4e895bb13c963` — confirmado en `.git/gentle-ai/review-transactions/v2/review-3cd4e895bb13c963/review-receipt.json`: `risk_level: high`, `selected_lenses: [review-risk, review-resilience, review-readability, review-reliability]`, `terminal_state: "approved"`. Primer recibo APPROVED de la serie del cambio 15, tal como declara el contexto del orquestador. Los 4 WARNINGs + 3 SUGGESTIONs del ciclo quedaron corregidos en `774ca29`, con los 6 tests nuevos como evidencia RED→GREEN (confirmado arriba).

### Issues Found

**CRITICAL**: Ninguno.

**WARNING**:
1. Desajuste de conteo entre lo declarado ("39/39 tareas" en `apply-progress` y en el contexto de esta fase) y el conteo real de `tasks.md` (49/49 tareas, IDs 1.1–8.5, todos `[x]`). No afecta el código ni los tests — es un error de reporte en el apply previo. Recomendación: corregir el número en futuras referencias a este cambio.
2. Desviación del endpoint de transcripciones (`getAllTranscripts` en vez del per-reunión mencionado literalmente en design.md/tasks.md) — documentada in-code y en apply-progress, no rompe ningún escenario, pero design.md/tasks.md no se actualizaron para reflejar el as-built. Recomendación: actualizar design.md en un futuro pase de mantenimiento de documentación (no bloquea archive).

**SUGGESTION**:
1. Planner `assignee`/`url` limitados (oid sin resolver a email; `url` siempre `None`) — mejora futura de UX si se necesita mostrar el asignado por nombre/email en la vista ejecutiva; no exigido por spec.md.
2. El sink `on_tokens_refreshed` está probado pero sin wiring de producción — correcto y esperado para esta ola, pero vale la pena que la ola 22 (wiring del engine) incluya explícitamente un test de persistencia de dos sesiones independientes cuando se cablee.

### Verdict

**PASS**

0 CRITICAL, 2 WARNING (documentales/no bloqueantes), 2 SUGGESTION. 729/729 tests esperados en verde (13 fallas legacy idénticas, cero regresión, confirmado en 2 corridas independientes), 10/10 escenarios de spec COMPLIANT con test real, 49/49 tareas de tasks.md coherentes con el código, ruff+mypy limpios, frontera solo-lectura confirmada por guard AST + inspección manual, degradaciones aisladas por capacidad, ER-model sin cambio, C4 actualizado con ortografía correcta, recibo nativo de revisión 4R APPROVED.
