# llm-port Specification

## Propósito

Puerto neutro para completions de modelos de lenguaje (`LlmPort`) con tres adaptadores intercambiables por variable de entorno (`fake`, `openai_compatible`, `anthropic`), DTOs congelados, taxonomía de errores tipada, validación local obligatoria de salida estructurada, reintentos deterministas nunca decididos por el modelo, y una guarda de destino que impide exfiltración de datos hacia una URL no autorizada. Vive en `backend/app/ai/`, sin persistencia, sin modelos SQLAlchemy, sin migraciones.

## Requirements

### Requirement: Contrato del puerto y DTOs congelados

El sistema DEBE exponer `LlmPort` con un único método asíncrono `complete(request: LlmRequest) -> LlmResponse`. `LlmRequest` DEBE incluir `system`, `messages` (rol en `{system, user, assistant}` y `content`), `json_schema` opcional, `temperature` opcional, `max_tokens` obligatorio y `timeout_seconds` opcional. `LlmResponse` DEBE incluir `text`, `parsed` (solo si se pidió esquema y validó localmente), `usage` (tokens de entrada y salida), `provider`, `model`, `prompt_version`, `latency_ms` y `finish_reason` en `{stop, length, refusal, tool}`. Ambos DTOs DEBEN ser inmutables (frozen dataclasses).

#### Scenario: Petición mínima produce una respuesta completa
- DADO un `LlmRequest` con `system`, un mensaje `user` y `max_tokens=200`
- CUANDO se invoca `complete()` contra el adaptador `fake`
- ENTONCES la respuesta trae `text`, `usage`, `provider`, `model`, `prompt_version`, `latency_ms >= 0` y `finish_reason == "stop"`

#### Scenario: Un DTO del puerto no se puede mutar
- DADO un `LlmRequest` ya construido
- CUANDO se intenta reasignar uno de sus campos
- ENTONCES la operación falla porque el dataclass es congelado

### Requirement: Selección del adaptador activo por entorno

El sistema DEBE resolver un único adaptador activo por proceso desde `settings.LLM_PROVIDER` en `{fake, openai_compatible, anthropic}`, leído en tiempo de llamada (nunca como constante de módulo). El valor por defecto DEBE ser `fake`. Un valor desconocido DEBE producir `llm_config_invalid` (422) sin abrir ninguna conexión.

#### Scenario: Proveedor por defecto es fake
- DADO `Settings` sin `LLM_PROVIDER` explícito
- CUANDO se resuelve el adaptador activo
- ENTONCES se obtiene `fake`, sin red

#### Scenario: Proveedor desconocido falla controladamente
- DADO `LLM_PROVIDER="ollama-legacy"`
- CUANDO se resuelve el adaptador activo
- ENTONCES se lanza `llm_config_invalid` (422) y no se abre ninguna conexión

#### Scenario: La selección es parcheable en pruebas tras el import
- DADO `monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")` después de importar el módulo
- CUANDO se resuelve el adaptador activo
- ENTONCES se obtiene `openai_compatible`, confirmando lectura en tiempo de llamada

### Requirement: Adaptador fake sin red

El adaptador `fake` DEBE completar sin abrir ninguna conexión y DEBE aceptar respuestas inyectables para pruebas de contrato. Con `json_schema`, DEBE validar localmente con Pydantic v2 y devolver `parsed` solo si valida; si no valida, DEBE lanzar `llm_schema_mismatch`.

#### Scenario: Esquema válido devuelve parsed
- DADO un `json_schema` y una respuesta inyectada que lo cumple
- CUANDO se invoca `complete()`
- ENTONCES `parsed` no es `None` y coincide con el esquema

#### Scenario: Esquema incumplido falla explícito
- DADO un `json_schema` y una respuesta inyectada que lo incumple
- CUANDO se invoca `complete()`
- ENTONCES se lanza `llm_schema_mismatch` (502), nunca un `parsed` inválido

### Requirement: Adaptador openai_compatible

El adaptador DEBE enviar `POST {base_url}/chat/completions` con `model`, `messages`, `temperature`, `max_tokens`, `stream=false`. La forma del cuerpo estructurado DEBE seleccionarse por `LLM_JSON_MODE` en `{json_schema_openai, json_schema_llamacpp, json_object}`. DEBE parsear `choices[0].message.content` y `usage`, validar localmente cuando se pidió esquema, y mapear: 401/403 → `llm_auth_error`; 429 → `llm_rate_limited` tras reintentos acotados respetando `Retry-After`; 5xx o error de conexión → `llm_unavailable`; timeout → `llm_timeout`; JSON de respuesta inválido → `llm_invalid_output`. Los reintentos DEBEN ser deterministas (`LLM_MAX_RETRIES`, techo `LLM_MAX_BACKOFF_SECONDS`), nunca decididos por el modelo.

#### Scenario: json_schema_llamacpp usa el esquema al nivel superior
- DADO `LLM_JSON_MODE="json_schema_llamacpp"` y un `json_schema`
- CUANDO se invoca `complete()`
- ENTONCES el cuerpo enviado lleva el esquema sin anidar bajo `json_schema`

#### Scenario: 429 agota reintentos y falla
- DADO un `MockTransport` que responde 429 con `Retry-After` hasta agotar `LLM_MAX_RETRIES`
- CUANDO se invoca `complete()`
- ENTONCES se lanza `llm_rate_limited` (503) con backoffs acotados a `LLM_MAX_BACKOFF_SECONDS`

#### Scenario: Timeout se mapea a llm_timeout
- DADO un transporte que agota el tiempo configurado
- CUANDO se invoca `complete()`
- ENTONCES se lanza `llm_timeout` (503)

### Requirement: Adaptador anthropic sobre el SDK oficial

El adaptador DEBE usar `AsyncAnthropic` con importación perezosa (el paquete `anthropic` NO DEBE estar en `sys.modules` cuando `LLM_PROVIDER` es distinto de `anthropic`). DEBE enviar `system` de nivel superior y `max_tokens` obligatorio, SIN reenviar `temperature`. La salida estructurada DEBE usar `output_config.format` o `messages.parse`, con validación local. `stop_reason` DEBE mapearse: `end_turn` → `finish_reason="stop"`; `max_tokens` → `finish_reason="length"` (y `llm_invalid_output` si se pidió esquema y no se completó); `refusal` (HTTP 200) → `llm_content_filtered` (422). Las excepciones tipadas del SDK DEBEN mapearse a la taxonomía del puerto. Reintentos y timeout DEBEN delegarse al SDK (`LLM_MAX_RETRIES`, `LLM_TIMEOUT_SECONDS`), sin backoff propio.

#### Scenario: Aislamiento de dependencia con otro proveedor activo
- DADO `LLM_PROVIDER="fake"` durante la suite de pruebas
- CUANDO el proceso arranca y se ejecuta
- ENTONCES `"anthropic"` no aparece en `sys.modules`

#### Scenario: Refusal con HTTP 200 se mapea a contenido filtrado
- DADO una respuesta simulada con `stop_reason="refusal"` y HTTP 200
- CUANDO se invoca `complete()`
- ENTONCES se lanza `llm_content_filtered` (422), nunca una respuesta con texto parcial como válida

#### Scenario: max_tokens con esquema pedido trunca de forma explícita
- DADO `json_schema` presente y `stop_reason="max_tokens"`
- CUANDO se invoca `complete()`
- ENTONCES se lanza `llm_invalid_output` (502) en vez de un `parsed` a partir de JSON incompleto

#### Scenario: Falta de API key con anthropic activo falla en configuración
- DADO `LLM_PROVIDER="anthropic"` y `LLM_API_KEY=""`
- CUANDO se resuelve el adaptador activo
- ENTONCES se lanza `llm_config_invalid` (422) antes de instanciar el cliente del SDK

### Requirement: Guarda de destino por allowlist

`LLM_BASE_URL` DEBE pertenecer a `LLM_BASE_URL_ALLOWLIST` (comparación exacta de origen y prefijo), validada en el constructor del cliente ANTES de cualquier petición. Una URL fuera de la lista DEBE producir `llm_config_invalid` sin tocar el transporte.

#### Scenario: URL fuera de la allowlist nunca llega al transporte
- DADO `LLM_BASE_URL="http://evil.example.com/v1"` ausente de `LLM_BASE_URL_ALLOWLIST`
- CUANDO se construye el adaptador `openai_compatible`
- ENTONCES se lanza `llm_config_invalid` (422) y el `MockTransport` no recibe ninguna llamada

#### Scenario: URL dentro de la allowlist procede
- DADO `LLM_BASE_URL="http://localhost:11434/v1"` presente en la lista
- CUANDO se construye el adaptador y se invoca `complete()`
- ENTONCES la petición llega al transporte inyectado sin error de configuración

### Requirement: Protección de secretos y datos en logs y errores

`LLM_API_KEY` NUNCA DEBE aparecer en logs, mensajes de error ni respuestas. Los cuerpos de petición (que en el cambio 49 llevarán contenido de buzón) NUNCA DEBEN registrarse. Los logs de error DEBEN limitarse a estado HTTP y como máximo 200 caracteres del cuerpo de RESPUESTA.

#### Scenario: Un error 401 no filtra la clave
- DADO un `MockTransport` que responde 401 con la clave reflejada en el cuerpo
- CUANDO se invoca `complete()` y se captura el log de error
- ENTONCES el log no contiene `LLM_API_KEY`, solo estado y hasta 200 caracteres del cuerpo de respuesta

#### Scenario: El cuerpo de petición nunca se registra
- DADO una petición con contenido de mensaje sensible
- CUANDO ocurre cualquier error durante `complete()`
- ENTONCES ningún log contiene el cuerpo de la petición enviada

### Requirement: Configuración LLM_* con valores por defecto seguros

`Settings` DEBE declarar el bloque `LLM_*` al final, con `LLM_PROVIDER="fake"`, `LLM_TIMEOUT_SECONDS=60.0`, `LLM_MAX_TOKENS` razonable, `LLM_MAX_RETRIES=2`, `LLM_MAX_BACKOFF_SECONDS=30.0` y `LLM_ANTHROPIC_FALLBACKS=false`. El bloque DEBE espejarse en `env.example` y `docker-compose.yml`, con el contenedor fijado en `fake`.

#### Scenario: Configuración por defecto no requiere ajuste
- DADO `Settings()` sin variables `LLM_*` en el entorno
- CUANDO se leen los valores
- ENTONCES `LLM_PROVIDER == "fake"`, `LLM_MAX_RETRIES == 2` y `LLM_ANTHROPIC_FALLBACKS is False`

#### Scenario: docker-compose arranca en modo fake
- DADO `docker-compose.yml` sin sobreescritura local de `LLM_PROVIDER`
- CUANDO el contenedor backend arranca
- ENTONCES el proceso usa `fake`, sin red hacia ningún proveedor de LLM
