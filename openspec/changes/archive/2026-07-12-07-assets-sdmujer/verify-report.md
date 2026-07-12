```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:474fe1144e057b5f2659431bf399fc491ca398c91229db705be66bb3776ccf12
verdict: pass
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 28/28
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia TEST_AUTH_TOKEN=*** API_BASE_URL=http://localhost:8000/api/v1 .venv/bin/python -m pytest tests/ -q
test_exit_code: 0
test_output_hash: sha256:474fe1144e057b5f2659431bf399fc491ca398c91229db705be66bb3776ccf12
build_command: cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy app
build_exit_code: 0
build_output_hash: sha256:c1e6f65f0910a658f3633e575e1bc6448776a646a843ba492d819cff1297c8ec
```

## Verification Report

**Cambio**: 07-assets-sdmujer
**Versión**: N/A (delta spec `specs/assets/spec.md`, sin versión numerada)
**Modo**: Strict TDD (con desviación documentada — ver sección de escrutinio)

### Completitud de tareas

| Métrica | Valor |
|---------|-------|
| Tareas totales | 19 |
| Tareas completas | 19 |
| Tareas incompletas | 0 |

`tasks.md` tiene las 19 tareas (T01-T19, Fase A y Fase B) marcadas `[x]`. `state.yaml`: `phases.apply: done`, `phases.verify: pending` (se actualiza a `done` al cierre de este reporte por el resultado PASS).

### Ejecución de build y tests

**Build (ruff + mypy)**: ✅ Passed
```text
$ ruff check .
All checks passed!

$ mypy app
Success: no issues found in 176 source files
```

**Tests**: ✅ 498 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
$ pytest tests/ -q   (TEST_DATABASE_URL + DATABASE_URL + TEST_AUTH_TOKEN + API_BASE_URL exportadas)
........................................................................ [ 14%]
........................................................................ [ 28%]
...
........................................................................ [100%]
498 passed, 1 warning in 134.26s (0:02:14)
```
El único warning es un `SAWarning` preexistente de ciclo FK en `dependencies/organizations/users`, ajeno a este cambio (ya presente en la línea base, confirmado en `alembic/env.py:55`).

Sin `TEST_AUTH_TOKEN`/`API_BASE_URL`, 12 tests preexistentes de otros módulos (`test_attachments`, `test_comments`, `test_sprint_close`, `test_subtasks`, `test_task_key`) fallan con `httpx.LocalProtocolError: Illegal header value b'Bearer '` porque leen `os.getenv("TEST_AUTH_TOKEN", "")` sin gate `skipif` — no son parte de este cambio, y desaparecen al exportar el token (confirmado: mismos 12 pasan en verde con el token presente). Los 498 esperados por `apply-progress` se confirman exactos con ambas variables presentes.

**Cobertura**: no se ejecutó `--cov` explícito en este ciclo de verify (no configurado como gate del proyecto); no aplica bloqueo.

### Alembic — migración 0010

| Chequeo | Resultado |
|---------|-----------|
| `alembic heads` (repo) | `0010 (head)` |
| Contenedor backend reconstruido (`docker compose up -d --build backend`) | ✅ Recreado, arrancó y aplicó `upgrade 0009 -> 0010, add_assets` automáticamente en el entrypoint |
| `alembic current` (contenedor, tras build) | `0010 (head)` ✅ |
| `alembic check` (contenedor, tras build) | `No new upgrade operations detected.` ✅ sin diff |
| `alembic downgrade -1` → `alembic current` | `0009` ✅ (elimina `asset_tasks`/`asset_licenses`/`assets` sin error) |
| `alembic upgrade head` → `alembic current` | `0010 (head)` ✅ |
| `alembic check` tras re-upgrade | `No new upgrade operations detected.` ✅ (ciclo downgrade→upgrade reproducible y limpio) |
| `pytest tests/test_migrations_baseline.py -v` (incluido en la corrida de 498) | ✅ pasa, incluido `test_alembic_check_reports_no_diff_after_upgrade` |

### Matriz de cumplimiento de especificación (28/28 escenarios)

| Requisito | Escenario | Test | Resultado |
|-----------|-----------|------|-----------|
| R1 Creación con taxonomía validada | Creación válida por admin | `test_assets.py::test_create_asset_by_admin_returns_201` | ✅ COMPLIANT |
| R1 | `asset_type` fuera del enum → 422 | `test_assets.py::test_create_asset_with_invalid_asset_type_returns_422` | ✅ COMPLIANT |
| R1 | Creación rechazada a no-admin → 403 | `test_assets.py::test_create_asset_rejected_for_non_admin` | ✅ COMPLIANT |
| R2 Consulta por cualquier miembro | Listado filtrado (`asset_type`) | `test_assets.py::test_list_assets_filtered_by_asset_type` | ✅ COMPLIANT |
| R2 | Filtro combinado `q`+`category` | `test_assets.py::test_list_assets_filtered_by_q_and_category` | ✅ COMPLIANT |
| R2 | Obtención inexistente o ajena → 404 | `test_assets.py::test_get_nonexistent_asset_returns_404` (+ `test_get_asset_of_another_org_returns_404` en R6) | ✅ COMPLIANT |
| R3 Edición/borrado admin | Edición válida por admin | `test_assets.py::test_update_asset_by_admin_updates_status_and_criticality` | ✅ COMPLIANT |
| R3 | Borrado soft | `test_assets.py::test_delete_asset_is_soft_delete_and_disappears_from_list` | ✅ COMPLIANT |
| R3 | Edición rechazada a no-admin → 403 | `test_assets.py::test_update_asset_rejected_for_non_admin` | ✅ COMPLIANT |
| R4 Licencias anidadas CRUD | Creación válida | `test_asset_licenses.py::test_create_license_with_valid_dates_returns_201` | ✅ COMPLIANT |
| R4 | Licencias inaccesibles tras borrado soft del padre (GET+PATCH+DELETE) | `test_asset_licenses.py::test_licenses_become_inaccessible_after_parent_asset_soft_delete` | ✅ COMPLIANT |
| R4 | Fechas inválidas → 422 | `test_asset_licenses.py::test_create_license_with_invalid_dates_returns_422` | ✅ COMPLIANT |
| R4 | Edición y borrado | `test_asset_licenses.py::test_update_license_by_admin` + `test_delete_license_is_soft_delete` | ✅ COMPLIANT |
| R4 | Licencia de activo ajeno → 404 | `test_asset_licenses.py::test_license_of_another_org_returns_404` | ✅ COMPLIANT |
| R5 Vínculo activo↔tarea existente | Vínculo válido | `test_assets.py::test_link_existing_task_appears_in_list` | ✅ COMPLIANT |
| R5 | Tarea de otra organización → 404 | `test_assets.py::test_link_task_from_another_org_returns_404` | ✅ COMPLIANT |
| R5 | Desvinculación | `test_assets.py::test_unlink_task_removes_it_from_list` | ✅ COMPLIANT |
| R6 Aislamiento multi-tenant | Activos de otra organización | `test_assets.py::test_list_assets_never_crosses_organizations` + `test_get_asset_of_another_org_returns_404` | ✅ COMPLIANT |
| R6 | Licencia de otra organización | `test_asset_licenses.py::test_license_of_another_org_returns_404` | ✅ COMPLIANT |
| R6 | Vínculo de otra organización | `test_assets.py::test_asset_task_link_of_another_org_returns_404` | ✅ COMPLIANT |
| R7 `license_expiring` escalonada | Aviso a 30 días | `test_license_alerts.py::test_evaluate_notifies_responsible_at_30_days` | ✅ COMPLIANT |
| R7 | Re-corrida no duplica | `test_license_alerts.py::test_repeated_evaluation_does_not_duplicate_notification` | ✅ COMPLIANT |
| R7 | Cruce a un umbral distinto sí avisa | `test_license_alerts.py::test_crossing_to_a_new_band_notifies_again` | ✅ COMPLIANT |
| R7 | `auto_renew=true` no alerta | `test_license_alerts.py::test_auto_renew_license_never_alerts` | ✅ COMPLIANT |
| R7 | Descubrimiento tardío → SOLO banda 7 | `test_license_alerts.py::test_late_discovery_at_5_days_fires_only_band_7` | ✅ COMPLIANT |
| R7 | Salto del día exacto del umbral (25→banda 30) | `test_license_alerts.py::test_threshold_skip_at_25_days_still_fires_band_30` | ✅ COMPLIANT |
| R8 `license_expired` | Aviso al vencer (responsable + admins) | `test_license_alerts.py::test_expired_license_notifies_responsible_and_admins` | ✅ COMPLIANT |
| R8 | Organización sin admins igual notifica al responsable | `test_license_alerts.py::test_expired_license_without_admins_still_notifies_responsible` | ✅ COMPLIANT |
| R8 | Sin duplicado entre corridas | `test_license_alerts.py::test_repeated_expired_evaluation_does_not_duplicate` | ✅ COMPLIANT |

**Resumen de cumplimiento**: 28/28 escenarios COMPLIANT (adicionalmente cubiertos, sin escenario propio dedicado: `test_random_license_id_returns_404`, `test_license_strategies_are_registered`, `test_blocked_task_alert.py::test_seed_creates_five_rules_including_blocked_task`/`test_reseed_does_not_duplicate_rules` ajustados 5→7).

### Corrección (evidencia estática)

| Requisito | Estado | Nota |
|-----------|--------|------|
| Taxonomía `asset_type`/`category` | ✅ Implementado | Enum de 6 valores sin `license`, `category String(80)` libre — coincide con proposal.md |
| Cascada de soft-delete Asset→AssetLicense | ✅ Implementado | `AssetService.delete_asset` marca `is_active=False`/`deleted_at` en las licencias ANTES del propio activo (service.py:147-159), documentado explícitamente porque las rutas planas `/asset-licenses/{id}` no hacen JOIN contra `Asset.is_active` |
| `AssetTask` con `TenantMixin` (divergencia de `TaskLabel`) | ✅ Implementado | Confirmado en `repository.py:172` (`AssetTask.organization_id == organization_id`) |
| `dedup_key` con banda mínima (`license_expiring`) | ✅ Implementado | `min(eligible_bands)` en `license_expiring.py:57` |
| Destinatarios independientes (`license_expired`) | ✅ Implementado | `set()` de `admin_ids` + `responsible_id`, SIN early-return `if not admins` (`license_expired.py:59-61`) |
| RBAC escritura `require_admin` / lectura `get_current_membership` | ✅ Implementado | Confirmado en black-box (403 con `carlos@solercia.com`, miembro) |

### Coherencia (Design)

| Decisión | ¿Seguida? | Notas |
|----------|-----------|-------|
| Un solo módulo `assets/` con 3 servicios/repos | ✅ Sí | `AssetService`/`AssetLicenseService`/`AssetTaskService` en un archivo |
| `AssetLicense.asset_id` CASCADE + soft-delete propagado en el service | ✅ Sí | Ver tabla de corrección |
| `AssetTask` hard-delete (convención `TaskLabel`) | ✅ Sí | `AssetTaskRepository.unlink` (no revisa `is_active`, hace delete físico del row — confirmado por `test_unlink_task_removes_it_from_list` re-vinculable) |
| Enums `native_enum=False` (paridad `alembic check`) | ✅ Sí | Confirmado — `alembic check` sin diff tras `upgrade head` |
| `dedup_key` con banda/recipient | ✅ Sí | Ver tabla de corrección |
| Corte en 2 lotes (commits 89bbe9b / c983bd2) | ✅ Sí | Confirmado en `git log` |

### Escrutinio especial — desviación TDD documentada

El `apply-progress` (Engram #1383) documenta que `schemas/repository/service/router` (T06-T09) y las 2 estrategias de alerta (T14-T15) se escribieron ANTES de que existieran sus tests RED, y que el RED se confirmó retroactivamente des-cableando temporalmente el punto de integración (comentar `include_router(assets_router)` para Fase A; dejar el registry/seed sin las 2 entradas para Fase B), en vez de un RED-first puro por archivo.

**Evaluación de esta verificación**: la desviación es una relajación del *orden* de escritura del código, no del *rigor* del rojo — el rojo demostrado (16/22 fallando por 404 de ruta no registrada; 6/17 fallando por lookup `None` del registry) prueba que el punto de integración real fue ejercitado, no solo importado. Para confirmar que las aserciones son sensibles a comportamiento real (y no solo a que el endpoint exista), se inspeccionaron 4 tests clave contra su implementación:

1. **Banda vigente / descubrimiento tardío** (`test_late_discovery_at_5_days_fires_only_band_7`): asserta `len(candidates) == 1` y `dedup_key == "...{license_id}:7"`. La implementación (`license_expiring.py:54-57`) calcula `eligible_bands = [b for b in leads if days_left <= b]` y toma `min(eligible_bands)`. Si el código generara una candidata por CADA banda elegible en vez de solo la mínima (bug plausible), `eligible_bands` para `days_left=5` con `leads=[30,7,1]` sería `[30,7]` → 2 candidatas → la aserción `len==1` fallaría. La aserción es sensible a comportamiento real, no solo a la existencia del endpoint.
2. **Organización sin admins** (`test_expired_license_without_admins_still_notifies_responsible`): asserta `len(candidates)==1` y `recipient_user_id==owner.id` cuando no hay ningún `OrganizationMember.role==admin`. La implementación (`license_expired.py:59-61`) usa `recipients = set(admin_ids)` (vacío) y luego `recipients.add(asset.responsible_id)` — sin el `if not admins: return []` prohibido explícitamente en el docstring del archivo. Si ese early-return se reintrodujera, `candidates` sería `[]` y la aserción de longitud fallaría. Prueba directa de la regla de negocio, no un artefacto de mocking.
3. **Propagación de soft delete** (`test_licenses_become_inaccessible_after_parent_asset_soft_delete`): asserta 404 en `GET .../licenses`, `PATCH /asset-licenses/{id}` Y `DELETE /asset-licenses/{id}` tras soft-borrar el activo padre. Se verificó el repository: `AssetLicenseRepository.get()` filtra por `AssetLicense.is_active.is_(True)` (repository.py:135-136) SIN hacer JOIN contra `Asset.is_active` — es decir, las rutas planas `/asset-licenses/{id}` dependen EXCLUSIVAMENTE de que `AssetService.delete_asset` haya marcado `is_active=False` en la licencia misma (service.py:151-155). Si esa cascada se eliminara del service, la licencia seguiría con `is_active=True` y las aserciones de `patch_response`/`delete_license_response` (200/204 en vez de 404) fallarían — solo `list_response` (que sí pasa por `_require_asset` primero) seguiría en 404. Esto confirma que 2 de las 3 aserciones del test dependen específicamente de la cascada a nivel de service, exactamente el gate que pedía el escrutinio.
4. **Aislamiento `two_orgs`** (`test_list_assets_never_crosses_organizations`, `test_get_asset_of_another_org_returns_404`): confirmado que `AssetRepository.list_assets`/`.get()` filtran por `Asset.organization_id == organization_id` (repository.py:53-54, 83-84) — el `organization_id` proviene del JWT vía dependencia (patrón as-built del resto del proyecto), no de un valor hardcodeado en el test. Si el filtro se omitiera, `test_list_assets_never_crosses_organizations` fallaría (el activo "Solo B" aparecería en la respuesta de la organización A).

**Conclusión del escrutinio**: las 4 muestras tienen aserciones que fallarían ante una regresión real del comportamiento (no solo ante la ausencia de la ruta). La desviación documentada no compromete la validez del contrato TDD; el "rojo por desconexión temporal del punto de integración" es un sustituto legítimo del rojo por-archivo cuando el diseño ya estaba fijado (`design.md`) y las 6 correcciones de gate vinculantes se codificaron antes del test — riesgo residual BAJO, no bloqueante.

### Black-box contra contenedor (`docker compose up -d --build backend`)

| Paso | Resultado |
|------|-----------|
| Rebuild + restart `backend` | ✅ Contenedor recreado; log de arranque muestra `Running upgrade 0009 -> 0010, add_assets` |
| `alembic current` (post-build) | `0010 (head)` ✅ |
| `POST /api/v1/assets` con `asset_type=hardware` (admin) | `201`, `created_by`/`updated_by` = admin ✅ |
| `POST /api/v1/assets` con `asset_type=license` (enum eliminado) | `422`, error `enum` en `asset_type` ✅ |
| `GET /api/v1/assets?asset_type=hardware` | `200`, envelope `{data, meta:{total:1}}`, todos `hardware` ✅ |
| `PATCH /api/v1/assets/{id}` (`responsible_id`=admin) | `200` ✅ |
| `POST /api/v1/assets/{id}/licenses` (vence en 5 días) | `201` ✅ |
| `GET /api/v1/alert-rules` | 7 reglas totales; `license_expiring` (`enabled=true`, `lead_days:[30,7,1]`) y `license_expired` (`enabled=true`) sembradas ✅ |
| `POST /api/v1/alerts/evaluate` (1ra corrida) | `200`, `{created:1}` — banda 7 (5 días ≤ 7) ✅ |
| `GET /api/v1/notifications` | Notificación "Licencia próxima a vencer" presente ✅ |
| `POST /api/v1/alerts/evaluate` (re-corrida) | `200`, `{created:0}` — sin duplicado ✅ |
| Login `carlos@solercia.com` (member, seed) + `POST /assets` | `403 forbidden` ✅ |
| Limpieza (`DELETE` licencia + activo) | `204`/`204`; `GET` del activo borrado → `404` ✅ |

### Issues encontrados

**CRITICAL**: Ninguno.

**WARNING**: Ninguno.

**SUGGESTION**:
- `apply-progress` reporta "8 tests" para `test_asset_licenses.py`; el conteo real del archivo es 7 (`R4`×5 + `R6`×2). Discrepancia cosmética en la nota de progreso, sin impacto en cobertura ni en el resultado 498/498 — no requiere acción.
- Los 12 tests black-box preexistentes (`test_attachments`, `test_comments`, `test_sprint_close`, `test_subtasks`, `test_task_key`) no tienen `skipif` cuando `TEST_AUTH_TOKEN` está ausente — fallan con `LocalProtocolError` en vez de `SKIPPED`. Es deuda preexistente ajena a este cambio; se documenta para una futura limpieza de tooling de tests.

### Veredicto

**PASS**

19/19 tareas completas, 498/498 tests en verde (0 fallos), ruff y mypy limpios, migración 0010 con `alembic check` sin diff y ciclo downgrade/upgrade reproducible, 28/28 escenarios de la delta spec con test cubridor pasando, black-box contra el contenedor reconstruido confirma el contrato REST + el motor de alertas de licencia end-to-end (incluida la regla del gate: `403` de escritura sin RBAC admin), y la desviación TDD documentada se verificó como benigna mediante inspección de 4 aserciones clave que fallarían ante una regresión real de comportamiento.
