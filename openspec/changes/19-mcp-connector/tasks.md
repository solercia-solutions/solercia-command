# Tasks: 19 · Conector MCP (adaptador de recursos externos read-only)

## Notas de alcance (coordinación de esquema)

El 19 **NO agrega migración propia**. `credential_kind` y `connectors.settings JSONB` son propiedad
exclusiva del **17-adapter-glpi** (primer apply de la serie 17→18→19). El único delta de datos del 19
es el valor `none` sobre el `CredentialKind` ya existente, más el namespace `settings.mcp.*`. El Lote 0
verifica en vivo que ambas columnas existan antes de tocar código; si falta cualquiera, el apply queda
**BLOQUEADO** y se reporta — nunca se crean desde el 19.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1500–1800 (fake MCP in-memory ~150 + puerto/DTOs ~160 + guard SSRF ~160 + sesión/reader/mapping ~410 + registro adaptador ~135 + delta `connectors`+REST ~490 + deps/docs ~20) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | Commits directos a `feat/consume-solercia-ui`, 7 commits por lote (Lote 0 sin commit, size:exception) |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|------------------|--------------------|
| 0 | Pre-flight: orden 17→18→19, `credential_kind`+`settings` en el modelo, pin en vivo del SDK `mcp` | PR 1 | N/A (verificación de estado, no test) | `cd backend && alembic heads` (real) + consulta en vivo a PyPI del paquete `mcp` | N/A — sin diff |
| 1 | Servidor MCP fake in-memory (`FastMCP`) + fixtures de contrato | PR 1 | N/A (solo fixtures de prueba) | N/A — sin red real, in-process | Eliminar `backend/tests/fixtures/mcp/` |
| 2 | Puerto `ExternalResourceReaderPort` + DTOs + valor `none` en `CredentialKind` (delta núcleo 14) | PR 1 | `pytest tests/test_integration_ports_external_resources.py -v` | N/A — contrato puro, sin I/O | Revert de las adiciones en `ports.py`/`dtos.py`; sin dependientes fuera del delta |
| 3 | Guard anti-SSRF con IP-pin (`ssrf.py`) | PR 1 | `pytest tests/test_mcp_ssrf.py -v` | N/A — lógica pura (`getaddrinfo` con IPs literales/monkeypatch) | Eliminar `adapters/mcp/ssrf.py` + test |
| 4 | Sesión efímera + reader del puerto contra el fake (`session.py`/`reader.py`/`mapping.py`) | PR 1 | `pytest tests/test_mcp_adapter_reader.py -v` | `create_connected_server_and_client_session` del SDK `mcp` (sin red real) | Eliminar `session.py`/`reader.py`/`mapping.py` + test; adaptador queda sin registrar |
| 5 | Registro import-time del adaptador `mcp` | PR 1 | `pytest tests/test_mcp_adapter_registry.py -v` | Import real vía `app/db_init.py` en arranque de pruebas | Eliminar `adapter.py`/`__init__.py` + revertir import en `db_init.py` |
| 6 | Delta `connectors`: registro MCP + REST de lectura | PR 1 | `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_mcp.py tests/test_connectors_mcp_reader.py -v` | `httpx.AsyncClient` contra el router montado en `app.main` (patrón `test_connectors_crud.py`) | Eliminar rutas `/{id}/mcp/*` + test; CRUD/OAuth existentes del 14 intactos |
| 7 | Pin del SDK `mcp` + documentación C4 + VERIFY final | PR 1 | `pytest tests/ -v` (suite completa) | `pip install -r backend/requirements.txt` (real) | Revertir línea `mcp==` en `requirements.txt`; revertir sección agregada en `c4-architecture.md` |

## Lote 0 — Pre-flight bloqueante (sin commit, sin diff)

- [x] 0.1 Confirmar en `state.yaml`/`depends_on` que `17-adapter-glpi` y `18-adapter-jira` están `archived` antes de iniciar el Lote 1 (orden estricto 17→18→19). CONFIRMADO: `openspec/changes/archive/2026-07-19-17-adapter-glpi/` y `archive/2026-07-19-18-adapter-jira/` existen.
- [x] 0.2 `cd backend && alembic heads` en vivo: confirmar head único. El 19 no fija migración propia. CONFIRMADO: `0017 (head)`, único.
- [x] 0.3 Verificar que el modelo `Connector` expone **ambas** columnas del 17: `credential_kind` (`oauth|api_token`) y `settings` (JSONB). CONFIRMADO en `app/modules/connectors/models.py` líneas 65-73 — ambas columnas existen, apply NO bloqueado.
- [x] 0.4 Verificar en vivo la versión estable del SDK `mcp` de Python en PyPI y fijar la versión exacta a pinnear en el Lote 7. PyPI en vivo: última estable `mcp==1.28.1`, pero requiere `pydantic>=2.11.0` — CONFLICTO con el pin `pydantic==2.10.4` ya congelado en `requirements.txt` (fuera de alcance del 19 tocarlo). Verificado en vivo (`pip download` + `pip install --dry-run`) que `mcp==1.12.0` es la ÚLTIMA versión compatible con `pydantic<3.0.0,>=2.8.0` (satisface el pin actual) y ya incluye `streamablehttp_client` estable. `sse-starlette` transitivo de `mcp` en su versión más reciente (3.4.5) exige `starlette>=0.49.1`, lo cual choca con el techo `starlette<0.42.0` de `fastapi==0.115.6` — se fija explícitamente `sse-starlette==2.2.1` (`starlette>=0.41.3`, compatible con el `starlette==0.41.3` ya instalado). Versión pinneada final: `mcp==1.12.0` + `sse-starlette==2.2.1`. Ver DESVIACIÓN documentada en apply-progress.

## Lote 1 — Servidor MCP fake in-memory + fixtures de contrato (Commit 1)

- [x] 1.1 `backend/tests/fixtures/mcp/fake_server.py`: servidor `FastMCP` in-memory con 3 recursos publicados (pequeño, grande para probar el tope de bytes, y uno con contenido tipo instrucción para MC-R8), 1 tool `readOnlyHint=True` y 1 tool de escritura (`readOnlyHint` ausente).
- [x] 1.2 `backend/tests/fixtures/mcp/__init__.py`: helper que arma streams in-memory vía `create_connected_server_and_client_session` del SDK `mcp`, reutilizado por los Lotes 4 y 6. Incluye además dos factories que simulan fallo (`unreachable_transport_factory`, `timeout_transport_factory`) para los escenarios MC-R3/MC-R6.

## Lote 2 — Puerto `external_resources` + DTOs + valor `none` (Commit 2)

- [x] 2.1 RED `backend/tests/test_integration_ports_external_resources.py`: `ExternalResourceReaderPort` expone `list_resources`/`read_resource`/`list_tools`/`call_tool` con DTOs agnósticos del proveedor; ningún puerto declara método de escritura salvo `call_tool` gateado; `CredentialKind` admite `none` sin redefinir `oauth`/`api_token`; adaptador con adquisición directa omite `authorize`/`callback`. [IP-R1, IP-R2, IP-R3]
- [x] 2.2 VERIFY confirmar T2.1 en ROJO antes de GREEN. CONFIRMADO: `ImportError: cannot import name 'ExternalResource'` antes de la implementación.
- [x] 2.3 GREEN `app/integrations/dtos.py`: `ExternalResource`, `ExternalTool`, `ExternalResourceContent` (frozen).
- [x] 2.4 GREEN `app/integrations/ports.py`: `Capability.external_resources`; `ExternalResourceReaderPort` Protocol; agrega el miembro `none` al `CredentialKind` ya definido por 17 (NO redefine `oauth`/`api_token`); asegura `IntegrationAdapter.credential_kinds: frozenset[CredentialKind]` en el Protocol. VERIFY T2.1 en verde (7/7 passed). DELTA no previsto en tasks.md: `credential_kinds` es un campo NUEVO obligatorio del Protocol → los 5 adaptadores pre-existentes (`fake`/`glpi`/`google`/`jira`/`microsoft365`) necesitaron una línea aditiva `credential_kinds = frozenset({credential_kind})` para seguir satisfaciendo la conformidad estructural de mypy (`register_adapter(adapter: IntegrationAdapter)`); sin comportamiento nuevo, solo el campo. mypy limpio tras el ajuste (252 archivos).

## Lote 3 — Guard anti-SSRF con IP-pin (Commit 3)

- [x] 3.1 RED `backend/tests/test_mcp_ssrf.py`: host fuera de `MCP_HOST_ALLOWLIST` → rechazado; `127.0.0.1`/`10.*`/`192.168.*`/`169.254.*`/`::1`/`fc00::/7` rechazados por defecto; host en la allowlist explícita permitido aunque resuelva a rango privado; `http://` rechazado en producción; `https://` permitido. [MC-R7]
- [x] 3.2 VERIFY confirmar T3.1 en ROJO antes de GREEN. CONFIRMADO: `ModuleNotFoundError: No module named 'app.integrations.adapters.mcp.ssrf'` (13/13 fallando) antes de la implementación.
- [x] 3.3 GREEN `app/integrations/adapters/mcp/ssrf.py`: `validate_mcp_url(url) -> PinnedTarget` (IP-pin) vía `getaddrinfo` + bloqueo de rangos privados/reservados (`MCP_BLOCK_PRIVATE_NETWORKS`) + `https`-only en prod (`MCP_ALLOW_HTTP`). VERIFY T3.1 en verde (13/13 passed). AJUSTE de orden no previsto: `MCP_HOST_ALLOWLIST`/`MCP_ALLOW_HTTP`/`MCP_BLOCK_PRIVATE_NETWORKS` se agregaron a `app/config.py` en este lote (en vez del Lote 4, tarea 4.1) porque `ssrf.py` los necesita para existir; el resto de las constantes (`MCP_CONNECT_TIMEOUT_SECONDS`, `MCP_TOTAL_TIMEOUT_SECONDS`, `MCP_MAX_LIST_ITEMS`, `MCP_MAX_RESOURCE_BYTES`) queda para el Lote 4 como estaba previsto. Se agregó además `app/integrations/adapters/mcp/errors.py` (taxonomía de errores de dominio, usada por Lotes 3/4/6) y un `__init__.py` mínimo de paquete (sin registro aún — eso es el Lote 5).

## Lote 4 — Sesión efímera + reader contra el fake (Commit 4)

- [x] 4.1 [Foundation] `app/config.py`: `MCP_CONNECT_TIMEOUT_SECONDS`, `MCP_TOTAL_TIMEOUT_SECONDS`, `MCP_MAX_LIST_ITEMS`, `MCP_MAX_RESOURCE_BYTES` (el resto — `MCP_HOST_ALLOWLIST`/`MCP_ALLOW_HTTP`/`MCP_BLOCK_PRIVATE_NETWORKS` — ya se agregó en el Lote 3, ver ajuste documentado ahí).
- [x] 4.2 RED `backend/tests/test_mcp_adapter_reader.py` (contra el fake del Lote 1, `transport_factory` inyectado): `initialize` habilita las llamadas siguientes; servidor inalcanzable en `initialize` → `MCP_SERVER_UNREACHABLE`; `list_resources` mapea a `ExternalResource`; `read_resource` dentro del tope → contenido completo; sobre el tope → rechazo sin cargar todo; `list_tools` mapea `readOnlyHint`; `call_tool` allowlisted+readOnly → OK; NO en allowlist → deny sin contactar al servidor; allowlisted pero de escritura → deny; timeout → `MCP_TIMEOUT` con conexión liberada; `MCP_MAX_LIST_ITEMS` respetado; contenido con texto tipo instrucción se retorna como dato plano, nunca se ejecuta. [MC-R3, MC-R4, MC-R5, MC-R6, MC-R8]
- [x] 4.3 VERIFY confirmar T4.2 en ROJO antes de GREEN. CONFIRMADO: `ModuleNotFoundError` (`app.integrations.adapters.mcp.reader`/`session` inexistentes) antes de la implementación.
- [x] 4.4 GREEN `app/integrations/adapters/mcp/session.py`: `open_session(ctx, transport_factory=streamable_http_default)` — `validate_mcp_url` antes de abrir socket → `streamablehttp_client`/fake → `ClientSession.initialize` por operación (sesión efímera, sin cache). `transport_factory` yield-a una `ClientSession` YA inicializada (no streams crudos, ver DESVIACIÓN en apply-progress) — IP-pin real vía `_PinnedIPTransport` (`httpx.AsyncHTTPTransport` + extensión `sni_hostname`).
- [x] 4.5 GREEN `app/integrations/adapters/mcp/mapping.py`: recurso/tool/contenido MCP → DTOs del puerto.
- [x] 4.6 GREEN `app/integrations/adapters/mcp/reader.py`: `list_resources`/`read_resource`/`list_tools`/`call_tool` orquestando sesión+mapeo+topes+enforcement (`name ∈ tools_allowlist` ∩ `readOnlyHint==true`, deny sin contactar si no está en allowlist). VERIFY T4.2 en verde (12/12 passed). DESVIACIÓN técnica documentada en apply-progress: `call_tool`/`read_resource` capturan la decisión de rechazo DENTRO del `async with` de la sesión y solo lanzan el error de dominio DESPUÉS de cerrarla limpiamente — lanzar una excepción mientras un `anyio.TaskGroup` interno del SDK sigue activo la envuelve en `BaseExceptionGroup`, rompiendo el `except` del llamador.

## Lote 5 — Registro import-time del adaptador (Commit 5)

- [ ] 5.1 RED `backend/tests/test_mcp_adapter_registry.py`: `get_adapter("mcp")` disponible tras importar el paquete sin ediciones a `ports.py` ni al orquestador; `capabilities == {external_resources}`; `credential_kinds == {api_token, none}`; único transporte disponible es Streamable HTTP remoto (sin opción `stdio`/subprocess). [MC-R2]
- [ ] 5.2 VERIFY confirmar T5.1 en ROJO antes de GREEN.
- [ ] 5.3 GREEN `app/integrations/adapters/mcp/adapter.py` + `app/integrations/adapters/mcp/__init__.py`: `McpAdapter` implementa `IntegrationAdapter`; `register_adapter(McpAdapter())`.
- [ ] 5.4 GREEN `app/integrations/adapters/__init__.py`, `app/db_init.py`: `import app.integrations.adapters.mcp` (registro import-time). VERIFY T5.1 en verde.

## Lote 6 — Delta `connectors`: registro MCP + REST de lectura (Commit 6)

- [ ] 6.1 [Foundation] `app/modules/connectors/schemas.py`: `ConnectorCreate` admite `settings.mcp={base_url,transport,auth_mode,tools_allowlist}` + credencial directa (`token?`) en el mismo request; `ConnectorRead` nunca expone el token.
- [ ] 6.2 [Foundation] `app/modules/connectors/repository.py`/`service.py`: persiste `settings.mcp` en `connectors.settings`; `api_token` → `crypto.encrypt` + crea `ConnectionCredentials`; `none` → sin fila de credenciales; `authorize(connector_id)` sobre conector de adquisición directa → `AppException` controlada (sin generar `state`).
- [ ] 6.3 RED `backend/tests/test_connectors_mcp.py`: admin/manager registra conector MCP con token estático → `credential_kind=api_token`, token cifrado; registro sin auth → `credential_kind=none`, sin fila `ConnectionCredentials`; member → `403` al registrar; URL de servidor fuera de allowlist/rango privado → rechazada al registrar (anti-SSRF), sin persistir; `http://` en producción → rechazado; `GET /connectors/{id}/authorize` sobre conector MCP → error controlado; token nunca en la respuesta de `POST`/`GET /connectors/{id}` ni en logs. [MC-R1, MC-R7, MC-R10, C-R1, C-R2, IP-R2]
- [ ] 6.4 RED `backend/tests/test_connectors_mcp_reader.py` (usa el fake del Lote 1 vía `transport_factory` inyectado): `GET /{id}/mcp/resources`, `GET /{id}/mcp/resources/read?uri=`, `GET /{id}/mcp/tools` accesibles por cualquier miembro; `POST /{id}/mcp/tools/{tool_name}/call` sobre tool allowlisted+readOnly → OK, sobre tool de escritura → rechazada; conector MCP de la organización A → `404` para usuario de la organización B; ninguna ruta bajo `/mcp/` muta el servidor externo. [MC-R1, MC-R5, MC-R9, MC-R10]
- [ ] 6.5 VERIFY confirmar T6.3/T6.4 en ROJO antes de GREEN.
- [ ] 6.6 GREEN `app/modules/connectors/router.py`: `GET /{id}/mcp/resources`, `GET /{id}/mcp/resources/read`, `GET /{id}/mcp/tools`, `POST /{id}/mcp/tools/{tool_name}/call` (RBAC de registro admin/manager ya existente del 14; lectura cualquier miembro); usa `get_adapter("mcp").port_for(external_resources)` + `open_session` con `transport_factory` real por defecto.
- [ ] 6.7 VERIFY `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_connectors_mcp.py tests/test_connectors_mcp_reader.py -v` en verde; `ruff check .`/`mypy app` limpios.

## Lote 7 — Dependencia runtime + documentación C4 + VERIFY final (Commit 7)

- [ ] 7.1 `backend/requirements.txt`: agregar `mcp==<versión pinneada en 0.4>` (arrastra `httpx`/`anyio`/`httpx-sse`/`sse-starlette`/`jsonschema` si no están ya presentes).
- [ ] 7.2 `docs/diagrams/c4-architecture.md`: nuevo nodo adaptador MCP en Integrations (C3) — cliente Streamable HTTP saliente + guard SSRF.
- [ ] 7.3 VERIFY final `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` — suite completa sin regresión; `ruff check .`/`mypy app` limpios en `app/integrations/adapters/mcp/` y `app/modules/connectors/`.

## Trazabilidad de requisitos

**`integration-ports`**: IP-R1 Puerto de solo lectura `external_resources` (2 esc.) · IP-R2 Protocolo de adaptador uniforme — adquisición directa (3 esc.) · IP-R3 Frontera solo-lectura estricta (3 esc.). → Lote 2 (contrato) + Lote 6 (enforcement en vivo).

**`connectors`**: C-R1 Extensión del enum `credential_kind` con `none` (2 esc.) · C-R2 Registro de conector con credencial directa (3 esc.). → Lote 2 (enum) + Lote 6 (registro).

**`mcp-connector`**: MC-R1 Registro de servidor MCP como conector (2 esc.) · MC-R2 Adaptador auto-registrado, transporte exclusivo Streamable HTTP (2 esc.) · MC-R3 Handshake `initialize` previo (2 esc.) · MC-R4 Recursos con tope de tamaño (3 esc.) · MC-R5 Tools con invocación controlada (4 esc.) · MC-R6 Timeout y topes por llamada (2 esc.) · MC-R7 Anti-SSRF de la URL del servidor (3 esc.) · MC-R8 Contenido tratado como dato inerte (1 esc.) · MC-R9 Frontera de solo lectura estricta (1 esc.) · MC-R10 Aislamiento multi-tenant y credenciales no expuestas (2 esc.) · MC-R11 Servidor MCP fake local para pruebas de contrato (1 esc.). → Lote 1 (MC-R11) · Lote 3 (MC-R7 unit) · Lote 4 (MC-R3, MC-R4, MC-R5, MC-R6, MC-R8) · Lote 5 (MC-R2) · Lote 6 (MC-R1, MC-R5 REST, MC-R7 en registro, MC-R9, MC-R10).

Total: 16 requisitos, 36 escenarios cubiertos por tareas RED explícitas en los Lotes 1–6.
