# Design: 19 · Conector MCP (adaptador de recursos externos read-only)

## Technical Approach

Adaptador `mcp` sobre el núcleo del 14: implementa `IntegrationAdapter`, se auto-registra en import-time (precedente `app/notify/registry.py` + `adapters/fake.py`), cero ediciones al orquestador. Puerto nuevo read-only `ExternalResourceReaderPort` (capacidad `external_resources`) con DTOs agnósticos. Cliente sobre el **SDK oficial `mcp` de Python** (transporte Streamable HTTP), **sesión efímera por operación**. Config del servidor como namespace `settings.mcp` dentro de la columna `connectors.settings JSONB` (dueño: 17-adapter-glpi, primer apply de la serie; **el 19 NO agrega columna**); token estático reutiliza `connection_credentials` (Fernet del 14). Guard anti-SSRF propio ANTES de conectar. TDD estricto contra servidor `FastMCP` in-memory del SDK.

> **Anclaje**: 14 `design.md`/specs son CONTRATO (el código `app/integrations/` aún no existe; 14 no aplicado). Credencial directa (token/none) ancla en el contrato del 17 (`credential_kind = oauth|api_token`; 17 sin `design.md`, se usa su `proposal.md`). El 19 no toca esquema (ver Migration).

## Architecture Decisions

### SDK oficial `mcp` vs cliente JSON-RPC propio
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **SDK `mcp`** (`ClientSession` + `streamablehttp_client`) | El SDK mantiene la parte frágil (framing Streamable HTTP, SSE, `Mcp-Session-Id`, negociación de `protocolVersion`, paginación por cursor, tipado Pydantic) sincronizada con la spec; trae **server+client in-memory** para TDD de contrato real; peso marginal bajo (starlette/uvicorn/httpx/pydantic ya presentes) | **Elegida** |
| JSON-RPC propio sobre `httpx` + `httpx.MockTransport` | Reimplementa el transporte exacto que el SDK ya mantiene; los fixtures probarían nuestros fixtures, no el contrato MCP; más superficie de test y de deriva por revisión de spec | Rechazada |

El anti-SSRF NO se delega al SDK: es un guard propio pre-conexión, así que elegir el SDK no cede ese control.

### Estructura, sesión, config, credencial y enforcement
| Decisión | Elegido | Rechazado / Rationale |
|----------|---------|-----------------------|
| Ubicación | Paquete `app/integrations/adapters/mcp/` (`adapter`, `reader`, `session`, `ssrf`, `mapping`); import path `app.integrations.adapters.mcp` preserva el contrato de registro de la spec | Módulo único `mcp.py` (proposal/spec): concentra 5 preocupaciones; el paquete aísla el guard SSRF y la sesión inyectable para TDD, con el MISMO import path |
| Ciclo de sesión | `initialize` **por operación** (abrir→initialize→leer→cerrar) | Sesión cacheada por conector: estado mutable compartido + riesgo de fuga cross-tenant + expiración de `Mcp-Session-Id`; el round-trip extra es aceptable en lectura admin de baja frecuencia y acotado por timeout |
| Config del conector | Namespace `settings.mcp = {base_url, transport, auth_mode, tools_allowlist, host_allowlist?}` DENTRO de `connectors.settings JSONB` (columna dueño: **17-adapter-glpi**, la agrega en su migración junto a `credential_kind`); el 19 NO agrega columna | Columna propia `connectors.config`: COLISIONA con `settings` del 17. Overload de `scopes` (OAuth-puro): descartado. El namespace en `settings` reutiliza la columna genérica ya provista por el 17 |
| `credential_kind` | 17 es el ÚNICO dueño de la columna/enum (`oauth\|api_token`); el delta legítimo de 19 es SOLO el VALOR `none` (extensión de datos, no de columna). Modo de auth MCP en `settings.mcp.auth_mode`; `api_token` marca la fila `ConnectionCredentials`, `none` NO crea fila (ausencia ⇒ none) | Que 19 cree/duplique la columna: PROHIBIDO. Orden estricto **17→18→19** con verificación de head en vivo; si `credential_kind`/`settings` no existen al apply del 19, el apply queda **BLOQUEADO** y lo reporta, nunca los crea |
| Adquisición de credencial | Protocolo declara `credential_kinds: frozenset[CredentialKind]`; token en el MISMO `POST /connectors` (spec `connectors` del 19), campo redactado en logs/respuestas; `authorize`/`callback` sobre conector directo → error controlado | `PUT /credential` separado: la spec ratificada exige el token en el request de creación; la fuga en logs se mitiga por redacción del campo, no por endpoint aparte |
| Enforcement read-only | `call_tool` = default-deny: `name ∈ tools_allowlist` (autoritativo, admin) **∩** `readOnlyHint == true` (secundario, no confiable). No en allowlist ⇒ deny SIN contactar al servidor | Confiar solo en `readOnlyHint`: el hint lo controla el servidor no confiable. Allowlist ∩ hint cubre servidor mentiroso Y error del admin |
| Anti-SSRF | `MCP_HOST_ALLOWLIST` default-deny + `getaddrinfo` + bloqueo de rangos privados/reservados + IP-pin (httpx conecta a la IP validada preservando Host/SNI) + https-only en prod | Solo allowlist de host: no cierra DNS-rebinding (TOCTOU); el IP-pin fija la IP resuelta y validada al conectar |

## Data Flow

    Registro (admin/manager) — credencial directa, sin navegador:
      POST /connectors {provider:"mcp", settings.mcp:{base_url,transport,auth_mode,tools_allowlist}, credential_kind, token?}
        → validate_mcp_url(base_url) [scheme+allowlist+DNS/rango-privado] → persist en connectors.settings.mcp (sin columna nueva)
        → api_token: crypto.encrypt(token) → ConnectedAccount(server) + ConnectionCredentials | none: sin fila de credenciales
      GET /connectors/{id}/authorize sobre conector directo → error controlado (no usa OAuth)

    Lectura (miembro):
      GET .../{id}/mcp/resources | .../mcp/tools | .../mcp/resources/read?uri=… | POST .../{id}/mcp/tools/{tool_name}/call
        → reader = get_adapter("mcp").port_for(external_resources)
        → ctx = AccessContext(base_url, headers=Authorization?, allowlist, caps)
        → open_session(ctx): validate_mcp_url → streamablehttp_client → ClientSession.initialize
        → session.list_resources/read_resource/list_tools/call_tool  [caps por llamada] → DTOs → cerrar

`call_tool` (read-only): deny sin contactar si `name ∉ allowlist`; si está, `list_tools` verifica `readOnlyHint==true`; si no → deny controlado.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/mcp/{__init__,adapter,reader,session,ssrf,mapping}.py` | Create | Adaptador MCP + reader del puerto + sesión inyectable + guard SSRF + mapeo→DTOs; auto-registro en `__init__` |
| `app/integrations/ports.py` | Modify | `Capability.external_resources`; `ExternalResourceReaderPort`; `CredentialKind`; `IntegrationAdapter.credential_kinds` (delta coordinada 17/19) |
| `app/integrations/dtos.py` | Modify | `ExternalResource`, `ExternalTool`, `ExternalResourceContent` (frozen) |
| `app/integrations/adapters/__init__.py`, `app/db_init.py` | Modify | Import del adaptador para registro import-time |
| `app/modules/connectors/{schemas,service,repository,router}.py` | Modify | Registro MCP (`settings.mcp` + credencial directa en `POST /connectors`, token redactado); REST de lectura bajo `/{id}/mcp/{resources, resources/read, tools, tools/{tool_name}/call}`; `authorize` sobre conector directo → error controlado |
| `app/config.py` | Modify | `MCP_HOST_ALLOWLIST`, `MCP_ALLOW_HTTP`, `MCP_BLOCK_PRIVATE_NETWORKS`, `MCP_CONNECT_TIMEOUT_SECONDS`, `MCP_TOTAL_TIMEOUT_SECONDS`, `MCP_MAX_LIST_ITEMS`, `MCP_MAX_RESOURCE_BYTES` |
| `requirements.txt` | Modify | `mcp` (pin exacto al apply; ≥ versión con `streamablehttp_client` estable; arrastra `httpx`/`anyio`/`httpx-sse`/`sse-starlette`/`jsonschema`) |
| _(ninguna migración)_ | — | El 19 NO agrega esquema: config MCP en el namespace `settings.mcp` (columna `connectors.settings` del 17); valor de enum `none` = extensión de datos sobre `credential_kind` del 17 |
| `docs/diagrams/c4-architecture.md` | Modify | Adaptador MCP en Integrations (C3): cliente Streamable HTTP saliente + guard SSRF |
| `docs/diagrams/er-model.md` | — | Sin cambio por parte del 19 (no agrega columna; `connectors.settings` la documenta el 17) |

## Interfaces / Contracts

```python
# dtos.py (deltas, frozen, provider-agnostic)
@dataclass(frozen=True)
class ExternalResource: uri: str; name: str; mime_type: str | None; description: str | None
@dataclass(frozen=True)
class ExternalTool: name: str; description: str | None; read_only: bool; input_schema: dict
@dataclass(frozen=True)
class ExternalResourceContent: uri: str | None; mime_type: str | None; text: str | None; blob_b64: str | None; truncated: bool

# ports.py (deltas)
class Capability(StrEnum): ...; external_resources = "external_resources"
class CredentialKind(StrEnum): oauth = "oauth"; api_token = "api_token"; none = "none"
class ExternalResourceReaderPort(Protocol):
    async def list_resources(self, ctx) -> list[ExternalResource]: ...
    async def read_resource(self, ctx, uri: str) -> ExternalResourceContent: ...
    async def list_tools(self, ctx) -> list[ExternalTool]: ...
    async def call_tool(self, ctx, name: str, arguments: dict) -> ExternalResourceContent: ...  # read-only: default-deny ∩ readOnlyHint
# IntegrationAdapter += credential_kinds: frozenset[CredentialKind]

# adapters/mcp/session.py — factory inyectable (TDD sustituye transport_factory por streams in-memory)
async def open_session(ctx, *, transport_factory=streamable_http_default):
    validate_mcp_url(ctx.base_url)                 # SSRF antes de abrir socket
    async with transport_factory(ctx) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize(); yield s
```

Contenido MCP = **dato inerte**: nunca se auto-ejecuta, evalúa ni interpola; solo se mapea a DTO. Todo error de red/timeout/tope → `AppException` controlada; tokens jamás en respuestas ni logs.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|--------------|----------|
| Unit — SSRF | `validate_mcp_url`: host fuera de allowlist; `127.0.0.1`/`10.*`/`192.168.*`/`169.254.*`/`::1`/`fc00::/7` rechazados; `http` en prod rechazado | pytest puro; `getaddrinfo` con IPs literales o monkeypatch |
| Unit — reader | `list_resources`/`read_resource`/`list_tools`/`call_tool` contra `FastMCP` in-memory (una tool `readOnlyHint` + una de escritura): recurso→DTO; `read` sobre tope de bytes → rechaza sin cargar todo; `list` con `MAX_LIST_ITEMS`; tool allowlisted+readOnly → OK; tool NO en allowlist → deny (sin contactar); tool allowlisted pero write (`readOnlyHint` false/ausente) → deny; timeout → `MCP_TIMEOUT`; servidor inalcanzable en `initialize` → `MCP_SERVER_UNREACHABLE` | SDK `create_connected_server_and_client_session` (sin red); `transport_factory` inyectado |
| Unit — registro | `mcp` se registra sin editar el núcleo; `capabilities == {external_resources}`; `credential_kinds == {api_token, none}` | fake registry |
| Integration `test_connectors_mcp.py` | Registrar conector MCP (config + `PUT /credential` token cifrado, sin navegador); lectura por miembro; registro solo admin/manager (member/viewer→403); token ausente de toda respuesta y log; aislamiento org A/B (404) | `client` ASGI + fixtures 01; `two_orgs` |

## Threat Matrix

Ejes formales (rutas doc-like, selección de repo Git, estado de commit/push, comandos PR) → **N/A**: MCP no usa shell, subprocess, `stdio` ni automatización VCS/PR (transporte solo HTTP remoto; el adaptador es cliente de red, no ejecuta código). Los riesgos propios (SSRF, ejecución de tool de escritura, agotamiento por respuesta grande/lenta, fuga de token, cruce multi-tenant, contenido no confiable) NO se omiten: se enumeran como Security Requirements con test RED por fila (ver Testing + Risks del `proposal.md`), mismo patrón que el 14.

## Migration / Rollout

**El 19 NO agrega esquema**: la config MCP vive como namespace `settings.mcp` en la columna `connectors.settings JSONB` (dueño: 17, la agrega junto a `credential_kind` en su migración) y el valor de enum `none` es extensión de datos sobre `credential_kind` (dueño: 17). Orden de applies estricto **17 → 18 → 19** con verificación de head de Alembic EN VIVO; si al apply del 19 no existen `credential_kind` o `connectors.settings`, el apply queda **BLOQUEADO** y lo reporta — nunca los crea. La serialización de applies ya gestiona la ranura Alembic (el 19 no prescribe números; el 14 renumera con verificación de head en vivo). Sin el adaptador `mcp` registrado el núcleo del 14 queda inerte. Rollback = revertir el merge. Dependencia dura: **14 archivado** antes del apply del 19.

## Open Questions

- [ ] **Versión del SDK `mcp` y revisión de spec**: no verificable desde este ejecutor (sin WebFetch/context7); confirmar en el apply la versión estable en PyPI (≥ la que estabiliza `streamablehttp_client`) y la `protocolVersion` vigente, y pinnearla exacta como el resto de `requirements.txt`.
- [x] **`credential_kind` / `settings` (coordinación)**: RESUELTO por el orquestador — 17 dueño único de `credential_kind` Y de `connectors.settings` (ambas en su migración, primer apply de la serie); el 19 solo aporta el valor `none` y el namespace `settings.mcp`. Orden estricto 17→18→19 con verificación de head en vivo; el apply del 19 BLOQUEA si faltan, nunca los crea.
- [ ] **DNS-rebinding**: el IP-pin cierra el TOCTOU; si se difiere, queda como riesgo residual documentado (allowlist de host lo acota).
- [x] **RBAC de `call_tool`**: la spec `mcp-connector` ratifica `cualquier miembro` (es read-only enforced); resuelto.
