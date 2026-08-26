# Design: 48 · Puerto LLM (`LlmPort`), adaptadores y `GET /assistant/health`

> Fase `sdd-design`. Store híbrido: espejo de Engram `sdd/48-puerto-llm/design`.
> Entradas: `proposal.md` (#3712), `exploration.md` (#3710), decisiones #3711 y #3709.
> Decisiones cerradas que este diseño **implementa sin reabrir**: A1 (factory por setting),
> B1 (salida estructurada por adaptador + validación Pydantic obligatoria), C2 (sonda opt-in),
> D2 (allowlist cerrada), `fake` por defecto, RBAC `admin+manager`, cuatro rebanadas.

## Enfoque técnico

Un núcleo neutro (`backend/app/ai/`) que no conoce FastAPI, SQLAlchemy ni proveedor alguno, tres
adaptadores intercambiables y un módulo HTTP de diagnóstico. El idioma es el de
`app/email/sender.py`: **Protocol + adaptadores concretos + factory que lee `settings` en tiempo de
llamada**. La disciplina HTTP es la de `adapters/jira/client.py` y `adapters/solercia_connect/client.py`:
transporte y `sleep` inyectables, validación del destino en el constructor, backoff acotado, log de
error con status + 200 caracteres del cuerpo de **respuesta**. Nada persiste; el cambio no crea
agregados, así que `agents/rules/solercia-persistence.md` no aplica.

La regla irrenunciable atraviesa todo el diseño: **el modelo nunca decide control de flujo**
(`docs/decisions/2026-08-23-solercia-platform-decisions.md:64`). Los reintentos son deterministas,
la validación es local y una respuesta que no valida es un error explícito, nunca un `parsed` a medias.

---

## Decisiones de arquitectura

### D1 · El esquema viaja como modelo Pydantic, no como `dict` de JSON Schema

**Elección**: `LlmRequest.output_schema: type[BaseModel] | None`. El adaptador deriva el JSON Schema
de alambre con `model_json_schema()` y valida con `Model.model_validate(...)`.

| Alternativa | Por qué se rechaza |
|---|---|
| `json_schema: dict` + `jsonschema.validate()` | `jsonschema` sólo llega **transitivamente** con `mcp` (`requirements.txt:27`, sin pin propio). Importarlo directamente obligaría a declararlo y a pinearlo para hacer algo que Pydantic v2 —dependencia de primera clase del repositorio— ya hace |
| `json_schema: dict` + modelo Pydantic dinámico (`create_model`) | Construye en tiempo de ejecución lo que el llamador ya tiene escrito; pierde tipos estáticos y duplica la fuente de verdad |

**Justificación**: B1 exige validación Pydantic obligatoria, y Pydantic v2 **no** puede compilar un
validador desde un JSON Schema arbitrario — sólo lo emite. Además el ayudante oficial del SDK
(`client.messages.parse(output_format=<modelo>)` → `response.parsed_output`) recibe exactamente un
modelo Pydantic, así que el adaptador `anthropic` usa el camino soportado sin una segunda validación
manual. El 49 definirá su esquema de clasificación como modelo Pydantic de todos modos.

**Desviación declarada**: la propuesta nombró el campo `json_schema`; el diseño lo renombra a
`output_schema` porque su tipo ya no es un `dict`. `ports.py` importa `pydantic` (a diferencia de
`integrations/dtos.py`, que evita hacerlo porque sus DTOs son instantáneas de proveedor).

*Gotcha*: `model_json_schema()` emite `$defs`/`$ref` para modelos anidados y los runtimes locales los
honran de forma desigual. Los esquemas del 49 deben ser planos; se documenta, no se fuerza.

### D2 · `max_tokens` opcional en el DTO, obligatorio en el alambre

**Elección**: `LlmRequest.max_tokens: int | None = None`; cada adaptador resuelve
`request.max_tokens or settings.LLM_MAX_TOKENS` y **siempre** pone un entero en el cuerpo.

**Alternativa rechazada**: campo obligatorio en el DTO (lo que decía la propuesta) — empuja `settings`
a todos los llamadores para un valor que el operador ya configuró una vez.

**Justificación**: el requisito real de Anthropic es sobre la petición, no sobre el DTO. La invariante
se prueba donde importa: una aserción de que el cuerpo enviado lleva `max_tokens` entero.

### D3 · Sin caché de instancias en el registro; `fake` sí es singleton

**Elección**: `get_llm_port()` construye un adaptador nuevo en cada llamada leyendo `settings` en ese
momento. `fake` es un singleton de módulo (calco de `_console_sender`, `email/sender.py:82`).

**Alternativas rechazadas**: `@lru_cache` sobre el puerto (congelaría `settings` en el primer uso, que
es exactamente el riesgo 5 de la exploración, y dejaría un `AsyncClient` de larga vida sin dueño de
`aclose()`).

**Justificación**: la frecuencia real es una clasificación por correo, no un tráfico que justifique un
pool. `openai_compatible` usa cliente efímero por llamada (`async with httpx.AsyncClient(...)`,
precedente `solercia_connect/client.py:92-97`) y `anthropic` usa `async with AsyncAnthropic(...)`.
El `fake` conserva estado para que las pruebas inspeccionen lo que se le pidió.

### D4 · `probe()` es parte del puerto, no una rama del servicio

**Elección**: `LlmPort` expone `async def probe(self) -> LlmProbe` además de `complete()`.

**Alternativa rechazada**: el servicio de salud ramifica por `settings.LLM_PROVIDER`. Eso reintroduce
el `if proveedor == ...` que el repositorio prohíbe explícitamente para metodologías
(`CLAUDE.md`, «la API y la UI leen el comportamiento DESDE la strategy»).

**Justificación**: la sonda es una capacidad del proveedor. `fake` → `ok`; `openai_compatible` →
`GET {base_url}/models`; `anthropic` → `not_probed` (sondear gastaría cuota). **Ninguna genera texto.**

### D5 · `anthropic` se pinea sin declarar `httpx2` por separado

**Elección**: una sola línea nueva, `anthropic==1.0.0`, con el comentario justificativo que el archivo
exige. `httpx2` se nombra en el comentario como transitivo, sin pin propio.

**Alternativa rechazada**: declarar también `httpx2>=2.0` (lo que sugiere la guía de migración del SDK
para importaciones directas). Aquí la única importación directa vive en la suite de pruebas, que no
puede correr sin `anthropic` instalado; y `requirements.txt:26-27` ya sienta el precedente de nombrar
dependencias indirectas en el comentario sin pinearlas.

**Hechos verificados en vivo (2026-08-27)**: `anthropic==1.0.0` exige `pydantic>=1.9.0,<3` (compatible
con el pin `pydantic==2.10.4`), Python ≥3.10 (el runtime es 3.12) y `httpx2>=2.0.0,<3`, paquete
**separado** de `httpx==0.28.1`: conviven sin conflicto de resolución.

**Corolario de pruebas**: el repositorio no usa `respx`/`pytest-httpx`/`vcrpy`, así que **no** hace
falta `httpx2.alias_httpx()`; basta el doble a nivel de transporte
`DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))`.

### D6 · `LLM_JSON_MODE` por defecto `json_object`

**Elección**: `json_object` (el más compatible) con el esquema adjunto al `system` como pista.
`json_schema_llamacpp` (esquema al nivel superior) y `json_schema_openai` (sobre anidado con `strict`)
quedan disponibles por configuración.

**Justificación**: el shim `/v1` de Ollama traduce `json_object` → `format:"json"` de forma
consistente, mientras que el sobre anidado está reportado como no honrado. Con validación local
obligatoria, el modo más compatible es el default correcto: una pista ignorada produce un
`llm_schema_mismatch` legible, nunca un `parsed` sin validar. Efecto lateral útil: el `system` con el
esquema contiene la palabra «json», requisito de las APIs compatibles para `json_object`.

### D7 · Ni reparación ni reintento ante fallo de esquema

**Elección**: una sola llamada por `complete()`. `LLM_MAX_RETRIES` cubre **sólo** transporte, 429 y 5xx.
Un cuerpo que no valida es `llm_schema_mismatch` inmediato.

**Justificación**: reintentar «pidiéndole al modelo que corrija» convierte la salida del modelo en
control de flujo (§3.4) y gasta tokens en un camino de error. La extracción sí es tolerante y
determinista: `json.loads` → sin cercas Markdown → subcadena entre el primer `{` y el último `}` →
`llm_invalid_output`.

---

## Estructura de módulos

| Archivo | Contenido |
|---|---|
| `backend/app/ai/__init__.py` | Vacío con docstring; **no** importa submódulos (precedente `integrations/adapters/__init__.py:1-7`) |
| `backend/app/ai/ports.py` | DTOs congelados + `LlmPort` |
| `backend/app/ai/errors.py` | Ocho subclases de `AppException` |
| `backend/app/ai/registry.py` | `_ADAPTERS` + `get_llm_port()` |
| `backend/app/ai/prompts/__init__.py` | `PROMPT_VERSION` + regla de versionado |
| `backend/app/ai/adapters/__init__.py` | Vacío: el registro importa de forma perezosa |
| `backend/app/ai/adapters/fake.py` | Cero red, estado inspeccionable |
| `backend/app/ai/adapters/openai_compatible.py` | httpx, transporte y `sleep` inyectables |
| `backend/app/ai/adapters/anthropic.py` | SDK oficial, import perezoso |
| `backend/app/modules/assistant/{__init__,router,service,schemas}.py` | `GET /api/v1/assistant/health` |

### Contrato del puerto (`ports.py`)

```python
Role = Literal["user", "assistant"]           # `system` es campo aparte, nunca un mensaje
FinishReason = Literal["stop", "other"]       # `length`/`content_filter` son errores, no resultados
Reachability = Literal["ok", "unreachable", "not_probed"]

@dataclass(frozen=True)
class LlmMessage:
    role: Role
    content: str

@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int

@dataclass(frozen=True)
class LlmRequest:
    system: str
    messages: tuple[LlmMessage, ...]
    output_schema: type[BaseModel] | None = None
    temperature: float = 0.0            # los runtimes locales lo honran; `anthropic` NUNCA lo reenvía
    max_tokens: int | None = None       # resuelto contra `LLM_MAX_TOKENS` por el adaptador (D2)
    timeout_seconds: float | None = None
    prompt_version: str | None = None

@dataclass(frozen=True)
class LlmResponse:
    text: str
    parsed: BaseModel | None            # existe SÓLO si se pidió esquema y validó (B1)
    usage: LlmUsage
    provider: str
    model: str
    prompt_version: str | None          # eco de la petición; el adaptador nunca lo inventa
    latency_ms: int
    finish_reason: FinishReason

@dataclass(frozen=True)
class LlmProbe:
    reachability: Reachability
    reason: str | None = None

class LlmPort(Protocol):
    async def complete(self, request: LlmRequest) -> LlmResponse: ...
    async def probe(self) -> LlmProbe: ...
```

`prompts/__init__.py`: `PROMPT_VERSION: Final[str] = "v1"` — cualquier cambio material de una plantilla
lo incrementa; el 49 lo persiste en `assistant_suggestions`.

### Taxonomía de errores (`errors.py`)

Subclases de `AppException` con mensaje en español colombiano formal, **sin interpolar jamás la clave
ni la URL** (regla escrita en `adapters/jira/errors.py:6-9`). El handler de `shared/exceptions.py:29-43`
las convierte en `{detail, code, status}` sin trabajo adicional.

| Clase | `code` | HTTP |
|---|---|---|
| `LlmUnavailable` | `llm_unavailable` | 503 |
| `LlmAuthError` | `llm_auth_error` | 401 |
| `LlmRateLimited` | `llm_rate_limited` | 503 |
| `LlmTimeout` | `llm_timeout` | 503 |
| `LlmInvalidOutput` | `llm_invalid_output` | 502 |
| `LlmSchemaMismatch` | `llm_schema_mismatch` | 502 |
| `LlmContentFiltered` | `llm_content_filtered` | 422 |
| `LlmConfigInvalid` | `llm_config_invalid` | 422 |

### Registro (`registry.py`)

```python
_ADAPTERS: dict[str, Callable[[Settings], LlmPort]] = {
    "fake": _build_fake,                          # devuelve el singleton de módulo
    "openai_compatible": _build_openai_compatible,
    "anthropic": _build_anthropic,                # importlib.import_module dentro de la función
}

def get_llm_port(settings: Settings | None = None) -> LlmPort:
    active = settings or default_settings          # leído en tiempo de LLAMADA (D3)
    builder = _ADAPTERS.get(active.LLM_PROVIDER)
    if builder is None:
        raise LlmConfigInvalid()                   # nunca KeyError; el valor NO se nombra
    return builder(active)
```

`_build_anthropic` hace `importlib.import_module("app.ai.adapters.anthropic")` dentro de la función, y
ese módulo hace `import anthropic` dentro de `_build_client()`. Con `LLM_PROVIDER` distinto de
`anthropic`, ni el módulo adaptador ni el paquete se cargan.
*Gotcha*: `app/ai/adapters/anthropic.py` e `import anthropic` conviven porque Python 3 usa importaciones
absolutas; las claves de `sys.modules` (`anthropic` y `app.ai.adapters.anthropic`) son distintas.

---

## Adaptador `openai_compatible`

`POST {base_url}/chat/completions`. Constructor: `(*, settings, transport=None, sleep=asyncio.sleep)`.
Valida **antes de cualquier petición** (precedente `solercia_connect/client.py:53-66`): `LLM_BASE_URL`
no vacía, presente en `LLM_BASE_URL_ALLOWLIST` normalizada (`strip().rstrip("/")`), `LLM_MODEL` no vacío.

### Cuerpo por `LLM_JSON_MODE`

| Modo | `response_format` | Notas |
|---|---|---|
| `json_object` (def.) | `{"type": "json_object"}` | El esquema se adjunta al `system` como bloque de pista |
| `json_schema_llamacpp` | `{"type": "json_schema", "schema": {…}}` | Esquema al **nivel superior** |
| `json_schema_openai` | `{"type": "json_schema", "json_schema": {"name": …, "schema": {…}, "strict": true}}` | Sobre anidado, LM Studio |

Base común: `{model, messages, max_tokens, temperature, stream: false}` con
`messages[0] = {"role": "system", "content": system(+pista)}`. El esquema de alambre siempre lleva
`required` completo y `additionalProperties: false` inyectado en cada nodo objeto.

### Lectura de la respuesta

`choices[0].message.content` → `LlmResponse.text`.
`usage.prompt_tokens|completion_tokens|total_tokens` → `LlmUsage` (ausente ⇒ ceros).
Con esquema: extracción tolerante (D7) → `Model.model_validate(...)` → `parsed`.
`latency_ms` con `time.perf_counter()`.

### Mapa de fallos

| Condición | Resultado |
|---|---|
| `httpx.TimeoutException` | `LlmTimeout` |
| `httpx.RequestError` | `LlmUnavailable` |
| `429` | Reintento acotado; agotado ⇒ `LlmRateLimited` |
| `≥500` | Reintento acotado; agotado ⇒ `LlmUnavailable` |
| `401` / `403` | `LlmAuthError` |
| `404` y demás `4xx` | `LlmConfigInvalid` (el cuerpo lo arma el adaptador: un 4xx señala `LLM_MODEL`/`LLM_BASE_URL`/`LLM_MAX_TOKENS`) |
| Cuerpo no JSON o sin `choices[0].message.content` | `LlmInvalidOutput` |
| `finish_reason == "length"` | `LlmInvalidOutput` (nunca texto truncado como válido) |
| `finish_reason == "content_filter"` | `LlmContentFiltered` |
| Esquema pedido y validación falla | `LlmSchemaMismatch`, `parsed is None` |

Backoff: `_retry_after_seconds()` = cabecera `Retry-After` como `float`, si no `1.0`, siempre
`min(valor, LLM_MAX_BACKOFF_SECONDS)` — calco literal de `jira/client.py:230-240`. El `sleep`
inyectado hace que las pruebas no duerman.

Log seguro: `logger.warning("El proveedor LLM respondió %s: %s", status, response.text[:200])`.
Nunca cabeceras, nunca cuerpo de petición, nunca la clave.

Sonda: `GET {base_url}/models`; 2xx ⇒ `ok` (si `LLM_MODEL` no aparece en la lista, `ok` con `reason`
legible); cualquier fallo ⇒ `unreachable` con motivo, sin excepción hacia arriba.

---

## Adaptador `anthropic`

```python
client = AsyncAnthropic(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
    timeout=settings.LLM_TIMEOUT_SECONDS,
    max_retries=settings.LLM_MAX_RETRIES,      # el SDK ya reintenta 408/409/429/≥500; no se duplica
    http_client=DefaultAsyncHttpxClient(transport=transport) if transport else None,
)
```

Constructor: `ImportError` del paquete ⇒ `LlmConfigInvalid`; `LLM_API_KEY` vacía ⇒ `LlmConfigInvalid`;
`LLM_BASE_URL` fuera de la allowlist ⇒ `LlmConfigInvalid`. Todo **antes** de cualquier petición.

| Camino | Llamada |
|---|---|
| Con esquema | `await client.messages.parse(model, max_tokens, system=…, messages=…, thinking={"type":"adaptive"}, output_format=Model)` → `response.parsed_output` |
| Texto libre | `await client.messages.create(model, max_tokens, system=…, messages=…, thinking={"type":"adaptive"})` → unión de bloques `type=="text"` |

El equivalente crudo del esquema es
`output_config={"format": {"type": "json_schema", "schema": {…, "required": [...], "additionalProperties": false}}}`;
el diseño usa el ayudante `parse` porque **es** la validación Pydantic local que exige B1.
Nunca se envía `temperature`/`top_p`/`top_k` (400 en Opus 5 / Fable 5 / 4.8 / 4.7, y `TypeError` en el
SDK 1.x), nunca `budget_tokens`, nunca prefill, nunca `fallbacks`/`betas`
(`LLM_ANTHROPIC_FALLBACKS=false`: un rechazo debe verse, no rescatarse en silencio).

| Señal | Resultado |
|---|---|
| `stop_reason == "refusal"` (HTTP 200) | `LlmContentFiltered`, motivo desde `stop_details.category`/`.explanation` |
| `stop_reason == "max_tokens"` | `LlmInvalidOutput` |
| `parsed_output is None` o `pydantic.ValidationError` | `LlmSchemaMismatch` |
| `AuthenticationError` / `PermissionDeniedError` | `LlmAuthError` |
| `NotFoundError` / `BadRequestError` | `LlmConfigInvalid` |
| `RateLimitError` | `LlmRateLimited` |
| `APITimeoutError` (**antes** de `APIConnectionError`, es subclase) | `LlmTimeout` |
| `APIConnectionError` | `LlmUnavailable` |
| `APIStatusError` restante (5xx, 529) | `LlmUnavailable` |

Uso: `usage.input_tokens`/`usage.output_tokens`, total = suma. Se registra `response._request_id`
(propiedad pública) para diagnóstico; la clave jamás. Sonda: `not_probed` con motivo
«sólo se valida la configuración; sondear consumiría cuota».

---

## Configuración

Bloque al **final** de `Settings` (tras `INTAKE_PULL_MAX_ITEMS`, `config.py:324`) para no colisionar
textualmente con el cambio 42, con el comentario justificativo que el archivo exige.

| Campo | Defecto | Nota |
|---|---|---|
| `LLM_PROVIDER: str` | `"fake"` | Espeja `EMAIL_BACKEND="console"`: la suite nunca toca la red |
| `LLM_BASE_URL: str` | `""` | Vacía ⇒ `LlmConfigInvalid` en el constructor |
| `LLM_MODEL: str` | `""` | Los identificadores no se infieren; los fija el operador |
| `LLM_API_KEY: str` | `""` | Sólo `anthropic` la exige |
| `LLM_TIMEOUT_SECONDS: float` | `60.0` | Convención `*_TIMEOUT_SECONDS` del repositorio |
| `LLM_MAX_TOKENS: int` | `1024` | Clasificaciones cortas |
| `LLM_MAX_RETRIES: int` | `2` | httpx propio / `max_retries` del SDK |
| `LLM_MAX_BACKOFF_SECONDS: float` | `30.0` | Techo, calco de `JIRA_MAX_BACKOFF_SECONDS` |
| `LLM_JSON_MODE: str` | `"json_object"` | D6 |
| `LLM_ANTHROPIC_FALLBACKS: bool` | `False` | Un rechazo debe verse |
| `LLM_BASE_URL_ALLOWLIST: list[str]` | `["http://localhost:11434/v1", "http://127.0.0.1:11434/v1", "http://host.docker.internal:11434/v1", "https://api.anthropic.com"]` | Forma de `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST` |

`env.example` (al final del bloque «Backend (FastAPI)»):

```dotenv
# Puerto LLM (change 48-puerto-llm). `fake` no toca la red y es el defecto.
LLM_PROVIDER=fake
# Ollama local: desde el host usa localhost; desde el contenedor, host.docker.internal.
# En Linux `host.docker.internal` no resuelve (el compose no declara extra_hosts):
# la sonda responderá reachability=unreachable con motivo legible.
# LLM_PROVIDER=openai_compatible
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=qwen3.5:9b-q4_K_M     # alternativas locales: gpt-oss:20b, qwen3.6:35b-a3b
# LLM_JSON_MODE=json_object       # llama.cpp: json_schema_llamacpp · LM Studio: json_schema_openai
# Nube (modo de excepción: saca contenido de la máquina):
# LLM_PROVIDER=anthropic
# LLM_BASE_URL=https://api.anthropic.com
# LLM_MODEL=claude-opus-5
# LLM_API_KEY=
```

`docker-compose.yml`, en `services.backend.environment`: `LLM_PROVIDER: "fake"` con un comentario que
remite a `env.example` para la activación local. Un `up` en limpio nunca falla por falta de runtime.

`requirements.txt`: una línea nueva, `anthropic==1.0.0`, precedida del comentario con los hechos
verificados de D5 (pydantic, Python, `httpx2` transitivo, import perezoso).

---

## Endpoint de salud

```
GET /api/v1/assistant/health?probe=false
```

- **`router.py`**: `APIRouter(prefix="/assistant", tags=["assistant"])`;
  `require_assistant_role = require_role(MemberRole.admin, MemberRole.manager)` como singleton de
  módulo (ruff B008, precedente `glpi_sync/router.py:24-26`); sobre literal
  `{"data": …, "message": "Estado del proveedor de IA."}`. Una línea en `main.py:190`.
- **`service.py`**: `AssistantHealthService.describe(*, probe: bool) -> AssistantHealthData`.
  Lee **toda** la configuración de `settings` (así el endpoint responde 200 incluso con el proveedor
  mal configurado) y consulta el puerto **sólo** para `probe()`.
- **`schemas.py`**: `AssistantHealthData(BaseModel)` con `provider`, `model`, `base_url_host`,
  `api_key_configured: bool`, `timeout_seconds`, `max_tokens`, `structured_output_mode`,
  `reachability: Reachability`, `reachability_reason: str | None`.

| Situación | `reachability` | `reachability_reason` |
|---|---|---|
| Sin `?probe=true` | `not_probed` | `None`, o el motivo si la configuración ya es inválida |
| Sonda ok | `ok` | `None`, o aviso de modelo no listado |
| Sonda falla o el puerto no se puede construir | `unreachable` | Motivo legible que **nombra el ajuste**, nunca el valor |

**Redacción de secretos** (frontera crítica): `base_url_host` se construye con
`parts.hostname` + `:{parts.port}`, **nunca** con `parts.netloc` — `netloc` incluye el `userinfo`, así
que una `LLM_BASE_URL` con `usuario:secreto@host` filtraría la credencial en un endpoint de salud.
`api_key_configured` es un `bool` derivado de `bool(settings.LLM_API_KEY.strip())`.

**Inyección para pruebas**: `AssistantHealthService(port_factory=None)` resuelve
`self._port_factory or get_llm_port` **dentro** de `describe()`, para que un `monkeypatch` del atributo
de módulo surta efecto (si se enlazara en `__init__` no lo haría).

---

## Flujo de datos — `complete()` con esquema

```
modules/assistant (o el 49)          app/ai                      Proveedor
        │                              │                            │
        │  LlmRequest(system, msgs,    │                            │
        │             output_schema)   │                            │
        ├─────────────────────────────▶│ get_llm_port(settings)     │
        │                              │  └─ dict _ADAPTERS[…]      │
        │                              │     (desconocido ⇒ 422)    │
        │                              │                            │
        │                              │ constructor: allowlist,    │
        │                              │ modelo, clave  ── falla ⇒ 422 (sin red)
        │                              │                            │
        │                              │ cuerpo por LLM_JSON_MODE   │
        │                              │ (o messages.parse)         │
        │                              ├───────────────────────────▶│
        │                              │◀───────────────────────────┤ 200 / 4xx / 5xx
        │                              │ mapa de fallos ⇒ excepción tipada
        │                              │ extracción tolerante        │
        │                              │ Model.model_validate(...)   │
        │                              │   falla ⇒ llm_schema_mismatch (parsed=None)
        │◀─────────────────────────────┤ LlmResponse(text, parsed, usage, …)
```

---

## Cambios de archivos

| Archivo | Acción | Descripción |
|---|---|---|
| `backend/app/ai/{__init__,ports,errors,registry}.py` | Crear | Núcleo neutro |
| `backend/app/ai/prompts/__init__.py` | Crear | `PROMPT_VERSION` |
| `backend/app/ai/adapters/{__init__,fake,openai_compatible,anthropic}.py` | Crear | Tres implementaciones |
| `backend/app/modules/assistant/{__init__,router,service,schemas}.py` | Crear | Endpoint de salud |
| `backend/app/config.py` (final de `Settings`) | Modificar | Bloque `LLM_*` comentado |
| `backend/app/main.py:190` | Modificar | Un `include_router` |
| `env.example`, `docker-compose.yml` | Modificar | Variables documentadas; `fake` fijado |
| `backend/requirements.txt` | Modificar | `anthropic==1.0.0` + comentario |
| `backend/tests/test_ai_port_contract.py` | Crear | Contrato único, tres adaptadores |
| `backend/tests/test_ai_adapter_openai_compatible.py` | Crear | `httpx.MockTransport` |
| `backend/tests/test_ai_adapter_anthropic.py` | Crear | `httpx2.MockTransport` vía `DefaultAsyncHttpxClient` |
| `backend/tests/test_ai_registry.py` | Crear | Selección, error controlado, import perezoso |
| `backend/tests/test_assistant_health_endpoint.py` | Crear | RBAC, redacción, sonda |

---

## Estrategia de pruebas (TDD estricto: rojo antes que código)

| Archivo | Pruebas en rojo (nombre → aserción decisiva) |
|---|---|
| `test_ai_port_contract.py` (fixture parametrizada `fake` / `openai_compatible` / `anthropic`, dobles herméticos) | `test_complete_returns_text_and_provider_metadata` → `finish_reason == "stop"`, `latency_ms >= 0`, `prompt_version` es eco de la petición · `test_parsed_is_none_when_no_schema_requested` → `parsed is None` · `test_parsed_is_a_validated_model_when_schema_requested` → `isinstance(parsed, TriageDecision)` · `test_schema_mismatch_never_returns_unvalidated_parsed` → `raises(LlmSchemaMismatch)`, `code == "llm_schema_mismatch"`, `status_code == 502` · `test_dtos_are_frozen` → `FrozenInstanceError` · `test_probe_never_generates_text` → el doble registra cero llamadas de generación |
| `test_ai_adapter_openai_compatible.py` (`Settings(**overrides)` + `httpx.MockTransport`, `sleep` inyectado) | `test_rejects_a_base_url_outside_the_allowlist_before_any_request` → el handler lanza `AssertionError` y **nunca** se ejecuta · `test_rejects_an_empty_model_before_any_request` · `test_system_travels_as_the_first_message_and_stream_is_false` · `test_json_mode_openai_sends_the_nested_envelope` / `_llamacpp_sends_the_schema_at_top_level` / `_json_object_sends_the_schema_as_a_prompt_hint` → forma exacta de `response_format`, `additionalProperties is False` · `test_parses_a_fenced_json_body` · `test_429_retries_then_raises_rate_limited` → sleeps registrados, cero espera real · `test_clamps_retry_after_to_max_backoff` → `Retry-After: 999` con techo 5.0 ⇒ `5.0` · `test_maps_500_401_404_timeout_connect_error` · `test_finish_reason_length_maps_to_invalid_output` · `test_finish_reason_content_filter_maps_to_content_filtered` · `test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` (`caplog`) · `test_probe_hits_models_and_reports_ok` / `test_probe_reports_unreachable_with_reason` |
| `test_ai_adapter_anthropic.py` (`DefaultAsyncHttpxClient(transport=httpx2.MockTransport(...))`; sin `skip`: el pin es requisito de la rebanada) | `test_system_is_top_level_and_temperature_is_never_sent` → `"temperature" not in body`, idem `top_p`/`top_k` · `test_always_sends_an_integer_max_tokens` · `test_sends_adaptive_thinking_without_budget_tokens` · `test_schema_request_carries_required_and_additional_properties_false` · `test_refusal_stop_reason_maps_to_content_filtered` → 200 con `stop_details` · `test_max_tokens_stop_reason_maps_to_invalid_output` · `test_typed_exceptions_map_to_the_port_taxonomy` (401/429/500/529/conexión/timeout, `APITimeoutError` antes que `APIConnectionError`) · `test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request` · `test_fallbacks_and_betas_are_never_requested` · `test_usage_maps_input_and_output_tokens` · `test_timeout_and_max_retries_come_from_settings` |
| `test_ai_registry.py` | `test_returns_the_fake_adapter_by_default` · `test_selects_the_adapter_named_by_llm_provider` · `test_unknown_provider_raises_llm_config_invalid_not_key_error` → `status_code == 422` y el valor **no** aparece en `detail` · `test_reads_the_setting_at_call_time_not_at_import` · `test_does_not_import_the_anthropic_package_for_other_providers` → `monkeypatch` de `builtins.__import__` que lanza ante `"anthropic"` (robusto aunque `sys.modules` esté contaminado), complementado con `"app.ai.adapters.anthropic" not in sys.modules` · `test_fake_adapter_is_a_process_singleton` |
| `test_assistant_health_endpoint.py` (`@skip_no_db`, `make_member`) | `test_admin_and_manager_get_200` · `test_member_and_viewer_get_403` → `code == "forbidden"` · `test_default_response_is_not_probed` · `test_body_never_contains_the_api_key_or_the_full_base_url` → aserción sobre `response.text` serializado · `test_base_url_userinfo_is_never_echoed` → `http://usuario:secreto@localhost:11434/v1` ⇒ `base_url_host == "localhost:11434"` y `"secreto" not in response.text` · `test_probe_true_reports_ok` / `test_probe_true_reports_unreachable_with_a_readable_reason` · `test_probe_never_generates_text` · `test_invalid_configuration_is_a_reason_not_a_500` |

Ninguna prueba toca la red. Línea base a no regresar: **1408 pasadas / 3 saltadas**.

---

## Threat Matrix

La matriz estándar (`references/threat-matrix.md`) cubre shell, git y automatización de PR; este cambio
no toca ninguna de esas fronteras.

| Frontera | Aplicabilidad |
|---|---|
| Rutas tipo documentación | N/A — el cambio no clasifica ni ejecuta archivos |
| Selección de repositorio git | N/A — no se invoca git |
| Estado del commit | N/A — sin automatización de VCS |
| Estado del push | N/A — sin automatización de VCS |
| Comandos de PR | N/A — sin automatización de PR |

La frontera real de este cambio es **egreso HTTP y secretos**, y sí es aplicable:

| Caso adversario | Comportamiento seguro | Prueba en rojo |
|---|---|---|
| `LLM_BASE_URL` apunta a un tercero (exfiltración) | Allowlist cerrada validada en el constructor; la petición nunca se construye | `test_rejects_a_base_url_outside_the_allowlist_before_any_request` (handler que lanza `AssertionError`) |
| La clave aparece en logs o en la respuesta HTTP | Sólo `api_key_configured: bool`; logs con status + 200 caracteres del cuerpo de respuesta | `test_error_log_...never_the_key_or_the_prompt`, `test_body_never_contains_the_api_key...` |
| `userinfo` en la URL base se filtra por `netloc` | `hostname` + `port` explícitos | `test_base_url_userinfo_is_never_echoed` |
| El proveedor induce control de flujo (bucle, reintento infinito) | Reintentos deterministas acotados por `LLM_MAX_RETRIES`/`LLM_MAX_BACKOFF_SECONDS`; sin reparación por modelo (D7) | `test_429_retries_then_raises_rate_limited`, `test_clamps_retry_after_to_max_backoff` |
| Salida no validada se presenta como buena | `parsed` sólo tras `model_validate`; truncado y filtrado son errores | `test_schema_mismatch_never_returns_unvalidated_parsed`, `test_finish_reason_length_maps_to_invalid_output` |
| El endpoint de salud gasta tokens | La sonda nunca genera texto | `test_probe_never_generates_text` |

---

## Rebanadas y carga de revisión

| # | Contenido | ≈ líneas | Verificación propia | Reversa |
|---|---|---|---|---|
| 1 | `ports`, `errors`, `fake`, `registry`, `prompts`, bloque `LLM_*` en `config.py`/`env.example`/`docker-compose.yml` | 350 | `test_ai_port_contract.py` (sólo `fake`) + `test_ai_registry.py` | Revertir commits; nada más lo importa |
| 2 | `adapters/openai_compatible.py` | 550 | `test_ai_adapter_openai_compatible.py` + contrato ampliado | Quitar el archivo y su entrada del dict |
| 3 | `adapters/anthropic.py` + `requirements.txt` | 500–600 | `test_ai_adapter_anthropic.py` + contrato ampliado | Quitar la línea del pin y el archivo (import perezoso) |
| 4 | `modules/assistant/` + `include_router` + runbook + specs | 400 | `test_assistant_health_endpoint.py` | Quitar el `include_router` |

Total estimado **≈1 700–1 900 líneas** (`additions + deletions`), ≈750–950 de pruebas. Por encima del
umbral de 400 y dentro del presupuesto de sesión de 2 000 ⇒ `auto-chain` con cadena de ramas. El
pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`)
lo emite `sdd-tasks`.

## Migración / despliegue

Sin migración Alembic: el esquema no cambia. El despliegue es una variable de entorno:
`LLM_PROVIDER=fake` (defecto) deja el sistema idéntico al de hoy. Activar `openai_compatible` o
`anthropic` es reiniciar con otra variable, y volver a `fake` es la reversa completa **sin desplegar
código**. Runbook manual de cierre: `GET /api/v1/assistant/health?probe=true` contra Ollama, desde el
host y desde el contenedor.

## Riesgos abiertos

| Riesgo | Mitigación en este diseño |
|---|---|
| El pin `anthropic==1.0.0` no resuelve en el entorno real (imagen, lockfile) | La rebanada 3 empieza instalando y corriendo la suite; si falla, la reversa es una línea y el adaptador cae a cliente httpx a mano, registrado como excepción |
| `thinking:{"type":"adaptive"}` devuelve 400 si el operador pinea un modelo anterior a 4.7 | Se mapea a `llm_config_invalid` 422, que nombra el ajuste; no se añade un setting nuevo fuera de lo decidido |
| El conjunto transitivo exacto de `anthropic==1.0.0` no está verificado más allá de `httpx2` | Se verifica al instalar en la rebanada 3 y se escribe en el comentario de `requirements.txt` |
| Esquemas anidados producen `$defs`/`$ref` que los runtimes locales ignoran | Se documenta la recomendación de esquemas planos para el 49 |

## Preguntas abiertas

- [ ] Ninguna que bloquee la implementación. Las cinco preguntas de producto de la propuesta siguen
      resueltas por supuesto y se ratifican o corrigen en el spec, no aquí.
