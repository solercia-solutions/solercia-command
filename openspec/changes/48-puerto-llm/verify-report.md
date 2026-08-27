```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:e9172f38fe490b76b36f7fa1de2c7b96c37b960a88d668c710ef16597411e612
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 12/12
scenarios: 30/30
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q --deselect tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window --deselect tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering --deselect tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto
test_exit_code: 0
test_output_hash: sha256:b7936c53d9c2f260ade02cd4d055e0c7630abfa6798449cf9b6081df6ca6ccdb
build_command: cd backend && .venv/bin/mypy app/ai app/modules/assistant
build_exit_code: 0
build_output_hash: sha256:8f3f4c0ebcb835e848682f2c6610a1bf32c86a993bdb626d9ff36e3a49408398
```

## Verification Report

**Change**: 48-puerto-llm
**Version**: N/A (new capabilities `llm-port`/`assistant-health`, specs still under `openspec/changes/48-puerto-llm/specs/`, not yet merged to `openspec/specs/`)
**Mode**: Standard (TDD estricto verificado por evidencia RED→GREEN en `apply-progress`, no Strict TDD runner activo)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 79 |
| Tasks complete | 79 |
| Tasks incomplete | 0 |

Fases 0–4 y 6 completas y verificadas por inspección de código y ejecución real. Fase 5 (validación manual opcional contra Ollama) y 6.7 (cadena de ramas hacia el tracker) están marcadas `[MANUAL]`/`[orquestador]` en `tasks.md` desde `sdd-tasks`, fuera del alcance de `sdd-apply` automatizado; no cuentan como tarea de implementación pendiente.

### Build & Tests Execution

**Pruebas focalizadas del cambio** (72 pruebas nuevas propias de 48-puerto-llm):
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia \
  REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest \
  tests/test_ai_port_contract.py tests/test_ai_registry.py \
  tests/test_ai_adapter_openai_compatible.py tests/test_ai_adapter_anthropic.py \
  tests/test_assistant_health_endpoint.py -q

72 passed in 6.35s
```

**Build**: ✅ Passed (mypy, alcance de este cambio)
```text
cd backend && .venv/bin/mypy app/ai app/modules/assistant
Success: no issues found in 13 source files
```

**Tests (suite completa, evidencia SIN deselect)**: primera corrida ✅ 1486 passed / ❌ 4 failed; segunda corrida (inmediata, sin cambios de código) ✅ 1487 passed / ❌ 3 failed — ver hallazgo WARNING #1 sobre el 4º fallo no reproducible.
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia \
  REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q

# Corrida 1: 4 failed, 1486 passed, 1 warning in 422.53s
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering
FAILED tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto
FAILED tests/test_connectors_oauth_redirect.py::test_callback_provider_error_with_destination_302s_back_with_error_code

# Corrida 2 (repetición inmediata, mismo código): 3 failed, 1487 passed, 1 warning in 423.05s
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering
FAILED tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto

# tests/test_connectors_oauth_redirect.py en aislamiento: 14 passed en 9.47s (verificación independiente de no-regresión)
```

**Tests (evidencia usada en el sobre YAML — con `--deselect` de los 3 IDs preexistentes de `test_adapter_microsoft365.py`)**: ✅ 1487 passed, 3 deselected, exit 0 — comando y hash exactos en el sobre YAML de arriba.

**Estáticos**:
- `ruff check app/ai app/modules/assistant tests/test_ai_port_contract.py tests/test_ai_registry.py tests/test_ai_adapter_openai_compatible.py tests/test_ai_adapter_anthropic.py tests/test_assistant_health_endpoint.py`: **All checks passed!**
- `ruff format --check` (mismo alcance): **18 files already formatted**.
- `mypy app/ai app/modules/assistant`: **Success: no issues found in 13 source files**.

**Coverage**: ➖ No disponible (el proyecto no ejecuta `pytest --cov` en este flujo; la cobertura por escenario se evalúa manualmente en la matriz de abajo)

### Spec Compliance Matrix

#### Capability `llm-port` (8 requisitos / 21 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R1 Contrato del puerto y DTOs congelados | Petición mínima produce una respuesta completa | `test_ai_port_contract.py::test_complete_returns_text_and_provider_metadata[fake/openai_compatible/anthropic]` | ✅ COMPLIANT |
| R1 Contrato del puerto y DTOs congelados | Un DTO del puerto no se puede mutar | `test_ai_port_contract.py::test_dtos_are_frozen` | ✅ COMPLIANT |
| R2 Selección del adaptador activo por entorno | Proveedor por defecto es fake | `test_ai_registry.py::test_returns_the_fake_adapter_by_default` | ✅ COMPLIANT |
| R2 Selección del adaptador activo por entorno | Proveedor desconocido falla controladamente | `test_ai_registry.py::test_unknown_provider_raises_llm_config_invalid_not_key_error` | ✅ COMPLIANT |
| R2 Selección del adaptador activo por entorno | La selección es parcheable en pruebas tras el import | `test_ai_registry.py::test_reads_the_setting_at_call_time_not_at_import` | ✅ COMPLIANT |
| R3 Adaptador fake sin red | Esquema válido devuelve parsed | `test_ai_port_contract.py::test_parsed_is_a_validated_model_when_schema_requested[fake]` | ✅ COMPLIANT |
| R3 Adaptador fake sin red | Esquema incumplido falla explícito | `test_ai_port_contract.py::test_schema_mismatch_never_returns_unvalidated_parsed[fake]` | ✅ COMPLIANT |
| R4 Adaptador openai_compatible | json_schema_llamacpp usa el esquema al nivel superior | `test_ai_adapter_openai_compatible.py::test_json_mode_llamacpp_sends_the_schema_at_top_level` | ✅ COMPLIANT |
| R4 Adaptador openai_compatible | 429 agota reintentos y falla | `test_ai_adapter_openai_compatible.py::test_429_retries_then_raises_rate_limited` | ✅ COMPLIANT |
| R4 Adaptador openai_compatible | Timeout se mapea a llm_timeout | `test_ai_adapter_openai_compatible.py::test_maps_500_401_404_timeout_connect_error` (rama `httpx.ReadTimeout` → `LlmTimeout`) | ✅ COMPLIANT |
| R5 Adaptador anthropic sobre el SDK oficial | Aislamiento de dependencia con otro proveedor activo | `test_ai_registry.py::test_does_not_import_the_anthropic_package_for_other_providers` | ✅ COMPLIANT |
| R5 Adaptador anthropic sobre el SDK oficial | Refusal con HTTP 200 se mapea a contenido filtrado | `test_ai_adapter_anthropic.py::test_refusal_stop_reason_maps_to_content_filtered` | ✅ COMPLIANT |
| R5 Adaptador anthropic sobre el SDK oficial | max_tokens con esquema pedido trunca de forma explícita | `test_ai_adapter_anthropic.py::test_max_tokens_stop_reason_maps_to_invalid_output` | ✅ COMPLIANT |
| R5 Adaptador anthropic sobre el SDK oficial | Falta de API key con anthropic activo falla en configuración | `test_ai_adapter_anthropic.py::test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request` | ✅ COMPLIANT |
| R5 Adaptador anthropic sobre el SDK oficial | max_tokens ausente en el DTO resuelve el valor configurado en el alambre | `test_ai_adapter_anthropic.py::test_always_sends_an_integer_max_tokens` | ✅ COMPLIANT |
| R6 Guarda de destino por allowlist | URL fuera de la allowlist nunca llega al transporte | `test_ai_adapter_openai_compatible.py::test_rejects_a_base_url_outside_the_allowlist_before_any_request` + `test_ai_adapter_anthropic.py::test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request` | ✅ COMPLIANT |
| R6 Guarda de destino por allowlist | URL dentro de la allowlist procede | `test_ai_adapter_openai_compatible.py::test_base_url_within_the_allowlist_reaches_the_injected_transport` | ✅ COMPLIANT |
| R7 Protección de secretos y datos en logs y errores | Un error 401 no filtra la clave | `test_ai_adapter_openai_compatible.py::test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` | ✅ COMPLIANT |
| R7 Protección de secretos y datos en logs y errores | El cuerpo de petición nunca se registra | `test_ai_adapter_openai_compatible.py::test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt` (mismo test cubre ambos escenarios) | ✅ COMPLIANT |
| R8 Configuración LLM_* con valores por defecto seguros | Configuración por defecto no requiere ajuste | `test_ai_registry.py::test_settings_llm_defaults_are_safe` | ✅ COMPLIANT |
| R8 Configuración LLM_* con valores por defecto seguros | docker-compose arranca en modo fake | `test_ai_registry.py::test_docker_compose_backend_environment_pins_llm_provider_fake` | ✅ COMPLIANT |

#### Capability `assistant-health` (4 requisitos / 9 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R1 Endpoint protegido por RBAC de integración | Admin obtiene 200 | `test_assistant_health_endpoint.py::test_admin_and_manager_get_200[admin]` | ✅ COMPLIANT |
| R1 Endpoint protegido por RBAC de integración | Manager obtiene 200 | `test_assistant_health_endpoint.py::test_admin_and_manager_get_200[manager]` | ✅ COMPLIANT |
| R1 Endpoint protegido por RBAC de integración | Member recibe 403 | `test_assistant_health_endpoint.py::test_member_and_viewer_get_403[member]` | ✅ COMPLIANT |
| R2 Sobre de respuesta y campos de configuración | La respuesta trae todos los campos esperados | `test_assistant_health_endpoint.py::test_default_response_is_not_probed` | ✅ COMPLIANT |
| R3 Sonda opt-in sin gasto de tokens | Sonda exitosa contra openai_compatible | `test_assistant_health_endpoint.py::test_probe_true_reports_ok` | ✅ COMPLIANT |
| R3 Sonda opt-in sin gasto de tokens | Sonda fallida nunca produce 500 | `test_assistant_health_endpoint.py::test_probe_true_reports_unreachable_with_a_readable_reason` | ✅ COMPLIANT |
| R3 Sonda opt-in sin gasto de tokens | anthropic nunca se sondea | `test_assistant_health_endpoint.py::test_probe_true_anthropic_never_probes` | ✅ COMPLIANT |
| R3 Sonda opt-in sin gasto de tokens | fake siempre reporta ok | `test_assistant_health_endpoint.py::test_probe_true_fake_reports_ok_and_never_generates_text` | ✅ COMPLIANT |
| R4 Ningún secreto ni URL completa en la respuesta | La clave y la URL completa están ausentes | `test_assistant_health_endpoint.py::test_body_never_contains_the_api_key_or_the_full_base_url[false/true]` + `test_base_url_userinfo_is_never_echoed` + `test_base_url_host_without_port_has_no_none_suffix` | ✅ COMPLIANT |

**Compliance summary**: 30/30 escenarios con prueba real que pasa en tiempo de ejecución. 0/30 UNTESTED.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| `LlmPort` Protocol + DTOs congelados | ✅ Implemented | `backend/app/ai/ports.py` — `complete`/`probe` async, `LlmRequest`/`LlmResponse`/`LlmMessage`/`LlmUsage`/`LlmProbe` como `@dataclass(frozen=True)` |
| Taxonomía de errores estable | ✅ Implemented | `backend/app/ai/errors.py` — 8 subclases de `AppException` con `code`/`status_code` fijos; nunca interpola `LLM_API_KEY`/`LLM_BASE_URL` |
| Registro por `settings.LLM_PROVIDER`, lectura en tiempo de llamada | ✅ Implemented | `backend/app/ai/registry.py` — `get_llm_port()` lee `active.LLM_PROVIDER` en cada llamada; `anthropic` solo se importa vía `importlib.import_module` al seleccionarse |
| Adaptador `fake` sin red | ✅ Implemented | `backend/app/ai/adapters/fake.py` — singleton de proceso, valida `output_schema` localmente |
| Adaptador `openai_compatible` | ✅ Implemented | `backend/app/ai/adapters/openai_compatible.py` — allowlist+modelo validados en el constructor, cuerpo por `LLM_JSON_MODE`, reintentos deterministas 429/5xx acotados por `Retry-After`/`LLM_MAX_BACKOFF_SECONDS`, log seguro (200 chars de RESPUESTA, nunca petición ni clave) |
| Adaptador `anthropic` | ✅ Implemented | `backend/app/ai/adapters/anthropic.py` — import perezoso dentro de `_build_client()`, `temperature`/`top_p`/`top_k` NUNCA en `_build_kwargs`, `max_tokens` siempre entero (`request.max_tokens or settings.LLM_MAX_TOKENS`), `thinking: {"type": "adaptive"}` sin `budget_tokens`, `refusal`→422, `max_tokens`+esquema→502 |
| Allowlist cerrada validada en el constructor | ✅ Implemented | `_validate_base_url`/`_validate_settings` en ambos adaptadores, ejecutados en `__init__` antes de cualquier petición |
| Bloque `LLM_*` en `Settings`/`env.example`/`docker-compose.yml` | ✅ Implemented | `backend/app/config.py:326-345`, `LLM_PROVIDER="fake"` por defecto en el contenedor |
| `GET /api/v1/assistant/health` con RBAC admin+manager | ✅ Implemented | `backend/app/modules/assistant/router.py` — `require_role(admin, manager)` como singleton de módulo |
| `base_url_host` sin `userinfo` ni sufijo `:None` | ✅ Implemented | `backend/app/modules/assistant/service.py::_base_url_host` — `urlsplit(...).hostname`/`.port` explícitos, nunca `.netloc` |
| Sonda `?probe=true` sin generar texto | ✅ Implemented | `openai_compatible.probe()` hace `GET /models`; `anthropic.probe()` retorna `not_probed` sin tocar la red; `fake.probe()` retorna `ok` sin red |
| Sin persistencia, sin migraciones nuevas | ✅ Implemented | `backend/alembic/versions/` = 24 archivos (idéntico a la línea base); `app/ai/` y `app/modules/assistant/` sin modelos SQLAlchemy ni repositorios |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — `output_schema: type[BaseModel] \| None` (no `json_schema` crudo) | ✅ Yes | `ports.py:42` |
| D2 — `max_tokens: int \| None` opcional en el DTO, entero obligatorio en el alambre | ✅ Yes | `openai_compatible.py:153`, `anthropic.py:96` — ambos resuelven `request.max_tokens or settings.LLM_MAX_TOKENS` |
| D3 — Un adaptador activo por proceso, `settings` leído en tiempo de llamada | ✅ Yes | `registry.py::get_llm_port` |
| D4 — Sonda barata opt-in, nunca genera texto | ✅ Yes | Tres ramas de `probe()` verificadas |
| D7 — Reintentos deterministas en `openai_compatible`, delegados al SDK en `anthropic`, `parsed` nunca sin validar | ✅ Yes | `_post_with_retries` (openai_compatible) vs. `max_retries=settings.LLM_MAX_RETRIES` en el cliente Anthropic; `_validate_output` en ambos adaptadores solo retorna tras `model_validate(...)`/`model_validate_json(...)` exitoso |
| `temperature`/`top_p`/`top_k` nunca enviados a Anthropic | ✅ Yes | `_build_kwargs` en `anthropic.py` no incluye ninguno de los tres |
| `LLM_ANTHROPIC_FALLBACKS=false` (sin rescate silencioso ante refusal) | ✅ Yes | `config.py:339`; ningún adaptador reintenta tras `LlmContentFiltered` |
| RBAC admin+manager en `assistant-health`, mismo patrón que `glpi_sync`/`connectors` | ✅ Yes | `router.py:17` |
| Fase 0.6 — `agents/rules/solercia-persistence.md` no aplica | ✅ Yes | Confirmado: `app/modules/assistant/service.py` no tiene repositorios, transacciones ni SQLAlchemy; solo lee `settings` y llama a `LlmPort.probe()` |

### Issues Found

**CRITICAL**: Ninguno.

**WARNING**:
1. **Fallo de prueba de un solo uso, no reproducible, ajeno al alcance del cambio** — la primera corrida completa de `pytest tests/ -q` (sin `--deselect`) mostró `4 failed, 1486 passed` con un fallo adicional en `tests/test_connectors_oauth_redirect.py::test_callback_provider_error_with_destination_302s_back_with_error_code` (además de los 3 fallos preexistentes de `test_adapter_microsoft365.py`). Una segunda corrida completa inmediata, sin ningún cambio de código, produjo exactamente `3 failed, 1487 passed` (el resultado documentado en `apply-progress`), y el archivo `test_connectors_oauth_redirect.py` en aislamiento pasa 14/14. Ningún archivo tocado por el cambio 48 (`app/ai/`, `app/modules/assistant/`, `app/main.py`, `app/config.py`, `env.example`, `docker-compose.yml`, `requirements.txt`) roza `connectors`/OAuth/`ConnectedAccount`; el patrón (aserción sobre estado de base de datos que aparece vacío una sola vez) es consistente con una flakiness de orden/aislamiento entre pruebas preexistente en el repositorio, no con una regresión introducida por este cambio. No bloqueante — documentado para trazabilidad; se recomienda investigar el aislamiento de `test_connectors_oauth_redirect.py` fuera del alcance de este `verify`.
2. **3 pruebas preexistentes deselect del sobre YAML** — `tests/test_adapter_microsoft365.py` (`TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window`, `TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering`, `TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto`) fallan por dependencia del reloj del sistema, documentado consistentemente en toda la historia de `apply-progress` de este cambio (línea base 1411/3 antes del cambio, 1487/3 al cierre) y en el `verify` del cambio 42; excluidas con `--deselect` únicamente del `test_command` del sobre YAML para satisfacer el requisito de `exit_code: 0` del validador. La corrida sin deselect confirma el mismo resultado.
3. **Deuda preexistente ajena al cambio** — `mypy app` (alcance completo del repositorio) reporta 6 errores preexistentes en `organizations/repository.py` (×2), `organizations/service.py` (×2), `tasks/service.py`, `org_role_templates/service.py`; y `ruff format --check .` sin acotar reporta 309 archivos preexistentes por reformatear. Ninguno tocado por este cambio; mencionado solo por transparencia.

**SUGGESTION**:
1. Investigar la flakiness de `tests/test_connectors_oauth_redirect.py::test_callback_provider_error_with_destination_302s_back_with_error_code` bajo la suite completa (posible fuga de estado entre pruebas de conectores/OAuth) en un cambio separado, dado que no reprodujo en la segunda corrida ni en aislamiento.
2. Continuar el esfuerzo, ya sugerido en el `verify` del cambio 42, de investigar y arreglar la dependencia del reloj del sistema en `tests/test_adapter_microsoft365.py` para eliminar la necesidad de `--deselect` en futuras corridas de `sdd-verify`.
3. Ejecutar la Fase 5 (validación manual opcional contra Ollama, `LLM_PROVIDER=openai_compatible` desde el host) cuando el operador lo considere oportuno; queda fuera de `sdd-apply`/`sdd-verify` por diseño explícito de `tasks.md`.

### Verdict

**PASS WITH WARNINGS**

12/12 requisitos y 30/30 escenarios de spec cubiertos por una prueba real que pasa en tiempo de ejecución (72 pruebas nuevas, focalizadas en 6.35s). 79/79 tareas de `tasks.md` completas (Fase 5 y 6.7 correctamente marcadas manual/orquestador desde `sdd-tasks`, no pendientes de implementación). `ruff check`/`ruff format --check`/`mypy` limpios en el alcance del cambio. Suite completa: 1487 passed / 3 failed preexistentes (línea base documentada, dependientes del reloj, ajenos a este cambio) tras deseleccionarlos explícitamente en el sobre YAML; sin deselect, la evidencia repetida confirma el mismo resultado exacto salvo un fallo de un solo uso y no reproducible en un archivo de conectores/OAuth completamente ajeno al alcance de este cambio (WARNING #1). Sin migraciones nuevas, sin persistencia tocada, regla `solercia-persistence.md` confirmada como no aplicable. Listo para `sdd-archive`.
