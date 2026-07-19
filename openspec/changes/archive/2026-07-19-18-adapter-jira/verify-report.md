```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:01ac1d1870c7cddcf1e35138d59b3271db019888
verdict: pass
blockers: 0
critical_findings: 0
requirements: 12/12
scenarios: 23/23
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v
test_exit_code: 1
test_output_hash: sha256:859d25fe5af59f76f897e98ea4e744c1f3c11442954b155405c61c151ed1f679
build_command: cd backend && mypy app/
build_exit_code: 0
build_output_hash: sha256:16113559ce257bb6e5a91b0aa64a7d1e22d37303e0cbfc5b3bb80f191155c18b
```

## Verification Report

**Cambio**: 18-adapter-jira (adaptador Jira Cloud solo-lectura, importador de issues de doble vía)
**HEAD verificado**: `01ac1d1` (11 commits de apply + 1 commit de corrección 4R)
**Modo**: Strict TDD

**Nota sobre `test_exit_code: 1`**: el proceso `pytest` retorna código 1 porque 13 pruebas *legacy* preexistentes fallan por un problema de entorno del servidor de pruebas vivo (`httpx.LocalProtocolError` sin `TEST_AUTH_TOKEN`), sin relación alguna con `jira`/`connectors`/`glpi`/`integrations`. Es el mismo baseline documentado y aceptado en el verify-report del cambio 17-adapter-glpi (`872 passed / 13 failed`, mismas 13 pruebas exactas). Se reproducen aquí de forma idéntica; ninguna es nueva ni fue introducida por este cambio.

### Completeness
| Métrica | Valor |
|--------|-------|
| Tareas totales (tasks.md) | 33 |
| Tareas completas | 33 |
| Tareas incompletas | 0 |

**Corrección de conteo**: el prompt de entrada citaba "tasks.md (43 [x])". El conteo directo real sobre `openspec/changes/18-adapter-jira/tasks.md` (verificado con `python3 -c "import re; ..."` contra `^- \[x\]`/`^- \[ \]`) da **33 tareas, todas marcadas `[x]`, cero sin marcar**. Se deja constancia de la discrepancia; no es bloqueante — el 100% de las tareas listadas está completo y coincide con `state.yaml` (`apply: done`) y `apply-progress`.

### Build & Tests Execution

**Build (mypy)**: ✅ Passed — `Success: no issues found in 252 source files`
```text
cd backend && mypy app/
exit 0
```

**Lint (ruff)**: ✅ Passed — `All checks passed!` (`ruff check app/ tests/`)

**Tests**: ✅ 949 passed / ❌ 13 failed (legacy, no relacionadas) / ⚠️ 0 skipped
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v
13 failed, 949 passed, 1 warning in 220.28s (0:03:40)

FAILED tests/test_attachments.py::test_upload_and_download_attachment
FAILED tests/test_attachments.py::test_upload_rejects_oversized_file
FAILED tests/test_attachments.py::test_download_requires_auth
FAILED tests/test_comments.py::test_create_comment_with_mentions
FAILED tests/test_comments.py::test_create_comment_empty_body_rejected
FAILED tests/test_sprint_close.py::test_close_sprint_sums_only_done_tasks
FAILED tests/test_sprint_close.py::test_close_sprint_moves_incomplete_to_backlog
FAILED tests/test_sprint_close.py::test_close_sprint_idempotent_409
FAILED tests/test_sprint_close.py::test_velocity_averages_closed_sprints
FAILED tests/test_subtasks.py::test_create_subtask_rejects_points
FAILED tests/test_subtasks.py::test_create_subtask_allows_hours
FAILED tests/test_task_key.py::test_create_task_assigns_task_key
FAILED tests/test_task_key.py::test_get_task_by_key
```
Aritmética: 942 (apply, 11 lotes) + 7 tests nuevos del fix 4R (`01ac1d1`) = 949. Baseline pre-cambio (17-adapter-glpi): 872 passed / 13 failed — mismas 13 fallas exactas, cero regresión.

Ejecución aislada de los 86 tests de `jira`/`connectors` relacionados (`test_jira_adapter_{dtos,mappings,normalizer,file_parser,client,registry,ticket_reader}.py`, `test_connectors_credentials.py`, `test_connectors_api_token.py`, `test_jira_import_router.py`): **86/86 passed**, 0 fallos, 0 skips.

**Coverage**: ➖ No disponible — `pytest-cov` no está instalado en el venv del proyecto. No es bloqueante (informativo, mismo tratamiento que en verify-reports previos de este backend).

**Alembic**: `alembic heads` → único head `0017` (`add_glpi_homologation`) — confirma que el 18 **no agrega migración propia**, tal como especifica `design.md`/`tasks.md`. `test_migrations_baseline.py::test_alembic_check_reports_no_diff_after_upgrade` pasa dentro de la suite (cubre el `alembic check` real contra una BD migrada con `alembic upgrade head`; la brecha de que `TEST_DATABASE_URL` usa `Base.metadata.create_all` en vez de `alembic upgrade head` es una brecha residual aceptada y documentada desde el cambio fundacional `01-fundacion-tdd`, no específica del 18).

### Spec Compliance Matrix — dominio `jira-import` (11 requisitos / 19 escenarios)

| Requisito | Escenario | Test | Resultado |
|-----------|-----------|------|-----------|
| Registro del adaptador | Registro sin editar el núcleo | `test_jira_adapter_registry.py::test_get_adapter_returns_the_jira_instance_after_import` | ✅ COMPLIANT |
| Registro del adaptador | Excluido de puertos no soportados | `test_jira_adapter_registry.py::test_excluded_from_ports_it_does_not_support` | ✅ COMPLIANT |
| Paginación API | Paginación completa hasta `isLast` | `test_jira_adapter_client.py::TestJiraClientPagination::test_list_issues_follows_next_page_token_until_is_last` | ✅ COMPLIANT |
| Paginación API | Import incremental por fecha (`since`) | `test_jira_adapter_client.py::TestJiraClientSinceFilter::test_since_wraps_the_jql_into_a_well_formed_updated_clause[×2]` + `test_jira_import_router.py::test_since_payload_reaches_the_search_request` (e2e) | ✅ COMPLIANT |
| Rate limit 429 | Reintento tras 429 con `Retry-After` | `test_jira_adapter_client.py::TestJiraClientRateLimit::test_retries_after_429_and_completes_on_the_next_2xx` + `test_retry_after_never_sleeps_past_the_backoff_ceiling` | ✅ COMPLIANT |
| Rate limit 429 | Reintentos agotados sin perder páginas previas | `test_jira_adapter_client.py::test_exhausted_retries_raises_without_losing_previously_fetched_pages` + `test_jira_import_router.py::test_exhausted_429_on_page_two_returns_200_with_page_one_truncated` (e2e, 200+`truncated=true`) | ✅ COMPLIANT |
| Custom fields configurables | Resolución por nombre vía `/field` | `test_jira_adapter_client.py::TestResolveFieldIds::test_resolves_story_points_and_sprint_by_name` | ✅ COMPLIANT |
| Custom fields configurables | Override cuando el nombre no calza | `test_jira_adapter_client.py::test_override_wins_when_the_name_does_not_calzar` | ✅ COMPLIANT |
| Import archivo = garantías API | CSV con BOM y columnas repetidas | `test_jira_adapter_file_parser.py::TestParseCsv::test_bom_is_stripped_and_repeated_labels_columns_merge_into_a_list` | ✅ COMPLIANT |
| Import archivo = garantías API | Convergencia API↔archivo | `test_jira_adapter_normalizer.py::TestNormalizeBatchConvergence::test_same_issue_via_api_and_file_normalizes_equivalently` + `test_jira_adapter_file_parser.py::test_parses_the_same_issue_as_the_csv_export` | ✅ COMPLIANT |
| Archivo malformado | Columna requerida ausente → error controlado | `test_jira_adapter_file_parser.py::test_missing_issue_key_column_raises_a_controlled_error_with_no_rows` + `test_jira_import_router.py::test_malformed_file_propagates_the_controlled_parser_error` (e2e) | ✅ COMPLIANT |
| Homologación tipo/estado/prioridad | Valor desconocido → fallback + reporte | `test_jira_adapter_normalizer.py::test_unknown_type_falls_back_to_task_and_is_flagged` + `test_unknown_priority_falls_back_to_medium_and_is_flagged` | ✅ COMPLIANT |
| Homologación tipo/estado/prioridad | Estado por `statusCategory` | `test_jira_adapter_normalizer.py::test_unknown_status_resolves_via_status_category` | ✅ COMPLIANT |
| Assignee/labels crudos | Assignee crudo en el issue normalizado | `test_jira_adapter_normalizer.py::test_assignee_and_labels_are_preserved_raw` | ✅ COMPLIANT |
| Credencial inválida sin exponer secreto | Token inválido → error controlado sin filtrar | `test_jira_adapter_client.py::TestJiraClientAuthError::test_401_raises_a_controlled_error` + `test_no_secret_leaks_in_the_exception_text_or_logs` | ✅ COMPLIANT |
| Superficie REST permisos/multi-tenant | Import por API devuelve issues+resumen | `test_jira_import_router.py::TestImportViaApi::test_returns_normalized_issues_and_a_summary` | ✅ COMPLIANT |
| Superficie REST permisos/multi-tenant | Import por archivo mismo contrato | `test_jira_import_router.py::TestImportViaFile::test_returns_the_same_contract_as_the_api_via` | ✅ COMPLIANT |
| Superficie REST permisos/multi-tenant | Conector ajeno → error sin ejecutar import | `test_jira_import_router.py::test_foreign_org_connector_returns_404` (+ `test_member_cannot_trigger_an_import` para RBAC) | ✅ COMPLIANT |
| Frontera solo-lectura estricta | Ningún efecto secundario (Task/Sprint/Label) | `test_jira_import_router.py::TestReadOnlyBoundary::test_import_creates_no_task_sprint_or_label_rows` | ✅ COMPLIANT |

### Spec Compliance Matrix — delta `connectors` (1 requisito ADDED / 4 escenarios)

| Requisito | Escenario | Test | Resultado |
|-----------|-----------|------|-----------|
| Provisión de credenciales `api_token` | Admin provee `email`+`api_token` (cuenta creada, token no expuesto) | `test_connectors_credentials.py::test_admin_registers_jira_api_token_credentials_validated_via_myself` (+ genérico del 17: `test_connectors_api_token.py::test_admin_registers_api_token_credentials_encrypted_and_hidden`) | ✅ COMPLIANT |
| Provisión de credenciales `api_token` | Member sin permiso → 403 | `test_connectors_api_token.py::test_member_cannot_register_api_token_credentials` (genérico del 17, cubre cualquier `credential_kind=api_token`, incluido Jira) | ✅ COMPLIANT |
| Provisión de credenciales `api_token` | Conector de otra organización → 404 | `test_connectors_api_token.py::test_register_credentials_against_foreign_org_connector_returns_404` (genérico del 17) | ✅ COMPLIANT |
| Provisión de credenciales `api_token` | Reenvío del mismo token actualiza sin duplicar | `test_connectors_credentials.py::test_resending_the_same_jira_account_updates_credentials_without_duplicating` | ✅ COMPLIANT |

**Compliance summary**: 23/23 escenarios COMPLIANT (19 jira-import + 4 connectors delta). 0 UNTESTED, 0 FAILING, 0 PARTIAL.

### Correctness (Static Evidence)
| Requisito | Estado | Notas |
|------------|--------|-------|
| Registro sin condicionales `if provider ==` | ✅ Implementado | `db_init.py` importa `app.integrations.adapters.jira`; el registro es automático vía `register_adapter` en import-time. Conviven 5 adaptadores: `fake`, `glpi`, `google`, `jira`, `microsoft365`. |
| Anti-SSRF `settings.jira.base_url` | ✅ Implementado | `JiraClient.__init__` valida `https://` + sufijo `*.atlassian.net` (`JIRA_BASE_URL_ALLOWED_SUFFIX`) **antes** de cualquier request — `JiraConfigError` levantado en el constructor. Tests: `test_rejects_base_url_without_https_before_any_request`, `test_rejects_host_outside_atlassian_net_before_any_request`. |
| Secreto `api_token` nunca expuesto | ✅ Implementado | Cifrado Fernet (contrato del 17); `test_no_secret_leaks_in_the_exception_text_or_logs` y `test_token_never_appears_in_the_response_or_logs` verifican ausencia del token tanto en excepciones como en la respuesta HTTP. |
| Techo de bytes ANTES de parsear (413) | ✅ Implementado (fix `01ac1d1`) | `router.py::import_via_file` compara `len(content)` contra `JIRA_FILE_MAX_BYTES` (10 MB) y levanta `AppException(status_code=413, code="jira_file_upload_too_large")` **antes** de invocar `service.import_via_file`/el parser. Test: `test_oversized_file_is_rejected_before_parsing`. |
| Bomba XLSX (filas/celdas) | ✅ Implementado | `file_parser.py` usa `openpyxl(read_only=True)` en streaming con contador incremental que aborta antes de terminar de leer la hoja (`JiraFileTooLarge`). Tests: `test_row_count_over_the_limit_is_rejected_without_finishing_the_read`, `test_bomb_file_over_the_row_limit_is_rejected_without_processing`, `test_cell_count_over_the_limit_is_also_rejected`. |
| `partial_issues` preservados ante 429 agotado (fix CRITICAL `01ac1d1`) | ✅ Implementado | `JiraRateLimited.partial_issues`/`normalized_partial_issues`/`partial_report` se rellenan en `client.list_issues`/`JiraAdapter.import_issues`; `JiraImportService` captura la excepción y responde `200` con `truncated=true`, `truncation_reason="rate_limited"`, conservando los issues de páginas previas — en vez de un `503` que los perdía (comportamiento pre-fix, corregido con RED demostrado). |
| Aislamiento por ítem malformado (`skipped_malformed`, fix `01ac1d1`) | ✅ Implementado | `normalize_api_batch`/`normalize_file_batch` capturan `AttributeError/TypeError/ValueError/KeyError` por ítem, registran `{index, key, error}` en `report.skipped_malformed` y continúan el batch sin abortar. Test: `test_a_malformed_api_issue_is_skipped_and_reported`. |
| RBAC `admin`/`manager` en la superficie REST | ✅ Implementado | `require_role` en `jira_import/router.py`; `test_member_cannot_trigger_an_import` → 403. |
| Multi-tenant (conector ajeno) | ✅ Implementado | `test_foreign_org_connector_returns_404`, `test_register_credentials_against_foreign_org_connector_returns_404`. |
| Sin persistencia (Task/Sprint/Label/insumos) | ✅ Implementado | `jira_import` no tiene `repository.py` propio; `TestReadOnlyBoundary::test_import_creates_no_task_sprint_or_label_rows` cuenta filas antes/después. |
| Sin migración Alembic propia | ✅ Implementado | `alembic heads` → único head `0017`; no existe `0018_*.py` en `backend/alembic/versions/`. |

### Coherence (Design)
| Decisión | ¿Se siguió? | Notas |
|----------|-----------|-------|
| `credential_kind` es propiedad exclusiva del 17; el 18 solo consume `api_token` | ✅ Sí | Lote 0 verificó ambas columnas antes de iniciar; `jira_import`/`connectors` no redefinen el enum ni la columna. |
| Orden estricto de apply 17→18 con verificación de head en vivo | ✅ Sí | Pre-flight `0.1`/`0.2`/`0.3` documentado y ejecutado; `17-adapter-glpi` ya archivado antes del Lote 1. |
| `JiraAdapter` satisface `port_for(Capability.tickets)` (Ticket fino) ADEMÁS de `import_issues()`/`parse_file()` (DTO rico) | ✅ Sí | Confirmado en `adapter.py` y probado por `test_jira_adapter_ticket_reader.py` (fix `01ac1d1`, precedente `test_adapter_glpi.py::TestGlpiAdapterListTickets`). |
| Un único normalizador para ambas vías (API/archivo) | ✅ Sí | `normalizer.normalize_api_issue`/`normalize_file_row` delegan a `_build_issue`; convergencia probada. |
| `settings.jira.*` como namespace de configuración (no `connectors.settings` genérico redefinido) | ✅ Sí | `mappings.py` lee overrides desde `settings.jira.{status_map,type_map,priority_map}`; `client.py` desde `settings.jira.{base_url,story_points_field,sprint_field}`. |
| Anti-SSRF por sufijo (no allowlist cerrado, a diferencia de GLPI) | ✅ Sí | Decisión documentada explícitamente en `design.md` y en el bloque de prosa del C4 (Lote 10); coherente con que Jira Cloud es por-tenant/ilimitado. |
| C4 documenta el nodo `jira`/`jira_import` con tildes correctas | ✅ Sí | El fix `01ac1d1` corrigió "paginacion"→"paginación" y "unico"→"único" en la línea `i_jira` del diagrama; el bloque de prosa extenso agregado en el Lote 10 ya tenía ortografía correcta. |
| `er-model.md` sin cambios propios del 18 | ✅ Sí | Única mención de "Jira" en `er-model.md` es genérica (lista de adaptadores 15-19), preexistente al 18, sin entidades nuevas. |

### TDD Compliance
| Check | Resultado | Detalle |
|-------|--------|---------|
| Evidencia TDD reportada | ✅ | `apply-progress` documenta ciclo RED→GREEN por lote (11 commits); el commit de fix `01ac1d1` documenta explícitamente "RED demostrado (7 tests nuevos)" para cada corrección. |
| Todas las tareas tienen test | ✅ | 33/33 tareas con test propio o cobertura N/A justificada (fixtures, docs, dependencias). |
| RED confirmado (archivos de test existen) | ✅ | 9 archivos de test del adaptador/módulo + `test_jira_adapter_ticket_reader.py` (nuevo en el fix) verificados en disco. |
| GREEN confirmado (tests pasan en ejecución real) | ✅ | 86/86 tests jira/connectors pasan; 949/962 de la suite completa (13 fallos son legacy preexistentes, no relacionados). |
| Triangulación adecuada | ✅ | Cada requisito con múltiples escenarios tiene múltiples casos de test (ej. homologación: 5 tests de tipo/estado/prioridad con valores DISTINTOS — no todos triviales/iguales). |
| Safety net en archivos modificados | ✅ | El fix `01ac1d1` modificó `service.py`/`normalizer.py`/`adapter.py`/`errors.py`/`dtos.py` ya existentes — la suite completa (942 tests previos) se ejecutó como red de seguridad antes de aceptar el fix; 949 confirma cero regresión. |

**TDD Compliance**: 6/6 checks pasados

---

### Test Layer Distribution
| Capa | Tests | Archivos | Herramientas |
|-------|-------|-------|-------|
| Unitario (DTOs, mappings, normalizador, parser, cliente con `MockTransport`) | 67 | 6 (`test_jira_adapter_{dtos,mappings,normalizer,file_parser,client,registry}.py`) | pytest + `httpx.MockTransport` (sin red real) |
| Integración (ASGI + Postgres real vía `TEST_DATABASE_URL`) | 19 | 3 (`test_jira_import_router.py`, `test_connectors_credentials.py`, `test_jira_adapter_ticket_reader.py`) | pytest-asyncio + `AsyncClient` + Postgres de pruebas |
| E2E | 0 | 0 | No aplica (backend-only, sin frontend en este cambio) |
| **Total (jira/connectors relacionados)** | **86** | **9** | |

---

### Changed File Coverage
Coverage analysis skipped — no hay herramienta de cobertura (`pytest-cov`) instalada en el venv del proyecto. No bloqueante.

---

### Assertion Quality
Escaneo de patrones prohibidos (tautologías `assert True`/`assert 1==1`, `toBe(true)`) sobre los 9 archivos de test de `jira`/`connectors`: **0 coincidencias**. Todas las aserciones revisadas manualmente (paginación, 429, SSRF, homologación, RBAC, frontera solo-lectura) llaman código de producción real y verifican valores concretos (no solo `toBeDefined()`/tipo). Sin acoplamiento a detalles de implementación (CSS, conteos de mock) — los tests usan `httpx.MockTransport` para simular el transporte HTTP, no para contar llamadas.

**Assertion quality**: ✅ Todas las aserciones verifican comportamiento real

---

### Quality Metrics
**Linter (ruff)**: ✅ Sin errores — `All checks passed!`
**Type Checker (mypy)**: ✅ Sin errores — `Success: no issues found in 252 source files`

### Issues Found

**CRITICAL**: Ninguno.

**WARNING**: Ninguno bloqueante para este cambio. Nota informativa: el prompt de entrada de esta fase citaba "tasks.md (43 [x])"; el conteo real y verificado es 33/33 — no afecta el veredicto (100% completo), se deja constancia por precisión.

**SUGGESTION**:
1. `pytest-cov` no está instalado en el venv de `backend/` — agregarlo permitiría reportar cobertura de línea/rama por archivo cambiado en futuros ciclos de verify (mismo hallazgo informativo que en 17-adapter-glpi).
2. Los 13 fallos legacy (`test_attachments`/`test_comments`/`test_sprint_close`/`test_subtasks`/`test_task_key`, todos `httpx.LocalProtocolError` por servidor vivo sin `TEST_AUTH_TOKEN`) siguen sin resolverse desde el baseline de 17-adapter-glpi. No son responsabilidad de este cambio, pero acumulan ruido en cada verify — considerar una tarea de mantenimiento dedicada fuera del flujo SDD de adaptadores.

### Verdict
**PASS**

12/12 requisitos y 23/23 escenarios COMPLIANT con test real que pasa (949 passed en la suite completa; 86/86 en ejecución aislada de jira/connectors). El fix `01ac1d1` corrigió el único CRITICAL de la revisión 4R previa (`partial_issues` perdidos ante 429 agotado, contradiciendo el spec literal "sin perder los issues ya extraídos en páginas previas") con 7 tests RED→GREEN nuevos, además de los 5 WARNING (aislamiento `skipped_malformed`, techo de bytes 413, cobertura de `since`, test de comportamiento del ticket reader, tildes en C4). ruff y mypy limpios. `alembic heads` confirma head único `0017` — el 18 no agrega migración ni cambia esquema. Frontera solo-lectura verificada con conteo real de filas antes/después. Convivencia de 5 adaptadores (`fake`, `glpi`, `google`, `jira`, `microsoft365`) sin regresión. Las 13 fallas restantes en la suite son legacy preexistentes, idénticas al baseline del cambio anterior (17-adapter-glpi), sin relación con este cambio.
