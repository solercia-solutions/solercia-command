# Proposal: 48 · Puerto LLM (`LlmPort`), adaptadores y `GET /assistant/health`

## Intent

**Problema de negocio.** El triage de correo y la evaluación de avance se hacen hoy a mano. La única costura preparada para automatizarlos, `ClassifierPort` (`backend/app/modules/intake/classifier.py:19-24`), sólo tiene una implementación por reglas y **no existe ninguna frontera hacia un modelo de lenguaje**: `backend/app/ai/` no existe. Sin esa frontera, los cambios 49 (clasificador), 50 (UI de triage) y 51 (borrador de cierre) tendrían que elegir proveedor, pegar HTTP y manejar fallos dentro de la lógica de negocio, y quedarían casados con el primer proveedor que funcione.

**Urgencia.** La decisión de plataforma es *local primero* (`docs/decisions/2026-08-23-solercia-platform-decisions.md`): el usuario ya tiene Ollama con modelos descargados y quiere poder cambiar a un proveedor en nube sin reescribir nada. Cada semana que el 49 espere es trabajo manual que no se automatiza; y si el 49 arranca sin puerto, la deuda se multiplica por tres cambios.

**Éxito.** Un backend que puede hablar con un modelo local o con Anthropic cambiando **una variable de entorno**, con salida estructurada validada localmente, errores tipados con el mismo idioma que el resto del repositorio, y un endpoint de salud que responde «¿está bien configurado y alcanzable?» sin gastar un solo token. Por defecto (`LLM_PROVIDER=fake`) el sistema se comporta exactamente como hoy y ninguna prueba toca la red.

## Scope

### In Scope

- Núcleo neutro en `backend/app/ai/`: `LlmPort` (Protocol) con `async complete(LlmRequest) -> LlmResponse`; `LlmMessage`/`LlmRequest`/`LlmResponse` como `@dataclass(frozen=True)` (idioma del repo: `integrations/dtos.py:1-5`).
- Taxonomía de errores en `app/ai/errors.py` como subclases de `AppException` con `code` estable: `llm_unavailable` 503, `llm_auth_error` 401, `llm_rate_limited` 503, `llm_timeout` 503, `llm_invalid_output` 502, `llm_schema_mismatch` 502, `llm_content_filtered` 422, `llm_config_invalid` 422.
- Tres adaptadores: `fake` (cero red), `openai_compatible` (Ollama/llama.cpp/LM Studio, httpx) y `anthropic` (SDK oficial, importado de forma perezosa).
- Registro `get_llm_port()` que resuelve **un** adaptador activo por `settings.LLM_PROVIDER` (calco de `email/sender.py:85-90`), con `AppException` para valor desconocido.
- Bloque `LLM_*` al final de `Settings` (`config.py:324`), espejado en `env.example` y `docker-compose.yml`, con lista blanca cerrada `LLM_BASE_URL_ALLOWLIST`.
- Módulo `backend/app/modules/assistant/` con `GET /api/v1/assistant/health` (router → service → puerto), RBAC `admin + manager`, sonda opcional `?probe=true` que no gasta tokens.
- Andamiaje `backend/app/ai/prompts/` con `PROMPT_VERSION` (el 49 lo persiste en `assistant_suggestions`).
- Pruebas de contrato, de adaptador y de RBAC. Runbook de validación manual contra Ollama.

### Out of Scope

- `LlmClassifier`, la cadena `RuleBasedClassifier → LlmClassifier` y cualquier cambio en `modules/intake/` — **cambio 49**.
- Tabla `assistant_suggestions`, casos de uso del asistente y UI de triage — cambios 49–51.
- Plantillas de prompt reales más allá del andamiaje y la constante de versión.
- Persistencia: cero modelos SQLAlchemy, cero repositorios, cero migraciones Alembic. `agents/rules/solercia-persistence.md` no aplica porque no nace ningún agregado.
- Streaming, *embeddings*, herramientas agénticas, caché de prompts y cualquier frontend.
- Humo en vivo automatizado contra Ollama (sin marcador nuevo en `pyproject.toml`): queda como paso manual del runbook.

## Capabilities

### New Capabilities

- `llm-port`: contrato del puerto, DTOs congelados, taxonomía de errores, selección de un único adaptador por entorno, salida estructurada con validación local obligatoria, reintentos acotados y guarda de URL base.
- `assistant-health`: endpoint de diagnóstico del proveedor activo con RBAC, sonda opt-in sin coste y respuesta que nunca revela la credencial ni la URL completa.

### Modified Capabilities

Ninguna. Ninguna capacidad existente cambia de requisitos: `intake-classifier` se toca en el 49, no aquí.

## Approach

### Piezas

| # | Pieza | Decisión |
|---|---|---|
| 1 | **Puerto** (`ports.py`) | `LlmRequest(system, messages, json_schema=None, temperature, max_tokens, timeout_seconds=None)`; `LlmResponse(text, parsed, usage, provider, model, prompt_version, latency_ms, finish_reason)`. `parsed` existe **sólo** si se pidió esquema *y* la validación local con Pydantic v2 pasó. Sin esa validación no hay `parsed`, hay `llm_schema_mismatch` |
| 2 | **Errores** (`errors.py`) | Subclases de `AppException`; el handler de `shared/exceptions.py:29-43` las convierte en `{detail, code, status}` sin trabajo adicional. Precedente literal: `integrations/adapters/jira/errors.py:78-136` |
| 3 | **Registro** (`registry.py`) | `dict[str, Callable[[], LlmPort]]` + lectura de `settings.LLM_PROVIDER` en tiempo de llamada. Un solo proveedor activo por proceso, que es el modelo real del problema |
| 4 | **`openai_compatible`** | httpx puro (`httpx==0.28.1`, ya fijado), transporte y `sleep` inyectables, reintentos deterministas acotados por `LLM_MAX_RETRIES`/`LLM_MAX_BACKOFF_SECONDS`/`Retry-After`, log de error con cuerpo truncado a 200 caracteres. Calco de `microsoft365/client.py:131-170` y `jira/client.py:195-228` |
| 5 | **`anthropic`** | SDK oficial `AsyncAnthropic`, importado sólo cuando `LLM_PROVIDER=anthropic` |
| 6 | **Configuración** | Bloque al final de `Settings` con el comentario justificativo que el archivo exige; `LLM_PROVIDER` por defecto `fake` (espeja `EMAIL_BACKEND="console"`) |
| 7 | **Salud** | `data` = `provider`, `model`, `base_url_host` (sólo `netloc`), `api_key_configured: bool`, `timeout_seconds`, `max_tokens`, `structured_output_mode`, `reachability ∈ {ok, unreachable, not_probed}`, `reachability_reason`. Sobre `{"data": …, "message": …}` construido en el router, como `glpi_sync/router.py:41` |

### Por qué el adaptador de Anthropic usa el SDK oficial

Esto **desvía** la nota «httpx, sin SDKs pesados» de la decisión previa (Engram #3686) y la desviación se ratifica aquí con su justificación:

| Argumento | Detalle |
|---|---|
| La unidad reemplazable es el adaptador, no el transporte | El core depende de `LlmPort`, no de httpx. Cambiar de proveedor sigue siendo cambiar una variable de entorno |
| El contrato cambió de forma material | Salida estructurada por `output_config.format`, `thinking` adaptativo sin `budget_tokens`, `stop_reason: "refusal"` con `stop_details` — un cliente a mano se desincroniza en silencio |
| No hay SDK equivalente del otro lado | Ollama/llama.cpp/LM Studio no tienen SDK oficial: ahí httpx a mano **es** la opción correcta, y se mantiene |
| El coste queda acotado | Dependencia **opcional en ejecución**: import perezoso dentro del adaptador. Con `LLM_PROVIDER=fake` u `openai_compatible` el SDK nunca se carga |

### Hechos del contrato de Anthropic que el adaptador honra

Fuente: skill oficial `claude-api` incluido en la sesión (`python/claude-api/README.md`, `tool-use.md`, `shared/error-codes.md`).

| Hecho | Consecuencia en el adaptador |
|---|---|
| `max_tokens` es obligatorio | El puerto no lo deja opcional; `LLM_MAX_TOKENS` da el valor por defecto |
| `system` es campo de nivel superior | `LlmRequest.system` no viaja como mensaje |
| Salida estructurada = `output_config={"format": {"type": "json_schema", "schema": …}}` (con `required` y `additionalProperties: false`), o el ayudante `client.messages.parse(...)` que recibe el modelo Pydantic y devuelve `response.parsed_output` | No se usa *prefill* (devuelve 400 en los modelos actuales) ni un campo `output_format` de nivel de petición |
| `thinking: {"type": "adaptive"}`; `budget_tokens` fue eliminado (400 en Opus 5 / Fable 5 / 4.8 / 4.7) | Nunca se envía `budget_tokens` |
| `temperature`, `top_p` y `top_k` fueron **eliminados** en esos mismos modelos: enviarlos devuelve 400 | El adaptador **no reenvía `temperature`**. El campo sigue en `LlmRequest` porque los runtimes locales sí lo honran; el diseño ratifica esta asimetría |
| `stop_reason` incluye `refusal` (HTTP 200, con `stop_details.category`/`.explanation`) y `max_tokens` | `refusal` → `llm_content_filtered`; `max_tokens` → error explícito, nunca un texto truncado presentado como válido |
| Excepciones tipadas (`AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `RateLimitError`, `APIStatusError`, `APIConnectionError`, `APITimeoutError`) y `.type` para granularidad fina | Mapeo directo a la taxonomía del puerto; nunca comparación de cadenas de error |
| El SDK ya reintenta conexión, 408, 409, 429 y ≥500 con backoff (`max_retries`, por defecto 2) y acepta `timeout` | Se configuran desde `LLM_MAX_RETRIES` y `LLM_TIMEOUT_SECONDS`; **no** se reimplementa backoff en este adaptador |
| `response._request_id` es público | Se registra para diagnóstico; la clave nunca |
| `anthropic` 1.x corre sobre **`httpx2`**, no sobre `httpx` | El idioma de prueba `httpx.MockTransport` del repo **no** sirve aquí: el diseño elige la técnica (transporte `httpx2` vía `DefaultAsyncHttpxClient`, o doble del cliente del SDK). Sea cual sea, ninguna prueba toca la red |
| `fallbacks` ante rechazo (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks: "default"`) | **Apagado** (`LLM_ANTHROPIC_FALLBACKS=false`): este producto sólo pide clasificaciones cortas; un rechazo debe verse, no rescatarse en silencio |
| Los identificadores de modelo no se infieren | `LLM_MODEL` lo fija el operador; ejemplo en `env.example`: `claude-opus-5`, **sin** sufijo de fecha |

### Configuración y activación

`LLM_PROVIDER=fake` por defecto en `docker-compose.yml`, para que un `up` en limpio nunca falle por falta de un runtime. La activación local se **documenta**, no se impone:

| Modo | Valores |
|---|---|
| Host (venv) | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen3.5:9b-q4_K_M` |
| Contenedor | idéntico, con `LLM_BASE_URL=http://host.docker.internal:11434/v1` |
| Nube | `LLM_PROVIDER=anthropic`, `LLM_BASE_URL=https://api.anthropic.com`, `LLM_MODEL=claude-opus-5`, `LLM_API_KEY=…` |

`LLM_BASE_URL_ALLOWLIST` contiene las cuatro formas y valida **en el constructor, antes de cualquier petición** (forma de `SOLERCIA_CONNECT_BASE_URL_ALLOWLIST`, `config.py:233-236`).

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `backend/app/ai/ports.py`, `errors.py`, `registry.py` | New | Núcleo neutro, sin FastAPI ni SQLAlchemy |
| `backend/app/ai/adapters/{fake,openai_compatible,anthropic}.py` | New | Tres implementaciones del puerto |
| `backend/app/ai/prompts/__init__.py` | New | Andamiaje + `PROMPT_VERSION` |
| `backend/app/modules/assistant/{__init__,router,service,schemas}.py` | New | `GET /api/v1/assistant/health` |
| `backend/app/config.py` (final de `Settings`, tras `INTAKE_*`) | Modified | Bloque `LLM_*` comentado |
| `backend/app/main.py` (bloque de `include_router`) | Modified | Una línea |
| `env.example`, `docker-compose.yml` | Modified | Variables documentadas; `LLM_PROVIDER=fake` |
| `backend/requirements.txt` | Modified | `anthropic==<pin verificado>` con comentario justificativo |
| `backend/tests/test_ai_*.py`, `test_assistant_health_endpoint.py` | New | Contrato, adaptadores, registro, RBAC |
| `openspec/specs/llm-port/`, `openspec/specs/assistant-health/` | New | Ver Capabilities |

**No se toca**: `backend/app/modules/intake/`, `backend/app/integrations/`, `db_init.py`, `app/maintenance/` ni `backend/scripts/` (cambio 42).

## Frontera de seguridad

| Regla | Cómo se cumple |
|---|---|
| Un `LLM_BASE_URL` mal puesto no puede exfiltrar contenido | Lista blanca cerrada validada en el constructor; una URL rechazada **nunca** llega al transporte (prueba con `AssertionError` en el handler, como `test_adapter_solercia_connect.py:86-100`) |
| La credencial nunca se registra ni se devuelve | El endpoint expone `api_key_configured: bool` y `base_url_host` (sólo `netloc`), jamás la clave ni la URL completa. Los logs de error llevan status + 200 caracteres del **cuerpo de respuesta**, nunca cabeceras ni cuerpo de petición |
| Contenido de buzón hacia terceros | El 48 **no envía contenido de buzón**: la sonda de salud no genera texto. La política de minimización para los prompts del 49 se decide allí; aquí sólo se deja el puerto y el aviso |
| El LLM no decide control de flujo | Reintentos deterministas en código o en el SDK, nunca sugeridos por el modelo (decisión de plataforma §3.4) |

## Rollback Plan

| Escenario | Reversa |
|---|---|
| Un adaptador falla o el proveedor se degrada | `LLM_PROVIDER=fake` + reinicio. Cero red, comportamiento idéntico al de hoy. **Reversible por variable de entorno, sin desplegar código** |
| El SDK de Anthropic causa conflicto de dependencias o crece la imagen | Quitar la línea de `requirements.txt` y el archivo `adapters/anthropic.py`; el resto no lo importa (import perezoso), así que no hay más que tocar |
| El endpoint expone algo indebido | Quitar la línea de `include_router` en `main.py`; el puerto sigue funcionando para el 49 |
| El código introduce regresiones | Revertir los commits de la rebanada afectada. **No hay migración Alembic que bajar**: el esquema no cambia |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| La salida estructurada no está garantizada en runtimes locales (llama.cpp ignora `json_schema` en silencio; Ollama no honra el sobre anidado de forma consistente) | Alta | Validación local con Pydantic obligatoria; `LLM_JSON_MODE ∈ {json_schema_openai, json_schema_llamacpp, json_object}`; `parsed` sólo existe si validó |
| El pin de `anthropic` choca con `pydantic==2.10.4` o duplica la pila HTTP (`httpx2` junto a `httpx==0.28.1`) | Media | **Compuerta**: verificar el pin en vivo contra PyPI antes de fijarlo, con el mismo rigor documentado en `requirements.txt:18-29`. Si no hay versión compatible, la rebanada 3 cae a un cliente httpx a mano y se registra la excepción |
| El idioma de prueba del repo (`httpx.MockTransport`) no aplica al SDK | Media | El diseño elige y documenta la técnica exacta; el criterio irrenunciable es que ninguna prueba toque la red |
| `host.docker.internal` no resuelve en Linux (el compose no declara `extra_hosts`) | Media | Se documenta; la sonda responde `reachability=unreachable` con motivo legible en vez de un error opaco |
| El singleton `settings` se congela en el import | Media | Leer `settings` en tiempo de llamada o recibir un `Settings` explícito, como en `test_adapter_solercia_connect.py:29-35` |
| Deriva de alcance hacia el 49 | Media | La sonda nunca genera texto; clasificador, sugerencias y casos de uso quedan fuera por escrito |
| Colisión textual con el cambio 42 en `config.py` / `docker-compose.yml` / `env.example` | Baja | El bloque `LLM_*` se inserta al final de `Settings` y al final de los bloques de entorno; el 42 ya está integrado en el tracker cuando el 48 llegue a `apply` |
| Modelos futuros de Anthropic vuelven a cambiar el contrato | Baja | Pin explícito del SDK y `stop_reason`/errores mapeados a la taxonomía propia, no propagados en crudo |

## Dependencies

- Verificación en vivo del pin de `anthropic` contra PyPI (compatibilidad con `pydantic==2.10.4`) antes de cerrar el diseño de la rebanada 3.
- Ninguna dependencia de otro cambio SDD. Este cambio **bloquea** al 49 (`clasificador-llm`) y, en cadena, al 50 y al 51.
- Para la validación manual del runbook: Ollama corriendo en el host con `qwen3.5:9b-q4_K_M` descargado (ya verificado en el entorno del usuario).

## Success Criteria

- [ ] TDD estricto: prueba en rojo antes del código en las cuatro rebanadas. `cd backend && pytest tests/ -v` en verde, sin regresión frente a la línea base **1408 pasadas / 3 saltadas**.
- [ ] Un mismo cuerpo de prueba de contrato pasa contra los **tres** adaptadores: `fake`, `openai_compatible` (con `httpx.MockTransport`) y `anthropic` (con la técnica de doble que fije el diseño). **Ninguna prueba toca la red.**
- [ ] `LLM_PROVIDER=fake` es el valor por defecto efectivo en `Settings`, `env.example` y `docker-compose.yml`; un `docker compose up` en limpio arranca sin ningún runtime de IA presente.
- [ ] Un valor desconocido de `LLM_PROVIDER` produce `llm_config_invalid` (422) al resolver el puerto, no un `KeyError`.
- [ ] Una `LLM_BASE_URL` fuera de `LLM_BASE_URL_ALLOWLIST` se rechaza en el constructor y **nunca alcanza el transporte**.
- [ ] Con esquema pedido y respuesta que no valida, el resultado es `llm_schema_mismatch` (502) y `parsed is None`; nunca un `parsed` sin validar.
- [ ] `GET /api/v1/assistant/health` devuelve 200 para `admin` y `manager`, y 403 para `member`/`viewer`.
- [ ] La respuesta del endpoint **no contiene** `LLM_API_KEY` ni la URL base completa en ningún campo (aserción explícita sobre el cuerpo serializado).
- [ ] `?probe=true` con `MockTransport` produce `reachability=ok`; un transporte que falla produce `reachability=unreachable` con motivo legible; sin el parámetro, `not_probed`. En ningún caso se genera texto ni se consumen tokens.
- [ ] Con `LLM_PROVIDER` distinto de `anthropic`, el paquete `anthropic` **no se importa** (prueba sobre `sys.modules`).
- [ ] Runbook manual ejecutado una vez contra Ollama: `GET /api/v1/assistant/health?probe=true` responde `reachability=ok` desde el host y desde el contenedor.

## Carga de revisión

Estimado **≈1 600–1 800 líneas** (`additions + deletions`), de las cuales ≈700–900 son pruebas. Muy por encima del umbral por defecto de 400 y por debajo del presupuesto de sesión de 2 000. Estrategia `auto-chain` con cadena de ramas; cada rebanada tiene inicio, fin, verificación y reversa propios:

| Rebanada | Contenido | ≈ líneas |
|---|---|---|
| 1 | `ports.py`, `errors.py`, `adapters/fake.py`, `registry.py`, bloque `LLM_*` en `config.py`/`env.example`/`docker-compose.yml`, andamiaje de prompts + pruebas de contrato y de registro | 350 |
| 2 | `adapters/openai_compatible.py` (reintentos, `LLM_JSON_MODE`, lista blanca, log seguro) + pruebas con `MockTransport` | 550 |
| 3 | `adapters/anthropic.py` + entrada verificada en `requirements.txt` + pruebas sin red | 500 |
| 4 | `modules/assistant/` + `include_router` + sonda `?probe=true` + pruebas de RBAC y de no filtración + runbook y specs | 400 |

El pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`) lo emite `sdd-tasks`.

## Proposal question round

Estas preguntas afinan reglas de producto antes de fijar el spec. **No reabren** lo ya decidido (A1+B1+C2+D2, `fake` por defecto, RBAC `admin+manager`, SDK oficial sólo para Anthropic, las cuatro rebanadas). Puedes responderlas, corregir el encuadre, saltarlas o pedir una segunda ronda. Como la ejecución es automática, cada una lleva el supuesto con el que se avanza si no hay respuesta.

1. **Salida de datos hacia un tercero.** Activar `LLM_PROVIDER=anthropic` significa que, a partir del 49, contenido de buzón institucional saldría de la máquina. ¿Debe quedar escrito en la spec que Anthropic es un modo de excepción que requiere habilitación explícita del operador, o es un modo de primera clase desde el inicio? *Supuesto: modo de excepción; local primero, y la política de minimización de datos del prompt se define en el 49.*
2. **Comportamiento del producto cuando el proveedor está caído.** En el 49, si el LLM no responde, ¿el usuario debe ver que la sugerencia automática no estuvo disponible, o el sistema degrada en silencio a las reglas actuales? *Supuesto: degradación silenciosa a reglas; la visibilidad del estado vive sólo en `/assistant/health`.*
3. **Tope de gasto.** ¿Hace falta un límite de consumo (tokens por día, alerta de coste) como requisito del producto, o `LLM_MAX_TOKENS` por llamada es suficiente por ahora? *Supuesto: suficiente; el 48 no hace llamadas reales y un tope de consumo sería un requisito del 49 en adelante.*
4. **Trazabilidad de lo que se le pidió al modelo.** ¿El negocio necesita poder auditar prompt y respuesta de cada sugerencia, o basta con `provider`/`model`/`prompt_version`? *Supuesto: basta con la tripleta; el 48 no persiste nada y el 49 decide qué guarda `assistant_suggestions`.*
5. **Compromiso de calidad del modelo local.** `qwen3.5:9b-q4_K_M` se documenta como ejemplo. ¿Existe una expectativa explícita de latencia o de acierto para clasificar correo que deba quedar en la spec como criterio de aceptación del 49? *Supuesto: no; el 48 sólo garantiza la frontera, y la calidad se mide en el 49 con datos reales.*
