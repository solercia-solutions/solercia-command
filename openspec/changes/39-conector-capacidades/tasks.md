# Tasks: 39 · Conector con panel de capacidades (de "conectado" a "útil")

## Reconciliación aplicada (orquestador)

1. **Ruta del probe**: `POST /connectors/{connector_id}/actions/probe` (gana `specs/connectors/spec.md`). El `/connectors/{connector_id}/probe` plano descrito en `proposal.md` y en `design.md` (File Changes, Data Flow, Interfaces) queda **superado**; router y tests de la Fase 2 usan la ruta anidada bajo `/actions/`.
2. **Reutilización del helper del 38**: el probe invoca `ConnectorService._run_readonly_probe(adapter, connector, ctx)`, introducido por `38-oauth-ms-google` (`design.md` Decisión 4). Los applies van **38 → 39**: si al aplicar el 39 el helper ya existe en `backend/app/modules/connectors/service.py`, la Fase 2 lo consume tal cual — el 39 **NO** duplica la selección de capability primaria ni el ciclo read-only. `state.yaml` ya declara `depends_on: [38-oauth-ms-google]`: el apply del 39 queda bloqueado hasta que 38 cierre.
3. **Campo de estado**: cada acción expone `state` (`available|requires_connection|coming_soon`), como fija la spec — consistente con `ConnectorActionRead`.

## Gate de dependencia

`sdd-apply` de 39 **NO** inicia hasta que `38-oauth-ms-google` esté aplicado y verificado (su `state.yaml` en `apply: done`). Mientras 38 no aplique, las acciones OAuth (m365/google) se derivan igual en `requires_connection`/`not_supported` — no bloquea la Fase 1, pero la Fase 2 depende del helper concreto de 38.

## Review Workload Forecast

| Campo | Valor |
|---|---|
| Líneas estimadas | ~380–450 (catálogo+descriptor ~70, service actions+probe ~110, schemas ~25, router ~40, tests backend ~90, front panel+key-handler+probe ~110, modelo/servicio ~30, i18n ~25) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | PR único; commits escalonados por fase (1→4); merge local a `preview` |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Objetivo | Commit (mismo PR) | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| U1 | Fase 1 — catálogo `CAPABILITY_ACTIONS` + `GET /connectors/{id}/actions` derivado de capabilities y estado | 1 | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_actions.py` | Pytest contra Postgres de test | Revert commit; endpoint+catálogo nuevos, cero impacto en rutas existentes |
| U2 | Fase 2 — `POST /connectors/{id}/actions/probe` reutilizando `_run_readonly_probe` del 38 | 2 | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_probe.py` | Pytest con `httpx.MockTransport(JiraAdapter)`; manual: probe real sobre Jira conectado vía túnel | Revert commit; depende del helper del 38 ya aplicado (gate de dependencia, no aislado) |
| U3 | Fase 3 — tarjeta expandida + panel de acciones desde el endpoint, retira `@if provider==` | 3 | `cd frontend && npm run build && npm run lint` | Manual: expandir tarjetas Jira/M365/MCP, ejecutar probe, ver spinner+resultado | Revert commit; tarjeta vuelve al bloque cableado por provider |
| U4 | Fase 4 — verde total + commits convencionales | 4 (final) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | N/A — regresión | Revert commit aislado |

## Fase 1 — Catálogo declarativo + derivación de acciones (STRICT TDD, backend)

- [ ] 1.1 [RED] Crear `backend/tests/test_connectors_actions.py`: registrar un adaptador fake con `capabilities` configurables (patrón `_MailOnlyAdapter` de `backend/tests/test_integration_fake_adapter.py:105`). Casos: (a) Jira con `ConnectedAccount` activa del USUARIO QUE LLAMA → `jira_import` en `coming_soon`, la acción de importar por archivo en `available`; (b) el mismo conector con cuenta activa de OTRO miembro pero no del caller → las acciones de `tickets` llegan en `requires_connection` (nunca mirar cuentas ajenas); (c) conector `mcp` conectado → acciones de explorar recursos/herramientas en `available`; (d) conector de otra organización → `404`; (e) sin token → `401`; (f) miembro sin rol admin/manager lee sin error. Falla hoy: ni `actions_catalog.py` ni el endpoint existen.
- [ ] 1.2 [GREEN] Crear `backend/app/modules/connectors/actions_catalog.py`: `@dataclass(frozen=True) class ActionDescriptor` (`key, label, capability, kind, requires_connection, default_state, target_route`) y `CAPABILITY_ACTIONS: dict[Capability, tuple[ActionDescriptor, ...]]` — `tickets`→(`jira_import` navigate/coming_soon, `jira_import_file` navigate/available, `tickets_sync` execute/requires_connection); `mail`→`read_mail`; `calendar`→`read_calendar` (execute); `external_resources`→`explore_resources`, `explore_tools` (execute). Etiquetas en español colombiano formal.
- [ ] 1.3 [GREEN] `backend/app/modules/connectors/schemas.py`: agregar `ConnectorActionRead` (`key, label, capability, state, kind, description`), `state: Literal["available", "requires_connection", "coming_soon"]`.
- [ ] 1.4 [GREEN] `backend/app/modules/connectors/service.py`: `async def list_actions(self, organization_id, connector_id, membership) -> list[ConnectorActionRead]` — `self._require_connector` (404 ajeno), `get_adapter(connector.provider)` (`None` → `[]`), intersecta `adapter.capabilities` con `CAPABILITY_ACTIONS`, resuelve si existe `ConnectedAccount` activa con `user_id == membership.user_id` (reutiliza `ConnectedAccountRepository.list_accounts(..., only_user_id=membership.user_id)`, **nunca** `only_user_id=None` como hace `list_connected_accounts` para admin/manager — la spec exige la cuenta del CALLER, no de cualquier miembro), calcula `state` (`coming_soon` fijo del descriptor > `requires_connection` si no hay cuenta propia > `available`). Cero `if provider ==`.
- [ ] 1.5 [GREEN] `backend/app/modules/connectors/router.py`: `GET /connectors/{connector_id}/actions` (`Depends(get_current_membership)`, mismo patrón que `list_connectors`/`get_connector`).
- [ ] 1.6 Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_actions.py` en verde.

Commit 1: `feat(connectors): agrega catalogo de acciones por capability y GET /connectors/{id}/actions`

## Fase 2 — `POST /connectors/{id}/actions/probe` reutilizando el helper del 38

- [ ] 2.1 [RED] Crear `backend/tests/test_connectors_probe.py`: (a) Jira con `ConnectedAccount` propia + credenciales cifradas (patrón `test_connectors_credentials.py:46`, `httpx.MockTransport(handler)` sobre `JiraAdapter`) → `200` con `outcome="ok"` y detalle de proyectos verificados, sin persistir filas nuevas (contar `Connector`/`ConnectedAccount`/`ConnectionCredentials` antes/después, deben ser iguales); (b) sin cuenta propia (aunque otro miembro sí tenga) → `200` `outcome="requires_connection"`, cero llamadas HTTP externas; (c) credencial inválida/expirada → `200` `outcome="error"` con mensaje es-CO, sin excepción cruda; (d) conector `mcp` conectado → `list_resources` real vía `McpResourceReader` con transport fake; (e) conector de otra organización → `404`; (f) sin sesión → `401`. Falla hoy: el endpoint no existe.
- [ ] 2.2 [GREEN] `backend/app/modules/connectors/service.py`: `async def probe(self, organization_id, connector_id, membership) -> ProbeResultRead` — `self._require_connector`, resuelve la cuenta propia del caller (`only_user_id=membership.user_id`), arma el `AccessContext` provider-aware reutilizando lo existente: Jira → `encode_access_context` (`app/integrations/adapters/jira/adapter.py:123`, mismo patrón que `jira_import.service._decrypt_credentials`); MCP → `self._build_mcp_access_context` (ya existe en `service.py:783`, se reutiliza sin cambios); OAuth (m365/google) → `outcome="not_supported"` explícito hasta que 38 aterrice su ctx-builder. Con el `ctx` armado, DELEGA la selección de capability primaria y el `list_*(limit=1)` a `ConnectorService._run_readonly_probe(adapter, connector, ctx)` (del 38 — **si ya existe al aplicar el 39, se invoca tal cual; el 39 no reimplementa el orden de preferencia ni el ciclo read-only**). Mapea el resultado a `ProbeResultRead`.
- [ ] 2.3 [GREEN] `backend/app/modules/connectors/schemas.py`: `ProbeResultRead` (`ok, outcome, detail, count`), `outcome: Literal["ok", "requires_connection", "not_supported", "error"]`.
- [ ] 2.4 [GREEN] `backend/app/modules/connectors/router.py`: `POST /connectors/{connector_id}/actions/probe` (`Depends(get_current_membership)`, ruta ANIDADA bajo `/actions/` — decisión de reconciliación, no la ruta plana de `proposal.md`/`design.md`).
- [ ] 2.5 Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q backend/tests/test_connectors_probe.py` en verde; confirmar una sola definición de `_run_readonly_probe` en `service.py` (la del 38, sin duplicar).

Commit 2: `feat(connectors): agrega POST /connectors/{id}/actions/probe reutilizando el helper del 38`

## Fase 3 — Frontend: tarjeta expandida + panel de acciones

- [ ] 3.1 `frontend/src/entities/connector/connector.model.ts`: agregar `ConnectorAction` (`key, label, capability, state, kind, description`) y `ProbeResult` (`ok, outcome, detail, count`).
- [ ] 3.2 `frontend/src/entities/connector/connectors.service.ts`: `actions(connectorId)` (`GET .../actions`) y `probe(connectorId)` (`POST .../actions/probe`).
- [ ] 3.3 `frontend/src/pages/connections/connections.component.ts`: la tarjeta expandible llama `actions(connector.id)` al expandirse y pinta el panel iterando la respuesta — retira TODOS los `@if (connector.provider === 'jira')` / `@if (credential_kind === 'oauth')` / `@if (credential_kind === 'api_token' && provider !== 'mcp')` del bloque de acciones (el carve-out de "registrar credenciales", fuera del bloque de acciones, se conserva — Open Question del design). Estados: `available` botón habilitado (`navigate` navega, `execute` llama `probe()`); `requires_connection` deshabilitado + texto de ayuda "conecta tu cuenta primero"; `coming_soon` deshabilitado + insignia "Próximamente". `jira_import_file` se mapea al `openJiraImport()` existente (preview de archivo, sin regresión).
- [ ] 3.4 Ejecutar una acción `kind=execute` (probe) muestra spinner mientras corre y el resultado inline (`detail` en éxito, mensaje es-CO en error) sin bloquear el resto de la tarjeta.
- [ ] 3.5 `frontend/src/shared/i18n` (es-CO): claves nuevas del panel (etiquetas de acción fallback, texto de ayuda de `requires_connection`, insignia "Próximamente", mensajes de resultado del probe) — tuteo formal, sin voseo.
- [ ] 3.6 Verify: `cd frontend && npm run build && npm run lint`; checklist manual: expandir tarjetas Jira/M365/MCP en la misma vista, conectar/desconectar cuentas sigue funcionando (no regresión), `jira_import` en `coming_soon` no bloquea la importación por archivo.

Commit 3: `feat(connections): panel de acciones por capability desde GET /connectors/{id}/actions`

## Fase 4 — Verde total

- [ ] 4.1 `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` completo (incluye suites existentes de `connectors`/`jira_import`/`mcp` sin regresión).
- [ ] 4.2 `cd frontend && npm run build && npm run lint`.
- [ ] 4.3 Checklist manual completo de los escenarios de `specs/connector-action-panel/spec.md` (estados visuales, resultado del probe visible, `jira_import` estable, no regresión de conectar/desconectar).
- [ ] 4.4 Merge local a `preview` (sin PR nuevo); commits convencionales en español ya creados por fase (1→3); confirmar en `state.yaml` que `tasks: done` antes de iniciar `sdd-apply`.

## Trazabilidad de requisitos

- Acciones disponibles por conector derivadas de capabilities y estado de conexión (spec `connectors`) · 1.1-1.6
- Verificación puntual de conexión — probe (spec `connectors`) · 2.1-2.5
- Panel de acciones renderizado desde el endpoint, sin condicionales por proveedor (spec `connector-action-panel`) · 3.3
- Estados visuales de acción (disponible / requiere conexión / próximamente) · 3.3-3.4
- Resultado del probe visible en el panel · 3.4
- Punto de entrada estable de importación Jira (`jira_import`) · 1.2, 3.3
- No regresión de conexión y desconexión de cuentas · 3.3, 3.6
- Textos en español colombiano formal (tuteo) · 3.5
