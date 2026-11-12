# Proposal: 39 · Conector con panel de capacidades (de "conectado" a "útil")

## Intent

Tras conectar, la tarjeta de Conexiones solo muestra el badge "conectado" + la lista de cuentas: no dice qué PUEDE hacer el usuario. Las pocas acciones que existen están cableadas por proveedor en el template (`connector.provider === 'jira'`, `credential_kind === 'oauth'`), rompiendo la regla de oro del proyecto de leer el comportamiento DESDE las capabilities del adaptador. No existe endpoint que exponga, por conector, qué acciones habilita según sus `capabilities` (`integrations/ports.py`) y su estado de conexión. La OLA 4 (fase 4.4) pide convertir "conectado" en acciones visibles. 39 define el patrón de la tarjeta expandida y el panel de acciones por capability, base que los cambios 40 (import Jira usuario) y 41 (import admin) llenarán con flujos completos.

## Scope

### In Scope
- Backend `GET /connectors/{connector_id}/actions`: deriva del adaptador (`get_adapter(provider).capabilities`) ∩ un catálogo declarativo capability→acciones + estado de conexión (cuenta activa del caller/org), la lista de acciones. Cada acción: `key`, `label`, `capability`, `state` (`available` | `requires_connection` | `coming_soon`), `kind` (`navigate` | `execute`). Lectura abierta a cualquier miembro (como el resto de `GET /connectors`); 404 si el conector es de otra org.
- Catálogo declarativo por Capability (NUNCA `if provider==`): `tickets`(jira)→importar proyectos / importar historias / sincronizar; `mail`/`calendar`(m365/google)→leer correo / leer calendario; `external_resources`(mcp)→explorar recursos/herramientas.
- Acción "Probar/Sincronizar" mínima ejecutable donde hay soporte real: `POST /connectors/{connector_id}/probe` ejerce el puerto primario con `limit=1` (jira `list_tickets`, m365/google reader port, mcp `list_resources`), solo verificación puntual, no persiste.
- Frontend: tarjeta expandible con panel de acciones renderizado DESDE el endpoint (elimina el bloque hardcodeado por provider). Botones con estados: disponible (habilitado), requiere conexión (deshabilitado + hint), próximamente (deshabilitado + badge).
- Entrada de import Jira = punto de entrada que navega al flujo del 40; `coming_soon` hasta que 40 aterrice (o cableado si ya existe — se documenta la frontera). El preview de archivo Jira actual se pliega como acción "importar historias (archivo)" ya disponible.
- TDD backend del endpoint de acciones: happy (jira conectado → acciones con estados correctos), permisos (miembro autenticado; sin sesión 401), conector de otra org → 404.

### Out of Scope
- Flujos completos de importación (elegir proyecto → preview → importar): cambios 40/41.
- Reparación OAuth M365/Google: cambio 38 (prerequisito).
- Sync programado/scheduler; el probe es acotado (`limit=1`), no periódico.
- Nuevas capabilities en el enum (mail/calendar/tickets/external_resources ya existen).
- Escritura en sistemas externos (todo read-only).

## Capabilities

### New Capabilities
- `connector-action-panel`: tarjeta de conector expandida (frontend) que renderiza las acciones post-conexión por capability con estados (disponible / requiere conexión / próximamente), reemplazando los botones cableados por proveedor.

### Modified Capabilities
- `connectors`: nuevo `GET /connectors/{id}/actions` que expone las acciones disponibles derivadas de las capabilities del adaptador y el estado de conexión, más un `POST /connectors/{id}/probe` acotado.

## Approach

Catálogo `CAPABILITY_ACTIONS` (mapa Capability→descriptores de acción) resuelto en `ConnectorService`: intersecta las `capabilities` del adaptador con el catálogo y calcula cada `state` según exista una `ConnectedAccount` activa. Nuevo endpoint de lectura en `connectors/router.py` (membership) y `ConnectorActionRead` en schemas. `probe` ejerce el puerto primario con `limit=1`. Frontend: la página pide las acciones por conector y pinta el panel expandido desde la respuesta; se retiran los `@if provider==` del bloque de acciones. Cero migración: el catálogo vive en código.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/connectors/{router,service,schemas}.py` | Modified | Endpoint `actions` + `probe`; `ConnectorActionRead` |
| `backend/app/modules/connectors/actions_catalog.py` | New | Mapa declarativo capability→acciones |
| `backend/app/integrations/ports.py` | Read-only | `Capability` enum (sin cambios) |
| `frontend/src/pages/connections/connections.component.ts` | Modified | Tarjeta expandida + panel de acciones |
| `frontend/src/entities/connector/{connector.model.ts,connectors.service.ts}` | Modified | Tipo `ConnectorAction` + fetch de acciones |
| `frontend/src/shared/i18n/*` | Modified | Textos de acciones/estados (es-CO formal) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| 38 sin aplicar → OAuth M365/Google roto | Media | Acciones OAuth se muestran "requiere conexión" (correcto); gating suave, no bloquea |
| 40 aún no existe → import Jira sin destino | Alta | Punto de entrada `coming_soon`; destino se cablea al aterrizar 40 (frontera documentada) |
| Catálogo con `if provider==` regado (anti-patrón) | Media | Mapa declarativo por Capability, revisado en spec |
| Sin harness front | Alta | `ng build` + `eslint` + checklist manual; endpoint cubierto por tests backend |

## Rollback Plan

Revertir los commits del endpoint+catálogo backend, de la página/entidad/servicio front y de los textos i18n. Sin migración Alembic: el catálogo está en código, no en esquema.

## Dependencies

- `38-oauth-ms-google`: OAuth reparado para que M365/Google conecten de verdad (estado de conexión real).
- Existentes: `14` connectors, `17` glpi, `18` jira-import, `19` mcp (`Capability` enum + adaptadores + módulo `jira_import`).
- Downstream: `40-jira-import-usuario` y `41-jira-import-admin` llenan los flujos de importación.

## Success Criteria

- [ ] `GET /connectors/{id}/actions` devuelve acciones por capability con estados correctos (jira conectado → importar proyectos/historias/sincronizar; m365 → correo/calendario).
- [ ] 404 para conector de otra org; miembro autenticado lee; sin sesión 401.
- [ ] La tarjeta expandida renderiza el panel DESDE el endpoint (cero `if provider==` en el bloque de acciones).
- [ ] "Probar" ejecuta un read acotado real donde hay soporte; import Jira = punto de entrada al 40 (o "próximamente").
- [ ] Suite backend en verde; `ng build`/`eslint` en verde; textos de UI en español colombiano formal (tuteo).

## Proposal question round

Supuestos a validar (el sub-agente no puede preguntar en vivo): (1) el endpoint de acciones deriva las opciones del catálogo declarativo Capability→acciones + estado de conexión, no de un `if provider==`; (2) estado "conectado" = existe una `ConnectedAccount` activa (OAuth o api_token) para el caller/org; (3) lectura del endpoint abierta a cualquier miembro (coherente con `GET /connectors`), escritura/probe admin-manager si se decide en spec; (4) import Jira se muestra como punto de entrada `coming_soon` hasta que 40 aterrice, y el preview de archivo Jira actual se conserva como acción ya disponible; (5) el probe es una verificación puntual `limit=1`, no un sync programado. Segunda ronda disponible para revisar el alcance del probe (¿ejecutable ya para M365/Google/MCP o solo jira?) y el RBAC del probe.
