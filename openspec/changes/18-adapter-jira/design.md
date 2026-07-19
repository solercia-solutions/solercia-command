# Design: 18 · Adaptador Jira (importador de issues, doble vía)

## Technical Approach

Primer adaptador real sobre el núcleo del 14: paquete `app/integrations/adapters/jira/` que se
auto-registra (`register_adapter`, precedente `adapters/fake.py`) con `provider="jira"` y
`capabilities={tickets}`. Dos vías —API REST v3 y archivo CSV/XLSX— convergen en un **único
normalizador** que emite `NormalizedJiraIssue` + `NormalizationReport`. Es solo-lectura y **no
persiste**: entrega en memoria en la respuesta HTTP (el storage y la conversión a `Task` son del 22).
Consume el modelo `connectors/connected_accounts/connection_credentials` + Fernet del 14 y el contrato
`credential_kind=api_token` del 17. TDD estricto contra fixtures (JSON de `/search/jql`, CSV/XLSX
reales), sin HTTP ni ficheros externos en vivo.

## Architecture Decisions

### DTO propio `NormalizedJiraIssue`, no el `Ticket` del puerto

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| DTO rico `NormalizedJiraIssue` (18↔22) + adaptador satisface `TicketReaderPort` con el `Ticket` fino del 14 | El puerto genérico queda como mínimo común (registro/descubrimiento); el import lleva tipo/asignado/sprint/points/labels que el `Ticket` no modela | **Elegida** |
| Ampliar el `Ticket` del 14 | Contamina el DTO agnóstico con campos Jira; toca el núcleo | Rechazada |

### Vocabulario de normalización anclado al código real (no a un enum inexistente)

Hallazgo verificado en `backend/app/modules/tasks/models.py` + `app/shared/enums.py`:
`Task.status` es `String(60)` **libre**, validado por metodología (no hay enum global de estados);
`Task.task_type` es `String(40)` libre (enum `TaskType` solo `{task,bug,story,epic}`, **sin** `subtask`).
Por eso el normalizador **no** fuerza un enum de estado de plataforma: deriva un bucket estable de
`statusCategory` (`new→todo`, `indeterminate→in_progress`, `done→done`) y **conserva el nombre crudo**;
la resolución a columna/estado de tablero es del 22. `issue_type` usa `{epic,story,task,subtask,bug}`
(vocabulario CLAUDE.md; `subtask` cabe en la columna libre) con fallback `task`. `priority` mapea al
enum real `Priority` `{critical,high,medium,low}`.

### Provisión api_token: contrato del 17 (delta mínimo, reusable)

| Punto | Forma esperada (contrato-17) | Consumo 18 |
|-------|------------------------------|------------|
| `connectors.credential_kind` | columna `oauth\|api_token` (String) | conectores Jira usan `api_token` |
| Ruta de registro sin redirección | `POST /connectors/{id}/credentials` (no browser) | registra `email`+`api_token`, valida con `/myself`, cifra Fernet |
| `connection_credentials` | `access_token_enc`=token, `refresh_token_enc`=null, `token_type="api_token"` | reuso directo del modelo del 14 |

**Regla cerrada (ratificada)**: el 17 es el **único dueño** de `credential_kind`; el 18 solo lo **consume**
(valor `api_token`) y NUNCA lo crea ni lo redefine. Orden de apply estricto **17 → 18** con verificación de
head en vivo. Si al momento del apply/archivo `credential_kind` no existe en el modelo, la operación del 18
queda **BLOQUEADA** y lo reporta (alineado con `specs/connectors/spec.md` línea 4). La ruta `POST /credentials`
sí la añade el delta del 18 (requisito ADDED de su spec), pero solo consume la columna del 17.

### `connectors.settings JSONB` (aditivo) para site URL + overrides de mapeo

El modelo del 14 no tiene URL de sitio ni config de mapeos. Se añade `settings JSONB` **nullable**
(aditivo, reusable por GLPI): `{base_url, story_points_field?, sprint_field?, status_map?, type_map?,
priority_map?}`. Ausente → defaults en código + resolución por nombre vía `GET /rest/api/3/field`.
La migración `0018_*` encadena **estricto tras** la del 17 y **solo** agrega `connectors.settings` (nunca `credential_kind`).

### Superficie de import en módulo propio `app/modules/jira_import/`

`router → service` (sin repository: no escribe BD); reusa el repository de `connectors` para leer el
conector y descifrar credenciales. RBAC `require_role(admin, manager)` (coherente con la config de
conectores del 14, que estrena `require_role`). `python-multipart` (ya en requirements) habilita el upload.

## Data Flow

    Vía API:  POST /connectors/{id}/jira/import {jql,since,fields}
      → service: connectors.repo.get + crypto.decrypt(cred[api_token])
      → JiraClient (httpx, Basic email:token) → GET /rest/api/3/field (resuelve customfields por nombre)
      → GET /rest/api/3/search/jql (pagina nextPageToken hasta isLast; 429→Retry-After+backoff)
      → normalizer(raw_issue) ─┐
    Vía archivo: POST /connectors/{id}/jira/import-file (multipart .csv/.xlsx)
      → parser (utf-8-sig BOM; headers repetidos→listas) → normalizer(raw_row) ─┤
                                                                                 ▼
                             NormalizedJiraIssue[] + NormalizationReport  →  respuesta (sin persistir)

Convergencia: ambos raw (dict API / dict fila) entran al **mismo** `normalizer` → idéntico DTO.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/integrations/adapters/jira/__init__.py` | Create | Auto-registro `register_adapter(JiraAdapter())` |
| `app/integrations/adapters/jira/adapter.py` | Create | `JiraAdapter`: `provider`, `capabilities`, `port_for(tickets)`, `import_issues()`, `parse_file()` |
| `app/integrations/adapters/jira/client.py` | Create | httpx Basic auth; paginación `/search/jql`; `/field`; backoff 429 |
| `app/integrations/adapters/jira/file_parser.py` | Create | CSV (`csv`)/XLSX (`openpyxl`); headers repetidos→multivalor; BOM |
| `app/integrations/adapters/jira/normalizer.py` | Create | raw→`NormalizedJiraIssue`; ADF→texto; homologación + reporte |
| `app/integrations/adapters/jira/mappings.py` | Create | Defaults Jira Cloud (statusCategory, tipo, prioridad) + merge de overrides |
| `app/integrations/adapters/jira/dtos.py` | Create | `NormalizedJiraIssue`, `NormalizationReport` (frozen) |
| `app/modules/jira_import/{__init__,router,service,schemas}.py` | Create | Superficie REST import API/archivo (solo-lectura) |
| `app/modules/connectors/*` | Modify | Añade `settings JSONB` + ruta `POST /credentials` (api_token); **consume** `credential_kind` del 17, no lo crea |
| `alembic/versions/0018_*.py` | Create | Aditivo: **solo** `connectors.settings` (nullable); encadena estricto tras la migración del 17 |
| `app/db_init.py` | Modify | `import app.integrations.adapters.jira` (registro) |
| `app/main.py` | Modify | `include_router(jira_import_router, prefix=API_PREFIX)` |
| `backend/requirements.txt` | Modify | `httpx` (**ausente hoy**) + `openpyxl`; `python-multipart` ya presente |
| `docs/diagrams/c4-architecture.md` | Modify | Nodo `jira` en el engine `app/integrations` (C3) + módulo `jira_import` en la capa HTTP |

**ER (`er-model.md`)**: sin cambios de tablas por el 18 (no hay staging). El único delta de columna del 18 es
`connectors.settings` (nullable). `credential_kind` NO es del 18 (lo aporta y refleja el 17).

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class NormalizedJiraIssue:
    key: str                      # external_id (p.ej. "PROJ-42")
    title: str; description: str | None
    issue_type: str               # {epic,story,task,subtask,bug}; fallback task
    status_raw: str; status_bucket: str   # bucket ∈ {todo,in_progress,done} (statusCategory)
    priority: str                 # {critical,high,medium,low}; desconocida→medium
    assignee_raw: str | None      # accountId/email/displayName crudo → homologa el 22
    sprint_name: str | None; sprint_state: str | None
    story_points: float | None    # → estimation_points (Fibonacci) en el 22
    labels: tuple[str, ...]
    created_at: datetime | None
    source: str                   # "api" | "file"

@dataclass(frozen=True)
class NormalizationReport:
    total: int; normalized: int
    unmapped_types: dict[str, int]; unmapped_statuses: dict[str, int]; unmapped_priorities: dict[str, int]
    story_points_field: str | None; sprint_field: str | None   # id resuelto o None (ausente)
    source: str
```

Homologación (proposal, tabla de mapeo): tipo desconocido→`task`; estado por `statusCategory` cuando el
nombre no calza; prioridad Highest→critical/High→high/Medium→medium/Low·Lowest→low/desconocida→medium.
Nunca se descarta un issue; todo fallback suma al reporte.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — normalizer | Convergencia API↔archivo (mismo issue→mismo DTO); valores desconocidos→reporte; `subtask` y ADF→texto | fixtures paridad JSON/CSV; sin BD |
| Unit — client | Paginación `nextPageToken` hasta `isLast`; `/field` resuelve story_points/sprint por nombre; **custom field ausente**→`None` en reporte; `429`+`Retry-After`→backoff acotado; `401`→error claro sin filtrar token | httpx `MockTransport`; fixtures paginadas |
| Unit — file_parser | CSV con BOM y columnas `Labels`/`Sprint` repetidas→listas; XLSX con openpyxl; **CSV malformado→error claro** | `.csv`/`.xlsx` de ejemplo en `tests/fixtures/jira/` |
| Unit — registry | `get_adapter("jira")` retorna; excluido de puertos que no soporta | precedente 14 |
| Integration — jira_import | POST import (API vía credencial fake) y import-file (multipart) → issues+reporte; RBAC admin/manager (member/viewer→403); multi-tenant; **token nunca en respuesta/logs** | `client` ASGI + fixtures 01 |

## Threat Matrix

N/A para los ejes formales (routing, shell, subprocess, automatización VCS/PR, clasificación de
ejecutables): no hay ejecución de procesos; es cliente HTTP saliente + parseo de ficheros en proceso.
Riesgos de seguridad relevantes NO se omiten → requisitos con test RED:

| Requisito | Test RED planeado |
|-----------|-------------------|
| Anti-SSRF en `settings.base_url` | host fuera del patrón `*.atlassian.net` (o allowlist) → rechazado antes de la request |
| Secreto api_token | token nunca en respuesta ni logs; cifrado Fernet en reposo (`access_token_enc != plaintext`) |
| Bomba de descompresión XLSX | archivo con relación de expansión/tamaño excesivo → error acotado (límite de filas/celdas, openpyxl read-only) |
| Aislamiento multi-tenant | import de org A no ve conector/credencial de org B |

## Migration / Rollout

Aditivo `0018` (**solo** `connectors.settings` nullable); `down_revision` encadenado estricto tras la
migración del 17. Orden de apply **17 → 18**; si `credential_kind` no existe al aplicar, el 18 se BLOQUEA
y lo reporta (no lo crea). `requirements.txt` suma `httpx`+`openpyxl`.
El adaptador se auto-registra al importarse; rollback = revertir el merge → deja de registrarse, el núcleo
del 14 vuelve a quedar inerte, sin credenciales Jira vivas ni datos que migrar (no hay persistencia propia).

## Open Questions

- [x] **Propiedad de `credential_kind` — CERRADO**: dueño único = 17. El 18 solo consume `api_token`; nunca crea ni redefine el campo. Apply estricto 17 → 18 con verificación de head en vivo; `0018_*` encadena tras la migración del 17 y solo agrega `connectors.settings`. Si `credential_kind` falta al aplicar, el 18 se BLOQUEA y lo reporta (spec/connectors línea 4).
- [ ] Umbral exacto de la guarda anti-bomba XLSX (máx. filas/celdas) — fijar en tasks con un valor por defecto conservador.
