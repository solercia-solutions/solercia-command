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

- [ ] 0.1 Confirmar en disco que `backend/app/ai/` no existe todavía (glob).
- [ ] 0.2 Confirmar en disco que el bloque `INTAKE_*` de `Settings` termina en `config.py:324` y que ningún otro cambio en curso insertó ya algo después de esa línea.
- [ ] 0.3 Confirmar en disco que `main.py:190` sigue siendo el punto de inserción del bloque `include_router` y que los cambios `42`/`43` no lo tocaron desde el commit `a9b9e00`.
- [ ] 0.4 Confirmar en disco que `env.example` (bloque `SEED_DEMO_DATA`, líneas 17-21) y `docker-compose.yml` (líneas 42-44) siguen intactos; el bloque `LLM_*` se inserta después, sin pisarlos.
- [ ] 0.5 Confirmar en disco que `dependencies.py:189-203` (`require_role`) y el patrón `require_role(MemberRole.admin, MemberRole.manager)` de `glpi_sync/router.py:24-26,41` siguen vigentes como precedente literal para `assistant/router.py`.
- [ ] 0.6 Confirmar explícitamente que `agents/rules/solercia-persistence.md` NO aplica: aunque `backend/app/modules/assistant/service.py` coincide por patrón de ruta (`*service*.py`), el cambio no crea repositorios, transacciones ni migraciones — `AssistantHealthService.describe()` solo lee `settings` y consulta `LlmPort`, sin SQLAlchemy. Se deja constancia; no se sigue el checklist de persistencia.
- [ ] 0.7 Registrar la línea base de pruebas del commit `fc97125` (2026-08-26): `cd backend && pytest tests/ -v` con `TEST_DATABASE_URL` apuntando a `solercia_test` en `127.0.0.1:5434` → **1411 pasadas / 3 fallidas preexistentes** en `test_adapter_microsoft365.py`. Confirmar que la variable sigue configurada así antes de fijar esta cifra como referencia.
- [ ] 0.8 Confirmar en disco que `backend/tests/test_ai_*.py` y `test_assistant_health_endpoint.py` no existen todavía (archivos nuevos de este cambio).

## Fase 1: Núcleo — puerto, errores, `fake`, registro y configuración [Rebanada 1]

> Spec `llm-port`: Requirement «Contrato del puerto y DTOs congelados» (R1), «Selección del adaptador activo por entorno» (R2), «Adaptador fake sin red» (R3), escenario de aislamiento de `anthropic` de R5, «Configuración LLM_* con valores por defecto seguros» (R8). Design: D1-D4, D6 (default), estructura de módulos.

- [ ] 1.1 RED — crear `backend/tests/test_ai_port_contract.py` con un modelo Pydantic de prueba `TriageDecision` (esquema plano) y fixture del adaptador `fake`; `test_complete_returns_text_and_provider_metadata` (llm-port R1 escenario 1: `text`/`usage`/`provider`/`model`/`prompt_version`/`latency_ms >= 0`/`finish_reason == "stop"`).
- [ ] 1.2 RED — `test_dtos_are_frozen` (llm-port R1 escenario 2: `FrozenInstanceError` al reasignar un campo de `LlmRequest`).
- [ ] 1.3 RED — `test_parsed_is_none_when_no_schema_requested` y `test_parsed_is_a_validated_model_when_schema_requested` (llm-port R3 escenario 1: `isinstance(parsed, TriageDecision)`).
- [ ] 1.4 RED — `test_schema_mismatch_never_returns_unvalidated_parsed` (llm-port R3 escenario 2: `raises(LlmSchemaMismatch)`, `code == "llm_schema_mismatch"`, `status_code == 502`).
- [ ] 1.5 RED — `test_probe_never_generates_text` (frontera de seguridad: el doble de generación registra cero llamadas al invocar `probe()`).
- [ ] 1.6 RED — crear `backend/tests/test_ai_registry.py`: `test_returns_the_fake_adapter_by_default` (llm-port R2 escenario 1), `test_selects_the_adapter_named_by_llm_provider`, `test_unknown_provider_raises_llm_config_invalid_not_key_error` (R2 escenario 2: `status_code == 422`, el valor NO aparece en `detail`), `test_reads_the_setting_at_call_time_not_at_import` (R2 escenario 3), `test_fake_adapter_is_a_process_singleton`.
- [ ] 1.7 RED — en el mismo archivo: `test_does_not_import_the_anthropic_package_for_other_providers` (llm-port R5 escenario «Aislamiento de dependencia»: `monkeypatch` de `builtins.__import__` ante `"anthropic"` + `"app.ai.adapters.anthropic" not in sys.modules`).
- [ ] 1.8 RED — `test_settings_llm_defaults_are_safe` (llm-port R8 escenario 1: `LLM_PROVIDER == "fake"`, `LLM_MAX_RETRIES == 2`, `LLM_ANTHROPIC_FALLBACKS is False`).
- [ ] 1.9 RED — `test_docker_compose_backend_environment_pins_llm_provider_fake` (llm-port R8 escenario 2: parsear `docker-compose.yml` y afirmar `services.backend.environment.LLM_PROVIDER == "fake"`).
- [ ] 1.10 GREEN — crear `backend/app/ai/__init__.py` (vacío con docstring, sin importar submódulos) y `backend/app/ai/ports.py`: `Role`/`FinishReason`/`Reachability` (`Literal`), `LlmMessage`/`LlmUsage`/`LlmRequest`/`LlmResponse`/`LlmProbe` como `@dataclass(frozen=True)`, `LlmPort(Protocol)` con `complete()` y `probe()`.
- [ ] 1.11 GREEN — crear `backend/app/ai/errors.py`: ocho subclases de `AppException` (`LlmUnavailable` 503, `LlmAuthError` 401, `LlmRateLimited` 503, `LlmTimeout` 503, `LlmInvalidOutput` 502, `LlmSchemaMismatch` 502, `LlmContentFiltered` 422, `LlmConfigInvalid` 422), sin interpolar nunca clave ni URL.
- [ ] 1.12 GREEN — crear `backend/app/ai/adapters/__init__.py` (vacío) y `backend/app/ai/adapters/fake.py`: singleton de módulo, cero red, estado inspeccionable, valida `output_schema` con `model_validate` si se pidió.
- [ ] 1.13 GREEN — crear `backend/app/ai/registry.py`: `_ADAPTERS` con solo `"fake"` (las claves `openai_compatible`/`anthropic` se agregan en las rebanadas 2 y 3), `get_llm_port()` leyendo `settings.LLM_PROVIDER` en tiempo de llamada, `LlmConfigInvalid` para valor desconocido.
- [ ] 1.14 GREEN — agregar el bloque `LLM_*` al final de `Settings` (`backend/app/config.py`, tras `INTAKE_PULL_MAX_ITEMS`): `LLM_PROVIDER="fake"`, `LLM_BASE_URL=""`, `LLM_MODEL=""`, `LLM_API_KEY=""`, `LLM_TIMEOUT_SECONDS=60.0`, `LLM_MAX_TOKENS=1024`, `LLM_MAX_RETRIES=2`, `LLM_MAX_BACKOFF_SECONDS=30.0`, `LLM_JSON_MODE="json_object"`, `LLM_ANTHROPIC_FALLBACKS=False`, `LLM_BASE_URL_ALLOWLIST=[...]`, con el comentario justificativo que el archivo exige.
- [ ] 1.15 GREEN — crear `backend/app/ai/prompts/__init__.py`: `PROMPT_VERSION: Final[str] = "v1"` + regla de versionado en docstring.
- [ ] 1.16 GREEN — `env.example`: agregar el bloque `LLM_*` comentado después del bloque `SEED_DEMO_DATA`, sección «Backend (FastAPI)».
- [ ] 1.17 GREEN — `docker-compose.yml`: agregar `LLM_PROVIDER: "fake"` al bloque `services.backend.environment`, con comentario que remite a `env.example` para la activación local.
- [ ] 1.18 Verificar en verde: `cd backend && pytest tests/test_ai_port_contract.py tests/test_ai_registry.py -v`.

## Fase 2: Adaptador `openai_compatible` [Rebanada 2]

> Spec `llm-port`: «Adaptador openai_compatible» (R4), «Guarda de destino por allowlist» (R6), «Protección de secretos y datos en logs y errores» (R7). Design: sección del adaptador, D6, D7.

- [ ] 2.1 RED — crear `backend/tests/test_ai_adapter_openai_compatible.py` (`Settings(**overrides)` + `httpx.MockTransport` + `sleep` inyectado); `test_rejects_a_base_url_outside_the_allowlist_before_any_request` (llm-port R6 escenario 1: el handler lanza `AssertionError`, nunca se ejecuta) y `test_base_url_within_the_allowlist_reaches_the_injected_transport` (R6 escenario 2).
- [ ] 2.2 RED — `test_rejects_an_empty_model_before_any_request`.
- [ ] 2.3 RED — `test_system_travels_as_the_first_message_and_stream_is_false`.
- [ ] 2.4 RED — `test_json_mode_openai_sends_the_nested_envelope`, `test_json_mode_llamacpp_sends_the_schema_at_top_level` (llm-port R4 escenario 1), `test_json_mode_json_object_sends_the_schema_as_a_prompt_hint`.
- [ ] 2.5 RED — `test_parses_a_fenced_json_body`.
- [ ] 2.6 RED — `test_429_retries_then_raises_rate_limited` (llm-port R4 escenario 2) y `test_clamps_retry_after_to_max_backoff`.
- [ ] 2.7 RED — `test_maps_500_401_404_timeout_connect_error` (llm-port R4 escenario 3, camino timeout).
- [ ] 2.8 RED — `test_finish_reason_length_maps_to_invalid_output` (con `output_schema` pedido) y `test_max_tokens_without_schema_returns_length` (sin esquema: `finish_reason == "length"`, `parsed is None`, sin excepción).
- [ ] 2.9 RED — `test_finish_reason_content_filter_maps_to_content_filtered`.
- [ ] 2.10 RED — `test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` (llm-port R7 escenarios 1 y 2, vía `caplog`).
- [ ] 2.11 RED — `test_probe_hits_models_and_reports_ok` y `test_probe_reports_unreachable_with_reason`.
- [ ] 2.12 GREEN — crear `backend/app/ai/adapters/openai_compatible.py`: constructor con `transport`/`sleep`/`settings` inyectables, validación de allowlist y modelo antes de cualquier petición, cuerpo por `LLM_JSON_MODE`, mapa de fallos, backoff con techo, log seguro, `probe()` contra `/models`.
- [ ] 2.13 GREEN — registrar `"openai_compatible"` en `_ADAPTERS` (`backend/app/ai/registry.py`).
- [ ] 2.14 GREEN — extender `test_ai_port_contract.py`: parametrizar la fixture también con `openai_compatible` (doble hermético vía `MockTransport`), confirmando que el mismo cuerpo de prueba pasa contra los dos adaptadores.
- [ ] 2.15 Verificar en verde: `cd backend && pytest tests/test_ai_adapter_openai_compatible.py tests/test_ai_port_contract.py tests/test_ai_registry.py -v`.

## Fase 3: Adaptador `anthropic` [Rebanada 3]

> Spec `llm-port`: «Adaptador anthropic sobre el SDK oficial» (R5). Design: D5, sección del adaptador `anthropic`.

- [ ] 3.0 [MANUAL — orquestador] Compuerta de inicio: reverificar en vivo contra PyPI el pin `anthropic==1.0.0` y su compatibilidad con `pydantic==2.10.4`, Python 3.12 y `httpx2>=2.0.0,<3` (ya documentado en `design.md` D5, verificado 2026-08-27); instalar el paquete en el entorno de la rebanada antes de escribir cualquier prueba. Si no resuelve, aplicar la reversa de `design.md` (cliente httpx a mano) y registrar la excepción.
- [ ] 3.1 RED — crear `backend/tests/test_ai_adapter_anthropic.py` (sin `skip`: el pin es requisito de la rebanada), fixture `DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler))`; `test_system_is_top_level_and_temperature_is_never_sent` (`"temperature" not in body`, ídem `top_p`/`top_k`).
- [ ] 3.2 RED — `test_always_sends_an_integer_max_tokens` (llm-port R5 escenario 5: `max_tokens=None` en el DTO ⇒ entero igual a `settings.LLM_MAX_TOKENS` en el cuerpo).
- [ ] 3.3 RED — `test_sends_adaptive_thinking_without_budget_tokens`.
- [ ] 3.4 RED — `test_schema_request_carries_required_and_additional_properties_false`.
- [ ] 3.5 RED — `test_refusal_stop_reason_maps_to_content_filtered` (llm-port R5 escenario 2, HTTP 200 con `stop_details`).
- [ ] 3.6 RED — `test_max_tokens_stop_reason_maps_to_invalid_output` (llm-port R5 escenario 3, con esquema pedido) y `test_max_tokens_without_schema_returns_length` (sin esquema: `finish_reason == "length"`, `parsed is None`, sin excepción).
- [ ] 3.7 RED — `test_typed_exceptions_map_to_the_port_taxonomy` (401/429/500/529/conexión/timeout; `APITimeoutError` antes que `APIConnectionError`, es subclase).
- [ ] 3.8 RED — `test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request` (llm-port R5 escenario 4).
- [ ] 3.9 RED — `test_fallbacks_and_betas_are_never_requested`, `test_usage_maps_input_and_output_tokens`, `test_timeout_and_max_retries_come_from_settings`.
- [ ] 3.10 GREEN — crear `backend/app/ai/adapters/anthropic.py`: `_build_client()` con `import anthropic` perezoso dentro de la función, `AsyncAnthropic` con `http_client=DefaultAsyncHttpxClient(transport=...)` cuando se inyecta, camino `messages.parse` (con esquema) y `messages.create` (texto libre), mapa de `stop_reason`/excepciones, `probe()` → `not_probed` sin red.
- [ ] 3.11 GREEN — registrar `"anthropic"` en `_ADAPTERS` vía `_build_anthropic`, que hace `importlib.import_module("app.ai.adapters.anthropic")` dentro de la función.
- [ ] 3.12 GREEN — agregar `anthropic==1.0.0` a `backend/requirements.txt` con el comentario justificativo (pydantic, Python, `httpx2` transitivo, import perezoso — hechos de `design.md` D5).
- [ ] 3.13 GREEN — extender `test_ai_port_contract.py`: parametrizar la fixture también con `anthropic` (doble hermético vía `httpx2.MockTransport`), confirmando que el mismo cuerpo de prueba pasa contra los tres adaptadores.
- [ ] 3.14 GREEN — si `mypy` reporta el módulo `anthropic` sin *stubs*, agregar `"anthropic.*"` a `[[tool.mypy.overrides]]` en `backend/pyproject.toml` con `ignore_missing_imports = true`; omitir si el paquete ya trae `py.typed`.
- [ ] 3.15 Verificar en verde: `cd backend && pytest tests/test_ai_adapter_anthropic.py tests/test_ai_port_contract.py tests/test_ai_registry.py -v`.

## Fase 4: Módulo `assistant` y `GET /assistant/health` [Rebanada 4]

> Spec `assistant-health`: R1-R4 completos. Design: sección «Endpoint de salud».

- [ ] 4.1 RED — crear `backend/tests/test_assistant_health_endpoint.py` (`@skip_no_db`, `make_member`): `test_admin_and_manager_get_200` (assistant-health R1 escenarios 1-2, parametrizado por rol) y `test_member_and_viewer_get_403` (R1 escenario 3: `code == "forbidden"`).
- [ ] 4.2 RED — `test_default_response_is_not_probed` (assistant-health R2 escenario único: `LLM_PROVIDER="openai_compatible"`, `LLM_BASE_URL="http://localhost:11434/v1"` ⇒ `data.base_url_host == "localhost:11434"`, `api_key_configured` booleano, `reachability == "not_probed"`).
- [ ] 4.3 RED — `test_body_never_contains_the_api_key_or_the_full_base_url` (assistant-health R4 escenario único) y `test_base_url_userinfo_is_never_echoed` (frontera de secretos: `userinfo` en la URL nunca se refleja).
- [ ] 4.4 RED — `test_base_url_host_without_port_has_no_none_suffix` (frontera de secretos: `"api.anthropic.com"` nunca `"api.anthropic.com:None"`).
- [ ] 4.5 RED — `test_probe_true_reports_ok` (assistant-health R3 escenario 1) y `test_probe_true_reports_unreachable_with_a_readable_reason` (R3 escenario 2, nunca 500).
- [ ] 4.6 RED — `test_probe_true_anthropic_never_probes` (R3 escenario 3: cero llamadas de red) y `test_probe_true_fake_reports_ok` (R3 escenario 4).
- [ ] 4.7 RED — `test_probe_never_generates_text` y `test_invalid_configuration_is_a_reason_not_a_500`.
- [ ] 4.8 GREEN — crear `backend/app/modules/assistant/__init__.py`, `schemas.py` (`AssistantHealthData`) y `service.py` (`AssistantHealthService.describe(*, probe: bool)`; `base_url_host` con `hostname`/`port` explícitos vía `urlsplit`, nunca `netloc`; `port_factory` resuelto dentro de `describe()` para que `monkeypatch` surta efecto).
- [ ] 4.9 GREEN — crear `backend/app/modules/assistant/router.py`: `APIRouter(prefix="/assistant", tags=["assistant"])`, `require_assistant_role = require_role(MemberRole.admin, MemberRole.manager)` como singleton de módulo, sobre `{"data": …, "message": "Estado del proveedor de IA."}`.
- [ ] 4.10 GREEN — `backend/app/main.py:190`: agregar `app.include_router(assistant_router, prefix=API_PREFIX)`.
- [ ] 4.11 Verificar en verde: `cd backend && pytest tests/test_assistant_health_endpoint.py -v`.
- [ ] 4.12 Documentar `backend/README.md`: extender «Variables de entorno» (línea 27) con el bloque `LLM_*`, extender «Endpoints (v1)» (línea 69) con `GET /api/v1/assistant/health`, y agregar la sección «Activación del proveedor LLM local» con el runbook host/contenedor y el paso manual de sonda contra Ollama.

## Fase 5: Validación manual opcional contra Ollama [MANUAL — orquestador, fuera de la suite]

- [ ] 5.1 [MANUAL, opcional] Levantar Ollama local con `qwen3.5:9b-q4_K_M` descargado; exportar `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=http://localhost:11434/v1` (host) o `http://host.docker.internal:11434/v1` (contenedor), `LLM_MODEL=qwen3.5:9b-q4_K_M`.
- [ ] 5.2 [MANUAL, opcional] `GET /api/v1/assistant/health?probe=true` desde el host y desde el contenedor; confirmar `reachability == "ok"` en ambos, o `unreachable` con motivo legible si `host.docker.internal` no resuelve (Linux).
- [ ] 5.3 [MANUAL, opcional] No agregar marcador de pytest para este paso (`pyproject.toml` no declara `markers`); queda fuera de la suite automatizada, tal como decide `proposal.md` (Out of Scope).

## Fase 6: Suite completa, calidad estática y cierre

- [ ] 6.1 Ejecutar `cd backend && pytest tests/ -v` completo con `TEST_DATABASE_URL` configurada; comparar contra la línea base **1411 pasadas / 3 fallidas preexistentes** (`test_adapter_microsoft365.py`); confirmar cero regresiones nuevas.
- [ ] 6.2 Ejecutar `cd backend && ruff format --check .` y `cd backend && ruff check .`; corregir hasta cero hallazgos en los archivos nuevos/modificados de este cambio.
- [ ] 6.3 Ejecutar `cd backend && mypy app`; corregir hasta cero errores nuevos en `app/ai/` y `app/modules/assistant/`.
- [ ] 6.4 Confirmar que `backend/alembic/versions/` sigue con exactamente los mismos archivos que en el commit base `a9b9e00` — sin migración nueva; este cambio no crea agregados ni modelos SQLAlchemy.
- [ ] 6.5 Releer `test_body_never_contains_the_api_key_or_the_full_base_url` y `test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt`: confirmar que ninguna aserción quedó comentada o debilitada durante el desarrollo.
- [ ] 6.6 Commits convencionales en español por unidad lógica, uno por rebanada: `feat(ai): agrega LlmPort, taxonomía de errores, adaptador fake y registro`, `feat(ai): agrega adaptador openai_compatible con reintentos deterministas`, `feat(ai): agrega adaptador anthropic sobre el SDK oficial`, `feat(assistant): agrega GET /assistant/health con RBAC y sonda opt-in`.
- [ ] 6.7 [orquestador, NO de apply] Cadena de ramas (feature-branch-chain): tracker `feat/48-puerto-llm` (base: `a9b9e00`) → `feat/48-s1-nucleo` (base: tracker) → `feat/48-s2-openai-compatible` (base: s1) → `feat/48-s3-anthropic` (base: s2) → `feat/48-s4-assistant` (base: s3), integradas al tracker por *fast-forward*. Solo el tracker se integra a `preview`. Confirmar que ningún commit de los cambios 42/43 cae en estas ramas.
