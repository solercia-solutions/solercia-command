# Tasks: 17 · Adaptador GLPI (casos + homologación de usuarios)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~3.400–3.800 (adaptador `glpi/` 6 archivos ~450 + fixtures GLPI ~130 + `glpi_sync/` 6 archivos ~600 + migración+modelos ~330 + deltas núcleo 14 ~230 + docs+config+wiring ~100 + tests ~1.700) |
| Riesgo de presupuesto (400 líneas) | High acumulado (8 lotes); Lotes 2 y 8 superan individualmente las 400 líneas por acoplamiento inherente (migración+3 modelos ORM+doc en Lote 2; cola+mapeos+REST+integración+doc C4 en Lote 8) |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote 1 (deltas núcleo 14) → Lote 2 (migración+modelos+er-model.md) → Lote 3 (conectores api_token) → Lote 4 (cliente GLPI base+SSRF) → Lote 5 (cache de sesión Redis) → Lote 6 (adaptador completo+registro) → Lote 7 (cascada de homologación) → Lote 8 (cola+mapeos+REST+c4-architecture.md+VERIFY final) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, un commit por lote (sin PR) |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota de tamaño por lote**: `delivery_strategy: exception-ok` ya cubre la excepción de los Lotes 2 y 8; no requiere pregunta adicional antes del apply.

**Orden serializado (fijado por el orquestador)**: el apply de este cambio va DESPUÉS de los applies de 14/15/16 (necesita `app/integrations/` del 14 en disco) y ANTES de 18/19 (que consumen `connectors.credential_kind`/`connectors.settings`). El Lote 1 abre con verificación explícita en disco.

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Deltas núcleo 14: `CredentialKind`, `OAuthHandshake`/`ApiTokenHandshake`, `ExternalPerson`, `Ticket.assignees` | 1 — `feat(integrations): credential_kind api_token y assignees en el nucleo de puertos` | `cd backend && pytest tests/test_integration_glpi_deltas.py -v` | N/A — piezas de puertos/dtos puras; verificadas con un adaptador de prueba local, sin HTTP | Revert commit; sin migración propia, sin consumidores fuera de `app/integrations/` |
| 2 | Migración única (`numero_documento`, `connectors.credential_kind`/`settings`, 3 tablas GLPI) + modelos ORM + `er-model.md` | 2 — `feat(glpi-sync): migracion de homologacion glpi con documento y ajustes de conectores` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_glpi_sync_migration.py -v` | Ciclo `alembic upgrade head`/`alembic downgrade -1` contra BD desechable (patrón `test_connectors_migration.py`) | Revert commit + `alembic downgrade -1` (elimina las 3 tablas GLPI → `connectors.settings`/`credential_kind` → `numero_documento`, sin filas vivas previas) |
| 3 | Conectores `api_token`: registro directo de credenciales + `authorize` rechazado | 3 — `feat(connectors): registro directo de credenciales api_token` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_api_token.py -v` | `httpx.AsyncClient` contra `POST /connectors/{id}/credentials` con un conector `credential_kind=api_token` sembrado y un adaptador de prueba `ApiTokenHandshake` | Revert commit; ruta y ramificación aislada del flujo `oauth` existente |
| 4 | Cliente GLPI base: `initSession`/`killSession`, paginación `Range`, allowlist anti-SSRF | 4 — `feat(glpi): cliente http base con paginacion range y allowlist anti-ssrf` | `cd backend && pytest tests/test_adapter_glpi.py -k TestGlpiClientBase -v` | N/A — pieza interna sin endpoint propio; verificada con `httpx.MockTransport` in-process | Revert commit; `client.py` es archivo nuevo sin consumidores todavía |
| 5 | Cache de `session_token` en Redis (TTL, reuso, reinicio ante `401`) | 5 — `feat(glpi): cache de session_token en redis con ttl y reinicio ante expiracion` | `cd backend && pytest tests/test_adapter_glpi.py -k "TestGlpiClientBase or TestGlpiSessionCache" -v` | N/A — mismo motivo; `fakeredis` + `MockTransport` | Revert commit; amplía `client.py`/crea `session.py`, sin otros módulos que los importen aún |
| 6 | Adaptador completo: `mapper.py`+`adapter.py`+`errors.py`+registro import-time | 6 — `feat(glpi): adaptador completo con asignados y registro en el nucleo` | `cd backend && pytest tests/test_adapter_glpi.py -v` (suite del adaptador) | `get_adapter("glpi").port_for(Capability.tickets)` invocado directo en tests contra `MockTransport` | Revert commit; `__init__.py`/`adapter.py`/`db_init.py` (1 línea); revertir deja el registro sin `provider="glpi"`, `fake` intacto |
| 7 | Cascada de homologación (correo→documento→nombre), sin BD | 7 — `feat(glpi-sync): cascada de homologacion por correo documento y nombre` | `cd backend && pytest tests/test_glpi_sync_matching.py -v` | N/A — funciones puras de normalización/matching, sin red ni BD | Revert commit; `service.py` (parte matching) sin consumidores del router aún |
| 8 | Cola cabecera/detalle + mapeos + REST + wiring final | 8 — `feat(glpi-sync): cola de pendientes mapeos rest y wiring final` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_glpi_sync.py -v` | `httpx.AsyncClient` contra `POST /glpi-sync/run` y los endpoints de cola/links con `MockTransport` simulando GLPI; VERIFY final `pytest tests/ -v` (suite completa) | Revert commit; rutas y repository/service nuevos, sin dependientes fuera del módulo |

## Lote 1 — Deltas núcleo 14: `credential_kind` + `assignees` (Commit 1)

- [x] 1.1 [Preflight] Verificar en disco que `app/integrations/{ports,dtos,registry,crypto}.py` (14) existen y exponen `Capability`, `IntegrationAdapter`, `register_adapter`/`get_adapter`, `encrypt`/`decrypt`, DTOs `Ticket`/`OAuthTokens`. Si falta alguno, detener y reportar bloqueo (17 depende del 14 aplicado).
- [x] 1.2 [Preflight] Verificar `app/shared/redis.py`: si el 14 o el 20 ya lo crearon, reutilizar `get_redis_client()` sin tocarlo; si no existe, crearlo aquí (mismo patrón condicional del 14 Lote 1).
- [x] 1.3 RED `backend/tests/test_integration_glpi_deltas.py`: `Ticket.assignees` es `tuple[ExternalPerson, ...]` vacía por defecto, nunca `None`; `ExternalPerson(external_id, display_name, email, document)` es dataclass frozen; `CredentialKind` expone `oauth`/`api_token`; un adaptador de prueba con `credential_kind=api_token` y sin `OAuthHandshake` hace que `oauth.build_authorize`/`handle_callback` del núcleo rechacen la operación con un error controlado, sin generar `state`. [IP17-R1, IP17-R2]
- [x] 1.4 VERIFY confirmar T1.3 en ROJO antes de GREEN.
- [x] 1.5 GREEN `app/integrations/dtos.py`: agregar `ExternalPerson` (frozen) y campo `assignees: tuple[ExternalPerson, ...] = ()` en `Ticket`.
- [x] 1.6 GREEN `app/integrations/ports.py`: `CredentialKind(StrEnum)`; extraer los métodos OAuth existentes (`authorize_url`/`exchange_code`/`refresh`) a `OAuthHandshake` (Protocol); nuevo `ApiTokenHandshake` (`connect(raw: Mapping[str, str]) -> AccountRef`); `IntegrationAdapter` gana `credential_kind` y expone `oauth`/`api_token` según corresponda, sin métodos opcionales `None` en un único Protocol.
- [x] 1.7 GREEN `app/integrations/oauth.py`: `build_authorize`/`handle_callback` verifican `credential_kind == oauth` antes de operar; si no, error de dominio claro.
- [x] 1.8 VERIFY `cd backend && pytest tests/test_integration_glpi_deltas.py -v` en verde; `ruff check .`/`mypy app` limpios en `app/integrations/`.

  **Desviación documentada**: T1.6 exigía que `IntegrationAdapter` "gane" `credential_kind`/`oauth`/`api_token` sin romper el as-built 15/16. Como el test de contrato existente (`test_integration_ports_contract.py::test_integration_adapter_protocol_declares_no_write_operation`) fijaba el set exacto de métodos declarados en `IntegrationAdapter` (`authorize_url/exchange_code/refresh/port_for`), extraerlos a `OAuthHandshake` es un cambio MODIFICADO explícito del spec delta (`specs/integration-ports/spec.md`), así que ese test se actualizó como parte del GREEN (no es una regresión silenciada) y se sumaron dos tests nuevos para `OAuthHandshake`/`ApiTokenHandshake`. Los 3 adaptadores as-built (`fake`, `microsoft365`, `google`) se ajustaron con `credential_kind = CredentialKind.oauth` + `self.oauth: OAuthHandshake | None = self` + `self.api_token: ApiTokenHandshake | None = None` (comportamiento en tiempo de ejecución sin cambios; solo satisface el nuevo Protocol para mypy). `connectors/service.py` sigue llamando `adapter.exchange_code(...)` directo (funciona en runtime porque el método sigue en la clase concreta) — su ramificación formal por `credential_kind` queda para el Lote 3 tal como lo fija tasks.md.

## Lote 2 — Migración única + modelos ORM + `er-model.md` (Commit 2)

- [ ] 2.1 [Foundation] Verificar el head real de Alembic (`cd backend && alembic heads`) EN VIVO justo antes de nombrar el archivo de migración; anclar `down_revision` al head real (NO hardcodear el número asumido en design.md).
- [ ] 2.2 [Foundation] `app/shared/enums.py`: `MatchMethod` (`email|document|name|manual`, `native_enum=False`), `UnmatchedStatus` (`pending|resolved|ignored`, `native_enum=False`).
- [ ] 2.3 [Foundation] `app/modules/connectors/models.py` (ampliar, delta 14): columnas `credential_kind CredentialKind default=oauth` y `settings JSONB NULL`.
- [ ] 2.4 [Foundation] `app/modules/glpi_sync/__init__.py`, `models.py`: `GlpiUserLink` (Pk+Timestamp+SoftDelete+Audit+Tenant; `connector_id FK CASCADE`, `glpi_user_id String(64)`, `user_id FK CASCADE`, `match_method MatchMethod`, `glpi_username?`, `glpi_email?`; `UNIQUE(connector_id, glpi_user_id)`); `GlpiUnmatchedAssignee` cabecera (Pk+Timestamp+Audit+Tenant; `connector_id FK CASCADE`, `glpi_user_id`, `glpi_username?`, `glpi_email?`, `glpi_document?`, `candidates JSONB`, `status UnmatchedStatus default=pending`, `resolved_user_id FK SET NULL?`, `resolved_at?`; `UNIQUE(connector_id, glpi_user_id)`); `GlpiUnmatchedCase` detalle (Pk+Timestamp; `unmatched_assignee_id FK CASCADE`, `glpi_ticket_id String(64)`, `glpi_ticket_title?`, `glpi_ticket_status?`; `UNIQUE(unmatched_assignee_id, glpi_ticket_id)`).
- [ ] 2.5 [Foundation] `app/db_init.py`: importar `GlpiUserLink`/`GlpiUnmatchedAssignee`/`GlpiUnmatchedCase` (registro en `Base.metadata`).
- [ ] 2.6 [Foundation] Migración (nombre confirmado en T2.1): `users.numero_documento String(32)?` + índice único parcial `WHERE numero_documento IS NOT NULL`; `connectors.credential_kind`+`connectors.settings JSONB NULL`; 3 tablas GLPI con FKs/unicidades/índices explícitos; `downgrade()` en orden inverso completo (`glpi_unmatched_cases` → `glpi_unmatched_assignees` → `glpi_user_links` → `connectors.settings`+`credential_kind` → `numero_documento`).
- [ ] 2.7 RED `backend/tests/test_glpi_sync_migration.py` (BD desechable + `alembic upgrade head`/`downgrade -1`): round-trip sin filas vivas; índice único parcial de `numero_documento` permite múltiples `NULL` y rechaza duplicado no-nulo; `UNIQUE(connector_id, glpi_user_id)` en `glpi_user_links` y en la cabecera; `UNIQUE(unmatched_assignee_id, glpi_ticket_id)` en el detalle. [UH-R1]
- [ ] 2.8 VERIFY confirmar T2.7 en ROJO antes de GREEN; luego `cd backend && alembic upgrade head` limpio + `pytest tests/test_glpi_sync_migration.py -v` en verde; `alembic check` sin diff.
- [ ] 2.9 [Docs] `docs/diagrams/er-model.md`: agregar `glpi_user_links`, `glpi_unmatched_assignees` (cabecera) **1:N** `glpi_unmatched_cases` (detalle), `users.numero_documento`, `connectors.credential_kind`, `connectors.settings JSONB` — mismo commit que la migración (obligatorio).

## Lote 3 — Conectores `api_token`: registro directo + `authorize` rechazado (Commit 3)

- [ ] 3.1 [Foundation] `app/modules/connectors/schemas.py` (ampliar): `ConnectorCreate`/`ConnectorRead` exponen `credential_kind`/`settings` (nunca secretos); `ApiTokenCredentials` (schema de entrada genérico, ej. `{"app_token": ..., "user_token": ...}` para GLPI).
- [ ] 3.2 [Foundation] `app/modules/connectors/service.py` (ampliar): `register_api_token_credentials(connector_id, raw, membership)` → `404` si conector ajeno/inexistente o `credential_kind != api_token`; invoca `adapter.api_token.connect(raw)` → `AccountRef`; cifra y persiste vía `crypto.encrypt`+`repository.upsert_account`+`save_credentials` (reuso de `ConnectionCredentials`, patrón del 14).
- [ ] 3.3 RED `backend/tests/test_connectors_api_token.py`: admin registra credenciales `api_token` contra un adaptador de prueba `ApiTokenHandshake` → se cifran y persisten sin exponerse en la respuesta; member → `403`; conector ajeno/inexistente → `404`; `GET /connectors/{id}/authorize` sobre conector `credential_kind=api_token` responde error controlado sin generar `state` ni URL; conector `oauth` por defecto sin especificar `credential_kind`. [C17-R1, C17-R2, C17-R3]
- [ ] 3.4 VERIFY confirmar T3.3 en ROJO (ruta inexistente) antes de GREEN.
- [ ] 3.5 GREEN `app/modules/connectors/router.py` (ampliar): `POST /connectors/{id}/credentials` (`Depends(require_role(MemberRole.admin, MemberRole.manager))`); `GET /connectors/{id}/authorize` (ampliar): rama `credential_kind=api_token` → error controlado antes de tocar `oauth.build_authorize`.
- [ ] 3.6 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_api_token.py -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 4 — Cliente GLPI base: `initSession`/paginación/allowlist (Commit 4)

- [ ] 4.1 [Fixtures] `tests/fixtures/glpi/init_session.json`, `kill_session.json`, `ticket_page_1.json` (con header `Content-Range` simulado), `ticket_page_2.json`.
- [ ] 4.2 [Foundation] `app/config.py`: `GLPI_SESSION_TTL_SECONDS` (default conservador), `GLPI_BASE_URL_ALLOWLIST` (análogo a `OAUTH_REDIRECT_ALLOWLIST` del 14).
- [ ] 4.3 RED `backend/tests/test_adapter_glpi.py::TestGlpiClientBase`: `GlpiClient` rechaza `base_url` sin esquema http(s) o fuera de `GLPI_BASE_URL_ALLOWLIST` **antes** de cualquier request HTTP (cero invocaciones al `MockTransport`); `initSession` envía `App-Token`+`Authorization: user_token ...` y devuelve `session_token`; `killSession` envía `Session-Token`+`App-Token`; paginación por header `Range` ensambla ambas páginas hasta agotar `Content-Range`. [Threat Matrix: SSRF — `client.py`]
- [ ] 4.4 VERIFY confirmar T4.3 en ROJO (módulo inexistente) antes de GREEN.
- [ ] 4.5 GREEN `app/integrations/adapters/glpi/client.py`: `GlpiClient(base_url, *, transport=None)`; valida `base_url` contra `GLPI_BASE_URL_ALLOWLIST` en el constructor; `init_session`/`kill_session`; `list_tickets(range_start, range_end)` vía header `Range`.
- [ ] 4.6 VERIFY `cd backend && pytest tests/test_adapter_glpi.py -k TestGlpiClientBase -v` en verde; `ruff check .`/`mypy app` limpios en `client.py`.

## Lote 5 — Cache de `session_token` en Redis + reinicio ante `401` (Commit 5)

- [ ] 5.1 [Fixtures] `tests/fixtures/glpi/session_expired_401.json`.
- [ ] 5.2 RED `TestGlpiSessionCache`: primera lectura sin cache llama `initSession` y cachea `session_token` en Redis (`SETEX glpi:session:{connector_id}`, TTL=`GLPI_SESSION_TTL_SECONDS`); segunda lectura reutiliza el cache sin llamar `initSession` de nuevo; `401`/expiración detectada invalida el cache, reinicia sesión UNA vez y reintenta la operación original de forma transparente; reinicio con credenciales revocadas propaga error controlado sin dejar `session_token` inválido cacheado; ningún `session_token`/`app_token`/`user_token` aparece en `caplog` ni en `str(exception)`. [GA-R2, GA-R3; Threat Matrix: sin fuga de secretos]
- [ ] 5.3 VERIFY confirmar T5.2 en ROJO antes de GREEN.
- [ ] 5.4 GREEN `app/integrations/adapters/glpi/session.py`: `get_or_init_session(connector_id, client) -> str` (Redis GET/SETEX); `with_session_retry(fn)` intercepta `401`, invalida cache, reinicia y reintenta 1 vez.
- [ ] 5.5 VERIFY `cd backend && pytest tests/test_adapter_glpi.py -k "TestGlpiClientBase or TestGlpiSessionCache" -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 6 — Adaptador completo: `mapper`+`adapter`+`errors`+registro (Commit 6)

- [ ] 6.1 [Fixtures] `tests/fixtures/glpi/ticket_user_assigned.json` (`type=2`), `ticket_user_requester_only.json` (`type=1`), `user.json`, `user_email.json`.
- [ ] 6.2 RED `TestGlpiMapper`/`TestGlpiWriteBoundary`/`TestGlpiErrors`/`TestGlpiMultiTenant`: ticket con `Ticket_User.type=2` → `assignees` con identidad completa (id/nombre/correo), excluye `type=1`/`type=3`; ticket solo con solicitante → `requester` poblado y `assignees=[]`; documento del asignado se lee del campo configurado en `connectors.settings.document_field` (default `registration_number`); ninguna llamada HTTP del paquete usa `POST`/`PUT`/`DELETE` sobre recursos de negocio GLPI (introspección estática); timeout/error de red → `GlpiUnavailable` estructurado sin credenciales en el mensaje; App-Token/user_token inválidos → `GlpiAuthError` sin cachear `session_token`; dos conectores GLPI de organizaciones distintas usan `session_token` cacheados aislados por `connector_id`, sin cruce. [GA-R1, GA-R4, GA-R5, GA-R6, GA-R7]
- [ ] 6.3 VERIFY confirmar T6.2 en ROJO antes de GREEN.
- [ ] 6.4 GREEN `app/integrations/adapters/glpi/errors.py`: `GlpiUnavailable`, `GlpiAuthError`.
- [ ] 6.5 GREEN `app/integrations/adapters/glpi/mapper.py`: JSON GLPI → `Ticket`/`ExternalPerson`.
- [ ] 6.6 GREEN `app/integrations/adapters/glpi/adapter.py`: `GlpiAdapter` (`provider="glpi"`, `credential_kind=api_token`, `capabilities={tickets}`, `api_token: ApiTokenHandshake` vía `initSession`/`killSession`, `port_for(Capability.tickets)`).
- [ ] 6.7 GREEN `app/integrations/adapters/glpi/__init__.py`: `register_adapter(GlpiAdapter())` en import-time.
- [ ] 6.8 GREEN `app/db_init.py`: `import app.integrations.adapters.glpi` (registro, precedente `adapters.fake`).
- [ ] 6.9 GREEN `requirements.txt`: promover `httpx` desde `requirements-dev.txt` (primer adaptador HTTP real que lo exige en runtime).
- [ ] 6.10 VERIFY `cd backend && pytest tests/test_adapter_glpi.py -v` (suite completa del adaptador) en verde; `ruff check .`/`mypy app` limpios en `app/integrations/adapters/glpi/`.

## Lote 7 — Cascada de homologación por asignado (Commit 7)

- [ ] 7.1 RED `backend/tests/test_glpi_sync_matching.py` (sin BD): `norm_email`/`norm_doc`/`norm_name` normalizan case/acentos/puntuación de cédula; correo exacto normalizado → `match_method=email` [auto]; sin correo, documento exacto → `match_method=document` [auto]; sin correo ni documento, `difflib.SequenceMatcher` sobre nombres normalizados de usuarios activos de la org → candidatos ordenados por score, NUNCA auto-confirma; dos usuarios con el mismo nombre normalizado (homónimos) → ambos candidatos, resultado permanece pendiente; link ya existente para `(connector_id, glpi_user_id)` → se salta la cascada completa. [UH-R2]
- [ ] 7.2 VERIFY confirmar T7.1 en ROJO antes de GREEN.
- [ ] 7.3 GREEN `app/modules/glpi_sync/service.py` (parte matching): `match_assignee(person, org_users, existing_link) -> MatchResult` con la cascada correo→documento→nombre.
- [ ] 7.4 VERIFY `cd backend && pytest tests/test_glpi_sync_matching.py -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 8 — Cola cabecera/detalle + mapeos + REST + wiring final (Commit 8)

- [ ] 8.1 [Foundation] `app/modules/glpi_sync/schemas.py`: `SyncRunResponse`, `UnmatchedAssigneeRead` (con `cases: list[UnmatchedCaseRead]` anidado), `ResolveRequest` (`user_id`), `GlpiUserLinkRead` — nunca expone tokens ni documento en claro fuera de lo homologado.
- [ ] 8.2 [Foundation] `app/modules/glpi_sync/repository.py`: `get_link`, `create_link`, `list_links`, `soft_delete_link` (org-scoped); `upsert_unmatched_header(connector_id, glpi_user_id, candidates)`, `append_unmatched_case(header_id, ticket)` (idempotente por `UNIQUE(unmatched_assignee_id, glpi_ticket_id)`), `list_unmatched`, `resolve_unmatched(header_id, user_id, actor)`, `ignore_unmatched(header_id)` (org-scoped vía `connector_id`).
- [ ] 8.3 [Foundation] `app/modules/glpi_sync/service.py` (ampliar): `run_sync(connector_id, membership)` — `404` si conector ajeno/inexistente/no-GLPI; `get_adapter("glpi").port_for(Capability.tickets).list_tickets(ctx)` → por asignado: link existente → skip; match determinístico → `create_link`; sin match → `upsert_unmatched_header`+`append_unmatched_case`; `resolve_unmatched_entry(id, user_id, actor)` → crea `glpi_user_link(match_method=manual)`, cabecera pasa a `resolved`, detalle queda histórico; `ignore_unmatched_entry(id)`.
- [ ] 8.4 RED `backend/tests/test_glpi_sync.py`: `POST /glpi-sync/run` extrae tickets vía adaptador mockeado, homologa determinísticos y puebla cola cabecera+detalle; segundo caso de la misma persona GLPI se agrega al detalle SIN duplicar la cabecera; `POST /unmatched/{id}/resolve` crea el link, cabecera pasa a `resolved`, homologa retroactivamente los casos ya listados; sincronización posterior de esa persona se resuelve directo contra el link sin volver a aparecer en la cola; `POST /unmatched/{id}/ignore` retira la entrada sin crear link; `GET /glpi-sync/links` y `DELETE /glpi-sync/links/{id}` (revocar → siguiente sync vuelve a pasar por la cascada); RBAC `member`/`viewer` → `403` en todos los endpoints; conector/cola/links de la organización A invisibles/`404` desde la organización B; conector ajeno en `run` → `404`. [UH-R3, UH-R4, UH-R5, UH-R6, UH-R7]
- [ ] 8.5 VERIFY confirmar T8.4 en ROJO (rutas inexistentes) antes de GREEN.
- [ ] 8.6 GREEN `app/modules/glpi_sync/router.py`: `POST /glpi-sync/run`, `GET /glpi-sync/unmatched`, `POST /glpi-sync/unmatched/{id}/resolve`, `POST /glpi-sync/unmatched/{id}/ignore`, `GET /glpi-sync/links`, `DELETE /glpi-sync/links/{id}` — todos `Depends(require_role(MemberRole.admin, MemberRole.manager))`; envelope estándar `{data, message, meta}`.
- [ ] 8.7 GREEN `app/main.py`: `include_router(glpi_sync_router, prefix=API_PREFIX)`.
- [ ] 8.8 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_glpi_sync.py -v` en verde; `ruff check .`/`mypy app` limpios.
- [ ] 8.9 [Docs] `docs/diagrams/c4-architecture.md`: agregar adaptador **GLPI** dentro de *Integrations* + módulo `glpi_sync` (cola/mapeos/REST) en el C3 — mismo commit (obligatorio).
- [ ] 8.10 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa sin regresión; `ruff check .`/`mypy app` limpios en `app/integrations/adapters/glpi/`, `app/modules/glpi_sync/` y `app/modules/connectors/`.

## Trazabilidad de requisitos

**`integration-ports` (delta)**: IP17-R1 Identidad de personas asignadas en el puerto de tickets (2 esc., Lote 1) · IP17-R2 Protocolo de adaptador uniforme con `credential_kind` (3 esc., Lote 1).

**`connectors` (delta)**: C17-R1 Tipo de credencial del conector (2 esc., Lote 3) · C17-R2 Registro directo de credenciales `api_token` (2 esc., Lote 3) · C17-R3 `authorize` distingue `oauth`/`api_token` (3 esc., Lote 3).

**`glpi-adapter`**: GA-R1 Registro del adaptador sin tocar el núcleo (1 esc., Lote 6) · GA-R2 Autenticación `api_token` con `session_token` cacheado (2 esc., Lote 5) · GA-R3 Reinicio de sesión ante expiración (2 esc., Lote 5) · GA-R4 Extracción de tickets con asignados (2 esc., Lote 6) · GA-R5 Frontera de solo lectura (1 esc., Lote 6) · GA-R6 GLPI inaccesible o credenciales inválidas (2 esc., Lote 6) · GA-R7 Aislamiento multi-tenant del adaptador (1 esc., Lote 6).

**`user-homologation`**: UH-R1 Documento de identidad con índice único parcial (2 esc., Lote 2) · UH-R2 Cascada de homologación correo→documento→nombre (4 esc., Lote 7) · UH-R3 Mapeos confirmados persistentes y revocables (3 esc., Lote 8) · UH-R4 Cola de asignados sin homologar consolidada por persona (2 esc., Lote 8) · UH-R5 Resolución manual de la cola (3 esc., Lote 8) · UH-R6 Sincronización manual on-demand (2 esc., Lote 8) · UH-R7 Aislamiento multi-tenant de la homologación (1 esc., Lote 8).

Total: 19 requisitos, 40 escenarios cubiertos por tareas RED explícitas en los Lotes 1–8.

**Threat Matrix (design.md)**: secretos cifrados y ausentes de respuestas/logs → Lotes 3 (conectores) y 5 (`session.py`) · SSRF (`GLPI_BASE_URL_ALLOWLIST`, test RED) → Lote 4 (`client.py`) · aislamiento multi-tenant → Lotes 3, 6 y 8. Las 3 filas quedan cubiertas antes de su producción correspondiente.
