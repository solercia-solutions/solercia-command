# Tasks: 48 · Puerto LLM (`LlmPort`), adaptadores y `GET /assistant/health`

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈1 700–1 900 (`additions + deletions`), ≈750–950 de pruebas, repartidas en 4 rebanadas |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Rebanada 1 → 2 → 3 → 4 (feature-branch-chain, cada una sobre la anterior) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

| Rebanada | Contenido | ≈ líneas | Presupuesto recomendado (×1,2) | Intentos máx. |
|---|---|---|---|---|
| 1 · núcleo | `ports.py`, `errors.py`, `adapters/fake.py`, `registry.py` (solo `fake`), `prompts/__init__.py`, bloque `LLM_*` en `config.py`/`env.example`/`docker-compose.yml` + `test_ai_port_contract.py` + `test_ai_registry.py` | 350 | 400 | 2 |
| 2 · openai_compatible | `adapters/openai_compatible.py` (reintentos, `LLM_JSON_MODE`, allowlist, log seguro) + `test_ai_adapter_openai_compatible.py` + contrato ampliado | 550 | 700 | 2 |
| 3 · anthropic | `adapters/anthropic.py` + entrada verificada en `requirements.txt` + `test_ai_adapter_anthropic.py` + contrato ampliado | 500–600 | 700 | 2 |
| 4 · assistant | `modules/assistant/` + `include_router` + sonda `?probe=true` + `test_assistant_health_endpoint.py` + README | 400 | 500 | 2 |

Cada presupuesto es por rebanada (una revisión a la vez), no acumulativo. Ningún commit de los cambios `42-purga-datos-demo` ni `43-tareas-origen-externo` debe caer en estas ramas.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Núcleo neutro con `fake` operativo y configuración `LLM_*` por defecto | PR 1 (base: tracker `feat/48-puerto-llm`) | `cd backend && pytest tests/test_ai_port_contract.py tests/test_ai_registry.py -v` | N/A — `fake` no toca red; sin runtime externo necesario | Revertir commits de `backend/app/ai/{ports,errors,registry,adapters/fake}.py`, bloque `LLM_*`; nada más lo importa aún |
| 2 | Adaptador `openai_compatible` con guarda de allowlist y reintentos deterministas | PR 2 (base: rama de PR 1) | `cd backend && pytest tests/test_ai_adapter_openai_compatible.py -v` | N/A en la suite (`httpx.MockTransport`); runbook manual en Fase 5 usa Ollama real | Quitar `adapters/openai_compatible.py` y su entrada en `_ADAPTERS`; `fake` sigue intacto |
| 3 | Adaptador `anthropic` sobre el SDK oficial, import perezoso | PR 3 (base: rama de PR 2) | `cd backend && pytest tests/test_ai_adapter_anthropic.py -v` | N/A en la suite (`httpx2.MockTransport`); sin llamada real a Anthropic | Quitar la línea de `requirements.txt` y `adapters/anthropic.py` (import perezoso: nada más lo importa) |
| 4 | `GET /assistant/health` con RBAC, sonda opt-in y redacción de secretos | PR 4 (base: rama de PR 3) | `cd backend && pytest tests/test_assistant_health_endpoint.py -v` | `GET /api/v1/assistant/health?probe=true` manual contra Ollama (Fase 5, fuera de la suite) | Quitar el `include_router` de `main.py`; el puerto sigue disponible para el cambio 49 |

## Fase 0: Verificación previa (gate)

- [x] 0.1 Confirmar en disco que `backend/app/ai/` no existe todavía (glob). Confirmado antes de crear el paquete en esta rebanada.
- [x] 0.2 Confirmar en disco que el bloque `INTAKE_*` de `Settings` termina en `config.py:324` y que ningún otro cambio en curso insertó ya algo después de esa línea. Confirmado: `INTAKE_PULL_MAX_ITEMS` en la línea 324, `config.py` con 334 líneas totales antes de editar; el bloque `LLM_*` se insertó justo después.
- [x] 0.3 Confirmar en disco que `main.py:190` sigue siendo el punto de inserción del bloque `include_router` y que los cambios `42`/`43` no lo tocaron desde el commit `a9b9e00`. Confirmado: `app.include_router(intake_router, prefix=API_PREFIX)` en la línea 190; `git log a9b9e00..HEAD -- backend/app/main.py` sin resultados (nadie lo tocó). Punto de inserción reservado para la rebanada 4.
- [x] 0.4 Confirmar en disco que `env.example` (bloque `SEED_DEMO_DATA`, líneas 17-21) y `docker-compose.yml` (líneas 42-44) siguen intactos; el bloque `LLM_*` se inserta después, sin pisarlos. Confirmado y respetado.
- [x] 0.5 Confirmar en disco que `dependencies.py:189-203` (`require_role`) y el patrón `require_role(MemberRole.admin, MemberRole.manager)` de `glpi_sync/router.py:24-26,41` siguen vigentes como precedente literal para `assistant/router.py`. Fuera del alcance de código de esta rebanada (Fase 4); precedente verificado como referencia para más adelante.
- [x] 0.6 Confirmar explícitamente que `agents/rules/solercia-persistence.md` NO aplica: aunque `backend/app/modules/assistant/service.py` coincide por patrón de ruta (`*service*.py`), el cambio no crea repositorios, transacciones ni migraciones — `AssistantHealthService.describe()` solo lee `settings` y consulta `LlmPort`, sin SQLAlchemy. Se deja constancia; no se sigue el checklist de persistencia. Confirmado; `backend/app/ai/` de esta rebanada tampoco crea modelos SQLAlchemy ni migraciones.
- [x] 0.7 Registrar la línea base de pruebas del commit `fc97125` (2026-08-26): `cd backend && pytest tests/ -v` con `TEST_DATABASE_URL` apuntando a `solercia_test` en `127.0.0.1:5434` → **1411 pasadas / 3 fallidas preexistentes** en `test_adapter_microsoft365.py`. Confirmar que la variable sigue configurada así antes de fijar esta cifra como referencia. Línea base real medida en el HEAD de esta rebanada (`03acf2f`, previa a los cambios): **1415 pasadas / 3 fallidas preexistentes** (la cifra difiere de 1411 por commits posteriores del tracker ya integrados); usada como referencia de no regresión.
- [x] 0.8 Confirmar en disco que `backend/tests/test_ai_*.py` y `test_assistant_health_endpoint.py` no existen todavía (archivos nuevos de este cambio). Confirmado antes de crear `test_ai_port_contract.py`/`test_ai_registry.py`.

## Fase 1: Núcleo — puerto, errores, `fake`, registro y configuración [Rebanada 1]

> Spec `llm-port`: Requirement «Contrato del puerto y DTOs congelados» (R1), «Selección del adaptador activo por entorno» (R2), «Adaptador fake sin red» (R3), escenario de aislamiento de `anthropic` de R5, «Configuración LLM_* con valores por defecto seguros» (R8). Design: D1-D4, D6 (default), estructura de módulos.

- [x] 1.1 RED — crear `backend/tests/test_ai_port_contract.py` con un modelo Pydantic de prueba `TriageDecision` (esquema plano) y fixture del adaptador `fake`; `test_complete_returns_text_and_provider_metadata` (llm-port R1 escenario 1: `text`/`usage`/`provider`/`model`/`prompt_version`/`latency_ms >= 0`/`finish_reason == "stop"`).
- [x] 1.2 RED — `test_dtos_are_frozen` (llm-port R1 escenario 2: `FrozenInstanceError` al reasignar un campo de `LlmRequest`).
- [x] 1.3 RED — `test_parsed_is_none_when_no_schema_requested` y `test_parsed_is_a_validated_model_when_schema_requested` (llm-port R3 escenario 1: `isinstance(parsed, TriageDecision)`).
- [x] 1.4 RED — `test_schema_mismatch_never_returns_unvalidated_parsed` (llm-port R3 escenario 2: `raises(LlmSchemaMismatch)`, `code == "llm_schema_mismatch"`, `status_code == 502`).
- [x] 1.5 RED — `test_probe_never_generates_text` (frontera de seguridad: el doble de generación registra cero llamadas al invocar `probe()`).
- [x] 1.6 RED — crear `backend/tests/test_ai_registry.py`: `test_returns_the_fake_adapter_by_default` (llm-port R2 escenario 1), `test_selects_the_adapter_named_by_llm_provider`, `test_unknown_provider_raises_llm_config_invalid_not_key_error` (R2 escenario 2: `status_code == 422`, el valor NO aparece en `detail`), `test_reads_the_setting_at_call_time_not_at_import` (R2 escenario 3), `test_fake_adapter_is_a_process_singleton`. Desviación declarada: el escenario 3 de R2 en la spec usa `openai_compatible` como valor alterno, aún no registrado en esta rebanada; la prueba prueba la lectura en tiempo de llamada con un valor no registrado (que dispara `LlmConfigInvalid`) y luego con `"fake"`, doble flip que ningún valor cacheado al importar podría observar.
- [x] 1.7 RED — en el mismo archivo: `test_does_not_import_the_anthropic_package_for_other_providers` (llm-port R5 escenario «Aislamiento de dependencia»: `monkeypatch` de `builtins.__import__` ante `"anthropic"` + `"app.ai.adapters.anthropic" not in sys.modules`).
- [x] 1.8 RED — `test_settings_llm_defaults_are_safe` (llm-port R8 escenario 1: `LLM_PROVIDER == "fake"`, `LLM_MAX_RETRIES == 2`, `LLM_ANTHROPIC_FALLBACKS is False`).
- [x] 1.9 RED — `test_docker_compose_backend_environment_pins_llm_provider_fake` (llm-port R8 escenario 2: parsear `docker-compose.yml` y afirmar `services.backend.environment.LLM_PROVIDER == "fake"`). Desviación declarada: sin `PyYAML` en `requirements.txt` (fuera de alcance de esta rebanada), la prueba lee el bloque `backend:`/`frontend:` como texto acotado en vez de parsear YAML.
- [x] 1.10 GREEN — crear `backend/app/ai/__init__.py` (vacío con docstring, sin importar submódulos) y `backend/app/ai/ports.py`: `Role`/`FinishReason`/`Reachability` (`Literal`), `LlmMessage`/`LlmUsage`/`LlmRequest`/`LlmResponse`/`LlmProbe` como `@dataclass(frozen=True)`, `LlmPort(Protocol)` con `complete()` y `probe()`.
- [x] 1.11 GREEN — crear `backend/app/ai/errors.py`: ocho subclases de `AppException` (`LlmUnavailable` 503, `LlmAuthError` 401, `LlmRateLimited` 503, `LlmTimeout` 503, `LlmInvalidOutput` 502, `LlmSchemaMismatch` 502, `LlmContentFiltered` 422, `LlmConfigInvalid` 422), sin interpolar nunca clave ni URL.
- [x] 1.12 GREEN — crear `backend/app/ai/adapters/__init__.py` (vacío) y `backend/app/ai/adapters/fake.py`: singleton de módulo, cero red, estado inspeccionable, valida `output_schema` con `model_validate` si se pidió.
- [x] 1.13 GREEN — crear `backend/app/ai/registry.py`: `_ADAPTERS` con solo `"fake"` (las claves `openai_compatible`/`anthropic` se agregan en las rebanadas 2 y 3), `get_llm_port()` leyendo `settings.LLM_PROVIDER` en tiempo de llamada, `LlmConfigInvalid` para valor desconocido.
- [x] 1.14 GREEN — agregar el bloque `LLM_*` al final de `Settings` (`backend/app/config.py`, tras `INTAKE_PULL_MAX_ITEMS`): `LLM_PROVIDER="fake"`, `LLM_BASE_URL=""`, `LLM_MODEL=""`, `LLM_API_KEY=""`, `LLM_TIMEOUT_SECONDS=60.0`, `LLM_MAX_TOKENS=1024`, `LLM_MAX_RETRIES=2`, `LLM_MAX_BACKOFF_SECONDS=30.0`, `LLM_JSON_MODE="json_object"`, `LLM_ANTHROPIC_FALLBACKS=False`, `LLM_BASE_URL_ALLOWLIST=[...]`, con el comentario justificativo que el archivo exige.
- [x] 1.15 GREEN — crear `backend/app/ai/prompts/__init__.py`: `PROMPT_VERSION: Final[str] = "v1"` + regla de versionado en docstring.
- [x] 1.16 GREEN — `env.example`: agregar el bloque `LLM_*` comentado después del bloque `SEED_DEMO_DATA`, sección «Backend (FastAPI)».
- [x] 1.17 GREEN — `docker-compose.yml`: agregar `LLM_PROVIDER: "fake"` al bloque `services.backend.environment`, con comentario que remite a `env.example` para la activación local.
- [x] 1.18 Verificar en verde: `cd backend && pytest tests/test_ai_port_contract.py tests/test_ai_registry.py -v`. 14/14 pasadas; suite completa 1429 pasadas / 3 fallidas preexistentes (línea base 1415 + 14 nuevas).

## Fase 2: Adaptador `openai_compatible` [Rebanada 2]

> Spec `llm-port`: «Adaptador openai_compatible» (R4), «Guarda de destino por allowlist» (R6), «Protección de secretos y datos en logs y errores» (R7). Design: sección del adaptador, D6, D7.

- [x] 2.1 RED — crear `backend/tests/test_ai_adapter_openai_compatible.py` (`Settings(**overrides)` + `httpx.MockTransport` + `sleep` inyectado); `test_rejects_a_base_url_outside_the_allowlist_before_any_request` (llm-port R6 escenario 1: el handler lanza `AssertionError`, nunca se ejecuta) y `test_base_url_within_the_allowlist_reaches_the_injected_transport` (R6 escenario 2). Confirmado en rojo: `ModuleNotFoundError: app.ai.adapters.openai_compatible`.
- [x] 2.2 RED — `test_rejects_an_empty_model_before_any_request`.
- [x] 2.3 RED — `test_system_travels_as_the_first_message_and_stream_is_false`.
- [x] 2.4 RED — `test_json_mode_openai_sends_the_nested_envelope`, `test_json_mode_llamacpp_sends_the_schema_at_top_level` (llm-port R4 escenario 1), `test_json_mode_json_object_sends_the_schema_as_a_prompt_hint`.
- [x] 2.5 RED — `test_parses_a_fenced_json_body`.
- [x] 2.6 RED — `test_429_retries_then_raises_rate_limited` (llm-port R4 escenario 2) y `test_clamps_retry_after_to_max_backoff`.
- [x] 2.7 RED — `test_maps_500_401_404_timeout_connect_error` (llm-port R4 escenario 3, camino timeout).
- [x] 2.8 RED — `test_finish_reason_length_maps_to_invalid_output` (con `output_schema` pedido) y `test_max_tokens_without_schema_returns_length` (sin esquema: `finish_reason == "length"`, `parsed is None`, sin excepción).
- [x] 2.9 RED — `test_finish_reason_content_filter_maps_to_content_filtered`.
- [x] 2.10 RED — `test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` (llm-port R7 escenarios 1 y 2, vía `caplog`).
- [x] 2.11 RED — `test_probe_hits_models_and_reports_ok` y `test_probe_reports_unreachable_with_reason`.
- [x] 2.12 GREEN — crear `backend/app/ai/adapters/openai_compatible.py`: constructor con `transport`/`sleep`/`settings` inyectables, validación de allowlist y modelo antes de cualquier petición, cuerpo por `LLM_JSON_MODE`, mapa de fallos, backoff con techo, log seguro, `probe()` contra `/models`. 17/17 pruebas en verde.
- [x] 2.13 GREEN — registrar `"openai_compatible"` en `_ADAPTERS` (`backend/app/ai/registry.py`).
- [x] 2.14 GREEN — extender `test_ai_port_contract.py`: parametrizar la fixture también con `openai_compatible` (doble hermético vía `MockTransport`), confirmando que el mismo cuerpo de prueba pasa contra los dos adaptadores.
- [x] 2.15 Verificar en verde: `cd backend && pytest tests/test_ai_adapter_openai_compatible.py tests/test_ai_port_contract.py tests/test_ai_registry.py -v`. 36/36 pasadas.

## Fase 3: Adaptador `anthropic` [Rebanada 3]

> Spec `llm-port`: «Adaptador anthropic sobre el SDK oficial» (R5). Design: D5, sección del adaptador `anthropic`.

- [x] 3.0 [MANUAL — orquestador] Compuerta de inicio: reverificado en vivo contra PyPI por el orquestador (2026-08-26): última `anthropic` es `1.0.0`; `Requires-Dist` exige `pydantic>=1.9.0,<3` (satisfecho por `pydantic==2.10.4`), `httpx2>=2.0.0,<3` (paquete separado de `httpx==0.28.1`), `Requires-Python>=3.10`. `pip install --dry-run anthropic==1.0.0` sin conflictos. Instalado en `backend/.venv` antes de escribir cualquier prueba (`anthropic==1.0.0`, `httpx2==2.12.0`, confirmado con `python -c "import anthropic, httpx2; print(...)"`). Resolvió limpio: no aplica la reversa de cliente httpx a mano.
- [x] 3.1 RED/GREEN — creado `backend/tests/test_ai_adapter_anthropic.py` (sin `skip`), fixture `httpx2.MockTransport(handler)` inyectado en `DefaultAsyncHttpxClient`; `test_system_is_top_level_and_temperature_is_never_sent`. **Desviación de proceso declarada**: el comportamiento exacto del SDK 1.0.0 (firma de `messages.create`/`.parse`, jerarquía de excepciones, forma de `output_config`, `stop_details`) se verificó primero de forma empírica contra el SDK instalado (scripts puntuales con `httpx2.MockTransport`, sin red real) antes de escribir la prueba y el adaptador en la misma pasada, en vez de confirmar cada prueba en rojo por separado contra un adaptador todavía inexistente — la evidencia empírica reemplaza el rojo literal por prueba individual; el archivo completo se confirmó en verde (17/17) antes de continuar.
- [x] 3.2 `test_always_sends_an_integer_max_tokens` (llm-port R5 escenario 5) — verde.
- [x] 3.3 `test_sends_adaptive_thinking_without_budget_tokens` — verde.
- [x] 3.4 `test_schema_request_carries_required_and_additional_properties_false` — verde.
- [x] 3.5 `test_refusal_stop_reason_maps_to_content_filtered` (HTTP 200 con `stop_details`) — verde.
- [x] 3.6 `test_max_tokens_stop_reason_maps_to_invalid_output` y `test_max_tokens_without_schema_returns_length` — verde.
- [x] 3.7 `test_typed_exceptions_map_to_the_port_taxonomy` (401/429/500/529/conexión/timeout, parametrizada; `APITimeoutError` antes que `APIConnectionError` verificado con `isinstance` empírico: `APITimeoutError` SÍ es subclase de `APIConnectionError` en 1.0.0) — verde.
- [x] 3.8 `test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request` (llm-port R5 escenario 4) — verde.
- [x] 3.9 `test_fallbacks_and_betas_are_never_requested`, `test_usage_maps_input_and_output_tokens`, `test_timeout_and_max_retries_come_from_settings` — verde.
- [x] 3.10 GREEN — creado `backend/app/ai/adapters/anthropic.py`: `_build_client()` con `import anthropic` perezoso dentro de la función, `AsyncAnthropic(http_client=DefaultAsyncHttpxClient(transport=...))` cuando se inyecta transporte. **Desviación declarada**: usa `client.messages.create(output_config={"format": {"type": "json_schema", "schema": ...}})` en vez de `messages.parse(output_format=...)` para el camino con esquema — verificado empíricamente que `messages.parse()` ejecuta `TypeAdapter(...).validate_json(text)` de forma interna y lanza `pydantic_core.ValidationError` ANTES de que el código llamador pueda inspeccionar `response.stop_reason`, lo que hace imposible distinguir `stop_reason="max_tokens"` (⇒ `llm_invalid_output`) de un incumplimiento genuino de esquema (⇒ `llm_schema_mismatch`) como exige la tabla de mapeo. `spec.md` R5 permite explícitamente ambos caminos ("DEBE usar `output_config.format` **o** `messages.parse(...)`"); se usa el primero con validación local propia (`schema.model_validate_json(text)`) tras comprobar `stop_reason`, que sí preserva el orden exigido. `probe()` no construye cliente ni importa el SDK (más perezoso aún que el snippet de `design.md`, sin romper ninguna prueba). Mapa de `stop_reason`/excepciones y `probe() → not_probed` sin red, según diseño.
- [x] 3.11 GREEN — registrado `"anthropic"` en `_ADAPTERS` vía `_build_anthropic`, que hace `importlib.import_module("app.ai.adapters.anthropic")` dentro de la función.
- [x] 3.12 GREEN — agregado `anthropic==1.0.0` a `backend/requirements.txt` con el comentario justificativo (pydantic, Python, `httpx2` transitivo, import perezoso, extras no instalados — hechos de la compuerta 3.0).
- [x] 3.13 GREEN — extendido `test_ai_port_contract.py`: fixture `fake` parametrizada también con `"anthropic"` (`_AnthropicDouble`, doble hermético vía `httpx2.MockTransport`); el mismo cuerpo de prueba pasa contra los tres adaptadores (12/12 parametrizadas × 3 = verde). Se agregó además una fixture `autouse`/`module` en este archivo y en `test_ai_adapter_anthropic.py` que limpia `sys.modules` de `anthropic`/`app.ai.adapters.anthropic` al terminar cada módulo: sin ella, el import perezoso real del SDK (disparado por `.complete()`) queda cacheado en `sys.modules` para el resto de la sesión de pytest y rompe el escenario de aislamiento de `test_ai_registry.py` cuando los tres archivos corren juntos en el orden dado por la verificación — confirmado con la corrida focalizada completa (41/41 verde, incluida `test_does_not_import_the_anthropic_package_for_other_providers`).
- [x] 3.14 GREEN — `mypy app/ai` (con caché limpia, `--no-incremental`, y una prueba aislada de `import anthropic` a nivel de módulo) NO reporta el módulo `anthropic` sin *stubs* pese a no traer `py.typed`: mypy 2.2.0, ejecutado con el intérprete del venv, resuelve tipos directamente desde el código fuente instalado (`type[AsyncAnthropic]` inferido correctamente). Condición «si mypy reporta…» no se cumple; no se toca `backend/pyproject.toml`.
- [x] 3.15 Verificado en verde: `cd backend && pytest tests/test_ai_adapter_anthropic.py tests/test_ai_port_contract.py tests/test_ai_registry.py -v` → **41/41 pasadas** (17 + 21 + 8; el archivo de contrato pasó de 15 a 21 pruebas contadas individualmente por la parametrización con 3 adaptadores).

## Fase 4: Módulo `assistant` y `GET /assistant/health` [Rebanada 4]

> Spec `assistant-health`: R1-R4 completos. Design: sección «Endpoint de salud».

- [x] 4.1 RED — creado `backend/tests/test_assistant_health_endpoint.py` (`@skip_no_db`, `make_member`): `test_admin_and_manager_get_200` (parametrizado admin/manager) y `test_member_and_viewer_get_403` (`code == "forbidden"`). Rojo confirmado: `ModuleNotFoundError: app.modules.assistant`.
- [x] 4.2 RED/GREEN — `test_default_response_is_not_probed` (R2: `base_url_host == "localhost:11434"`, `api_key_configured` booleano, `reachability == "not_probed"`).
- [x] 4.3 RED/GREEN — `test_body_never_contains_the_api_key_or_the_full_base_url` (parametrizada `probe` false/true) y `test_base_url_userinfo_is_never_echoed`.
- [x] 4.4 RED/GREEN — `test_base_url_host_without_port_has_no_none_suffix` (`"api.anthropic.com"`, nunca `":None"`).
- [x] 4.5 RED/GREEN — `test_probe_true_reports_ok` y `test_probe_true_reports_unreachable_with_a_readable_reason` (nunca 500).
- [x] 4.6 RED/GREEN — `test_probe_true_anthropic_never_probes` (guarda sobre `AnthropicAdapter._build_client`: si se llamara, produciría 500 vía el handler catch-all) y `test_probe_true_fake_reports_ok_and_never_generates_text`.
- [x] 4.7 RED/GREEN — `test_invalid_configuration_is_a_reason_not_a_500` (`LLM_MODEL=""` ⇒ `LlmConfigInvalid` en el constructor, capturado como `unreachable` con motivo, nunca 500). `test_probe_never_generates_text` se fusionó en 4.6 (`fake_adapter.calls` no crece).
- [x] 4.8 GREEN — creados `backend/app/modules/assistant/__init__.py`, `schemas.py` (`AssistantHealthData`) y `service.py` (`AssistantHealthService.describe(*, probe: bool)`; `_base_url_host()` con `hostname`/`port` explícitos vía `urlsplit`, nunca `netloc`; `get_llm_port` resuelto dentro de `describe()` — `monkeypatch` del atributo de módulo en `app.modules.assistant.service` surte efecto).
- [x] 4.9 GREEN — creado `backend/app/modules/assistant/router.py`: `APIRouter(prefix="/assistant", tags=["assistant"])`, `require_assistant_role = require_role(MemberRole.admin, MemberRole.manager)` singleton de módulo, sobre `{"data": …, "message": "Estado del proveedor de IA."}`.
- [x] 4.10 GREEN — `backend/app/main.py`: agregado `app.include_router(assistant_router, prefix=API_PREFIX)` tras `intake_router` (línea 190 original) + import alfabético entre `assets`/`attachments`.
- [x] 4.11 Verificado en verde: `cd backend && pytest tests/test_assistant_health_endpoint.py -v` → 14/14 pasadas. Desviación declarada: `test_all_modules_are_classified` (`tests/test_cross_tenant_isolation.py`, meta-test preexistente del cambio 25) rompió al agregar el paquete `app/modules/assistant/` sin clasificar; se agregó `"assistant"` a `INFRA_NO_READ` con comentario justificativo (sin superficie de lectura cross-tenant: config global por proceso, RBAC-only) — necesario para no regresar la suite completa (Fase 6.1).
- [x] 4.12 Documentado `backend/README.md`: bloque `LLM_*` en «Variables de entorno», fila `GET /api/v1/assistant/health` en «Endpoints (v1)», y sección nueva «Activación del proveedor LLM local» con el runbook host/contenedor (Ollama) y el `curl` de sonda manual.

## Fase 5: Validación manual opcional contra Ollama [MANUAL — orquestador, fuera de la suite]

- [x] 5.1 [MANUAL, opcional] Levantar Ollama local con `qwen3.5:9b-q4_K_M` descargado; exportar `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://localhost:11434/v1` (host) o `http://host.docker.internal:11434/v1` (contenedor), `LLM_MODEL=qwen3.5:9b-q4_K_M`. **Hecho (orquestador, 2026-08-26)**: `ollama serve` levantado temporalmente (no estaba corriendo; se apagó al terminar); modelos disponibles `qwen3.5:9b-q4_K_M`, `glm-ocr`, `gemma4`, `qwen3.6:35b-a3b`, `gemma3:1b`.
- [x] 5.2 [MANUAL, opcional] `GET /api/v1/assistant/health?probe=true` desde el host y desde el contenedor; confirmar `reachability == "ok"` en ambos, o `unreachable` con motivo legible si `host.docker.internal` no resuelve (Linux). **Hecho**: desde el host, `AssistantHealthService.describe(probe=True)` con el adaptador real → `provider=openai_compatible`, `model=qwen3.5:9b-q4_K_M`, `base_url_host=localhost:11434`, `api_key_configured=False`, `reachability=ok`; una completación real (`max_tokens=32`) devolvió `finish_reason="length"`, `usage 30/32/62`, `latency 5.2 s` y texto vacío — contrato respetado (sin esquema, `length` es respuesta válida) y hallazgo para el 49: los modelos locales con razonamiento gastan el presupuesto en «pensamiento» (subir `max_tokens` o desactivar *think*). Desde el contenedor (`gestion_proyectos-backend-1`, sin reconstruir la imagen con el 48), `http://host.docker.internal:11434/v1/models` responde con los mismos modelos: la ruta contenedor→host resuelve.
- [x] 5.3 [MANUAL, opcional] No agregar marcador de pytest para este paso (`pyproject.toml` no declara `markers`); queda fuera de la suite automatizada, tal como decide `proposal.md` (Out of Scope). **Confirmado**: sin marcador ni prueba automatizada; evidencia solo en esta bitácora.

## Fase 6: Suite completa, calidad estática y cierre

- [x] 6.1 Ejecutado `cd backend && pytest tests/ -v` completo con `TEST_DATABASE_URL` apuntando a `127.0.0.1:5434/solercia_test`. Línea base real vigente al inicio de esta rebanada: **1473 pasadas / 3 fallidas preexistentes** (nota: `tasks.md` Fase 0.7 registró 1411/1415 al inicio del cambio 48; la cifra creció por commits del tracker ya integrados entre rebanadas). Resultado final: **1487 pasadas / 3 fallidas preexistentes** (`test_adapter_microsoft365.py`, dependen del reloj) — 1473 + 14 pruebas nuevas de este archivo, cero regresiones nuevas tras corregir la desviación de 4.11.
- [x] 6.2 `cd backend && ruff format --check .` y `ruff check .` sobre los archivos de este cambio (`app/ai/`, `app/modules/assistant/`, `app/main.py`, `tests/test_ai_*.py`, `tests/test_assistant_*.py`): cero hallazgos. `ruff format --check .` sin acotar reporta 309 archivos preexistentes por reformatear (deuda ajena, no tocada); `ruff check .` reporta un único `E501` preexistente en `tests/test_cross_tenant_isolation.py:133` (línea `assert not missing, f"..."`, ya así antes de esta rebanada) — se reporta, no se toca.
- [x] 6.3 `cd backend && mypy app` → 6 errores preexistentes ajenos (`organizations/repository.py`×2, `organizations/service.py`×2, `tasks/service.py`, `org_role_templates/service.py`); cero errores nuevos en `app/ai/` ni `app/modules/assistant/`.
- [x] 6.4 Confirmado: `backend/alembic/versions/` tiene 24 archivos tanto en `a9b9e00` como en `HEAD` — sin migración nueva.
- [x] 6.5 Releídas `test_body_never_contains_the_api_key_or_the_full_base_url` (más `test_base_url_userinfo_is_never_echoed`) y `test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` (`test_ai_adapter_openai_compatible.py`, rebanada 2, sin tocar): ninguna aserción comentada ni debilitada.
- [x] 6.6 Confirmados en `git log`: `dc97855` (núcleo), `fd8197a` (openai_compatible), `42c401b` (anthropic), y el commit de esta rebanada `feat(assistant): agrega GET /assistant/health con RBAC y sonda opt-in`.
- [x] 6.7 [orquestador, NO de apply] Cadena de ramas (feature-branch-chain): tracker `feat/48-puerto-llm` (base: `a9b9e00`) → `feat/48-s1-nucleo` (base: tracker) → `feat/48-s2-openai-compatible` (base: s1) → `feat/48-s3-anthropic` (base: s2) → `feat/48-s4-assistant` (base: s3), integradas al tracker por *fast-forward*. Solo el tracker se integra a `preview`. Confirmar que ningún commit de los cambios 42/43 cae en estas ramas. **Hecho (orquestador, 2026-08-26)**: cadena real `03acf2f` (punta integrada del 42 archivado, base efectiva) → `dc97855` (s1) → `d9b264f` (bitácora) → `fd8197a` (s2) → `42c401b` (s3) → `d39236d` (s4), cada rama creada sobre la anterior y el tracker avanzado por *fast-forward* a `d39236d`. Los commits del 42 son ancestros de la base (el tracker nació de la punta archivada del 42), no commits caídos en estas ramas; los artefactos del 43/44/45a viven en sus propias ramas (`feat/43-tareas-origen-externo` = `8da4b1a`, confirmados vía worktree temporal), no en esta cadena.
