## Verification Report

**Change**: 02-contrato-api
**Version**: N/A (delta specs sobre `api-conventions`)
**Mode**: Strict TDD

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 33 |
| Tasks complete | 33 |
| Tasks incomplete | 0 |

### Contexto crítico de esta verificación

El apply dejó documentado que el contenedor Docker del backend corre desde una **imagen bakeada sin volume mount**, por lo que los 43+ tests black-box preexistentes (`test_subtasks.py`, `test_attachments.py`, `test_comments.py`, `test_sprint_close.py`, `test_task_key.py`) se ejecutaban contra la imagen VIEJA durante el apply, no contra el working tree real. Antes de aceptar cualquier evidencia se ejecutó:

1. `docker compose up -d --build backend` — reconstrucción forzada desde el working tree actual. El log de arranque confirma `Running upgrade 0001 -> 0002, add_audit_fields` vía el entrypoint, y `Seed completed`.
2. Reset manual de `solercia_test` (`DROP SCHEMA public CASCADE`) — el mismo gotcha que documentó apply (`create_all` no hace `ALTER TABLE` sobre un esquema preexistente de una sesión previa).
3. Login real contra `admin@solercia.com` / `Admin123*` sobre el servidor reconstruido para obtener un JWT fresco (`TEST_AUTH_TOKEN`).
4. Suite completa ejecutada con `TEST_DATABASE_URL` + `API_BASE_URL=http://localhost:8000/api/v1` + `TEST_AUTH_TOKEN` reales — esta vez SÍ contra el working tree.

### Build & Tests Execution

**Build**: ✅ Passed
```text
docker compose up -d --build backend
# Running upgrade 0001 -> 0002, add_audit_fields
# Seed completed (organization, RBAC, users and demo data ensured).
# Uvicorn running on http://0.0.0.0:8000
```

**Tests**: ✅ 135 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
cd backend && pytest tests/ -v
(TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test
 API_BASE_URL=http://localhost:8000/api/v1
 TEST_AUTH_TOKEN=<JWT fresco vía /auth/login>)
======================= 135 passed, 1 warning in 19.70s =======================
```
El único warning es el `SAWarning` de ciclo de FK entre `dependencies/organizations/users` durante `alembic env.py`, ya documentado por apply como benigno (no afecta la creación real de las 22 constraints, solo el orden interno de sorting del autogenerate).

**Coverage**: ➖ No hay herramienta de coverage configurada en el proyecto (no bloqueante, informativo).

### TDD Compliance

`apply-progress` no incluye una tabla literal "TDD Cycle Evidence" con columnas RED/GREEN/TRIANGULATE/SAFETY NET/REFACTOR — reporta en su lugar un resumen técnico + evidencia de ejecución. El artefacto equivalente y más granular es `tasks.md`, donde cada tarea está etiquetada explícitamente `RED`/`GREEN` con su archivo de test y escenario (T01-T31). Se usó `tasks.md` como fuente primaria de evidencia RED/GREEN (mismo criterio aplicado en el verify de `01-fundacion-tdd`, precedente de este mismo proyecto) y se cruzó cada RED contra la existencia real del archivo y cada GREEN contra la ejecución real de la suite.

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reportada | ⚠️ Parcial | Sin tabla literal en apply-progress; `tasks.md` sí etiqueta RED/GREEN por tarea con archivo+escenario — evidencia equivalente aceptada |
| Todas las tareas con test | ✅ | 12 archivos de test nuevos/extendidos confirmados por `git diff --stat` sobre el rango de commits del cambio |
| RED confirmado (tests existen) | ✅ | 12/12 archivos verificados en el árbol de trabajo |
| GREEN confirmado (tests pasan) | ✅ | 135/135 tests pasan en ejecución real post-rebuild |
| Triangulación adecuada | ✅ | Cada endpoint paginable tiene 4 casos (compat, slice, sort inválido, sort/order válido); `test_audit_exposure.py` parametriza 11 modelos + 10 schemas |
| Safety Net en archivos modificados | ✅ | `test_sprint_close.py` (modificado, no nuevo) — los 8 tests preexistentes de ese archivo pasaron junto con el nuevo `test_close_sprint_stamps_updated_by_on_moved_tasks` |

**TDD Compliance**: 5/6 checks en verde, 1 parcial no bloqueante (formato del artefacto de evidencia, no ausencia de evidencia real).

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Integration (ASGI in-process) | ~95 | 10 | httpx AsyncClient + fixtures de 01 |
| Integration (black-box HTTP contra servidor vivo) | ~40 | 5 (preexistentes + `test_sprint_close.py`, `test_audit_stamping.py` parcialmente) | httpx contra `API_BASE_URL` real |
| Unit (estructural, sin BD) | ~20 | `test_pagination.py`, `test_audit_mixin.py`, parte de `test_audit_exposure.py` | pytest puro / `sqlalchemy.inspect` |
| **Total** | **135** | **~24** | |

---

### Assertion Quality

Escaneo de patrones prohibidos (tautologías, bucles fantasma, aserciones huérfanas, smoke-tests) sobre los 12 archivos de test nuevos/extendidos: `test_pagination.py`, `test_actor_id_dependency.py`, `test_audit_mixin.py`, `test_audit_stamping.py`, `test_audit_exposure.py`, `test_catalog_pagination.py`, `test_menus_pagination.py`, `test_nested_pagination.py`, `test_notifications_pagination.py`, `test_tasks_pagination.py`, `test_users_roles_pagination.py`, `test_sprint_close.py` (extensión).

- Cero tautologías (`assert True`, `assert 1 == 1`).
- Cero aserciones huérfanas sobre colecciones vacías sin test compañero no-vacío.
- Los únicos bucles encontrados iteran sobre literales fijos (nombres hardcodeados para fixtures, o la tupla fija `("created_by", "updated_by")` en `test_audit_exposure.py`) — nunca sobre resultados de query que pudieran estar vacíos; no son bucles fantasma.
- `test_close_sprint_stamps_updated_by_on_moved_tasks` (gate #2) usa DOS actores distintos (creador vs. quien cierra el sprint) deliberadamente, para que la aserción solo pase si el UPDATE masivo realmente re-estampa `updated_by` — no se puede confundir con "nunca se enhebró".
- `test_audited_model_declares_nullable_created_by_and_updated_by` y `test_audited_read_schema_exposes_optional_created_by_and_updated_by` están parametrizados sobre los 11 modelos y 10 schemas respectivamente (confirmado en la salida de `pytest -v`: 11 + 10 IDs individuales, todos PASSED).

**Assertion quality**: ✅ Todas las aserciones auditadas ejercitan comportamiento real con valores concretos.

---

### Quality Metrics
**Linter** (`ruff check .` desde `backend/`): ✅ All checks passed!
**Type Checker** (`mypy app` desde `backend/`, comando canónico del proyecto — `pyproject.toml` restringe `files=["app"]`): ✅ Success, no issues found in 106 source files.

Nota heredada de apply (no regresión): `mypy .` sin restringir a `app/` reporta 1 error preexistente y no relacionado (`asyncpg` sin stubs en `test_migrations_baseline.py`, de 01-fundacion-tdd) — fuera del scope configurado de mypy para este proyecto.

---

### Spec Compliance Matrix

**api-pagination.md**

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R1 Envelope opt-in | Sin params (byte-compat) | `test_list_*_without_params_is_byte_compatible` (10 endpoints) + live `GET /projects`, `GET /admin/menus`, `GET /projects/{id}/tasks` sin params | ✅ COMPLIANT |
| R1 Envelope opt-in | Error tipado heredado (sin cambios) | Comportamiento no tocado por este cambio; sin regresión en 135/135 | ✅ COMPLIANT (heredado, sin regresión) |
| R1 Envelope opt-in | `page`+`size` → slice correcto | `test_list_*_page_and_size_returns_correct_slice` (10 endpoints) | ✅ COMPLIANT |
| R2 Validación de límites | `page`/`size` fuera de rango → 422 | `test_pagination_params_page_below_one_is_422`, `test_pagination_params_size_above_max_is_422` + live `?page=0`, `?size=1000` | ✅ COMPLIANT |
| R3 Whitelist de sort | `sort` no permitido → 422 | `test_paginate_sort_outside_whitelist_raises_422_without_querying` + `test_list_tasks_sort_assignee_name_is_422` + live `GET /admin/users?sort=hashed_password` | ✅ COMPLIANT |
| R3 Whitelist de sort | `sort`+`order` válidos → 200 ordenado | `test_list_*_sort_*_desc_orders_results` (10 endpoints) | ✅ COMPLIANT |
| G1 `meta.tree` de menus se preserva | Con y sin paginación | `test_list_menus_without_params_is_byte_compatible_and_has_tree`, `test_list_menus_page_and_size_slices_data_but_tree_stays_whole`, `test_build_list_meta_preserves_foreign_keys_like_menus_tree` + live `GET /admin/menus` y `GET /admin/menus?page=1&size=2` | ✅ COMPLIANT |
| G3 `assignee_name` excluido | `?sort=assignee_name` → 422 | `test_list_tasks_sort_assignee_name_is_422` + live | ✅ COMPLIANT |

**audit-fields.md**

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| R4 Auditoría automática | `created_by` poblado en creación | `test_post_task_stamps_created_by_and_updated_by_with_actor_id` + live `POST /projects`, `POST /projects/{id}/tasks` | ✅ COMPLIANT |
| R4 Auditoría automática | `updated_by` poblado en modificación, `created_by` intacto | `test_patch_task_stamps_updated_by_via_http`, `test_service_layer_patch_stamps_different_editor_preserves_created_by` + live `PATCH /tasks/{id}` | ✅ COMPLIANT |
| R4 Auditoría automática | Filas preexistentes → NULL, sin fallo de serialización | `test_task_detail_exposes_null_audit_fields_for_a_seed_style_row` + live `GET /admin/menus`, `GET /admin/roles` (seed) | ✅ COMPLIANT |
| G2 UPDATE masivo (`close_sprint`) estampa `updated_by` | Cerrar sprint mueve tareas y re-estampa `updated_by` con un actor DISTINTO al creador | `test_close_sprint_stamps_updated_by_on_moved_tasks` | ✅ COMPLIANT |
| R5 Exposición de auditoría | Detalle/lista exponen `created_by`/`updated_by` | `test_audited_read_schema_exposes_optional_created_by_and_updated_by` (10 schemas parametrizados) + live (`GET /projects` expone ambos campos) | ✅ COMPLIANT |
| R5 Exposición de auditoría | `null` cuando no hay auditoría poblada | `test_task_detail_exposes_null_audit_fields_for_a_seed_style_row` + live | ✅ COMPLIANT |
| G4 Criterio de 11 modelos SoftDeleteMixin | Los 11 modelos (incl. `Menu` global) declaran las columnas | `test_audited_model_declares_nullable_created_by_and_updated_by` (11 IDs parametrizados, todos PASSED) + `rg AuditMixin` sobre los 11 `models.py` | ✅ COMPLIANT |
| G5 Filas del seed sin auditoría (aceptado) | `db_init.py` deja `NULL` permanente | `test_task_detail_exposes_null_audit_fields_for_a_seed_style_row` + live (menus/roles seed) | ✅ COMPLIANT |
| G6 Cobertura del artefacto de migración | `alembic check` sin diff tras `upgrade head` | `test_alembic_upgrade_head_creates_full_schema`, `test_alembic_check_reports_no_diff_after_upgrade` (de 01, cubre la revisión 0002) | ✅ COMPLIANT |

**Compliance summary**: 17/17 escenarios/gates compliant.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Migración `0002_add_audit_fields` encadena sobre `0001` | ✅ Implementado | `down_revision: str \| None = "0001"` confirmado en el archivo; `0001` tiene `down_revision = None` |
| `Notification` excluido de `AuditMixin` | ✅ Implementado | `Notification(PkMixin, TimestampMixin, TenantMixin, Base)` — sin `AuditMixin` ni `SoftDeleteMixin`, confirmado por inspección de código |
| `AuditMixin` mezclado en los 11 modelos | ✅ Implementado | Confirmado por `rg AuditMixin` en `alert_rules`, `attachments`, `comments` (`TaskComment`), `dependencies`, `menus`, `organizations`, `projects`, `roles`, `sprints`, `tasks`, `users` — exactamente 11 |
| `docs/API.md` documenta la superficie real | ✅ Implementado | Sección «Paginación» nueva (línea 36), 4 módulos antes no documentados (comments, attachments, notifications, alert-rules) presentes, `velocity`/`close`/`by-key`/`subtasks` documentados, bug de shape de `/admin/menus` corregido en el texto |
| Sin scope creep | ✅ Confirmado | `git show --stat` en `41268d8`, `903c057`, `312ee58` — únicamente rutas `backend/`, `openspec/changes/02-contrato-api/` y `docs/API.md`; cero rutas `frontend/` |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Paginación opt-in (sin params = comportamiento actual) | ✅ Yes | Confirmado en tests y en vivo — disparador es `page` o `sort`, nunca `size`/`order` solos |
| Mecánica reutilizable + whitelist de orden vía dict de `InstrumentedAttribute` | ✅ Yes | `pagination.py` implementado exactamente como diseñado; `SORTABLE_FIELDS` por módulo |
| Auditoría por asignación explícita en servicio (no event listeners) | ✅ Yes | `get_actor_id` enhebrado router→service→repository, tolera `None` |
| Alcance de auditoría = 11 modelos SoftDeleteMixin, migración aditiva única | ✅ Yes | Confirmado estructuralmente y en runtime |
| Corrección de gate #1 (`meta.tree` se preserva) | ✅ Yes | `build_list_meta()` solo añade/actualiza `page`/`size`/`total`, nunca remueve otras claves — verificado con test dedicado y en vivo |
| Corrección de gate #2 (UPDATE masivo estampa auditoría) | ✅ Yes | `close_sprint` enhebra `actor_id` hasta `.values(...)` — verificado con actor distinto al creador |
| Corrección de gate #3 (`assignee_name` fuera de whitelist) | ✅ Yes | Confirmado en test y en vivo |

### Issues Found

**CRITICAL**: None.

**WARNING**: None.

**SUGGESTION**:
1. No existe una prueba negativa explícita que confirme que `Notification` NO lleva `AuditMixin` (solo se confirma por inspección de código y por su ausencia en `AUDITED_MODELS`). Un test negativo dedicado evitaría un drift silencioso si alguien agrega `SoftDeleteMixin` a `Notification` en el futuro sin notar la exclusión documentada.
2. La evidencia TDD de apply-progress no sigue el formato literal de tabla "TDD Cycle Evidence" — se aceptó `tasks.md` (etiquetas RED/GREEN por tarea) como equivalente, mismo criterio ya aplicado en el verify de `01-fundacion-tdd`. Recomendado para cambios futuros: que `sdd-apply` incluya la tabla literal en su reporte para reducir la carga de reconciliación manual en verify.
3. El artefacto real de migración (`0002_add_audit_fields.py`) solo está cubierto por `alembic check` (guardia genérica de 01), no por un test que verifique explícitamente las 22 FKs nombradas una por una contra el archivo de migración — riesgo ya declarado explícitamente en `design.md` como brecha aceptada (Testing Strategy, nota "Artefacto de migración"), no bloqueante.

### Verdict
**PASS**
33/33 tareas completas, 135/135 tests pasando en ejecución real contra la imagen Docker reconstruida (no la imagen bakeada obsoleta), 17/17 escenarios/gates de spec compliant con evidencia de runtime (pytest + llamadas HTTP en vivo tras el rebuild), `ruff`/`mypy` limpios, migración `0002` encadenada y verificada simétrica, sin scope creep. Cero hallazgos CRITICAL o WARNING; 3 SUGGESTION no bloqueantes documentadas arriba.
