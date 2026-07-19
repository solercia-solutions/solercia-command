# Proposal: 18 · Adaptador Jira (importador de issues, doble vía)

## Intent

Las entidades que hoy gestionan su trabajo en Jira necesitan traer sus issues a la plataforma sin retecleo manual. El núcleo hexagonal del cambio 14 ya define el puerto de lectura, el registro de adaptadores, el modelo de conectores/cuentas/credenciales cifradas y el adaptador `fake`, pero no existe ningún adaptador real. Este cambio implementa el **adaptador Jira solo-lectura** con **dos vías que convergen en el mismo pipeline de import y normalización**: (a) API REST de Jira Cloud para entidades con acceso, y (b) el reporte CSV/Excel exportado de Jira para entidades sin acceso API. El resultado es un conjunto de issues normalizados al vocabulario del puerto/plataforma. **La conversión a tareas de la plataforma y el almacenamiento de insumos son del cambio 22; aquí solo se trae y se normaliza.** Entregable backend-only.

## Scope

### In Scope
- **Adaptador Jira** que implementa el protocolo de adaptador del 14 (se registra en import-time con `provider="jira"`, declara la capacidad de issues/tickets; el núcleo lo descubre sin `if provider == ...`).
- **Vía API REST** (Jira Cloud): consulta paginada de issues por JQL, selección de campos, resolución de custom fields (story points/sprint), manejo de paginación y rate limits (`429` + `Retry-After`).
- **Vía archivo**: parser del reporte CSV/Excel (`.csv`/`.xlsx`) exportado de Jira, tolerante a columnas multivalor repetidas (labels, sprint) y a BOM/encoding.
- **Modelo normalizado de issue** (`NormalizedJiraIssue`) anclado al vocabulario del `Task` de la plataforma: `title`, `description`, `issue_type` → `task_type` (epic/story/task/subtask/bug), `status`, `priority`, `assignee` (crudo), `sprint` (nombre/estado), `story_points` → `estimation_points`, `labels`, `key`/`external_id`.
- **Homologación de valores** Jira → enums de la plataforma (tipo, estado, prioridad) con fallback seguro y **reporte de valores no homologados** (nunca se descarta un issue).
- **Provisión de credenciales por API token** (Basic auth) reutilizando `connection_credentials` + cifrado Fernet del 14, para conectores que NO usan el baile OAuth `authorize`/`callback`.
- **Superficie REST** que dispara un import (por API o por archivo cargado) y **devuelve** los issues normalizados + un resumen (conteos, no homologados), con permisos y multi-tenant.

### Out of Scope
- Convertir issues en `Task` de la plataforma; crear sprints, labels o proyectos (cambio 22).
- **Almacenar** los issues normalizados como ítems de entrada persistidos (el storage de insumos es del cambio 22).
- Homologar el `assignee` de Jira contra usuarios de la plataforma (se conserva el identificador crudo; la resolución es del 22, análoga a la cola de "sin homologar" del 17-GLPI).
- Escritura hacia Jira (crear/editar issues); los puertos son solo-lectura.
- Otros adaptadores (15, 16, 17, 19) y cualquier cambio en `frontend/`.

## Capabilities

### New Capabilities
- `jira-import`: adaptador Jira, pipeline de import de doble vía (API REST + archivo CSV/Excel), modelo normalizado de issue, homologación con reporte de no homologados y superficie REST de import solo-lectura.

### Modified Capabilities
- `connectors`: añadir la **provisión de credenciales por API token** (Basic auth) para conectores sin flujo OAuth `authorize`/`callback`, reutilizando `connection_credentials` + Fernet. Es la generalización que también consumirá el 17-GLPI (misma consideración de api_token); el delta debe mantenerse mínimo y compatible con el modelo del 14.

## Approach

**Autenticación primaria elegida: API token (Basic auth) de Jira Cloud.** Es la vía de menor barrera para una entidad que solo quiere importar: el usuario crea un API token en `id.atlassian.com` y se autentica con `email:api_token` (header Basic) contra `https://{site}.atlassian.net/rest/api/3/...`, sin registrar una app OAuth ni consentimiento de administrador. OAuth 2.0 (3LO) queda como **vía futura documentada**: encaja sin cambios en `authorize_url`/`exchange_code` del protocolo del 14 cuando la organización registre una app Atlassian. El API token se persiste cifrado (Fernet) en `connection_credentials` (`access_token_enc` = token, `refresh_token_enc` = null, `token_type = "api_token"`); el `Connector` guarda el `provider="jira"` y la URL del sitio; el `email`/identificador de cuenta va en `connected_accounts.external_account_id`. **Ambas vías (API y archivo) desembocan en el mismo normalizador**, que produce `NormalizedJiraIssue` y garantiza que el mismo issue rinda el mismo resultado por cualquier vía.

### Mapeo Jira → modelo normalizado → plataforma

| Campo Jira | API REST (v3) | Columna CSV/Excel | Normalizado | Ancla en la plataforma |
|-----------|---------------|-------------------|-------------|------------------------|
| Key | `key` | `Issue key` | `key`/`external_id` | Referencia externa |
| Tipo | `fields.issuetype.name` | `Issue Type` | `issue_type` | `task_type`: epic/story/task/subtask/bug (homologación) |
| Resumen | `fields.summary` | `Summary` | `title` | `Task.title` |
| Descripción | `fields.description` (ADF) | `Description` | `description` | `Task.description` |
| Estado | `fields.status.name` (+ `statusCategory`) | `Status` | `status` | enum: backlog/to_do/in_progress/in_review/done/cancelled |
| Prioridad | `fields.priority.name` | `Priority` | `priority` | enum: critical/high/medium/low |
| Asignado | `fields.assignee` (accountId/email/displayName) | `Assignee` | `assignee` (crudo) | homologación de usuario → cambio 22 |
| Sprint | `fields.customfield_10xxx` (Agile) | `Sprint` (repetida) | `sprint` (nombre/estado) | `Sprint` (no se crea aquí) |
| Story points | `fields.customfield_10xxx` | `Story Points` / `Custom field (Story Points)` | `story_points` | `estimation_points` (Fibonacci) |
| Labels | `fields.labels[]` | `Labels` (repetida) | `labels` | `Label` (homologación → 22) |
| Creado | `fields.created` | `Created` | `created_at` | metadato |

Homologación con fallback y reporte: tipo desconocido → `task`; estado por `statusCategory` (To Do/In Progress/Done) cuando el nombre no calza; prioridad Highest→critical, High→high, Medium→medium, Low/Lowest→low, desconocida→medium. Los custom field IDs de story points/sprint varían por instancia: en la vía API se resuelven por nombre vía `GET /rest/api/3/field`; en la vía archivo, por encabezado de columna.

### Paginación y rate limits (vía API)

- **Paginación por token** (`GET /rest/api/3/search/jql`): iterar con `nextPageToken`/`maxResults` hasta `isLast`; `fields` acota el payload. Se documenta la paginación por offset (`startAt`/`maxResults`/`total`) del `/search` legado como respaldo.
- **Rate limits**: honrar `429 Too Many Requests` con `Retry-After` (backoff exponencial + jitter, reintentos acotados). Import incremental por JQL (`updated >= :desde`) para no re-traer todo.
- **Archivo**: sin rate limits; retos son tamaño (lectura por filas), encoding/BOM UTF-8 y columnas multivalor repetidas; `.xlsx` vía openpyxl, `.csv` estándar.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/integrations/adapters/jira/` | New | Adaptador Jira (cliente API + parser de archivo + normalizador + homologación); se auto-registra |
| `backend/app/modules/connectors/` | Modified | Endpoint de provisión de credenciales por API token (no-OAuth), reusando crypto + `connection_credentials` |
| `backend/app/modules/jira_import/` (o dentro de connectors) | New | Superficie REST que dispara import (API/archivo) y devuelve issues normalizados + resumen |
| `backend/tests/` | New | Fixtures JSON de la API (paginada + `429`) y CSV/`.xlsx` de ejemplo; pruebas de contrato/normalización/homologación |
| `backend/requirements.txt` | Modified | `openpyxl` (lectura `.xlsx`); `httpx` ausente en runtime (solo en `requirements-dev.txt`) → se promueve a `requirements.txt` en el apply |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Custom field IDs (story points/sprint) varían por instancia | High | Resolución por nombre vía `/field`; override configurable; fixtures parametrizadas |
| Homologación ambigua de tipo/estado/prioridad (workflows custom de Jira) | High | Fallback seguro + reporte de no homologados; nunca descartar el issue |
| El 14 solo provisiona credenciales por OAuth; API token no encaja en `authorize`/`callback` | Med | Delta mínimo en `connectors` (provisión por token), reutilizable por 17-GLPI; frontera lista para back-port al 14 |
| API token es secreto de larga vida (Basic auth) | Med | Cifrado Fernet (reuso del 14), jamás en logs/respuestas, scoped por org/usuario |
| Rate limits / organizaciones grandes | Med | `Retry-After` + backoff; import incremental por `updated` |
| Deriva del formato de export CSV/Excel (columnas según configuración) | Med | Parser tolerante + validación explícita de columnas requeridas |
| Endpoint `/search` legado deprecado | Low | Usar `/search/jql` con paginación por token; offset solo como respaldo |

## Rollback Plan

Área nueva y aislada (adaptador + pipeline de import). Rollback = revertir el merge: el adaptador Jira deja de auto-registrarse y el núcleo del 14 vuelve a quedar inerte (solo el `fake`). El delta en `connectors` (provisión por token) es aditivo; si se revierte, no quedan credenciales Jira vivas y no se afecta el flujo OAuth existente. Sin persistencia propia de insumos, no hay datos que migrar de vuelta.

## Dependencies

- **14-integration-ports archivado** (puerto, registro, protocolo de adaptador, modelo `connectors`/`connected_accounts`/`connection_credentials`, cifrado Fernet, adaptador `fake`).
- `openpyxl` como dependencia nueva de backend (lectura `.xlsx`); `httpx` ya existe.
- Habilita el cambio 22-intake-classifier, que consumirá los issues normalizados para almacenarlos y convertirlos en tareas.

## Success Criteria

- [ ] El adaptador Jira se registra en import-time; `get_adapter("jira")` lo devuelve y queda excluido de puertos que no soporta.
- [ ] Vía API: paginación completa (hasta `isLast`), resolución de custom fields y backoff ante `429`, verificados con fixtures JSON.
- [ ] Vía archivo: parseo de CSV y `.xlsx` de ejemplo con columnas multivalor y BOM.
- [ ] **Convergencia**: el mismo issue por API y por archivo produce el mismo `NormalizedJiraIssue`.
- [ ] Mapeo completo de tipo/estado/prioridad/asignado/sprint/story points/labels, con reporte de valores no homologados.
- [ ] Credencial por API token cifrada en `connection_credentials`; token nunca en respuestas ni logs.
- [ ] El import es solo-lectura: no crea `Task`, sprints, labels ni proyectos, ni persiste insumos (frontera con el 22 respetada).

## Ronda de preguntas de propuesta

> Ejecutor delegado (sin pregunta en vivo). Supuestos a ratificar antes de spec/design:

1. **Auth primaria**: ¿se confirma API token (Basic auth) como vía primaria y OAuth 3LO como futura documentada —asumido—, o la entidad ya tiene una app OAuth registrada y prefiere 3LO desde ya?
2. **Ubicación de la provisión por token**: ¿delta mínimo en `connectors` (endpoint de credenciales no-OAuth, reutilizable por GLPI) —asumido—, o back-port al 14, o endpoint local del 18?
3. **Handoff con el 22**: ¿el import solo-lectura DEVUELVE los normalizados en la respuesta (sin persistir) —asumido— o se necesita una tabla de staging mínima ya en el 18? (El storage de insumos es del 22.)
4. **Estrictitud de la homologación**: ¿fallback seguro + reporte de no homologados —asumido— o se rechaza el import si hay tipos/estados sin mapear?
5. **Homologación de assignee/labels**: ¿se conserva el crudo y se difiere al 22 —asumido, como el 17-GLPI— o se intenta homologar usuarios/labels ya en el 18?
