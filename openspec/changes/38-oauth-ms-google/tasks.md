# Tasks: 38 · OAuth de Microsoft 365 y Google reparado y probable end-to-end

## Reconciliación aplicada (orquestador)

1. **Helper de prueba read-only único** — `design.md` (Decisión 4) define
   `_run_readonly_probe(adapter, connector, ctx)` como el ÚNICO mecanismo de
   verificación de una conexión. Por instrucción explícita del orquestador,
   este helper se implementa como **método exportable de `ConnectorService`**
   (no una función suelta ni un método nuevo en cada `Protocol` de puerto) —
   el cambio 38 lo consume desde `POST /connectors/{id}/accounts/{account_id}/test`
   y el cambio 39 lo reutilizará TAL CUAL desde `POST
   /connectors/{id}/actions/probe`, sin duplicar la heurística de selección
   de capacidad. Fase 4 (2.11/4.11) deja el método con firma estable y
   docstring que referencia explícitamente al 39 como segundo consumidor.
2. **RBAC de `POST .../accounts/{account_id}/test`** — por instrucción
   explícita del orquestador: **dueño de la cuenta O admin/manager de la
   organización** — el MISMO criterio exacto que `disconnect_account`
   (`service.py:706-737`), reutilizado literalmente (misma comparación
   `is_owner`/`is_privileged`, mismo código `forbidden`/403). Un `member`
   ajeno al dueño y sin rol privilegiado recibe `403`.

## Notas técnicas adicionales (autor de este documento, no reconciliación del orquestador)

Estas siete decisiones resuelven ambigüedades o conflictos reales entre
`design.md`, `specs/connectors/spec.md` y el código actual, descubiertos al
leer el código fuente antes de escribir este desglose. Ninguna estaba en la
lista de reconciliación obligatoria del orquestador; se documentan aquí para
que `sdd-apply` no tenga que volver a investigarlas.

1. **Nombre de la variable de entorno — `design.md` vs `spec.md` difieren.**
   `design.md` (Decisión 1) elige una URL completa explícita y la llama
   `OAUTH_CALLBACK_URL`, rechazando expresamente derivarla de una "base +
   ruta fija" por la fragilidad del túnel/Docker. `specs/connectors/spec.md`
   (Requirement "Inicio del flujo OAuth") usa el NOMBRE
   `OAUTH_CALLBACK_BASE_URL` para la misma variable. Resolución: el setting
   se llama **`OAUTH_CALLBACK_BASE_URL`** (gana el nombre literal de la
   spec, que es la fuente de verdad de interfaz/contrato), pero su
   SEMÁNTICA es la de `design.md`: contiene la URL COMPLETA y literal del
   callback (p. ej. `http://localhost:8081/api/v1/connectors/oauth/callback`),
   nunca una base que el código concatene con una ruta fija. `state.yaml`
   module_decision ya autorizaba "OAUTH_CALLBACK_BASE_URL (o equivalente)",
   así que esta resolución no contradice ninguna decisión previa, solo
   fija cuál de las dos fuentes gana en el nombre.
2. **`redirect_uri` deja de ser un parámetro que el caller puede fijar, ni
   siquiera dentro de la allowlist.** El código actual
   (`service.py:339-409`) acepta un `redirect_uri` opcional del caller y lo
   valida contra `OAUTH_REDIRECT_ALLOWLIST` — exactamente el mecanismo que
   `design.md` (Threat Matrix, "redirect_uri canónico NO elegible por el
   caller") ordena eliminar. Fase 2 ELIMINA el parámetro `redirect_uri` de
   `ConnectorService.authorize()` y de la query de `GET
   /connectors/{id}/authorize` por completo — no se "ignora en silencio",
   deja de existir como argumento aceptado. Esto hace que
   `backend/tests/test_connectors_security.py::test_redirect_uri_outside_allowlist_is_rejected`
   y `::test_redirect_uri_inside_allowlist_is_accepted` (Row 5 —
   anti-SSRF/open-redirect) queden **obsoletos por diseño**: probaban
   exactamente el mecanismo que se retira. Fase 2 los REEMPLAZA (no los deja
   caer sin más) por dos pruebas que verifican la invariante nueva: cualquier
   `?redirect_uri=` en la query —incluso uno que antes estaba en la
   allowlist— se ignora siempre, sin excepción y sin 400.
3. **`oauth_code_exchange_failed` distingue fallo controlado de fallo
   inesperado en `exchange_code`, sin romper la prueba existente.** Hoy,
   `_complete_oauth_callback` (`service.py:539`) deja que CUALQUIER
   excepción de `adapter.oauth.exchange_code` suba tal cual:
   - Si es un `AppException` (p. ej. Google/M365 real emiten
     `oauth_token_invalid` vía `errors.py`), su `code` propio viaja intacto
     hasta el `?error=` del front.
   - Si NO es `AppException` (p. ej. un `RuntimeError` de transporte), el
     `except Exception` de `handle_oauth_callback` (`service.py:455-471`) ya
     la mapea a `oauth_unexpected_error` — cubierto por la prueba EXISTENTE
     `test_unexpected_exchange_failure_redirects_with_generic_error_code`
     (`test_connectors_oauth_redirect.py:381`), que debe seguir en verde.

   `design.md` (Decisión 3) pide un código ÚNICO y estable
   (`oauth_code_exchange_failed`) para "exchange_code falló", sin importar
   la taxonomía interna del adaptador. Resolución: envolver SOLO la línea
   `tokens = await adapter.oauth.exchange_code(...)` en un
   `try/except AppException` que relanza
   `AppException(..., code="oauth_code_exchange_failed", status_code=502)`
   — un `RuntimeError` u otra excepción NO-`AppException` en esa misma
   línea NO se captura ahí y sigue subiendo al `except Exception` genérico
   existente, preservando `oauth_unexpected_error` para ese caso intacto.
4. **"Proveedor no configurado" reutiliza el código y el mecanismo YA
   existentes (`provider_not_registered` cuando `get_adapter(...)` es
   `None`), no un chequeo nuevo de `M365_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_ID`
   vacíos.** El escenario de `specs/connectors/spec.md` ("Proveedor no
   configurado": "Dado un proveedor sin `client_id`/`client_secret`
   configurados") describe la situación DESDE la perspectiva del operador,
   pero el mecanismo que ya existe en TODO el código (`service.py:371,
   522, 639`; también `glpi_sync/service.py`, `intake/service.py`,
   `jira_import/service.py`) es "adapter ausente del registry ⇒
   `provider_not_registered`" — nunca una validación de que
   `client_id`/`client_secret` NO estén vacíos (los adaptadores M365/Google
   se auto-registran en el import sin mirar sus credenciales; validar
   credenciales en blanco exigiría tocar el `Protocol`/adaptadores 15-16,
   fuera de alcance por "reuse-existing-adapters"). Fase 3 prueba este
   escenario simulando un adapter ausente (`monkeypatch` sobre
   `get_adapter` del módulo `connectors.service`), reutilizando el camino
   YA cubierto, sin agregar código de validación de credenciales nuevo —
   coherente con "Fuera de alcance: registrar apps reales en Azure/Google".
5. **La lista de preferencia de capacidades de `_run_readonly_probe` cubre
   5 de las 6 capacidades del orden declarativo de `design.md` (Decisión
   4).** El orden `(calendar, mail, tickets, external_tasks,
   meeting_notes, external_resources)` agrupa 5 puertos con la MISMA forma
   (`list_*(ctx, *, since=None, limit=N) -> list[...]`, `ports.py:84-121`)
   más `external_resources` (`ports.py:124-151`), cuya forma es
   ESTRUCTURALMENTE distinta (`list_resources(ctx)`, sin `limit`/`since`) y
   que NINGÚN adaptador `credential_kind=oauth` actualmente registrado
   declara (`mcp` es el único con `external_resources` y es
   `api_token`/`none`, nunca `oauth` — `mcp/adapter.py:21`). El helper
   implementa el despacho genérico solo para los 5 puertos uniformes;
   `external_resources` queda deliberadamente FUERA del `dict` de despacho
   de este cambio, documentado en el docstring del método como limitación
   conocida para un futuro adaptador `oauth` que además declare
   `external_resources` (no bloquea ningún escenario de
   `specs/connectors/spec.md`, que solo pide M365/Google/Jira).
6. **Ruta anidada + verificación de pertenencia connector↔account.** El
   contrato de `design.md` (`POST
   /connectors/{id}/accounts/{account_id}/test`) anida `connector_id`, a
   diferencia de la ruta plana de `disconnect_account`
   (`/connected-accounts/{account_id}`). El servicio valida AMBOS: que
   `connector_id` exista en la organización (`_require_connector`, ya
   existente) Y que la cuenta pertenezca a ESE conector
   (`account.connector_id == connector_id`, si no `404
   connected_account_not_found`) — mismo criterio de "recurso anidado" que
   `GET /connectors/{id}/accounts`.
7. **El refresco-en-lectura de `test_connection` REPLICA el patrón ya
   probado de `IntakeService._build_access_context`** (cambio
   22-intake-classifier, `intake/service.py:314-383`): refresco
   PROACTIVO cuando `expires_at` ya venció, sink `on_tokens_refreshed`
   conectado a `ConnectedAccountRepository.save_refreshed_credentials`, y
   los MISMOS códigos de error (`credentials_not_found`,
   `refresh_token_missing`, `provider_not_registered`) — no se inventa una
   taxonomía nueva. Un refresco fallido NUNCA sobrescribe las credenciales
   existentes (la excepción del adaptador se propaga ANTES de llamar a
   `save_refreshed_credentials`), igual que en el 22.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~640–740 (producción ~270–310: `config.py` ~15, `backend/.env.example` ~35 nuevo, `connectors/service.py` (authorize simplificado + wrap `exchange_code` + `test_connection`/`_run_readonly_probe`/contexto de acceso) ~150-170, `connectors/router.py` ~30, `connectors/schemas.py` ~10, frontend (`connectors.service.ts`+`connections.component.ts`+`es-CO.json`) ~90-110; tests ~370–430: extensiones a `test_connectors_oauth_redirect.py`/`test_connectors_oauth_flow.py` ~70, REESCRITURA de 2 pruebas en `test_connectors_security.py` ~40, `test_connectors_test_connection.py` NUEVO ~220-260, prueba de `.env.example` ~20) |
| 400-line budget risk | High — el diagnóstico de código (no solo `design.md`) reveló una reescritura de pruebas de seguridad existentes (Row 5, anti-open-redirect) que el forecast original de `design.md` (~330-420) no contemplaba; aun así, el cambio es acotado a un módulo (`connectors`) sin migración |
| Chained PRs recommended | No — instrucción explícita: single-pr, merge local a `preview` |
| Suggested split | Fase 1 config + `.env.example` (suite intacta) → Fase 2 fix `authorize()` (elimina `redirect_uri` del caller) → Fase 3 catálogo de errores del callback → Fase 4 `test_connection` + `_run_readonly_probe` → Fase 5 frontend (botón + i18n) + build → Fase 6 suite completa + guía de prueba + commits |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U1 | Fase 1 — `OAUTH_CALLBACK_BASE_URL`, limpieza de la allowlist, `.env.example` | 1 — `fix(connectors): repara la configuración del callback OAuth y documenta las credenciales` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_redirect.py backend/tests/test_connectors_oauth_flow.py` | Pytest contra Postgres real de test | Revert commit; sin cambios de esquema, config vuelve a sus defaults de puertos stale |
| U2 | Fase 2 — `authorize()` deja de leer `redirect_uri` del caller; siempre usa `OAUTH_CALLBACK_BASE_URL` | 2 — `fix(connectors): el redirect_uri del authorize ya no lo elige el caller` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_flow.py backend/tests/test_connectors_security.py` | Pytest + cliente HTTP real | Revert commit; el conector sigue funcionando pero vuelve a caer en el bug raíz (SPA como redirect_uri) |
| U3 | Fase 3 — `oauth_code_exchange_failed` en el callback | 3 — `feat(connectors): agrega el codigo oauth_code_exchange_failed al callback OAuth` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_redirect.py` | Ídem | Revert commit; el callback vuelve a propagar el código interno del adaptador sin normalizar |
| U4 | Fase 4 — `test_connection` + `_run_readonly_probe` | 4 — `feat(connectors): agrega la prueba de conexion post-oauth con refresco de token` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_test_connection.py` | Pytest + cliente HTTP real; refresco simulado con el adapter `fake` | Revert commit; quita el endpoint nuevo, resto del módulo `connectors` sin cambios |
| U5 | Fase 5 — botón "Probar conexión" + errores es-CO por código | 5 — `feat(connectors): agrega el boton probar conexion y los mensajes es-CO del callback` | `cd frontend && npm run build` | Build real (sin runner de tests configurado para esta página, mismo precedente que el cambio 37 Fase 5) | Revert commit; el backend sigue funcionando sin el botón nuevo |
| U6 | Fase 6 — suite completa + guía de prueba + commits | 6 — `docs(oauth): documenta el registro manual de apps M365/Google en la guia de prueba` (solo si aplica) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem + `cd frontend && npm run build` | Revert commit aislado; documentación pura, sin impacto en código |

## Fase 1 — Config: `OAUTH_CALLBACK_BASE_URL`, allowlist y `.env.example` (Commit 1)

- [ ] 1.1 Baseline: confirmar que `test_connectors_oauth_redirect.py`/`test_connectors_oauth_flow.py`/`test_connectors_security.py` están verdes ANTES de tocar código. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_redirect.py backend/tests/test_connectors_oauth_flow.py backend/tests/test_connectors_security.py`
- [ ] 1.2 [RED] `test_oauth_callback_base_url_setting_defaults_to_local_backend_callback` (en `test_connectors_oauth_redirect.py`): `assert settings.OAUTH_CALLBACK_BASE_URL == "http://localhost:8081/api/v1/connectors/oauth/callback"`. Hoy falla: el setting no existe (`AttributeError`). Verify: `pytest -q backend/tests/test_connectors_oauth_redirect.py -k oauth_callback_base_url_setting`
- [ ] 1.3 [RED] `test_allowlist_no_longer_includes_stale_settings_connectors_spa_page`: `assert "http://localhost:4200/settings/connectors" not in settings.OAUTH_REDIRECT_ALLOWLIST`. Hoy falla: la entrada stale SIGUE presente (`config.py:107`). Verify: `-k allowlist_no_longer_includes_stale`
- [ ] 1.4 [GREEN] `backend/app/config.py`: agregar `OAUTH_CALLBACK_BASE_URL: str = "http://localhost:8081/api/v1/connectors/oauth/callback"` (URL completa y literal, NUNCA una base a concatenar — nota técnica 1); eliminar `"http://localhost:4200/settings/connectors"` de `OAUTH_REDIRECT_ALLOWLIST` (los otros 3 valores `/connections` de `:4200/:4242/:4243` se conservan intactos); realinear el comentario/valor de `GOOGLE_OAUTH_REDIRECT_URI` al callback canónico (documental — el adaptador nunca lo usa, `config.py:158-161`). Verify: 1.2 y 1.3 en verde.
- [ ] 1.5 [GREEN] Crear `backend/.env.example` documentando `M365_CLIENT_ID`, `M365_CLIENT_SECRET`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `OAUTH_CALLBACK_BASE_URL`, `OAUTH_REDIRECT_ALLOWLIST` con placeholders vacíos (sin secretos reales) y un comentario con la matriz de URLs local (`:8081`/`:4242`) vs túnel devtunnel (`design.md` Decisión 1).
- [ ] 1.6 [RED] `test_env_example_documents_oauth_variables_without_secrets` (nuevo archivo `backend/tests/test_env_example.py` o extensión de `test_connectors_oauth_redirect.py`): lee `backend/.env.example`, verifica que las 6 claves anteriores están presentes y que ninguna tiene un valor no vacío/no-placeholder. Hoy falla: el archivo no existe. Verify: `pytest -q backend/tests/test_env_example.py`
- [ ] 1.7 [GREEN] Confirmar 1.6 en verde con el archivo creado en 1.5.
- [ ] 1.8 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_redirect.py backend/tests/test_connectors_oauth_flow.py backend/tests/test_env_example.py`

Commit 1: `fix(connectors): repara la configuración del callback OAuth y documenta las credenciales`

## Fase 2 — Fix del `authorize()`: `redirect_uri` deja de elegirlo el caller (Commit 2)

- [ ] 2.1 [RED] `test_authorize_redirect_uri_is_always_oauth_callback_base_url` (en `test_connectors_oauth_flow.py`): autorizar SIN pasar `redirect_uri` → decodificar el `state` persistido en `patched_redis` → `assert payload["redirect_uri"] == settings.OAUTH_CALLBACK_BASE_URL`. Hoy falla: el state guarda `settings.OAUTH_REDIRECT_ALLOWLIST[0]` (`service.py:376,398`). Verify: `pytest -q backend/tests/test_connectors_oauth_flow.py -k redirect_uri_is_always_oauth_callback_base_url`
- [ ] 2.2 [RED] Reemplazar `test_connectors_security.py::test_redirect_uri_outside_allowlist_is_rejected` por
  `test_redirect_uri_query_param_is_always_ignored_never_used_as_state_redirect_uri`: enviar
  `?redirect_uri=https://evil.test/steal-tokens` → la respuesta sigue siendo `302` (YA NO 400 —
  el parámetro simplemente no se lee) y el `state` persistido tiene `redirect_uri ==
  settings.OAUTH_CALLBACK_BASE_URL`, nunca el valor malicioso. Verify: `pytest -q backend/tests/test_connectors_security.py -k redirect_uri_query_param_is_always_ignored`
- [ ] 2.3 [RED] Reemplazar `test_connectors_security.py::test_redirect_uri_inside_allowlist_is_accepted` por
  `test_redirect_uri_query_param_even_if_previously_allowlisted_is_still_ignored`: enviar
  `?redirect_uri=<valor que ANTES estaba en OAUTH_REDIRECT_ALLOWLIST>` → `302` y el `state`
  persistido SIGUE teniendo `redirect_uri == settings.OAUTH_CALLBACK_BASE_URL` (nunca el valor
  de la query, aunque coincida con la vieja allowlist) — prueba que el valor se ignora SIEMPRE,
  no condicionalmente. Verify: `pytest -q backend/tests/test_connectors_security.py -k redirect_uri_query_param_even_if_previously_allowlisted`
- [ ] 2.4 [GREEN] `backend/app/modules/connectors/service.py`: eliminar el parámetro `redirect_uri`
  de `ConnectorService.authorize()`; el `state_payload["redirect_uri"]` SIEMPRE es
  `settings.OAUTH_CALLBACK_BASE_URL`; eliminar por completo el bloque de validación contra
  `OAUTH_REDIRECT_ALLOWLIST` para `redirect_uri` (código `oauth_redirect_not_allowed` queda
  retirado — confirmar que ninguna otra prueba lo referencia antes de borrarlo, `rg
  oauth_redirect_not_allowed backend/tests`). La validación de `redirect_to` contra la
  allowlist NO cambia.
- [ ] 2.5 [GREEN] `backend/app/modules/connectors/router.py`: eliminar el parámetro de query
  `redirect_uri: str | None = Query(default=None)` de `authorize_connector`; actualizar la
  llamada a `service.authorize(organization_id, connector_id, user_id, redirect_to=redirect_to)`
  (sin el argumento posicional `redirect_uri`); actualizar el docstring del endpoint para reflejar
  que `redirect_uri` ya no es un parámetro que el caller controle.
- [ ] 2.6 Regresión: confirmar que `test_authorize_with_allowed_redirect_to_302s_to_provider`,
  `test_authorize_with_disallowed_redirect_to_is_rejected_without_state` y el resto de
  `test_connectors_oauth_redirect.py` siguen en verde (la lógica de `redirect_to` no se tocó).
- [ ] 2.7 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_flow.py backend/tests/test_connectors_oauth_redirect.py backend/tests/test_connectors_security.py`

Commit 2: `fix(connectors): el redirect_uri del authorize ya no lo elige el caller`

## Fase 3 — Catálogo de errores del callback: `oauth_code_exchange_failed` (Commit 3)

- [ ] 3.1 [RED] `test_code_exchange_appexception_maps_to_oauth_code_exchange_failed_with_destination`
  (en `test_connectors_oauth_redirect.py`, junto a
  `test_unexpected_exchange_failure_redirects_with_generic_error_code`): `monkeypatch` de
  `FakeAdapter.exchange_code` para que lance `AppException("mensaje interno", code="algo_especifico_del_adaptador", status_code=401)`
  (simula lo que Google/M365 reales ya hacen vía `errors.oauth_token_invalid()`) → callback CON
  `redirect_to` almacenado → `302` a `return_to` con `?error=oauth_code_exchange_failed` (NO el
  código propio del adaptador); nada se persiste. Hoy falla: el código propio del adaptador viaja
  intacto. Verify: `pytest -q backend/tests/test_connectors_oauth_redirect.py -k code_exchange_appexception_maps_to_oauth_code_exchange_failed_with_destination`
- [ ] 3.2 [RED] `test_code_exchange_appexception_without_destination_keeps_json_with_new_code`: mismo
  monkeypatch, callback SIN `redirect_to` almacenado → respuesta JSON con `code ==
  "oauth_code_exchange_failed"` (no el código propio del adaptador), status `502`. Verify: `-k code_exchange_appexception_without_destination_keeps_json_with_new_code`
- [ ] 3.3 [RED] Escenario "Proveedor no configurado" —
  `test_callback_with_unregistered_provider_redirects_with_provider_not_registered`: crear
  conector `fake`, iniciar `authorize` normalmente (state válido), luego `monkeypatch` de
  `app.modules.connectors.service.get_adapter` para que devuelva `None` justo antes de invocar el
  callback (simula el proveedor "sin configurar"/ausente del registry — nota técnica 4) → `302`
  con `?error=provider_not_registered`; nada se persiste. Confirma el mecanismo YA existente
  (`service.py:519-525`), no agrega código nuevo. Verify: `-k callback_with_unregistered_provider`
- [ ] 3.4 [GREEN] `backend/app/modules/connectors/service.py::_complete_oauth_callback`: envolver
  ÚNICAMENTE la línea `tokens = await adapter.oauth.exchange_code(code, redirect_uri)` en
  `try/except AppException as exc: raise AppException("No pudimos completar la conexión con el "
  "proveedor.", code="oauth_code_exchange_failed", status_code=502) from exc` — una excepción
  NO-`AppException` en esa misma línea NO se captura aquí (sigue subiendo al `except Exception`
  genérico de `handle_oauth_callback`, preservando `oauth_unexpected_error` intacto para ese
  caso).
- [ ] 3.5 Regresión explícita: confirmar que
  `test_unexpected_exchange_failure_redirects_with_generic_error_code` (RuntimeError NO-AppException
  desde `exchange_code`) SIGUE devolviendo `oauth_unexpected_error`, no
  `oauth_code_exchange_failed` — nota técnica 3. Verify: `pytest -q backend/tests/test_connectors_oauth_redirect.py -k unexpected_exchange_failure`
- [ ] 3.6 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_oauth_redirect.py backend/tests/test_connectors_oauth_flow.py backend/tests/test_connectors_security.py`

Commit 3: `feat(connectors): agrega el codigo oauth_code_exchange_failed al callback OAuth`

## Fase 4 — `test_connection` + `_run_readonly_probe` (Commit 4)

Crear `backend/tests/test_connectors_test_connection.py` (fixtures `client`/`session`/`two_orgs`/`make_member`/`patched_redis` de `conftest.py`; helper `_connect_fake_account` que hace authorize+callback contra el adapter `fake` para dejar una `ConnectedAccount` + `ConnectionCredentials` reales).

- [ ] 4.1 [RED] `test_test_connection_success_returns_ok_with_sample_from_primary_capability`: cuenta
  `fake` conectada (token vigente) → `POST /connectors/{id}/accounts/{account_id}/test` (dueño) →
  `200`; `data.ok is True`, `data.capability == "calendar"` (primera capacidad del orden de
  preferencia que `fake` soporta), `data.sample` contiene `"1"` y el sustantivo de la capacidad
  (p. ej. `"1 eventos"`), `data.refreshed is False`. Hoy falla: `404` (ruta no existe). Verify:
  `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_test_connection.py -k success_returns_ok`
- [ ] 4.2 [RED] `test_test_connection_refreshes_expired_token_and_persists_rotation`: cuenta `fake`
  conectada, `ConnectionCredentials.expires_at` forzado al pasado (vía `session`/repo directo) →
  `POST .../test` → `200`, `data.refreshed is True`; releer la fila de `ConnectionCredentials` en
  BD y confirmar que `access_token_enc` CAMBIÓ (descifra a `"fake-access-refreshed-..."`) —
  prueba que `save_refreshed_credentials` persistió la rotación (nota técnica 7, mismo patrón que
  `IntakeService`). Verify: `-k refreshes_expired_token_and_persists_rotation`
- [ ] 4.3 [RED] `test_test_connection_refresh_failure_returns_accionable_error_and_keeps_old_credentials`:
  cuenta `fake` con `expires_at` vencido; `monkeypatch` de `FakeAdapter.refresh` para que lance
  `AppException("La conexión expiró o fue revocada. Debes reconectar la cuenta.",
  code="oauth_refresh_failed", status_code=401)` → `POST .../test` responde `401`
  `oauth_refresh_failed`; releer `ConnectionCredentials` y confirmar que el `access_token_enc`
  ORIGINAL (aún vencido) NO cambió — nada se sobrescribe con una rotación fallida. Verify: `-k refresh_failure_returns_accionable_error`
- [ ] 4.4 [RED] `test_test_connection_capability_read_failure_returns_ok_false_not_500`: cuenta `fake`
  con token vigente; `monkeypatch` del puerto `calendar` de `fake`
  (`_FakeCalendarPort.list_events`) para que lance una `AppException` tipo
  `capability_unavailable` (403) → `POST .../test` responde `200` con `data.ok is False`,
  `data.capability == "calendar"`, `data.sample is None` — degradación controlada, no un `500` ni
  una excepción sin manejar. Verify: `-k capability_read_failure_returns_ok_false`
- [ ] 4.5 [RED] `test_test_connection_admin_or_manager_can_test_any_member_account`: `member` A
  conecta una cuenta `fake`; un `admin` (o `manager`, `make_member`) de la MISMA organización
  llama `POST .../test` sobre la cuenta de A → `200` (RBAC de la reconciliación: privilegiado
  aunque no sea el dueño). Verify: `-k admin_or_manager_can_test_any_member_account`
- [ ] 4.6 [RED] `test_test_connection_other_member_gets_403`: `member` A conecta una cuenta `fake`;
  `member` B (`make_member`, mismo org, rol `member`) llama `POST .../test` sobre la cuenta de A
  → `403` `forbidden` (mismo código/mensaje que `disconnect_account`). Verify: `-k other_member_gets_403`
- [ ] 4.7 [RED] `test_test_connection_cross_organization_returns_404`: conector+cuenta de la
  organización A (`two_orgs`); un `admin` de la organización B llama `POST
  /connectors/{connector_a_id}/accounts/{account_id}/test` → `404`. Verify: `-k cross_organization_returns_404`
- [ ] 4.8 [RED] `test_test_connection_mismatched_connector_and_account_returns_404`: crear un
  SEGUNDO conector (`provider="jira"`, misma organización — `fake` solo admite uno por
  `uq_connectors_organization_provider`) y llamar `POST
  /connectors/{jira_connector_id}/accounts/{fake_account_id}/test` (cuenta real, pero de OTRO
  conector) → `404` `connected_account_not_found` (nota técnica 6). Verify: `-k mismatched_connector_and_account`
- [ ] 4.9 [RED] `test_test_connection_no_capability_available_returns_controlled_error`:
  `monkeypatch` temporal de `FakeAdapter.capabilities` a `frozenset()` → `POST .../test` responde
  un error controlado (`422 no_probe_capability_available`), nunca una excepción sin manejar.
  Verify: `-k no_capability_available_returns_controlled_error`
- [ ] 4.10 [GREEN] `backend/app/modules/connectors/schemas.py`: agregar
  `ConnectionTestResult(BaseModel)` con `ok: bool`, `capability: str`, `sample: str | None`,
  `refreshed: bool` (`design.md` Interfaces/Contracts).
- [ ] 4.11 [GREEN] `backend/app/modules/connectors/service.py`: agregar
  `_run_readonly_probe(self, adapter, connector, ctx) -> ConnectionTestResult` — método
  EXPORTABLE (reconciliación 1, consumido tal cual por el cambio 39): recorre el orden de
  preferencia `(Capability.calendar, Capability.mail, Capability.tickets,
  Capability.external_tasks, Capability.meeting_notes)` (nota técnica 5 — `external_resources`
  excluido de este dispatcher), toma la primera capacidad presente en
  `adapter.capabilities`, resuelve su puerto vía `adapter.port_for(capability)` y llama el
  método `list_*` correspondiente (`list_events`/`list_messages`/`list_tickets`/`list_tasks`/
  `list_notes`) con `limit=1`; si la llamada lanza `AppException` devuelve `ConnectionTestResult(ok=False,
  capability=..., sample=None, refreshed=...)` en vez de propagarla (degradación controlada, 4.4);
  si ninguna capacidad del orden está en `adapter.capabilities`, lanza `AppException(code="no_probe_capability_available", status_code=422)`.
- [ ] 4.12 [GREEN] `backend/app/modules/connectors/service.py`: agregar
  `_build_test_connection_access_context(self, organization_id, connector, account_id) ->
  tuple[AccessContext, bool]` (retorna también si hubo refresco) replicando LITERALMENTE el
  patrón de `IntakeService._build_access_context` (nota técnica 7): refresco proactivo si
  `expires_at <= now`, sink `on_tokens_refreshed` → `self.accounts.save_refreshed_credentials`,
  mismos códigos `credentials_not_found`/`refresh_token_missing`/`provider_not_registered`.
- [ ] 4.13 [GREEN] `backend/app/modules/connectors/service.py`: agregar
  `test_connection(self, organization_id, connector_id, account_id, membership) ->
  ConnectionTestResult`: `_require_connector` (404 si ajeno/inexistente) → `self.accounts.get_account`
  (404 `connected_account_not_found` si no existe o `account.connector_id != connector_id`) → RBAC
  dueño-o-admin/manager IDÉNTICO a `disconnect_account` (reconciliación 2, 403 `forbidden`) →
  `get_adapter(connector.provider)` (404 `provider_not_registered` si ausente o sin
  `credential_kind == oauth`) → `_build_test_connection_access_context` → `_run_readonly_probe`.
- [ ] 4.14 [GREEN] `backend/app/modules/connectors/router.py`: `POST
  /connectors/{connector_id}/accounts/{account_id}/test` con `Depends(get_current_membership)`
  (ruta abierta a cualquier miembro autenticado, mismo patrón que `disconnect_account` — el RBAC
  vive DENTRO del servicio, no en un `require_role`); delega en `service.test_connection`.
- [ ] 4.15 Suite dirigida verde. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_test_connection.py`

Commit 4: `feat(connectors): agrega la prueba de conexion post-oauth con refresco de token`

## Fase 5 — Frontend: botón "Probar conexión" + errores es-CO por código (Commit 5)

- [ ] 5.1 `frontend/src/entities/connector/connector.model.ts`: agregar interfaz
  `ConnectionTestResult { ok: boolean; capability: string; sample: string | null; refreshed:
  boolean }` (espejo 1:1 del schema backend).
- [ ] 5.2 `frontend/src/entities/connector/connectors.service.ts`: agregar `testConnection(connectorId:
  string, accountId: string): Observable<{ data: ConnectionTestResult }>` → `POST
  ${apiBase}/connectors/${connectorId}/accounts/${accountId}/test`.
- [ ] 5.3 `frontend/src/pages/connections/connections.component.ts`: agregar botón "Probar conexión"
  en cada `<li>` de cuenta conectada (junto al botón `accountsRevoke` existente, líneas
  169-195), con estado inline del resultado (éxito con `sample`, o error con el mensaje es-CO del
  código); un signal `testingAccountId`/`testResults: Map<string, ConnectionTestResult |
  { errorCode: string }>` deshabilita el botón mientras la petición está en curso.
- [ ] 5.4 `frontend/src/pages/connections/connections.component.ts::consumeOAuthReturn`: reemplazar
  el mensaje genérico único `connectors.banner.error` (interpolado con el código crudo) por una
  búsqueda en un diccionario por código
  (`oauth_provider_error`/`oauth_state_invalid`/`oauth_code_exchange_failed`/`provider_not_registered`/
  `oauth_unexpected_error`) con un mensaje genérico de reserva para cualquier código no mapeado —
  `design.md` Decisión 3 ("reemplaza el banner genérico actual que muestra el código crudo").
- [ ] 5.5 `frontend/src/assets/i18n/es-CO.json`: bajo `connectors`, agregar
  `banner.errors.{oauth_provider_error,oauth_state_invalid,oauth_code_exchange_failed,provider_not_registered,oauth_unexpected_error}`
  con los textos es-CO formal/tuteo de `design.md` Decisión 3 (adaptados a tuteo donde el
  original use 3ª persona, p. ej. "...o la cancelaste" en vez de "...o el usuario canceló"); y
  `accounts.test{Action,Success,Error,Aria}` para el botón nuevo.
- [ ] 5.6 Build de frontend verde. Verify: `cd frontend && npm run build`

Commit 5: `feat(connectors): agrega el boton probar conexion y los mensajes es-CO del callback`

## Fase 6 — Suite completa + guía de prueba + commits convencionales (Commit 6)

- [ ] 6.1 Suite completa del backend sin regresión. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q`
- [ ] 6.2 Confirmar que ningún test referencia el código retirado `oauth_redirect_not_allowed`.
  Verify: `rg "oauth_redirect_not_allowed" backend/` → sin resultados (o solo en este `tasks.md`)
- [ ] 6.3 Confirmar cero fugas de tokens: `test_connectors_security.py` (Rows 1-4, cifrado/anti-fuga/
  anti-CSRF/aislamiento) sigue en verde sin cambios de comportamiento fuera de la Row 5
  reescrita en Fase 2. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_security.py`
- [ ] 6.4 Build de frontend verde (repetir tras cualquier ajuste de las Fases 2-5). Verify: `cd frontend && npm run build`
- [ ] 6.5 `PRUEBA_PREVIEW.md`: agregar una nueva subsección "3.7 OAuth real de M365/Google + Probar
  conexión (cambio 38)" después de "3.6 Auditoría de componentes UI", documentando en español
  colombiano formal los pasos MANUALES (fuera de CI, `credential_kind=oauth` real):
  1. Registrar una app en Azure AD (portal.azure.com) con `redirect_uri` EXACTO igual a
     `OAUTH_CALLBACK_BASE_URL` (local `:8081` o el `https://<tunel>` de devtunnel).
  2. Registrar credenciales OAuth en Google Cloud Console (consent screen + client) con el mismo
     `redirect_uri` exacto.
  3. Volcar `M365_CLIENT_ID`/`M365_CLIENT_SECRET`/`GOOGLE_OAUTH_CLIENT_ID`/
     `GOOGLE_OAUTH_CLIENT_SECRET`/`OAUTH_CALLBACK_BASE_URL` reales en `.env` (nunca commitear).
  4. Levantar `./gestion.sh on` (túnel activo), crear el conector real desde `/connections`,
     completar el flujo OAuth y usar el botón "Probar conexión" para confirmar el resultado.
- [ ] 6.6 Commit final con los ajustes de 6.1-6.4 si generaron correcciones no cubiertas por los
  commits 1-5; la actualización de la guía (6.5) siempre aporta un commit propio de
  documentación.

Commit 6: `docs(oauth): documenta el registro manual de apps M365/Google en la guía de prueba`

## Trazabilidad de requisitos

- Authorize genera `redirect_uri` hacia el callback backend, nunca hacia `OAUTH_REDIRECT_ALLOWLIST[0]` ni elegible por el caller · 1.2,1.4,2.1,2.2,2.3,2.4,2.5
- Authorize sobre conector ajeno/inexistente sigue en 404 sin generar `state` (regresión) · 2.6
- Authorize sobre conector `api_token` responde error controlado (regresión, sin cambios) · 2.6
- Redirección final del callback hacia `redirect_to` con éxito o `?error=<código>` (regresión + código nuevo) · 3.1,3.2,3.4
- Proveedor no configurado → `provider_not_registered` sin crear cuenta/credenciales · 3.3
- Usuario canceló la autorización → `oauth_provider_error` sin crear cuenta (regresión) · 3.5,6.3
- Nuevo código estable `oauth_code_exchange_failed` para fallos controlados de `exchange_code` · 3.1,3.2,3.4,3.5
- Prueba de conexión post-OAuth: éxito muestra detalle de muestra · 4.1,4.10,4.11,4.13,4.14
- Token vencido se refresca y persiste antes de probar · 4.2,4.12
- Refresco fallido responde error accionable sin sobrescribir credenciales · 4.3,4.12
- Member no puede probar la cuenta de otro; dueño y admin/manager sí pueden (RBAC reconciliado) · 4.5,4.6,4.13
- Aislamiento organizacional y de recurso anidado (connector↔account) del endpoint de prueba · 4.7,4.8
- `backend/.env.example` documenta las variables OAuth sin secretos reales · 1.5,1.6,1.7
- Helper `_run_readonly_probe` exportable, único mecanismo de verificación (frontera con el 39) · 4.11 + reconciliación 1
- UI: botón "Probar conexión" con resultado inline es-CO · 5.1,5.2,5.3,5.6
- UI: catálogo de errores del callback es-CO por código, reemplaza el banner genérico · 5.4,5.5
- Suite backend en verde con fake adapter; regresión completa · 6.1,6.2,6.3
- Guía de prueba documenta el registro manual de apps reales Azure/Google · 6.5

## Risks

- **Reescritura de pruebas de seguridad existentes (Row 5, `test_connectors_security.py`)**: no
  es un simple "agregar pruebas nuevas" — dos pruebas YA VERDES prueban exactamente el mecanismo
  que este cambio retira (`redirect_uri` elegible por el caller dentro de una allowlist). Fase 2
  las reemplaza explícitamente (2.2/2.3); si `sdd-apply` solo AGREGA pruebas sin tocar las
  viejas, la suite quedará con dos pruebas contradictorias entre sí (una espera `400`, la
  invariante nueva no lo produce).
- **Ambigüedad de nombre de variable resuelta unilateralmente** (nota técnica 1):
  `OAUTH_CALLBACK_BASE_URL` (nombre de la spec) con semántica de URL completa (de `design.md`).
  Si el equipo prefiere el nombre literal `OAUTH_CALLBACK_URL` de `design.md`, es un rename de
  bajo riesgo antes de cerrar Fase 1 — no cambia ninguna otra decisión.
- **Alcance de "Proveedor no configurado"** (nota técnica 4): se prueba reutilizando el mecanismo
  existente (`get_adapter` ausente) en vez de agregar una validación nueva de
  `client_id`/`client_secret` vacíos. Si en producción un operador deja `M365_CLIENT_ID=""` con
  el adaptador SÍ registrado, el fallo real ocurrirá más tarde (contra la API de Microsoft con
  `client_id=` vacío, mapeado por `errors.py` del adaptador 15, probablemente
  `oauth_code_exchange_failed` vía la Fase 3) — no como un `404 provider_not_registered`
  inmediato. Esto es consistente con "Fuera de alcance: registrar apps reales", pero vale la
  pena confirmarlo explícitamente si el equipo lo considera insuficiente.
- **`_run_readonly_probe` no cubre `external_resources`** (nota técnica 5): ningún escenario de
  `specs/connectors/spec.md` lo requiere hoy (M365/Google/Jira), pero un futuro adaptador
  `oauth` + `external_resources` necesitaría una extensión de este helper antes de que el cambio
  39 pueda depender de él para ese caso.
- **Tamaño**: el forecast honesto (~640-740 líneas) supera con holgura el presupuesto de 400
  líneas, principalmente por la reescritura de pruebas de seguridad y la matriz RBAC/aislamiento
  de `test_connection` (8-9 casos) que el `design.md` original no anticipó en su propio forecast
  (~330-420) — instrucción explícita: single-pr con commits escalonados, sin PRs encadenados,
  merge local a `preview`.
