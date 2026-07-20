# Design: 39 · Conector con panel de capacidades (de "conectado" a "útil")

## Technical Approach

Backend expone `GET /connectors/{id}/actions` (miembro) y `POST /connectors/{id}/probe`
(miembro, sobre su propia cuenta). Las acciones se derivan de
`get_adapter(provider).capabilities` ∩ un catálogo declarativo `CAPABILITY_ACTIONS`
(clave = `Capability`, NUNCA `if provider==`); el `ConnectorService` decora cada
descriptor con su `state` según exista una `ConnectedAccount` activa visible al caller.
El probe ejerce el **puerto primario** del adaptador (`port_for(cap).<read>(limit=1)`),
sin método nuevo en el core (`ports.py` queda read-only). Frontend: tarjeta expandible
que pinta el panel DESDE el endpoint, retira `provider === 'jira'` del bloque de acciones
y mapea `action.key → handler`. Cero migración: el catálogo vive en código.

## Architecture Decisions

### Decisión 1: catálogo declarativo por `Capability` (no `actions()` en el port)

| Opción | Tradeoff | Decisión |
|---|---|---|
| **`CAPABILITY_ACTIONS: dict[Capability, tuple[ActionDescriptor,…]]` en `actions_catalog.py`; el service lo intersecta con `adapter.capabilities` y calcula `state`** | Una sola fuente declarativa; cero cambio en el core/adaptadores; el adaptador "declara" sus acciones transitivamente por las capabilities que ya declara | **Elegida** |
| Método `actions()` en `IntegrationAdapter` (port) | Toca `ports.py` (core) y obliga a los 6 adaptadores + fake a implementarlo; duplica el mapeo | Rechazada |
| Mapa por `provider` | Reintroduce el anti-patrón `if provider==` que 39 elimina | Rechazada |

Divergencia futura por proveedor (dos providers, misma capability, acciones distintas) queda
como seam abierto: un `actions()` opcional en el adaptador podría **anular** el catálogo sin
tocar la plantilla. MVP: solo capability-keyed.

### Decisión 2: probe ejerce el puerto primario existente (sin puerto nuevo)

| Opción | Tradeoff | Decisión |
|---|---|---|
| **`probe()` en el service resuelve la capability primaria (orden `tickets, external_resources, mail, calendar, external_tasks, meeting_notes`), toma `port_for(cap)` y llama su read con `limit=1`; `ProbeResult` tipado** | Capability-driven; reutiliza clientes ya guardados (jira, mcp SSRF); no toca el core | **Elegida** |
| `probe()` en el port/adaptador | Cambio de Protocol en el core, contra `reuse-adapter-registry` | Rechazada |

Assembly del `AccessContext` es inherentemente provider-shaped (jira = blob JSON →
`encode_access_context`; mcp = `_build_mcp_access_context`; oauth = access_token) — vive en
código provider-aware, precedente `jira_import._decrypt_credentials`, no en el template.
Real en **jira** (reusa el patrón de `jira_import`) y **mcp** (`list_resources`); **oauth
(m365/google)** devuelve `not_supported` (stub honesto) hasta que 38 aterrice y se agregue su
ctx-builder. Sin cuenta activa → `requires_connection`. `not_supported`/`requires_connection`
responden **200** con outcome tipado; 404 conector ajeno; 401 sin sesión.

### Decisión 3: seam del 40 = flag declarativa en el catálogo

`ActionDescriptor(kind="navigate", default_state="coming_soon", target_route=None)` para
`jira_import_projects`. El front pinta `coming_soon` como botón deshabilitado + tooltip
"Disponible próximamente". El 40 hace un cambio de **una línea** en el catálogo
(`default_state="available"`, cablea `target_route`) y registra la ruta — sin tocar la
plantilla. El preview de archivo actual se conserva como `jira_import_file` (state
`available`), cuyo `key` el front mapea a `openJiraImport()`.

## Data Flow

    GET /connectors/{id}/actions
      _require_connector(org,id)  ─404 ajeno
      adapter = get_adapter(provider)  ─(None → [])
      for cap in adapter.capabilities ∩ CAPABILITY_ACTIONS:
        state = coming_soon | (requires_connection si no hay cuenta activa visible) | available
      ▼  [{key,label,capability,state,kind}]
    POST /connectors/{id}/probe (member, cuenta propia)
      primary_cap → port_for(cap) → build ctx (jira/mcp real, oauth not_supported) → read(limit=1)
      ▼  ProbeResult{ok, outcome, detail, count}

## File Changes

| File | Action | Description |
|---|---|---|
| `backend/app/modules/connectors/actions_catalog.py` | Create | `ActionDescriptor` + `CAPABILITY_ACTIONS` + orden de capability primaria |
| `backend/app/modules/connectors/schemas.py` | Modify | `ConnectorActionRead`, `ProbeResultRead` |
| `backend/app/modules/connectors/service.py` | Modify | `list_actions`, `probe`, `_build_probe_context` |
| `backend/app/modules/connectors/router.py` | Modify | `GET /connectors/{id}/actions`, `POST /connectors/{id}/probe` (membership) |
| `backend/tests/test_connectors_actions.py` | Create | Derivación de acciones/estados; permisos; 404 |
| `backend/tests/test_connectors_probe.py` | Create | Probe jira real; sin cuenta; oauth `not_supported` |
| `frontend/src/entities/connector/connector.model.ts` | Modify | `ConnectorAction`, `ProbeResult` |
| `frontend/src/entities/connector/connectors.service.ts` | Modify | `actions(id)`, `probe(id)` |
| `frontend/src/pages/connections/connections.component.ts` | Modify | Tarjeta expandible; panel desde endpoint; `key→handler`; spinner+resultado; retira `provider === 'jira'` |
| Textos i18n Conexiones (es-CO) | Modify | Chrome del panel, hints de estado, labels de acción (fallback) |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class ActionDescriptor:
    key: str                       # p.ej. "jira_import_projects", "tickets_sync"
    label: str                     # es-CO (fallback; el front puede localizar por key)
    capability: Capability
    kind: Literal["navigate", "execute"]
    requires_connection: bool
    default_state: Literal["available", "coming_soon"]
    target_route: str | None = None

class ConnectorActionRead(BaseModel):    # {key,label,capability,state,kind}
    state: Literal["available", "requires_connection", "coming_soon"]

class ProbeResultRead(BaseModel):        # {ok,outcome,detail,count}
    outcome: Literal["ok", "requires_connection", "not_supported", "error"]
```
```ts
export interface ConnectorAction { key: string; label: string; capability: string;
  state: 'available'|'requires_connection'|'coming_soon'; kind: 'navigate'|'execute'; }
```

Catálogo MVP: `tickets` → `import_projects`(navigate, coming_soon), `import_stories_file`
(navigate, available), `tickets_sync`(execute, requires_connection); `mail`→`read_mail`,
`calendar`→`read_calendar`, `external_resources`→`explore_resources` (todas execute/probe).

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Backend unit | Derivación desde `capabilities` + estados; catálogo por Capability | Fake `_CapAdapter(capabilities=…)` registrado (patrón `_MailOnlyAdapter`) |
| Backend integr. | Actions: jira con cuenta activa → estados correctos; sin sesión 401; conector ajeno 404 | httpx AsyncClient + fixtures org/membership |
| Backend integr. | Probe: jira real (MockTransport, `list_tickets` limit=1); sin cuenta → `requires_connection`; oauth → `not_supported` | Reusa `JiraAdapter(transport=…)` |
| Build/Lint | Panel desde endpoint; cero `provider==` en acciones | `ng build`, `eslint .`, checklist manual |

## Threat Matrix

Las filas del matrix (docs-like paths, selección de repo git, commit/push/PR) son **N/A**:
39 no toca shell, subprocesos, git ni clasificación de ejecutables. El único borde de
integración de procesos es el egress del probe, que **reutiliza** clientes ya guardados
(jira client; mcp reader con `validate_mcp_url` SSRF) — sin nueva superficie de egress. Rutas
nuevas = rutas FastAPI estáticas; el seam de navegación del 40 = ruta Angular estática.

## Migration / Rollout

Sin migración Alembic (catálogo en código). 39 se apoya en 38 (OAuth real); si 38 no aplicó,
las acciones OAuth muestran `requires_connection` y el probe oauth `not_supported` (correcto,
no bloquea). Rollback: revertir commits de endpoint+catálogo, entidad/servicio/página front e
i18n.

## Open Questions

- [ ] Label de acción: ¿front localiza por `key` o consume el `label` es-CO del catálogo? (decidido: `label` del catálogo como default, `key`-override opcional en front, patrón `providerLabel`).
- [ ] Carve-out `provider !== 'mcp'` del botón "registrar credenciales" (establecimiento de conexión, fuera del bloque de acciones) — se mantiene; su limpieza es de un cambio futuro de establecimiento, no de 39.

## Forecast de tamaño (para sdd-tasks)

Estimado ~380–450 líneas (catálogo+descriptor ~70, service actions+probe ~110, schemas ~25,
router ~40, tests backend ~90, front panel+key-handler+probe ~110, modelo/servicio ~30, i18n
~25). `400-line budget risk: Medium`. `Decision needed before apply: No`. `Chained PRs
recommended: No` (corte opcional: slice backend endpoint+catálogo vs slice frontend).
