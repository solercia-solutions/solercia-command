# Tasks: 18 · Adaptador Jira (importador de issues, doble vía)

## Notas de alcance (ajuste de coordinación aplicado)

`connectors.settings` (JSONB) **ya no es del 18**: la agrega el **17** en su propia migración,
junto a `credential_kind`. El 18 **no tiene migración Alembic propia** — no cambia esquema. Los
mapeos de configuración de Jira viven en el namespace **`settings.jira.*`** del conector
(`base_url`, `story_points_field`, `sprint_field`, `status_map`, `type_map`, `priority_map`).
El pre-flight del Lote 0 verifica que **ambas** columnas (`credential_kind` y `settings`) existan
antes de continuar; si falta alguna, el apply queda **BLOQUEADO** y se reporta. No hay tarea de
`er-model.md` (sin cambio de esquema propio); se mantiene la de `c4-architecture.md`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2200–2800 (7 archivos del adaptador + 4 del módulo `jira_import` + delta `connectors` + 4 fixtures + ~9 archivos de test) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | PR único a `feat/consume-solercia-ui`, 11 commits por lote (size:exception) |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|------------------|--------------------|
| 0 | Pre-flight: orden 17→18, `credential_kind`+`settings` en el modelo | PR 1 | N/A (verificación de estado, no test) | `cd backend && alembic heads` (real) | N/A — sin diff |
| 1 | Fixtures Jira (JSON API, CSV/XLSX, malformado, bomba) | PR 1 | N/A (solo fixtures) | N/A — sin código | Eliminar `backend/tests/fixtures/jira/` |
| 2 | DTOs + tablas de mapeo | PR 1 | `pytest tests/test_jira_adapter_dtos.py tests/test_jira_adapter_mappings.py -v` | N/A — lógica pura | Eliminar `dtos.py`, `mappings.py` + tests |
| 3 | Normalizador + convergencia API↔archivo | PR 1 | `pytest tests/test_jira_adapter_normalizer.py -v` | N/A — lógica pura | Eliminar `normalizer.py` + test |
| 4 | Parser de archivo + guarda antibomba XLSX | PR 1 | `pytest tests/test_jira_adapter_file_parser.py -v` | N/A — opera sobre fixtures en memoria | Eliminar `file_parser.py` + test + fixtures |
| 5 | Cliente API Jira (paginación/429/SSRF/401) | PR 1 | `pytest tests/test_jira_adapter_client.py -v` | httpx `MockTransport` (sin red real) | Eliminar `client.py` + test |
| 6 | Registro del adaptador en el núcleo | PR 1 | `pytest tests/test_jira_adapter_registry.py -v` | Import real vía `app/db_init.py` en arranque de pruebas | Eliminar `adapter.py`, `__init__.py` + revertir import en `db_init.py` |
| 7 | Delta `connectors`: credenciales por `api_token` | PR 1 | `pytest tests/test_connectors_credentials.py -v` | `TEST_DATABASE_URL=... pytest` (ASGI + Postgres test) | Eliminar ruta `POST /credentials` + test; OAuth existente intacto |
| 8 | Superficie REST `jira_import` (API + archivo) | PR 1 | `pytest tests/test_jira_import_router.py -v` | `TEST_DATABASE_URL=... pytest` (ASGI end-to-end, credencial fake) | Eliminar `app/modules/jira_import/` + `include_router` en `main.py` |
| 9 | Promoción de dependencias runtime | PR 1 | `pytest tests/ -k jira -v` (smoke) | `pip install -r backend/requirements.txt` (real) | Revertir líneas agregadas en `requirements.txt` |
| 10 | Documentación C4 | PR 1 | N/A — solo documentación | N/A | Revertir sección agregada en `c4-architecture.md` |

## Lote 0 — Verificación de orden y precondiciones (bloqueante, sin diff)

- [x] 0.1 Ejecutar `cd backend && alembic heads` en vivo; confirmar head único. El 18 no fija `down_revision` propio (sin migración propia). **Verificado**: head único `0017` (`add_glpi_homologation`).
- [x] 0.2 Verificar que el modelo `connectors` expone **tanto** `credential_kind` **como** `settings` (columnas del 17). Si falta cualquiera → apply del 18 **BLOQUEADO**, reportarlo y detener el lote. **Verificado**: ambas columnas presentes en `app/modules/connectors/models.py`.
- [x] 0.3 Confirmar en `state.yaml`/`depends_on` que `17-adapter-glpi` está `archived` antes de iniciar el Lote 1. **Verificado**: `openspec/changes/archive/2026-07-19-17-adapter-glpi/`, fases `apply`/`archive` en `done`.

## Lote 1 — Fixtures reales (RED, sin código de producción)

- [x] 1.1 `backend/tests/fixtures/jira/search_page1.json`, `search_page2.json` (paginación `nextPageToken`/`isLast`) y `search_429.json` (`Retry-After`).
- [x] 1.2 `backend/tests/fixtures/jira/fields.json` (`GET /field`: "Story Points"→`customfield_10032`, sprint field).
- [x] 1.3 `backend/tests/fixtures/jira/export.csv` (BOM UTF-8, `Labels`/`Sprint` repetidas) y `export.xlsx` equivalente (mismo issue que 1.1).
- [x] 1.4 `backend/tests/fixtures/jira/export_malformado.csv` (sin columna "Issue key") y fixture/generador de `export_bomba.xlsx` (>50.000 filas o >500.000 celdas).

## Lote 2 — DTOs y tablas de mapeo (RED→GREEN)

- [x] 2.1 RED `backend/tests/test_jira_adapter_dtos.py`: `NormalizedJiraIssue`/`NormalizationReport` frozen, campos completos.
- [x] 2.2 GREEN `backend/app/integrations/adapters/jira/dtos.py`.
- [x] 2.3 RED `backend/tests/test_jira_adapter_mappings.py`: defaults Jira Cloud (tipo/estado/prioridad) + merge con overrides de `settings.jira.{status_map,type_map,priority_map}`.
- [x] 2.4 GREEN `backend/app/integrations/adapters/jira/mappings.py`.

## Lote 3 — Normalizador (RED→GREEN) — R7, R8, convergencia (parte de R5)

- [x] 3.1 RED `backend/tests/test_jira_adapter_normalizer.py`: tipo desconocido→`task`+reporte; estado por `statusCategory`; prioridad desconocida→`medium`+reporte; `assignee`/`labels` crudos; ADF→texto; `subtask` soportado.
- [x] 3.2 RED: mismo issue (fixture 1.1 vs fila de 1.3) → `NormalizedJiraIssue` equivalente.
- [x] 3.3 GREEN `backend/app/integrations/adapters/jira/normalizer.py`.

## Lote 4 — Parser de archivo (RED→GREEN) — R5, R6, guarda antibomba XLSX

- [x] 4.1 RED `backend/tests/test_jira_adapter_file_parser.py`: CSV con BOM y columnas repetidas→listas; XLSX vía `openpyxl`; columna "Issue key" ausente→error controlado con columnas faltantes, sin fila normalizada.
- [x] 4.2 RED: archivo con **>50.000 filas o >500.000 celdas** → error claro y acotado, sin procesar.
- [x] 4.3 GREEN `backend/app/integrations/adapters/jira/file_parser.py` con guarda de límite (50.000 filas / 500.000 celdas, `openpyxl(read_only=True)`). Deviation: se agregó `app/integrations/adapters/jira/errors.py` (no listado explícitamente en design.md pero SÍ en el precedente `glpi/errors.py`) para centralizar `JiraFileFormatError`/`JiraFileTooLarge`; se extiende en el Lote 5 con los errores del cliente HTTP.

## Lote 5 — Cliente API Jira (RED→GREEN) — R2, R3, R4, R9, anti-SSRF

- [x] 5.1 RED `backend/tests/test_jira_adapter_client.py`: paginación `nextPageToken` hasta `isLast`; resolución story_points/sprint por nombre vía `/field`; override por `settings.jira.story_points_field`/`sprint_field`; custom field ausente→`None` en reporte.
- [x] 5.2 RED: `429`+`Retry-After`→backoff exponencial acotado y reintento; reintentos agotados→error controlado sin perder páginas previas.
- [x] 5.3 RED: `401`→error controlado sin filtrar el token en excepción ni en log.
- [x] 5.4 RED: `settings.jira.base_url` fuera de `*.atlassian.net`→rechazado antes de la request (anti-SSRF).
- [x] 5.5 GREEN `backend/app/integrations/adapters/jira/client.py` (httpx Basic `email:token`, backoff, validación de host). Agrega `JIRA_BASE_URL_ALLOWED_SUFFIX`/`JIRA_TIMEOUT_SECONDS`/`JIRA_PAGE_SIZE`/`JIRA_MAX_PAGES`/`JIRA_MAX_RETRIES`/`JIRA_MAX_BACKOFF_SECONDS` a `Settings` y extiende `errors.py` con `JiraUnavailable`/`JiraAuthError`/`JiraConfigInvalid`/`JiraRateLimited`/`JiraRequestFailed`.

## Lote 6 — Registro del adaptador (RED→GREEN) — R1

- [x] 6.1 RED `backend/tests/test_jira_adapter_registry.py`: `get_adapter("jira")` tras importar el paquete; excluido de puertos no soportados.
- [x] 6.2 GREEN `backend/app/integrations/adapters/jira/adapter.py` + `__init__.py` (`register_adapter`); wire en `backend/app/db_init.py`. `JiraAdapter` implementa `port_for(tickets)` con el `Ticket` fino (decisión de diseño) además de `import_issues()`/`parse_file()` con el DTO rico, consumidos directamente por `jira_import` (Lote 8).

## Lote 7 — Delta `connectors`: credenciales por `api_token` (RED→GREEN) — CR1

- [ ] 7.1 RED `backend/tests/test_connectors_credentials.py`: admin provee `email`+`api_token`→`ConnectedAccount`+`ConnectionCredentials` cifrada (`credential_kind=api_token`), respuesta sin token; `member`→403; conector de otra organización→404; reenvío del mismo token→actualiza sin duplicar.
- [ ] 7.2 GREEN `POST /connectors/{id}/credentials` en `backend/app/modules/connectors/router.py` + `service.py` (consume `credential_kind`/`settings` del 17, no los redefine).

## Lote 8 — Superficie REST `jira_import` (RED→GREEN) — R9(cierre), R10, R11

- [ ] 8.1 RED `backend/tests/test_jira_import_router.py`: `POST /connectors/{id}/jira/import` (JQL, credencial fake) → issues normalizados + resumen; `member`/`viewer`→403; conector de org ajena→404; token nunca en respuesta ni logs.
- [ ] 8.2 RED: `POST /connectors/{id}/jira/import-file` (multipart) → mismo contrato; archivo malformado propaga el error del Lote 4.
- [ ] 8.3 RED: tras el import, no existen `Task`/`Sprint`/`Label` nuevos ni filas de insumos persistidos (frontera solo-lectura).
- [ ] 8.4 GREEN `backend/app/modules/jira_import/{__init__,router,service,schemas}.py`; wire `include_router` en `backend/app/main.py`.

## Lote 9 — Dependencias runtime

- [ ] 9.1 Promover `httpx>=0.27` de `requirements-dev.txt` a `backend/requirements.txt`.
- [ ] 9.2 Agregar `openpyxl` a `backend/requirements.txt`; confirmar `python-multipart` ya presente (sin cambio).

## Lote 10 — Documentación C4

- [ ] 10.1 `docs/diagrams/c4-architecture.md`: nodo `jira` en el motor `app/integrations` (C3) + módulo `jira_import` en la capa HTTP.

## Trazabilidad Requisito → Lote

| Requisito | Lote(s) |
|-----------|---------|
| jira-import · Registro del adaptador | 6 |
| jira-import · Paginación vía API | 5 |
| jira-import · Rate limit 429 | 5 |
| jira-import · Custom fields configurables | 5 (override vía `settings.jira`) |
| jira-import · Import por archivo = garantías de la API | 3, 4 |
| jira-import · Archivo malformado | 4 |
| jira-import · Homologación tipo/estado/prioridad + reporte | 3 |
| jira-import · Assignee/labels crudos | 3 |
| jira-import · Credencial inválida sin exponer secreto | 5, 8 |
| jira-import · Superficie REST, permisos y multi-tenant | 8 |
| jira-import · Frontera solo-lectura estricta | 8 |
| connectors (delta) · Provisión de credenciales por `api_token` | 7 |
| Threat · Anti-SSRF en `settings.jira.base_url` | 5 |
| Threat · Secreto `api_token` nunca expuesto | 7, 8 |
| Threat · Bomba de descompresión XLSX (50.000 filas / 500.000 celdas) | 4 |
| Threat · Aislamiento multi-tenant | 7, 8 |
