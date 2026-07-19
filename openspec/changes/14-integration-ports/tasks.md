# Tasks: 14 · Puertos de integración (núcleo hexagonal + conectores)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~2.200–2.600 (motor ~830 incl. pruebas + migración/modelos/docs ~395 + CRUD ~415 + OAuth/seguridad ~525 + cuentas conectadas ~265) |
| Riesgo de presupuesto (400 líneas) | High |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote 1 (núcleo `app/integrations/` + Redis compartido) → Lote 2 (migración + modelos + docs) → Lote 3 (CRUD `/connectors` + RBAC) → Lote 4 (OAuth authorize/callback + seguridad) → Lote 5 (cuentas conectadas: listar/desconectar) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, un commit por lote (sin PR) |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

**Nota de tamaño por lote**: los Lotes 1 y 4 superan individualmente las 400 líneas por acoplamiento inherente entre `state_store`+`oauth`+`crypto`+adaptador fake (Lote 1) y entre `authorize`/`callback`+las 5 filas de Security Requirements (Lote 4). `delivery_strategy: exception-ok` ya cubre esta excepción; no requiere pregunta adicional antes del apply.

**Serialización con 21-project-hierarchy**: este cambio toma la migración `0014` sobre `down_revision="0013"` — SIEMPRE que `21-project-hierarchy` no la haya tomado antes. El Lote 2 incluye una tarea explícita de verificación del head real de Alembic (probablemente `0014` ya tomado → esta migración será `0015`).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Núcleo hexagonal `app/integrations/` (puertos, DTOs, registro, cifrado, state store Redis, OAuth genérico, adaptador fake) + `app/shared/redis.py` compartido (condicional) | 1 — `feat(integrations): nucleo hexagonal de puertos oauth cifrado y adaptador fake` | `cd backend && pytest tests/test_integration_ports_contract.py tests/test_integration_registry.py tests/test_integration_crypto.py tests/test_integration_state_store.py tests/test_integration_fake_adapter.py -v` | `oauth.build_authorize()`→`oauth.handle_callback()` invocados directamente contra el fake en tests (sin HTTP real), Redis vía `fakeredis` | Revert commit (sin migración propia); `app/integrations/` completo es nuevo y aislado |
| 2 | Migración de tablas + 3 modelos + `docs/diagrams/er-model.md` + `docs/diagrams/c4-architecture.md` | 2 — `feat(connectors): migracion y modelos de conectores cuentas y credenciales cifradas` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_migration.py -v` | Ciclo `alembic upgrade head`/`alembic downgrade -1` contra BD desechable (patrón `test_boards_backfill_migration.py`) | Revert commit + `alembic downgrade -1` (elimina `connection_credentials`→`connected_accounts`→`connectors`, sin filas vivas previas) |
| 3 | CRUD `/connectors` (POST/GET/PATCH/DELETE) con RBAC `require_role(admin,manager)` + envelope | 3 — `feat(connectors): crud de conectores con rbac y aislamiento multi-tenant` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_crud.py -v` | `httpx.AsyncClient` contra el router montado en `app.main` (patrón `test_assets.py`) | Revert commit; ruta y schemas nuevos, sin dependientes fuera del módulo |
| 4 | `authorize`/`callback` OAuth + 5 filas de Security Requirements (cifrado, no-fuga, anti-CSRF/replay, aislamiento tenant, anti-SSRF) | 4 — `feat(connectors): flujo oauth authorize callback con cifrado y anti replay` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_oauth_flow.py tests/test_connectors_security.py -v` | `httpx.AsyncClient` contra `GET /connectors/{id}/authorize` y `GET /connectors/oauth/callback` con el fake registrado; Redis vía `fakeredis` | Revert commit; sin migración propia, sin dependientes fuera del módulo |
| 5 | `GET /connectors/{id}/accounts` + `DELETE /connected-accounts/{id}` + VERIFY final de la suite completa | 5 — `feat(connectors): listado y desconexion de cuentas conectadas` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connected_accounts.py -v` | `httpx.AsyncClient` contra el router montado; VERIFY final `pytest tests/ -v` (suite completa) | Revert commit; ruta plana nueva, sin dependientes |

## Lote 1 — Núcleo `app/integrations/` + Redis compartido (Commit 1)

- [x] 1.1 [Foundation] Verificar si `backend/app/shared/redis.py` ya existe (el cambio 20 comparte la misma instrucción condicional). Si NO existe, crearlo: `get_redis_client()` vía `redis.asyncio.from_url(settings.REDIS_URL)`. Si ya existe, omitir sin tocarlo. — Verificado ausente; creado con `@lru_cache`.
- [x] 1.2 [Foundation] `app/config.py`: agregar `INTEGRATIONS_FERNET_KEY` (default dev válido base64 32B, análogo a `JWT_SECRET`), `OAUTH_STATE_TTL_SECONDS`, `OAUTH_REDIRECT_ALLOWLIST`.
- [x] 1.3 [Foundation] `app/integrations/__init__.py`, `dtos.py`: 6 dataclasses frozen agnósticas de proveedor (`MailMessage`, `CalendarEvent`, `ExternalTask`, `MeetingNote`, `Ticket`, `OAuthTokens`).
- [x] 1.4 [Foundation] `app/integrations/ports.py`: `Capability` (StrEnum) + 5 Protocols read-only (`MailReaderPort`/`CalendarReaderPort`/`ExternalTaskReaderPort`/`MeetingNotesReaderPort`/`TicketReaderPort`) + `IntegrationAdapter` Protocol (`provider`, `capabilities`, `authorize_url`, `exchange_code`, `refresh`, `port_for`). Incluye `AccessContext` (adenda ratificada: `scopes` + `on_tokens_refreshed`).
- [x] 1.5 RED `backend/tests/test_integration_ports_contract.py`: ningún puerto ni el protocolo de adaptador declara método de escritura hacia el proveedor. [IP-R5]
- [x] 1.6 [Foundation] `app/integrations/registry.py`: `register_adapter(a)`/`get_adapter(provider) -> IntegrationAdapter | None` (dict mutable, precedente `notify.registry`).
- [x] 1.7 RED `backend/tests/test_integration_registry.py`: adaptador de prueba se registra en import-time sin editar `ports.py`/`oauth.py`; consulta por `provider` sin condicionales; dos adaptadores (Outlook/Gmail simulados) exponen el mismo contrato de puerto de correo. [IP-R1, IP-R2]
- [x] 1.8 [Foundation] `app/integrations/crypto.py`: `encrypt(plaintext) -> str`/`decrypt(ciphertext) -> str` vía Fernet con `settings.INTEGRATIONS_FERNET_KEY`.
- [x] 1.9 RED `backend/tests/test_integration_crypto.py`: round-trip cifrado/descifrado; `ciphertext != plaintext`.
- [x] 1.10 [Foundation] `app/integrations/state_store.py`: `put(state, payload, ttl)` (`SETEX oauth:state:{state}`), `pop(state) -> payload | None` (`GETDEL`, single-use).
- [x] 1.11 RED `backend/tests/test_integration_state_store.py` (vía `fakeredis`): `put`+`pop` recupera el payload una sola vez; segunda llamada a `pop` devuelve `None`; TTL vencido devuelve `None`.
- [x] 1.12 [Foundation] `app/integrations/oauth.py`: `build_authorize(adapter, redirect_uri, scopes, *, state_payload, ttl) -> (state, url)` orquesta `state_store.put`+`adapter.authorize_url`; `handle_callback(adapter, code, state, redirect_uri) -> (state_payload, OAuthTokens)` orquesta `state_store.pop`+`adapter.exchange_code`, sin conocer al proveedor. Nota: firma elaborada respecto al pseudocódigo simplificado del design — ver desviaciones documentadas.
- [x] 1.13 [Foundation] `app/integrations/adapters/__init__.py`, `adapters/fake.py`: adaptador `fake` autoregistrado en import-time, implementa los 5 puertos con datos de prueba y el handshake OAuth simulado sin HTTP real (precedente autoregistro `app/email/outbox.py`).
- [x] 1.14 RED `backend/tests/test_integration_fake_adapter.py`: el fake responde a cada puerto sin HTTP real; `build_authorize`→`handle_callback` contra el fake completa el flujo simulado; adaptador con solo capacidad "correo" queda excluido del puerto "calendario"; el núcleo delega el canje de tokens sin lógica por proveedor. [IP-R3, IP-R4]
- [x] 1.15 VERIFY confirmado T1.5/1.7/1.9/1.11/1.14 en ROJO (ModuleNotFoundError, colección fallida) antes de GREEN; luego `cd backend && pytest tests/test_integration_ports_contract.py tests/test_integration_registry.py tests/test_integration_crypto.py tests/test_integration_state_store.py tests/test_integration_fake_adapter.py -v` → 16/16 en verde; `ruff check .`/`mypy app` limpios.
- [x] 1.16 `requirements.txt`: agregado `cryptography==49.0.0`. `requirements-dev.txt`: agregado `fakeredis>=2.26`.

## Lote 2 — Migración + modelos + docs de arquitectura (Commit 2)

- [x] 2.1 [Foundation] Verificar el head real de Alembic (`cd backend && alembic heads`) ANTES de nombrar el archivo de migración — verificado en vivo: head real = `0014` (`21-project-hierarchy` ya lo tomó), por lo tanto la nueva migración es `0015_add_connectors.py` (`down_revision="0014"`).
- [x] 2.2 [Foundation] `app/shared/enums.py`: `ConnectorStatus` (`active|inactive|error`, `native_enum=False`), `AccountStatus` (`active|expired|revoked|error`, `native_enum=False`).
- [x] 2.3 [Foundation] `app/modules/connectors/__init__.py`, `models.py`: `Connector` (Pk+Timestamp+SoftDelete+Audit+Tenant; `provider String(50) idx`, `scopes JSONB`, `status ConnectorStatus`; `UNIQUE(organization_id, provider)`); `ConnectedAccount` (mismos mixins; `connector_id FK CASCADE`, `user_id FK CASCADE`, `external_account_id String idx`, `display_name`, `status AccountStatus`; `UNIQUE(connector_id, external_account_id)`); `ConnectionCredentials` (Pk+Timestamp+Tenant; `connected_account_id FK CASCADE`, `access_token_enc Text`, `refresh_token_enc Text?`, `expires_at DateTime?`, `token_type`, `scopes JSONB?`; `UNIQUE(connected_account_id)`).
- [x] 2.4 [Foundation] `app/db_init.py`: importar `Connector`/`ConnectedAccount`/`ConnectionCredentials` (registro en `Base.metadata`) e `import app.integrations.adapters.fake` (registro del adaptador).
- [x] 2.5 [Foundation] Migración `0015_add_connectors.py`: 3 tablas con FKs/unicidades/índices explícitos (patrón `0010_add_assets.py`); `downgrade()` en orden inverso (`connection_credentials`→`connected_accounts`→`connectors`).
- [x] 2.6 RED `backend/tests/test_connectors_migration.py` (patrón `test_project_hierarchy_migration.py`, BD desechable + `alembic upgrade 0014`/`0015`/`downgrade 0014`): round-trip sin filas vivas; `UNIQUE(organization_id, provider)`, `UNIQUE(connector_id, external_account_id)` y `UNIQUE(connected_account_id)` existen tras el upgrade. [C-R1, C-R3]
- [x] 2.7 VERIFY confirmado T2.6 en ROJO (`CommandError: Can't locate revision identified by '0015'`) antes de GREEN; luego 2/2 en verde. `alembic upgrade head` limpio verificado vía `tests/test_migrations_baseline.py` (BD desechable, mismo patrón que el resto del proyecto — `solercia_test` ya tiene esquema por `create_all`, no por Alembic, "Brecha residual aceptada"); `alembic check` sin diff (4/4 tests de baseline en verde).
- [x] 2.8 [Docs] `docs/diagrams/er-model.md`: agregado Dominio 5 (`connectors`/`connected_accounts`/`connection_credentials` con FKs, unicidades y `organization_id`) — mismo commit que la migración.
- [x] 2.9 [Docs] `docs/diagrams/c4-architecture.md`: nuevo componente **app/integrations** (puertos+registro+oauth+crypto+state_store+adaptador fake), módulo `connectors`, store de `state` en Redis y cifrado Fernet — mismo commit que la migración.

## Lote 3 — CRUD `/connectors` con RBAC (Commit 3)

- [x] 3.1 [Foundation] `app/modules/connectors/schemas.py`: `ConnectorCreate`/`ConnectorUpdate`/`ConnectorRead` (Pydantic v2; nunca expone tokens).
- [x] 3.2 [Foundation] `app/modules/connectors/repository.py`: `create`/`get`/`list_connectors`/`save` scoped por `organization_id` (patrón `assets/repository.py`).
- [x] 3.3 [Foundation] `app/modules/connectors/service.py` (parte CRUD): orquesta repository; `created_by`/`updated_by` = actor.
- [x] 3.4 RED `backend/tests/test_connectors_crud.py`: admin crea conector con `created_by`/`updated_by`; member `POST` → `403`; member `GET /connectors` lista sin rol admin/manager; manager también permitido en `POST`/`PATCH`/`DELETE`; `DELETE` es soft-delete; conector de otra organización → `404` en `GET`/`PATCH`/`DELETE`; `POST` responde `201` con `{"data":...,"message":...}`; `GET` lista responde `{"data":[...],"meta":{"total":n}}`. [C-R1, C-R2, C-R9]
- [x] 3.5 VERIFY confirmado T3.4 en ROJO (ruta inexistente, `KeyError: 'data'`) antes de GREEN.
- [x] 3.6 GREEN `app/modules/connectors/router.py`: `POST`/`GET`/`PATCH`/`DELETE /connectors[/{id}]` — escritura con `Depends(require_connector_write_role)` (singleton módulo de `require_role(MemberRole.admin, MemberRole.manager)`, ruff B008), lectura con `Depends(get_current_membership)`; envelope estándar.
- [x] 3.7 GREEN `app/main.py`: `include_router(connectors_router, prefix=API_PREFIX)`.
- [x] 3.8 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_crud.py -v` → 7/7 en verde; `ruff check .`/`mypy app` limpios.

## Lote 4 — Flujo OAuth (authorize/callback) + seguridad (Commit 4)

- [x] 4.1 [Foundation] `app/modules/connectors/schemas.py` (ampliar): `AuthorizeResponse` (`authorize_url`); ningún schema de salida expone tokens.
- [x] 4.2 [Foundation] `app/modules/connectors/repository.py` (ampliar): `ConnectedAccountRepository.upsert_account(...)` (crea o actualiza por `external_account_id`), `save_credentials(connected_account_id, ...)`.
- [x] 4.3 [Foundation] `app/modules/connectors/service.py` (ampliar): `authorize(organization_id, connector_id, user_id, redirect_uri)` → resuelve adaptador + valida `OAUTH_REDIRECT_ALLOWLIST` + `oauth.build_authorize` + `404` si conector ajeno/inexistente; `handle_oauth_callback(code, state, error)` → error del proveedor → `AppException(code="oauth_provider_error", status_code=400)`; state inválido/vencido/reusado → `AppException(code="oauth_state_invalid", status_code=400)`; éxito → `state_store.pop`+`registry.get_adapter`+`adapter.exchange_code`+`crypto.encrypt`+`repository.upsert_account`+`save_credentials`. Nota de arquitectura: usa `state_store.pop`/`registry.get_adapter` DIRECTAMENTE (no `oauth.handle_callback`) porque la ruta es GLOBAL — el adaptador solo se conoce DESPUÉS de extraer el `connector_id` del payload del state; `oauth.handle_callback` (Lote 1) sigue vigente/probado para el caso en que el adaptador ya se conoce de antemano.
- [x] 4.4 RED `backend/tests/test_connectors_oauth_flow.py`: `authorize` persiste state en Redis (`fakeredis`) y responde URL del proveedor; conector ajeno/inexistente → `404` sin generar state; callback válido crea/actualiza cuenta+credenciales cifradas e invalida el state; reutilización del mismo state (2º callback) → rechazado sin crear/actualizar nada; state vencido → error sin crear cuenta; state que no corresponde (nunca emitido) → rechazado sin registrar nada; `?error=` del proveedor → error controlado sin registros a medias; segunda cuenta externa distinta del mismo conector → segunda fila `ConnectedAccount` sin colisión; reconexión de la misma cuenta externa actualiza credenciales sin duplicar fila. [C-R3, C-R4, C-R5, C-R6]
- [x] 4.5 RED `backend/tests/test_connectors_security.py` (5 filas Security Requirements de design.md): `access_token_enc`/`refresh_token_enc` cifrados (`!= texto plano`, round-trip `crypto.decrypt`) tras callback exitoso; ningún token en el JSON de `authorize`/`callback` ni en logs del logger `solercia.connectors` (verificado con `caplog`, confirmando además que SÍ se loguea sin filtrar tokens); state reusado → `400` (`GETDEL` single-use); conector/cuenta/credencial de la organización A invisible a la B (aserción directa sobre `organization_id` persistido + `404` en `authorize` cross-org); `redirect_uri` fuera de `OAUTH_REDIRECT_ALLOWLIST` rechazado (anti-SSRF/open-redirect) + triangulación con uno permitido. [C-R1, C-R7]
- [x] 4.6 VERIFY confirmado T4.4/T4.5 en ROJO (15/16 fallaron por rutas inexistentes; 1 caso 404-esperado coincidió por accidente con la ruta 404 genérica, re-verificado como GREEN real tras el GREEN) antes de GREEN.
- [x] 4.7 GREEN `app/modules/connectors/router.py` (ampliar): `GET /connectors/{id}/authorize` (membresía, `302` al IdP vía `RedirectResponse`, `redirect_uri` opcional por query param validado contra el allowlist) y `GET /connectors/oauth/callback` (ruta GLOBAL, sin dependencia de autenticación, validado por `state`, no por rol).
- [x] 4.8 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_oauth_flow.py tests/test_connectors_security.py -v` → 16/16 en verde; `ruff check .`/`mypy app` limpios.

## Lote 5 — Cuentas conectadas: listar/desconectar + verificación final (Commit 5)

- [x] 5.1 [Foundation] `app/modules/connectors/schemas.py` (ampliar): `ConnectedAccountRead` (sin campos de token).
- [x] 5.2 [Foundation] `app/modules/connectors/repository.py` (ampliar): `ConnectedAccountRepository.list_accounts(connector_id, org_id, *, only_user_id=None)`, `get_account(org_id, account_id)`, `soft_delete_account(account, *, actor_id=None)` — soft-delete de la cuenta + PURGA física (hard delete) de `ConnectionCredentials`, dado que esa tabla no lleva `SoftDeleteMixin` (design.md "Tablas": Pk+Timestamp+Tenant únicamente); corregido también el docstring del modelo `ConnectionCredentials` (Lote 2) que describía incorrectamente un soft-delete de ambas filas.
- [x] 5.3 [Foundation] `app/modules/connectors/service.py` (ampliar): `list_connected_accounts(...)` — admin/manager ven todas, member solo las propias; `disconnect_account(org_id, account_id, membership)` — dueño o admin/manager, si no → `403`.
- [x] 5.4 RED `backend/tests/test_connected_accounts.py`: member ve solo sus propias cuentas en `GET /connectors/{id}/accounts`, admin/manager (y manager explícito) ven todas; tokens ausentes en la respuesta (ni cifrados ni en claro); dueño desconecta su cuenta (`DELETE /connected-accounts/{id}`) → soft-delete de cuenta + purga de credenciales; admin desconecta cuenta de otro member de su organización; member distinto intenta desconectar cuenta ajena → `403`; cuenta de otra organización → `404` en `GET`/`DELETE`. [C-R1, C-R7, C-R8]
- [x] 5.5 VERIFY confirmado T5.4 en ROJO (6/7 fallaron por rutas inexistentes; 1 caso 404-esperado coincidió por accidente, re-verificado GREEN real tras el GREEN) antes de GREEN.
- [x] 5.6 GREEN `app/modules/connectors/router.py` (ampliar): `GET /connectors/{id}/accounts`, `DELETE /connected-accounts/{id}` (ruta plana, precedente `assets/router.py:157,175`).
- [x] 5.7 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connected_accounts.py -v` → 7/7 en verde; `ruff check .`/`mypy app` limpios.
- [x] 5.8 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa: 13 fallas preexistentes documentadas (entorno httpx/conftest, ninguna del cambio 14) + 636 pasan, cero regresión; `ruff check .`/`mypy app` (repo completo) limpios; ciclo `alembic upgrade head`/`downgrade -1`/`upgrade head` verificado manualmente contra BD desechable además del test automatizado.

## Trazabilidad de requisitos

**`integration-ports`**: IP-R1 Puertos de lectura por capacidad (2 esc.) · IP-R2 Registro de adaptadores extensible en import-time (2 esc.) · IP-R3 Protocolo de adaptador uniforme (2 esc.) · IP-R4 Adaptador fake en memoria para pruebas de contrato (2 esc.) · IP-R5 Frontera solo-lectura estricta (2 esc.).

**`connectors`**: C-R1 Modelo de datos y aislamiento multi-tenant (2 esc.) · C-R2 CRUD de conectores con permisos por rol (3 esc.) · C-R3 Varias cuentas del mismo proveedor por usuario (2 esc.) · C-R4 Inicio del flujo OAuth — authorize (2 esc.) · C-R5 Callback exitoso del flujo OAuth (2 esc.) · C-R6 Error y expiración del state en el callback (3 esc.) · C-R7 Cifrado de tokens en reposo y no exposición (2 esc.) · C-R8 Listado y desconexión de cuentas conectadas (3 esc.) · C-R9 Contratos de API envueltos `{data, message, meta}` (2 esc.).

Total: 14 requisitos, 31 escenarios cubiertos por tareas RED explícitas en los Lotes 1–5.
