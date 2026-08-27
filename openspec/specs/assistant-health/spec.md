# assistant-health Specification

## Propósito

Endpoint de diagnóstico `GET /api/v1/assistant/health` que reporta la configuración activa del `LlmPort` (proveedor, modelo, alcanzabilidad) sin exponer secretos ni gastar tokens, protegido con el mismo RBAC que los demás módulos de integración. Vive en `backend/app/modules/assistant/` (router → service → puerto), sin persistencia.

## Requirements

### Requirement: Endpoint protegido por RBAC de integración

El sistema DEBE exponer `GET /api/v1/assistant/health` con `require_role(admin, manager)`, igual patrón que `connectors`, `glpi_sync`, `jira_import` e `intake`. Roles `member` y `viewer` DEBEN recibir 403. El endpoint DEBE resolver el tenant desde el JWT como el resto de módulos de integración; ninguna organización ve el estado del `LlmPort` de otra.

#### Scenario: Admin obtiene 200
- DADO un usuario con rol `admin` autenticado en su organización
- CUANDO invoca `GET /api/v1/assistant/health`
- ENTONCES la respuesta es 200 con el sobre `{data, message}`

#### Scenario: Manager obtiene 200
- DADO un usuario con rol `manager` autenticado
- CUANDO invoca `GET /api/v1/assistant/health`
- ENTONCES la respuesta es 200

#### Scenario: Member recibe 403
- DADO un usuario con rol `member` autenticado
- CUANDO invoca `GET /api/v1/assistant/health`
- ENTONCES la respuesta es 403 y no revela ningún campo de `data`

### Requirement: Sobre de respuesta y campos de configuración

`data` DEBE incluir `provider`, `model`, `base_url_host` (solo el `netloc`, nunca ruta ni credenciales embebidas), `api_key_configured` (booleano), `timeout_seconds`, `max_tokens`, `structured_output_mode`, `reachability` en `{ok, unreachable, not_probed}` y `reachability_reason`.

#### Scenario: La respuesta trae todos los campos esperados
- DADO `LLM_PROVIDER="openai_compatible"` y `LLM_BASE_URL="http://localhost:11434/v1"`
- CUANDO se invoca el endpoint sin `?probe=true`
- ENTONCES `data.base_url_host == "localhost:11434"`, `data.api_key_configured` es booleano y `data.reachability == "not_probed"`

### Requirement: Sonda opt-in sin gasto de tokens

Con `?probe=true` y proveedor `openai_compatible`, el sistema DEBE hacer `GET {base_url}/models` (sin generar texto) y reportar `reachability="ok"` o `"unreachable"` con un `reachability_reason` legible, nunca un 500. Con proveedor `anthropic`, DEBE reportar `reachability="not_probed"` sin llamada de red. Con proveedor `fake`, DEBE reportar `reachability="ok"`. Sin `?probe=true` (o con valor por defecto `false`), el sistema DEBE reportar únicamente configuración, igual que sin sonda.

#### Scenario: Sonda exitosa contra openai_compatible
- DADO `LLM_PROVIDER="openai_compatible"` y un `MockTransport` que responde 200 en `/models`
- CUANDO se invoca `GET /assistant/health?probe=true`
- ENTONCES `data.reachability == "ok"`

#### Scenario: Sonda fallida nunca produce 500
- DADO `LLM_PROVIDER="openai_compatible"` y un `MockTransport` que rechaza la conexión a `/models`
- CUANDO se invoca `GET /assistant/health?probe=true`
- ENTONCES la respuesta es 200 con `data.reachability == "unreachable"` y un `reachability_reason` legible

#### Scenario: anthropic nunca se sondea
- DADO `LLM_PROVIDER="anthropic"`
- CUANDO se invoca `GET /assistant/health?probe=true`
- ENTONCES `data.reachability == "not_probed"` y ninguna llamada de red ocurre

#### Scenario: fake siempre reporta ok
- DADO `LLM_PROVIDER="fake"`
- CUANDO se invoca `GET /assistant/health?probe=true`
- ENTONCES `data.reachability == "ok"` sin red

### Requirement: Ningún secreto ni URL completa en la respuesta

La respuesta NUNCA DEBE contener `LLM_API_KEY` ni el valor completo de `LLM_BASE_URL` (ruta, query o credenciales embebidas), en ningún estado de `reachability`.

#### Scenario: La clave y la URL completa están ausentes
- DADO `LLM_API_KEY="sk-secreta"` y `LLM_BASE_URL="http://localhost:11434/v1"` configurados
- CUANDO se invoca el endpoint con y sin `?probe=true`
- ENTONCES el cuerpo de la respuesta serializado no contiene `"sk-secreta"` ni la cadena `"/v1"` de la URL completa
