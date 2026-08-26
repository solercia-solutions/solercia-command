```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:1f0d435a30f0278accbf9357c21d17019d45248955f36e1d409d4c92eaf12945
verdict: fail
blockers: 2
critical_findings: 2
requirements: 12/15
scenarios: 32/35
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q
test_exit_code: 1
test_output_hash: sha256:f420bfc44b249f43a17f8d3be92190cea0d7793241b4f4a5cfcb3698a164fc2e
build_command: cd backend && .venv/bin/mypy app/maintenance scripts
build_exit_code: 0
build_output_hash: sha256:14fdf673bd175fe32ef42df34666481bb15e465313f7dbef32d0aea2ba76a26e
```

## Verification Report

**Change**: 42-purga-datos-demo
**Version**: N/A (specs de este cambio aún no fusionadas a `openspec/specs/`; se leyeron de `openspec/changes/42-purga-datos-demo/specs/`)
**Mode**: Standard (TDD estricto verificado por evidencia RED→GREEN en `apply-progress`, no Strict TDD runner activo)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 55 (0.1–0.8, 1.1–1.11, 2.1–2.14, 3.1–3.16, 4.1–4.7, 5.1–5.8, 6.1–6.6) |
| Tasks complete | 55 |
| Tasks incomplete | 0 |

Todas las tareas de `tasks.md` están marcadas `[x]`. La tarea 5.8 (`--purge-upload-files`) está marcada `[x]` con nota explícita **«Decisión: no ejecutado»** — decisión válida y documentada del usuario, no un pendiente oculto.

### Build & Tests Execution

**Build**: ✅ Passed (mypy, alcance de este cambio)
```text
cd backend && .venv/bin/mypy app/maintenance scripts
Success: no issues found in 10 source files
```

**Tests**: ✅ 1411 passed / ❌ 3 failed / ⚠️ 0 skipped
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia \
  REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q

3 failed, 1411 passed, 1 warning in 277.74s (0:04:37)

FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering
FAILED tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto
```

Los 3 fallos son EXACTAMENTE la línea base preexistente documentada en el lanzamiento (commit `fc97125`, 2026-08-26: 1411 passed / 3 failed), dependientes del reloj del sistema en `test_adapter_microsoft365.py`, ajenos al alcance de este cambio. **Cero regresiones nuevas.**

**Estáticos adicionales**:
- `ruff check app scripts tests` (repo completo): 1 error preexistente en `tests/test_cross_tenant_isolation.py:128` (E501, línea 102>100), archivo NO tocado por este cambio (último commit `9be4a40`, ajeno al 42). Alcance de este cambio (`app/maintenance app/config.py app/db_init.py scripts` + los 5 archivos de test nuevos): **All checks passed**.
- `ruff format --check` (repo completo): 285 de 465 archivos requerirían reformateo — deuda de formato preexistente y transversal al repositorio, no introducida por este cambio. **Alcance de este cambio**: 7 de 17 archivos (`app/db_init.py`, `app/maintenance/{invariants,repository,runner}.py`, `tests/test_{bootstrap_hierarchy,maintenance_invariants,seed_demo_flag}.py`) también difieren del formateador — ver hallazgo WARNING abajo.
- `mypy app scripts` (repo completo): 6 errores preexistentes en 4 archivos NO tocados por este cambio (`organizations/repository.py`, `organizations/service.py`, `org_role_templates/service.py`, `tasks/service.py`). **Alcance de este cambio** (`app/maintenance scripts`): `Success: no issues found in 10 source files`.

**Coverage**: ➖ No disponible (el proyecto no ejecuta `pytest --cov` en este flujo; la cobertura por escenario se evalúa manualmente en la matriz de abajo)

### Dry-run operativo contra la base real (evidencia adicional, NO sustituye pruebas)

```text
cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia
```
Resultado: **exit 0**, alcance planeado en 0 filas para las 6 tablas, inventario en 0, huérfanos preexistentes en 0, bootstrap "ya existía — reutilizado" para SDM/SEG/PAN, **8/8 invariantes I1–I8 en PASS**. Confirma que la ejecución real de Fase 5 (orquestador, 2026-08-26) dejó la base `solercia` exactamente en el estado esperado y que un dry-run posterior es un no-op limpio.

### Spec Compliance Matrix

#### Capability `data-maintenance` (9 requisitos / 19 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Compuerta SEED_DEMO_DATA | Con flag false no se crean usuarios demo | `test_seed_demo_flag.py::test_ensure_demo_members_no_crea_usuarios_con_flag_apagado` | ✅ COMPLIANT |
| Compuerta SEED_DEMO_DATA | Con flag true la semilla demo funciona en BD vacía | `test_ensure_demo_members_crea_usuarios_con_flag_encendido` + `test_seed_demo_workitems_crea_proyectos_tareas_y_sprint_con_flag_encendido` | ✅ COMPLIANT |
| Compuerta SEED_DEMO_DATA | Restart no revive miembros demo tras la purga | `test_restart_con_flag_apagado_no_revive_miembros_tras_purga` | ✅ COMPLIANT |
| Purga idempotente, dry-run por defecto | Dry-run no modifica la base | `test_purge_demo_data.py::test_dry_run_no_deja_cambios_visibles` | ✅ COMPLIANT |
| Purga idempotente, dry-run por defecto | Execute borra y segunda corrida es no-op | `test_purga_es_idempotente_en_segunda_corrida` | ✅ COMPLIANT |
| Orden de borrado hoja-raíz y huérfanos sin FK | Attachments/notifications huérfanos en cero | `test_purga_borra_adjuntos_notificaciones_y_recordatorios_huerfanos` + `test_execute_con_arbol_bajo_solercia_y_huerfanos_preexistentes_deja_i6_e_i7_en_pass` | ✅ COMPLIANT |
| Orden de borrado hoja-raíz y huérfanos sin FK | Proyecto padre no se borra antes que su hijo | `test_purga_borra_subarbol_completo_de_hoja_a_raiz` | ✅ COMPLIANT |
| Protección del catálogo y de conectores reales | El catálogo de plantillas sobrevive a la purga | `test_purga_conserva_admin_org_solercia_y_plantillas_de_sistema` + `test_maintenance_invariants.py::test_invariante_i7_falla_si_hay_instantiations_del_alcance_demo` | ✅ COMPLIANT |
| Protección del catálogo y de conectores reales | Solo el conector fake se borra | `test_purga_borra_conector_fake_y_conserva_los_reales` + `test_invariante_i8_falla_si_sobrevive_un_conector_fake` | ✅ COMPLIANT |
| Fallo cerrado si una connected_account pertenece a un usuario a borrar | Cuenta conectada de un usuario demo bloquea la purga | `test_purga_falla_cerrado_si_una_cuenta_conectada_pertenece_a_un_usuario_demo` | ✅ COMPLIANT |
| Fallo cerrado si una connected_account pertenece a un usuario a borrar | Sin cuentas de usuarios demo la purga procede | `test_purga_borra_org_demo_usuarios_y_proyectos` (sin guarda disparada) + dry-run/execute reales contra `solercia` (Fase 5.3/5.5) | ✅ COMPLIANT |
| Respaldo obligatorio y verificado | Backup ausente aborta la ejecución | `test_purge_cli.py::test_execute_sin_backup_file_falla_con_codigo_1` | ✅ COMPLIANT |
| Respaldo obligatorio y verificado | Backup vacío aborta la ejecución | `test_backup_file_inexistente_o_vacio_falla_con_codigo_1` | ✅ COMPLIANT |
| Bootstrap idempotente de SDMUJER | Primera ejecución crea la jerarquía completa | `test_bootstrap_hierarchy.py::test_bootstrap_crea_sdmujer_seguridad_pandora_con_codigos_y_metodologias` + `test_seguridad_tiene_siete_columnas_y_completada_es_la_de_mayor_order` | ✅ COMPLIANT |
| Bootstrap idempotente de SDMUJER | Segunda ejecución es un no-op | `test_bootstrap_es_idempotente_y_reutiliza_proyectos_por_codigo` | ✅ COMPLIANT |
| Invariantes post-ejecución, código de salida no cero | Todas las invariantes en verde terminan con código 0 | `test_maintenance_invariants.py::test_todas_las_invariantes_pasan_tras_un_bootstrap_correcto` + `test_purge_cli.py::test_execute_exitoso_con_invariantes_en_pass_retorna_codigo_0` + ejecución real Fase 5.5 (exit 0, I1–I8 PASS) | ✅ COMPLIANT |
| Invariantes post-ejecución, código de salida no cero | Una invariante rota termina con código distinto de cero | 8× `test_invariante_i{1..8}_falla_...` + `test_purge_cli.py::test_invariante_en_fail_retorna_codigo_3` | ✅ COMPLIANT |
| Contrato de ejecución en el host | `--database-url` permite ejecutar desde el host | `test_purge_cli.py::test_dry_run_real_via_subprocess_registra_el_orm_completo` + dry-run real (Fase 5.3) | ✅ COMPLIANT |
| Contrato de ejecución en el host | `--purge-upload-files` borra solo los archivos referenciados | **(ninguna)** | ❌ **UNTESTED** |

#### Delta `api-conventions` (3 requisitos / 9 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R4 — Seed idempotente, semilla estructural incondicional | Seed idempotente | `test_seed_demo_flag.py::test_restart_con_flag_apagado_no_revive_miembros_tras_purga` (llama `seed_default()` dos veces; solo verifica no-duplicación de `organization_members`, no del universo completo de la semilla estructural) | ⚠️ PARTIAL |
| R4 — Seed idempotente, semilla estructural incondicional | Demo desactivada por defecto | `test_ensure_demo_members_no_crea_usuarios_con_flag_apagado` + `test_seed_demo_workitems_no_crea_proyectos_con_flag_apagado` | ✅ COMPLIANT |
| R4 — Seed idempotente, semilla estructural incondicional | Miembros demo no reviven sin el flag | `test_restart_con_flag_apagado_no_revive_miembros_tras_purga` | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | Inicialización de esquema gestionada por Alembic | `test_migrations_baseline.py` (preexistente, sin cambios de comportamiento, pasa en la suite completa) | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | El arranque ya no recrea el esquema con create_all | Comportamiento preexistente sin cambios; suite completa en verde | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | Sin migración nueva para el flag de semilla demo | Verificación directa en disco: `backend/alembic/versions/` sigue con exactamente 24 archivos (`0001`–`0024`), sin ninguno nuevo (tarea 6.3 + confirmado por este verify) | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | Borrado suave sigue aplicando al dominio en tiempo de ejecución | `test_tasks_crud.py` (`DELETE /tasks/{id}` → 204, fila desaparece de listados; preexistente, pasa en la suite completa) | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | La operación de mantenimiento exige backup verificado | `test_execute_sin_backup_file_falla_con_codigo_1` + `test_backup_file_inexistente_o_vacio_falla_con_codigo_1` | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | El mantenimiento nunca se expone por HTTP | **(ninguna)** — verificado solo por inspección estática (`rg` sin coincidencias de `app.maintenance`/`scripts.purge_demo_data` en `app/main.py` ni en ningún `router.py`), sin prueba automatizada que enumere rutas en runtime | ❌ **UNTESTED** |

#### Delta `multi-tenancy` (1 requisito / 3 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R4 — Seed idempotente con miembros demo condicionales | Organización y admin incondicionales | `test_ensure_demo_members_no_crea_usuarios_con_flag_apagado` (admin/org existen sin importar el flag) | ✅ COMPLIANT |
| R4 — Seed idempotente con miembros demo condicionales | Miembros demo condicionados al flag | `test_ensure_demo_members_no_crea_usuarios_con_flag_apagado` | ✅ COMPLIANT |
| R4 — Seed idempotente con miembros demo condicionales | Restart no revive miembros demo tras la purga | `test_restart_con_flag_apagado_no_revive_miembros_tras_purga` | ✅ COMPLIANT |

#### Delta `org-role-templates` (1 requisito / 2 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| La purga preserva el catálogo de plantillas de sistema | La purga borra el árbol instanciado y el ledger, no el catálogo | `test_purge_demo_data.py::test_purga_borra_arbol_bajo_solercia_alias_oap_ti_y_barre_huerfanos_preexistentes` + `test_execute_con_arbol_bajo_solercia_y_huerfanos_preexistentes_deja_i6_e_i7_en_pass` + ejecución real Fase 5.5 (instantiations=0, templates=5) | ✅ COMPLIANT |
| La purga preserva el catálogo de plantillas de sistema | El catálogo sigue disponible tras la purga | `test_purga_conserva_admin_org_solercia_y_plantillas_de_sistema` + dry-run real post-reinicio (5 plantillas `is_system=true` intactas) | ✅ COMPLIANT |

#### Delta `intake-classifier` (1 requisito / 2 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| Bootstrap satisface el proyecto por defecto sin crear "Tareas Outlook" | `default_project_id` preconfigurado evita la creación perezosa | `test_bootstrap_hierarchy.py::test_intake_settings_apunta_a_seguridad_sin_crear_tareas_outlook` | ✅ COMPLIANT |
| Bootstrap satisface el proyecto por defecto sin crear "Tareas Outlook" | Sin bootstrap previo, el comportamiento perezoso original sigue vigente | `test_intake_classifier_endpoints.py::test_first_use_creates_default_project_and_second_use_reuses_it` (preexistente, confirmado sin modificar — tarea 6.2) | ✅ COMPLIANT |

**Compliance summary**: 32/35 escenarios COMPLIANT, 1/35 PARTIAL, 2/35 UNTESTED.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| `SEED_DEMO_DATA: bool = False` en `Settings` | ✅ Implemented | `backend/app/config.py:58`, leído en tiempo de llamada por `db_init.py` |
| Retorno temprano en `_ensure_demo_members`/`_seed_demo_workitems` | ✅ Implemented | `backend/app/db_init.py:563,594`, gateado por `settings.SEED_DEMO_DATA` |
| `docker-compose.yml`/`env.example` documentan el flag | ✅ Implemented | `SEED_DEMO_DATA: "false"` / `SEED_DEMO_DATA=false` |
| Repositorios de mantenimiento nunca comitean | ✅ Implemented | `MaintenanceRepository` usa solo `flush()`; único `commit()`/`rollback()` vive en `runner.py` (regla de persistencia del repo verificada) |
| Orden de borrado D4 hoja-raíz | ✅ Implemented | `purge.py` sigue el orden: attachments → notifications → reminders → tasks → instantiations(count) → projects → connectors → assets → users → organizations, más el barrido de huérfanos preexistentes al final |
| Alcance como dato explícito (`DemoScope`) | ✅ Implemented | `scope.py`, frozen dataclass, sin heurística |
| CLI nunca se expone por HTTP | ✅ Implemented (sin prueba automatizada — ver hallazgo CRITICAL) | Verificado por inspección: cero referencias a `app.maintenance`/`scripts.purge_demo_data` en `app/main.py` o cualquier `router.py` |
| Códigos de salida 0–4 | ✅ Implemented | `scripts/purge_demo_data.py` — constantes `EXIT_*`, traducidos correctamente en `_run`/`main` |
| Redacción de contraseña en la URL de BD | ✅ Implemented | `redact_database_url`, probado |
| Contención de rutas de `--purge-upload-files` | ✅ Implemented (función de borrado real sin prueba — ver hallazgo CRITICAL) | `is_within_upload_dir` probado; `delete_referenced_files` sin invocación en ninguna prueba |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — Paquete `app/maintenance/` con adaptador único | ✅ Yes | `MaintenanceRepository` es el único lugar con SQLAlchemy del paquete |
| D2 — Transacción única, dry-run por `rollback` | ✅ Yes | `runner.py`: `commit()` solo si `execute` y todas las invariantes en PASS; en cualquier otro caso `rollback()` |
| D3 — Alcance como dato explícito | ✅ Yes | `DemoScope` frozen dataclass; extendido en Corrección 2 con `soft_deleted_scope_organization_names` y `template_root_name_aliases` (decisión #3682, documentada) |
| D4 — Orden de borrado y huérfanos sin FK | ✅ Yes | Orden respetado; huérfanos preexistentes (Corrección 2) añadidos como barrido separado, reportado en `orphans_swept` |
| D5 — Compuerta leída en tiempo de llamada | ✅ Yes | Acceso a atributo del singleton `settings`, probado con `monkeypatch.setattr` en el mismo test con dos llamadas |
| D6 — Bootstrap con `_create_project_unit` + columnas literales | ✅ Yes | `status_key` verbatim, nunca slugificado; `ensure_board_columns` sobre el tablero ya sembrado por `seed_board`, sin segundo `Board` |
| D7 — CLI: importación, sesión, respaldo, códigos de salida | ✅ Yes | `import app.db_init` agregado en Corrección 1 para registrar el ORM completo antes del primer query (defecto real reproducido y corregido) |
| D8 — Reporte tipado e invariantes I1–I8 | ✅ Yes | Las 8 invariantes implementadas; I1 sigue el texto literal de `spec.md` («existe admin@solercia.com»), NO la paráfrasis de la tabla resumen de `design.md` («es el único usuario») — desviación documentada en `apply-progress`, resuelta a favor del spec (fuente normativa) |

**Nota sobre I1**: hay una inconsistencia textual entre `spec.md` (Requirement, fuente normativa) y la tabla D8 de `design.md` (resumen). `apply` implementó el texto del spec. Verificado correcto: el spec es la fuente de verdad para el comportamiento; el resumen de diseño es descriptivo, no normativo. No es un defecto — clasificado como observación, no como hallazgo.

### Issues Found

**CRITICAL**:
1. **UNTESTED** — Requisito «Contrato de ejecución en el host», escenario «`--purge-upload-files` borra solo los archivos referenciados»: la función `delete_referenced_files` (`backend/scripts/purge_demo_data.py:131-148`), que ejecuta el borrado físico real de ficheros en `UPLOAD_DIR`, no tiene NINGUNA prueba que la invoque. Las pruebas existentes (`test_purge_upload_files_esta_apagado_por_defecto`, `test_purge_upload_files_rechaza_rutas_fuera_de_upload_dir`) cubren solo la lógica de contención de rutas (`is_within_upload_dir`) de forma aislada, nunca el flujo completo «crea N ficheros, borra solo los referenciados, los demás permanecen intactos» que el escenario exige textualmente. Riesgo real acotado (bandera apagada por defecto, nunca ejecutada contra `solercia` — tarea 5.8 «decisión: no ejecutado»), pero la regla dura de esta fase («un escenario de spec es conforme solo cuando una prueba que lo cubre pasó en tiempo de ejecución») no admite excepción por bajo riesgo.
2. **UNTESTED** — Requisito ADDED de `api-conventions` «Alcance del borrado suave y excepción de mantenimiento», escenario «El mantenimiento nunca se expone por HTTP»: ninguna prueba automatizada enumera las rutas registradas de FastAPI para confirmar la ausencia de un endpoint que ejecute borrado físico. La verificación realizada en este `verify` es puramente estática (`rg` sobre `app/main.py` y cada `router.py`, cero coincidencias de `app.maintenance`/`scripts.purge_demo_data`), no una prueba en tiempo de ejecución como el escenario exige textualmente («Dado el backend en ejecución, Cuando se inspeccionan las rutas registradas»).

**WARNING**:
1. **PARTIAL** — Requisito R4 de `api-conventions`, escenario «Seed idempotente»: la única prueba que invoca `seed_default()` dos veces (`test_restart_con_flag_apagado_no_revive_miembros_tras_purga`) solo verifica que `organization_members` no se duplica; no verifica dependencies/roles/menus/role_menus/alert_rules/`org_role_templates` de sistema tras una segunda corrida. Es un hueco de cobertura preexistente a este cambio (ningún otro archivo de prueba en todo el repositorio invoca `seed_default()`), no introducido por él — no bloqueante, pero documentado para trazabilidad.
2. **Formato** — `ruff format --check`, alcance de este cambio: 7 de 17 archivos (`app/db_init.py`, `app/maintenance/{invariants,repository,runner}.py`, `tests/test_{bootstrap_hierarchy,maintenance_invariants,seed_demo_flag}.py`) difieren del formateador configurado (`line-length = 100`, ruff 0.15.21) por líneas que caben en un solo renglón dentro del límite pero quedaron envueltas manualmente en varias. Consistente con una deuda de formato transversal y preexistente en el repositorio (285/465 archivos totales también difieren) — no es una regresión de este cambio, pero `apply` verificó solo `ruff check` (linting), nunca `ruff format --check`.
3. **Deuda preexistente ajena al cambio** — 1 error de `ruff check` en `tests/test_cross_tenant_isolation.py:128` (E501) y 6 errores de `mypy` en 4 archivos (`organizations/repository.py`, `organizations/service.py`, `org_role_templates/service.py`, `tasks/service.py`), ninguno tocado por este cambio (confirmado por `git log` — último commit de ese archivo es `9be4a40`, ajeno al 42). Fuera de alcance de este `verify`, mencionado solo por transparencia.

**SUGGESTION**:
1. Considerar agregar una prueba de integración para `--purge-upload-files --execute` que cree ficheros reales en un `tmp_path`, ejecute la CLI con `run_maintenance` mockeado o contra una BD real mínima, y verifique que solo los ficheros referenciados desaparecen — cerraría el hallazgo CRITICAL #1 con un esfuerzo pequeño (el helper `_seed_demo_fixture` ya existe para poblar `attachments` con `stored_name` conocido).
2. Considerar una prueba `test_maintenance_nunca_se_expone_por_http` que itere `app.routes` (o `app.openapi()["paths"]`) y confirme que ninguna ruta bajo `/api/v1` importa o invoca símbolos de `app.maintenance`/`scripts.purge_demo_data` — cerraría el hallazgo CRITICAL #2 con una prueba de arquitectura reutilizable para cambios futuros.
3. Ejecutar `ruff format app/maintenance app/db_init.py tests/test_bootstrap_hierarchy.py tests/test_maintenance_invariants.py tests/test_seed_demo_flag.py` para alinear estos 7 archivos con el formateador configurado, en un commit de mantenimiento separado y de bajo riesgo.

### Verdict

**FAIL**

2 escenarios de spec obligatorios («`--purge-upload-files` borra solo los archivos referenciados» y «El mantenimiento nunca se expone por HTTP») no tienen ninguna prueba automatizada que los cubra en tiempo de ejecución — solo lógica parcial o inspección estática. El resto del cambio (32/35 escenarios, 55/55 tareas, 1411/1414 pruebas de la suite completa con los 3 fallos preexistentes esperados, dry-run real contra `solercia` con 8/8 invariantes en PASS) está conforme y listo. Remediación sugerida: 2 pruebas nuevas y acotadas (ver SUGGESTION #1–#2), reejecutar `sdd-apply` en modo corrección, y volver a `sdd-verify`.
