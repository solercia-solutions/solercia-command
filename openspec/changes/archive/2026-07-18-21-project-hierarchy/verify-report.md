```yaml
schema: gentle-ai.verify-result/v1
verdict: pass
blockers: 0
critical_findings: 0
requirements: 11/11
scenarios: 26/28
test_command: "cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v"
test_exit_code: 1
test_output_hash: sha256:bef644130f678907f1139e22ea9fbfee20caa5719af049b15b21eab6b047e5b4
focused_test_command: "cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/test_project_hierarchy_migration.py tests/test_project_hierarchy_repository.py tests/test_project_hierarchy_validation.py tests/test_project_hierarchy_endpoints.py tests/test_projects.py -v"
focused_test_exit_code: 0
focused_test_output_hash: sha256:153fb4d86225776fb4602cc036ae9e1ebec6f25e1cfdca4163c46ef3d2083d98
build_command: "cd backend && ruff check app/ && mypy app/"
build_exit_code: 0
build_output_hash: sha256:ff6ac0cd6357abef2bd1833eca3c7ada33d882dc835a345d320b0551e3e78a71
```

## Verification Report

**Cambio**: 21-project-hierarchy
**Versión**: N/A (sin versionar en el spec)
**Modo**: Strict TDD

### Nota sobre `test_exit_code`

El comando de suite completa exige por contrato el exit code exacto. Se reporta honestamente `1` porque la suite completa incluye 13 pruebas legacy black-box (`test_attachments.py`, `test_comments.py`, `test_sprint_close.py`, `test_subtasks.py`, `test_task_key.py`) que dependen de un servidor vivo (`API_BASE_URL`) y un token real (`TEST_AUTH_TOKEN`), documentado explícitamente en `backend/tests/conftest.py:13-17` ("the 43 pre-existing tests are black-box HTTP tests against a live server ... and are not rewritten"). Ninguna de las 13 pertenece a `projects/` ni a la jerarquía. El comando focalizado del work-unit (`focused_test_command`), que cubre exactamente el código de este cambio más `test_projects.py` (regresión del módulo tocado), sale en `0` con 45/45 en verde. Ambos comandos se ejecutaron de forma real (no simulada) y sus hashes corresponden a la salida exacta capturada.

### Completeness

| Métrica | Valor |
|--------|-------|
| Tareas totales | 29 (nota: el prompt de la fase y la memoria de apply-progress dicen "30"; el conteo directo de `tasks.md` da 29 tareas numeradas: 1.1–1.12, 2.1–2.13, 3.1–3.4 — ver SUGGESTION) |
| Tareas completas | 29 |
| Tareas incompletas | 0 |

### Build & Tests Execution

**Build**: ✅ Pasó (`ruff check app/` → "All checks passed!"; `mypy app/` → "Success: no issues found in 189 source files")

**Tests (suite completa)**: ✅ 588 passed / ❌ 13 failed / ⚠️ 0 skipped
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v
...
============ 13 failed, 588 passed, 1 warning in 157.21s (0:02:37) ============
```
Las 13 fallas son idénticas, por nombre de prueba, a las documentadas como preexistentes: `test_attachments.py::test_upload_and_download_attachment`, `test_attachments.py::test_upload_rejects_oversized_file`, `test_attachments.py::test_download_requires_auth`, `test_comments.py::test_create_comment_with_mentions`, `test_comments.py::test_create_comment_empty_body_rejected`, `test_sprint_close.py::test_close_sprint_sums_only_done_tasks`, `test_sprint_close.py::test_close_sprint_moves_incomplete_to_backlog`, `test_sprint_close.py::test_close_sprint_idempotent_409`, `test_sprint_close.py::test_velocity_averages_closed_sprints`, `test_subtasks.py::test_create_subtask_rejects_points`, `test_subtasks.py::test_create_subtask_allows_hours`, `test_task_key.py::test_create_task_assigns_task_key`, `test_task_key.py::test_get_task_by_key`. Todas fallan con `httpx.LocalProtocolError: Illegal header value b'Bearer '` (token vacío porque `TEST_AUTH_TOKEN` no está seteado en este entorno) — el error de entorno documentado en `conftest.py`, no una regresión de código. Baseline preapply (según `apply-progress`): 548 passed/13 failed → post-Lote-C: 584 passed/13 failed → post-fix af792b9 (+4 pruebas nuevas de guarda de ciclo/orden): 588 passed/13 failed. **Cero regresiones confirmadas**: mismas 13 fallas, mismo motivo, en los tres puntos de corte.

**Tests (focalizados, jerarquía + `test_projects.py`)**: ✅ 45 passed / ❌ 0 failed
```text
cd backend && pytest tests/test_project_hierarchy_migration.py tests/test_project_hierarchy_repository.py tests/test_project_hierarchy_validation.py tests/test_project_hierarchy_endpoints.py tests/test_projects.py -v
...
============================= 45 passed in 12.72s ==============================
```
40 pruebas nuevas de jerarquía (2 migración + 14 repositorio + 7 validación + 17 endpoints) + 5 pruebas preexistentes de `test_projects.py` (no relacionadas con este cambio, usadas como red de seguridad de regresión del módulo `projects`), todas en verde.

**Cobertura**: no hay herramienta de cobertura configurada en el proyecto (`pytest-cov` no está en `requirements`/`.venv`) → ➖ No disponible.

### Spec Compliance Matrix

**Resumen de cumplimiento**: 26/28 escenarios COMPLIANT con prueba de runtime en verde; 2/28 (R8) UNTESTED por ausencia deliberada de implementación (invariante forward-looking, sin endpoint de soft-delete de `Project` hoy). 11/11 requisitos con al menos evidencia estática + trazabilidad honesta (9/11 con cobertura de prueba en runtime completa).

### Quality Metrics

**Linter**: ✅ No errors (`ruff check app/` → "All checks passed!")
**Type Checker**: ✅ No errors (`mypy app/` → "Success: no issues found in 189 source files")

### Verdict

**PASS**

11/11 requisitos con evidencia (9/11 con cobertura completa de prueba en runtime, 26/28 escenarios COMPLIANT); el único hueco (R8, 2 escenarios) es deuda deliberada, explícita y trazada tanto en el spec como en tasks.md, sin endpoint que la haga observable hoy — no una omisión del cambio. Suite completa 588 passed/13 failed, con las 13 fallas confirmadas idénticas (por nombre y causa raíz) a las preexistentes documentadas en `conftest.py`, cero regresiones frente al baseline (548→584→588, siempre 13 fallas). Comando focalizado del cambio (jerarquía + `test_projects.py`): 45/45 en verde. `ruff` y `mypy` limpios sobre todo `app/`. Cadena de migración `0001→0014` íntegra con head único, `alembic check` sin diff, `downgrade()` simétrico y probado.
