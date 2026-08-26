# Exploración — 48-puerto-llm (`LlmPort` + adaptadores + registro + health)

> Fase `sdd-explore`. Store híbrido: este contenido está también en Engram (`sdd/48-puerto-llm/explore`, observación #3710).

## Resumen ejecutivo

El repositorio ya tiene **dos precedentes distintos** para «puerto + adaptadores», y el cambio 48 necesita el segundo, no el primero: `app/integrations/registry.py` resuelve *muchos proveedores activos a la vez, buscados por nombre* (por conector), mientras que `app/email/sender.py:85-90` resuelve *un único adaptador activo por proceso, elegido por una variable de entorno* — que es exactamente la forma del `LlmPort`. La recomendación es copiar el idioma de `EmailSender` (Protocol + adaptadores concretos + `get_llm_port()` leyendo `settings.LLM_PROVIDER`, con `fake` por defecto igual que `EMAIL_BACKEND="console"`), montar los dos clientes reales sobre la disciplina httpx ya probada en `microsoft365/client.py` y `jira/client.py` (transporte inyectable, `sleep` inyectable, backoff acotado, taxonomía de errores tipada, jamás loguear la credencial), y exponer `GET /api/v1/assistant/health` desde un módulo nuevo `backend/app/modules/assistant/` con `require_role(admin, manager)` y el sobre `{data, message, meta}`. No hay persistencia en este cambio.

Hallazgo con consecuencia de diseño: **la salida estructurada NO es homogénea entre los backends compatibles con OpenAI**. Ollama, llama.cpp y LM Studio interpretan `response_format` de forma distinta (y llama.cpp lo ignora en silencio en varios casos reportados). Por tanto el esquema JSON viaja como *pista*, y la **validación local con Pydantic v2 es obligatoria y es la única garantía real**: un `parsed` sin validar no debe existir en `LlmResponse`.

---

## Estado actual con evidencia

### 1. Dónde vive el puerto y cómo se selecciona el adaptador

| Precedente | Forma | Evidencia |
|---|---|---|
| Registro mutable por nombre | dict `provider -> adapter`, auto-registro en import | `backend/app/integrations/registry.py:11-23`; auto-registro en `adapters/microsoft365/__init__.py:10`, `google/__init__.py:11`, `glpi/__init__.py:13`, `jira/__init__.py:13`, `mcp/__init__.py:11`, `solercia_connect/__init__.py:14`, `fake.py:187` |
| Activación explícita del registro | el paquete NO importa sus submódulos; lo hace `db_init.py` | `backend/app/integrations/adapters/__init__.py:1-7`; `backend/app/db_init.py:26-36` |
| Lista mutable (fan-out) | `list[DeliveryChannel]` | `backend/app/notify/registry.py:14-26`; canales en `app/email/outbox.py:104`, `app/realtime/publisher.py:89` |
| Dict estático + factory | `dict[str, type[Strategy]]` + `get_strategy()` | `backend/app/alerts/registry.py:11-24`; `backend/app/methodology/factory.py:12-37` (error controlado `AppException` para valor inválido) |
| **Un adaptador activo elegido por env** | **Protocol + adaptadores + factory que lee `settings`** | **`backend/app/email/sender.py:24-29` (Protocol `EmailSender`), `:32-49` (`ConsoleEmailSender`, cero red), `:85-90` (`get_email_sender()` selecciona *sólo* por `settings.EMAIL_BACKEND`)** |

Puertos como `Protocol` disjunto por capacidad: `backend/app/integrations/ports.py:61-71` (`Capability`), `:74-81` (`AccessContext` como `@dataclass(frozen=True)`), `:84-89` (`MailReaderPort`), `:216-247` (`IntegrationAdapter` con `port_for`). El mismo criterio en `backend/app/notify/ports.py:35-71` («modelar la política como TIPO, no como rama `None`»).

Costura que consumirá el cambio 49: `backend/app/modules/intake/classifier.py:19-24` (`ClassifierPort`), cuyo docstring `:6-9` la declara «la ÚNICA costura que un futuro `LLMClassifier` implementaría sin tocar `service.py`»; hoy se instancia a mano en `backend/app/modules/intake/service.py:198`. **El 48 no toca esa costura.**

`backend/app/ai/` **no existe** (verificado con glob): el cambio 48 crea el árbol desde cero.

### 2. Contrato del puerto

- DTOs de frontera del repo = **frozen dataclasses**: `backend/app/integrations/dtos.py:1-5` («Frozen dataclasses: a port response is a pure snapshot of provider data, never an ORM row»), `:11-22` (`MailMessage`). `AccessContext` también (`ports.py:74-81`).
- Pydantic v2 se usa para **esquemas de API** (`openspec/config.yaml:6-10`; `app/modules/*/schemas.py`) — no para DTOs de puerto.
- Errores tipados, dos estilos vigentes:
  - `AppException` con `code` estable y `status_code` → llega al cliente HTTP tal cual: `backend/app/shared/exceptions.py:14-27` y handler `:29-43` (`{detail, code, status}`); ejemplo completo en `backend/app/integrations/adapters/jira/errors.py:78-136` (`jira_unavailable` 503, `jira_auth_error` 401, `jira_config_invalid` 422, `jira_rate_limited` 503, `jira_request_failed` 502).
  - Jerarquía de excepciones planas cuando el fallo es del adaptador y el llamador decide cómo degradarlo: `backend/app/integrations/adapters/solercia_connect/errors.py:11-51`.
- Regla de no filtrar secretos escrita en el propio código: `jira/errors.py:6-9` («NEVER interpolate an `email`/`api_token` into any message built here»), `solercia_connect/client.py:60-64` («Naming the value would echo an operator-supplied host into logs»).

### 3. Configuración

- `backend/app/config.py:9-21` — `Settings(BaseSettings)` con `SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")`; `:327-334` — `@lru_cache get_settings()` + singleton de módulo `settings = get_settings()`.
- Secretos: `JWT_SECRET` (`:28`), `INTEGRATIONS_FERNET_KEY` (`:98-104`, con default de desarrollo válido y validación *fail-fast* al arranque en `backend/app/main.py:102`), `SMTP_PASSWORD` (`:89`), `M365_CLIENT_SECRET` (`:149`), `GOOGLE_OAUTH_CLIENT_SECRET` (`:173`). Ninguno se imprime nunca.
- Guardas anti-SSRF ya existentes, por orden de rigidez: `MCP_HOST_ALLOWLIST` (`:283`, *default-deny* de hosts, `adapters/mcp/ssrf.py:108-116` rechaza **antes** de resolver DNS) > `GLPI_BASE_URL_ALLOWLIST` (`:202`, lista cerrada de URLs completas) ≈ `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST` (`:233-236`, incluye `http://host.docker.internal:8765`) > `JIRA_BASE_URL_ALLOWED_SUFFIX` (`:261`, sufijo obligatorio) > `_require_https` fijo (`adapters/microsoft365/client.py:46-53`).
- Convención de nombres de timeout ya establecida: `M365_TIMEOUT_SECONDS` (`:153`), `GOOGLE_TIMEOUT_SECONDS` (`:181`), `GLPI_TIMEOUT_SECONDS` (`:203`), `SOLERCIA_CONNECT_TIMEOUT_SECONDS` (`:237`), `JIRA_TIMEOUT_SECONDS` (`:262`). ⇒ `LLM_TIMEOUT_SECONDS`, no `LLM_TIMEOUT_S` (desviación menor respecto de la decisión Engram #3686, a ratificar en la propuesta).
- Puntos de inserción de entorno: `env.example:10-21` (bloque «Backend (FastAPI)») y `docker-compose.yml:36-44` (`services.backend.environment`). El compose **no** declara `extra_hosts`.

### 4. Idioma del cliente HTTP

Dos formas conviven; ambas con transporte inyectable (`httpx.MockTransport`) para que las pruebas nunca toquen la red.

- **Cliente de larga vida** (`AsyncClient` en el constructor + `aclose()`): `adapters/microsoft365/client.py:69-90` y `:232-235`; `adapters/jira/client.py:95-113` y `:256-259`.
- **Cliente efímero por llamada** (`async with httpx.AsyncClient(...)`): `adapters/solercia_connect/client.py:92-97`.
- **Frontera de resiliencia**, idéntica en ambos clientes reales: `microsoft365/client.py:131-170` (401 → refresh + 1 reintento; 429 → backoff acotado por `Retry-After`; 403 → capacidad no disponible; ≥500 → reintentables; resto de 4xx → no reintentable) y `jira/client.py:195-228`. El techo del backoff se aplica en `microsoft365/client.py:215-225` y `jira/client.py:230-240` (`min(seconds, MAX_BACKOFF_SECONDS)`).
- **`sleep` inyectable** para que el backoff no duerma de verdad en pruebas: `microsoft365/client.py:74`, `jira/client.py:103`.
- **Log seguro de errores**: `microsoft365/client.py:201-213` y `jira/client.py:242-254` — status + cuerpo truncado a 200 caracteres (`:30` / `:41`), nunca la cabecera `Authorization`.
- **Validación de destino en el constructor, antes de cualquier request**: `jira/client.py:51-59`, `solercia_connect/client.py:53-66`, `microsoft365/client.py:78-79`.
- `httpx==0.28.1` ya está fijado (`backend/requirements.txt:16`). No hay SDK `openai` ni `anthropic` en el archivo y no debe agregarse (filosofía artesanal; el precedente de justificar cada dependencia nueva está en `requirements.txt:18-29`).

### 5. Endpoint de salud

- `backend/app/main.py:61` (`API_PREFIX = "/api/v1"`), `:158-190` (bloque de `include_router`), `:193-194` (inclusión condicional por flag, precedente si se quisiera un `LLM_ENABLED`), `:204-208` (`GET /api/v1/health` actual, sin autenticación y sin dependencias).
- RBAC: `backend/app/dependencies.py:189-203` (`require_role(*roles)`); todos los módulos de integración usan `admin + manager`: `modules/glpi_sync/router.py:26`, `modules/connectors/router.py:57`, `modules/jira_import/router.py:27`, `modules/intake/router.py:32-34`. El *singleton* a nivel de módulo existe por ruff B008 (`glpi_sync/router.py:24-26`).
- Sobre de respuesta: se construye literalmente en cada router — `glpi_sync/router.py:41` (`{"data":…, "message":…}`) y `:53` (`{"data":…, "meta":{…}}`). **No existe un helper compartido** (búsqueda en `app/shared/` sin resultados), así que el módulo nuevo replica el literal.
- Screaming Architecture y regla `router → service → repository`: `openspec/config.yaml:22` y `CLAUDE.md:129`.

### 6. Pruebas

- `backend/tests/conftest.py:37-40` — `skip_no_db` (las pruebas que tocan BD se saltan sin `TEST_DATABASE_URL`); `:204-242` — `make_member(session, org, role)`; `:245-267` — `rbac_admin` (catálogo RBAC, sistema **distinto** de `MemberRole`).
- Adaptador HTTP sin red: `backend/tests/test_adapter_solercia_connect.py:29-35` construye `Settings(**overrides)` explícito (no monkeypatch), `:70-83` inyecta `httpx.MockTransport`, `:86-100` prueba que una URL rechazada **nunca** llega al transporte (el handler lanza `AssertionError`). Mismo patrón en 15 archivos (`test_adapter_microsoft365.py`, `test_jira_adapter_client.py`, `test_adapter_google_client.py`, …).
- Parcheo del singleton de settings: `monkeypatch.setattr(settings, "EMAIL_ENABLED", True)` en `backend/tests/test_email_outbox.py:39`; `test_seed_demo_flag.py:83`.
- Prueba de RBAC 403 sobre endpoint: `backend/tests/test_intake_rules_endpoints.py:32-62`.
- `backend/pyproject.toml:52-60` — `[tool.pytest.ini_options]` sólo declara `asyncio_default_fixture_loop_scope`; **no hay `markers` registrados**, así que un marcador opcional de humo en vivo obliga a añadir la clave `markers` allí.
- TDD estricto obligatorio: `openspec/config.yaml:26-33` (`cd backend && pytest tests/ -v`).

### 7. Hechos del entorno local (lo que el código necesita que sea cierto)

- Backend en contenedor (`docker-compose.yml:32-49`, puerto host 8081→8000) y venv en el host (`CLAUDE.md:40`). Un runtime local (Ollama 11434, LM Studio 1234, llama.cpp 8080) escucha en el **host**, no en la red de Docker.
- Desde el contenedor, en macOS con Docker Desktop, la dirección es `http://host.docker.internal:<puerto>/v1`; desde el venv del host, `http://localhost:<puerto>/v1`. El repo ya depende de ese nombre (`config.py:233-236`), lo que confirma que la topología es la asumida.
- Consecuencia: `LLM_BASE_URL` **no puede tener un único valor correcto** para ambos modos de ejecución. El valor efectivo debe venir del entorno (`docker-compose.yml` para el contenedor, `.env`/shell para el host), y la lista de permitidos debe contener **ambas** formas, igual que `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST`.
- El compose no declara `extra_hosts`, por lo que en un host Linux `host.docker.internal` no resolvería; conviene documentarlo, no resolverlo en este cambio.

### 8. Prompts y versionado

- Ubicación planeada `backend/app/ai/prompts/` (plan §6: «plantillas versionadas (texto en código, inglés técnico), sin voz de persona»), confirmada por Engram #3686.
- `prompt_version` es requisito del cambio 49 (`assistant_suggestions` guarda `provider`, `model`, `prompt_version`) ⇒ el 48 debe dejar el campo disponible en la metadata de `LlmResponse` aunque no lo persista. La regla de idioma del repo obliga a que el *prompt* sea inglés técnico y a que el texto pedido al modelo para el usuario final sea español colombiano formal (tuteo) — eso se instruye en el prompt, no en el puerto.

### 9. Contratos externos (evidencia limitada: `WebFetch` bloqueado en esta sesión)

`.atl/skill-registry.md` **no lista ningún skill `claude-api`**. `WebFetch` fue rechazado por un hook del entorno; sólo se usó `WebSearch`. **Todo lo siguiente debe reconfirmarse en `sdd-design` contra la documentación oficial** (el orquestador aporta el contrato de Anthropic verificado en la sección final).

**Compatible con OpenAI — `POST {base_url}/chat/completions`**

- Petición: `{model, messages:[{role: system|user|assistant, content}], temperature, max_tokens, stream:false, response_format?, tools?, tool_choice?}`.
- Respuesta: `{choices:[{index, message:{role, content, tool_calls?}, finish_reason}], usage:{prompt_tokens, completion_tokens, total_tokens}, model, id}`.
- **Divergencias confirmadas por búsqueda** (el punto de diseño más importante del cambio):
  - Ollama: su API nativa (`/api/chat`) usa `format`, que acepta el literal `"json"` o un esquema JSON crudo. El *shim* `/v1/chat/completions` traduce `response_format.type="json_object"` → `format:"json"` y deja pasar el esquema; el sobre anidado de OpenAI (`{"type":"json_schema","json_schema":{"name":…,"schema":{…},"strict":true}}`) está reportado como no honrado de forma consistente.
  - llama.cpp server: documenta `{"type":"json_object","schema":{…}}` y `{"type":"json_schema","schema":{…}}` — con el esquema **al nivel superior**, no anidado bajo `json_schema`; hay defectos abiertos donde `json_schema` se ignora **en silencio**, sin error ni aviso.
  - LM Studio: documenta aceptar `response_format` con esquema JSON al estilo OpenAI.
- Conclusión para el adaptador: el esquema es una **pista best-effort**; la validación local es la garantía.

**Anthropic — `POST https://api.anthropic.com/v1/messages`**

- Cabeceras: `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`.
- Cuerpo obligatorio: `model`, `max_tokens`, `messages`. `system` es un campo **de nivel superior**, no un rol dentro de `messages`. Opcionales: `temperature`, `tools`, `tool_choice`, `stop_sequences`.
- Respuesta: `{id, type:"message", role:"assistant", content:[{type:"text"|"tool_use", …}], model, stop_reason ∈ {end_turn, max_tokens, stop_sequence, tool_use}, usage:{input_tokens, output_tokens}}`.
- Salida estructurada: una sola herramienta cuyo `input_schema` es el esquema JSON, con `tool_choice:{type:"tool", name:…}`; se lee el bloque `content[]` con `type=="tool_use"` y se toma su `input`.
- Errores: 400 `invalid_request_error`, 401 `authentication_error`, 403 `permission_error`, 404 `not_found_error`, 413 `request_too_large`, 429 `rate_limit_error`, 500 `api_error`, 529 `overloaded_error`. Reintentables: 429 (con `Retry-After`), 500, 529. No reintentables: 400/401/403/404/413.
- **`max_tokens` es obligatorio** y excederlo produce 400 ⇒ el puerto no puede dejarlo opcional sin default.
- **Los identificadores de modelo no se asumen**: `LLM_MODEL` es una cadena que fija el operador, sin default codificado para Anthropic.

---

## Áreas afectadas

| Ruta | Por qué |
|---|---|
| `backend/app/ai/ports.py` (nuevo) | `LlmPort` Protocol + `LlmRequest`/`LlmResponse`/`LlmMessage` como frozen dataclasses |
| `backend/app/ai/errors.py` (nuevo) | Taxonomía tipada (unavailable / auth / rate-limited / timeout / invalid-output / content-filter / config) |
| `backend/app/ai/registry.py` (nuevo) | Selección del adaptador activo por `settings.LLM_PROVIDER` |
| `backend/app/ai/adapters/{fake,openai_compatible,anthropic}.py` (nuevos) | Tres implementaciones del puerto |
| `backend/app/ai/prompts/` (nuevo) | Plantillas versionadas; en el 48 basta el andamiaje + `PROMPT_VERSION` |
| `backend/app/modules/assistant/{__init__,router,service,schemas}.py` (nuevos) | `GET /api/v1/assistant/health` (router → service → puerto) |
| `backend/app/config.py:314-324` (después de `INTAKE_*`) | Bloque `LLM_*` con el comentario justificativo que el archivo exige |
| `backend/app/main.py:190` | `app.include_router(assistant_router, prefix=API_PREFIX)` |
| `env.example:21` · `docker-compose.yml:44` | Variables `LLM_*` documentadas / fijadas |
| `backend/tests/test_ai_*.py`, `test_assistant_health*.py` (nuevos) | Contrato + adaptadores + RBAC |

**No se toca**: `backend/app/modules/intake/` (es el 49), `backend/app/integrations/` (dominio distinto), `backend/app/db_init.py`, ni nada bajo `backend/app/maintenance/` ni `backend/scripts/` (cambio 42). Cero migraciones, cero modelos SQLAlchemy, cero repositorios: la regla de persistencia (`agents/rules/solercia-persistence.md:41-42`) no aplica porque no hay agregado nuevo.

---

## Opciones comparadas

### A. Cómo se selecciona el adaptador activo

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **A1. Factory por setting** (calco de `email/sender.py:85-90` + `methodology/factory.py:20-37`) | Un solo proveedor activo, que es el modelo real; error controlado para valor inválido; sin efectos de import; el `fake` por defecto garantiza cero red; `get_llm_port()` es trivial de sustituir en pruebas | Añadir un cuarto proveedor toca el dict del núcleo (una línea) | **Bajo** |
| A2. Auto-registro en import (calco de `integrations/registry.py`) | «Sin tocar el núcleo» para un proveedor nuevo | Resuelve un problema que aquí no existe; acopla el arranque de la IA a `db_init.py`; deja adaptadores registrados que nunca se usan | Medio |
| A3. Híbrido: dict estático + `register_llm_adapter()` | Cubre ambos casos | Dos mecanismos para una decisión; superficie sin consumidor hoy | Medio |

### B. Estrategia de salida estructurada

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **B1. Por adaptador + validación local obligatoria** (`json_schema` traducido a la forma de cada backend en `openai_compatible`; *tool-use* forzado en `anthropic`; Pydantic valida siempre y `parsed` sólo existe si validó) | Aprovecha el mejor mecanismo de cada proveedor; sobrevive a que llama.cpp ignore el esquema en silencio; `LlmSchemaMismatch` es un fallo explícito | Más código en `openai_compatible` (forma del `response_format` configurable) | **Medio** |
| B2. Sólo modo JSON + esquema en el prompt | Máxima compatibilidad; el más simple | Peor tasa de acierto; desperdicia el *tool-use* de Anthropic | Bajo |
| B3. *Tool-use* en ambos | Un solo camino mental | Soporte de `tools` desigual en runtimes locales | Alto |

### C. Alcance de la sonda de `GET /assistant/health`

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| C1. Sólo configuración (sin red) | Cero coste, siempre responde | No responde «¿está prendido Ollama?» | Bajo |
| **C2. Sonda barata y sin tokens, opt-in por query param** (`?probe=true` → `GET {base_url}/models` en `openai_compatible`; en `anthropic` sólo valida configuración y reporta `reachability="not_probed"`) | Responde la pregunta real para el caso local; nunca gasta tokens ni dinero; por defecto es idéntico a C1 | Dos ramas por proveedor; `/models` puede existir y el modelo pedido no estar cargado (se reporta) | **Bajo-Medio** |
| C3. Generación mínima (`max_tokens=1`) | Prueba el camino completo | Gasta tokens y dinero; efecto secundario en un endpoint de salud | Medio |

### D. Guarda de la URL base del LLM

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| D1. Sin guarda | Cero fricción | Un `LLM_BASE_URL` mal puesto envía contenido de buzón a un tercero: exfiltración | Bajo |
| **D2. Lista blanca cerrada de URLs base** (forma de `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST`), validada en el constructor antes de cualquier request | Mismo idioma que la guarda hermana; admite red privada explícitamente; el error nombra el ajuste, nunca el valor | Cambiar de puerto local exige editar la lista | **Bajo** |
| D3. Lista de hosts *default-deny* con fijado de IP (forma MCP) | La más estricta | Desproporcionada: la URL la fija el operador | Alto |

---

## Recomendación

1. **A1 + B1 + C2 + D2.**
2. **Núcleo** en `backend/app/ai/`, sin SQLAlchemy ni FastAPI: `LlmMessage(role, content)`, `LlmRequest(system, messages, json_schema=None, temperature, max_tokens, timeout_seconds=None)` y `LlmResponse(text, parsed, usage, provider, model, prompt_version, latency_ms, finish_reason)` como `@dataclass(frozen=True)`. `parsed` es `None` salvo que se pidiera esquema **y** la validación local haya pasado. `LlmPort(Protocol)` con `async def complete(self, request: LlmRequest) -> LlmResponse`. Errores en `app/ai/errors.py` como subclases de `AppException` con `code` estable: `llm_unavailable` 503, `llm_auth_error` 401, `llm_rate_limited` 503, `llm_timeout` 503, `llm_invalid_output` 502, `llm_schema_mismatch` 502, `llm_content_filtered` 422, `llm_config_invalid` 422. Reintentos **deterministas y acotados** en código (`LLM_MAX_RETRIES`, `LLM_MAX_BACKOFF_SECONDS`, `Retry-After`).
3. **Adaptadores** en `backend/app/ai/adapters/` con constructor del repo (`transport`, `sleep`, `settings` inyectables): `fake.py`; `openai_compatible.py` (`POST {base_url}/chat/completions`, forma de `response_format` configurable; validación local siempre); `anthropic.py` (`POST {base_url}/v1/messages`, `x-api-key` + `anthropic-version`, `system` de nivel superior, herramienta única con `tool_choice` forzado, mapa 400/401/403/404/413/429/500/529).
4. **Registro**: `app/ai/registry.py` con `_ADAPTERS: dict[str, Callable[[], LlmPort]]` y `get_llm_port()` leyendo `settings.LLM_PROVIDER`, con `AppException` para valor desconocido.
5. **Configuración** al final de `Settings`: `LLM_PROVIDER: str = "fake"`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY: str = ""`, `LLM_TIMEOUT_SECONDS: float = 60.0`, `LLM_MAX_TOKENS: int`, `LLM_MAX_RETRIES: int = 2`, `LLM_MAX_BACKOFF_SECONDS: float = 30.0`, `LLM_JSON_MODE: str`, `LLM_BASE_URL_ALLOWLIST: list[str]` (`http://localhost:11434/v1`, `http://127.0.0.1:11434/v1`, `http://host.docker.internal:11434/v1`, `https://api.anthropic.com`). Espejo en `env.example` y `docker-compose.yml`.
6. **Endpoint** `GET /api/v1/assistant/health` en `backend/app/modules/assistant/` con `require_role(admin, manager)` y sobre `{"data": {...}, "message": "..."}`; `data` reporta `provider`, `model`, `base_url_host` (sólo `netloc`), `api_key_configured: bool`, `timeout_seconds`, `max_tokens`, `structured_output_mode`, `reachability ∈ {ok, unreachable, not_probed}` y `reachability_reason`. Nunca la clave, nunca la URL completa.
7. **Pruebas** (TDD estricto): `test_ai_port_contract.py` (mismo cuerpo contra los tres adaptadores), `test_ai_adapter_openai_compatible.py`, `test_ai_adapter_anthropic.py`, `test_ai_registry.py`, `test_assistant_health_endpoint.py` (RBAC 200/403; la respuesta no contiene clave ni URL completa; `probe=true` con `MockTransport`). Ninguna prueba toca la red.

**Presupuesto de revisión**: 1.600–1.800 líneas estimadas (≈700–900 de pruebas). Encadenar: (1) núcleo `ports`/`errors`/`fake`/`registry` + configuración; (2) adaptador `openai_compatible`; (3) adaptador `anthropic`; (4) módulo `assistant` + endpoint.

---

## Riesgos

1. **La salida estructurada no está garantizada en los runtimes locales** (llama.cpp ignora `json_schema` en silencio en defectos abiertos; Ollama no honra consistentemente el sobre anidado). *Mitigación*: validación local obligatoria y `LLM_JSON_MODE` configurable.
2. **Contratos externos verificados sólo a nivel de búsqueda** por el explorador; el orquestador aporta el contrato de Anthropic verificado con el skill oficial (sección final).
3. **Fuga de secretos**: el prompt del 49 llevará contenido de buzón. *Mitigación*: replicar `_log_error_response` (status + 200 caracteres del cuerpo de respuesta, nunca cabeceras ni cuerpo de petición) y una prueba que lo asevere.
4. **`host.docker.internal` no es universal** (sin `extra_hosts` en compose). *Mitigación*: documentar; `reachability=unreachable` con motivo legible.
5. **El singleton `settings` se congela en import**. *Mitigación*: leer `settings` en tiempo de llamada o recibir un `Settings` explícito.
6. **Colisión textual con el cambio 42** en `config.py`/`docker-compose.yml`. *Mitigación*: insertar el bloque `LLM_*` al final de `Settings`; el 42 ya está integrado en el tracker cuando el 48 llegue a `apply`.
7. **Deriva de alcance hacia el 49.** *Mitigación*: la sonda nunca genera texto; clasificador/sugerencias/casos de uso son del 49.
8. **Desviación de nombre**: `LLM_TIMEOUT_SECONDS` en lugar de `LLM_TIMEOUT_S` — ratificada.

---

## ¿Listo para propuesta?

**Sí.** Tres preguntas resueltas por el orquestador (sección siguiente).

## Decisiones del orquestador (2026-08-27)

- **A1 + B1 + C2 + D2** aceptadas. `LLM_TIMEOUT_SECONDS` ratificado.
- **`LLM_PROVIDER` por defecto `fake`** (espeja `EMAIL_BACKEND="console"`: la suite nunca toca la red). En `docker-compose.yml` y `env.example` se documenta la activación local: `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://host.docker.internal:11434/v1` (contenedor) / `http://localhost:11434/v1` (host), `LLM_MODEL=qwen3.5:9b-q4_K_M` (modelo ya descargado en el Ollama del usuario; alternativas locales: `gpt-oss:20b`, `qwen3.6:35b-a3b`). Anthropic se activa con `LLM_PROVIDER=anthropic`, `LLM_BASE_URL=https://api.anthropic.com`, `LLM_MODEL` (el usuario ya define `ANTHROPIC_MODEL` en su entorno) y `LLM_API_KEY`.
- **RBAC del endpoint**: `admin + manager`.
- **Humo en vivo contra Ollama**: fuera del 48 (sin marcador nuevo en `pyproject.toml`); queda como validación manual documentada en el runbook del cambio (`GET /api/v1/assistant/health?probe=true`).
- **Rebanadas** (feature-branch-chain): (1) núcleo + config + fake + registry; (2) `openai_compatible`; (3) `anthropic`; (4) módulo `assistant` + endpoint + docs.
