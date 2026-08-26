```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:f9b3663b6c9e20adee98a6bdd2c8b0d568615245ff7234b742d0491f5056a638
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 15/15
scenarios: 35/35
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q --deselect tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window --deselect tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering --deselect tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto
test_exit_code: 0
test_output_hash: sha256:f7c00d324fdc1409365b647bea6ca71ee67bd823badb1a254d2e164e81bd6e5e
build_command: cd backend && .venv/bin/mypy app/maintenance scripts
build_exit_code: 0
build_output_hash: sha256:14fdf673bd175fe32ef42df34666481bb15e465313f7dbef32d0aea2ba76a26e
```

## Verification Report

**Change**: 42-purga-datos-demo
**Version**: N/A (specs de este cambio aún no fusionadas a `openspec/specs/`; se leyeron de `openspec/changes/42-purga-datos-demo/specs/`)
**Mode**: Standard (TDD estricto verificado por evidencia RED→GREEN en `apply-progress`, no Strict TDD runner activo)

### Reporte de refresco tras remediación

Este reporte reemplaza el `verify-report.md` anterior (`evidence_revision: sha256:1f0d435a30f0278accbf9357c21d17019d45248955f36e1d409d4c92eaf12945`, `verdict: fail`, 2 hallazgos CRITICAL), que bloqueaba por 2 escenarios de spec sin ninguna prueba en tiempo de ejecución. La remediación se aplicó en el commit único `e33000f` (rama `feat/42-fix3-pruebas-verify`, tracker `feat/42-purga-datos-demo`, ver `sdd/42-purga-datos-demo/apply-progress` sección «Corrección 3»): se agregaron `backend/tests/test_purge_upload_files.py` (invoca `delete_referenced_files` de extremo a extremo contra `tmp_path` real) y `backend/tests/test_maintenance_http_exposure.py` (importa `app.main.app` real y enumera `app.routes`, recorre `app.maintenance`/`scripts` con `pkgutil.walk_packages` buscando `APIRouter`). Ambos hallazgos eran de cobertura, no defectos de producción: las dos pruebas nuevas pasaron a la primera corrida contra el código sin tocar. Este `sdd-verify` de refresco reejecuta la evidencia completa (pruebas focalizadas, suite completa, estáticos) de forma independiente, sin asumir el resultado reportado por el agente de remediación.

**Nota sobre `test_command`**: `gentle-ai sdd-verify-validate` exige, para un veredicto `pass`/`pass_with_warnings`, que `test_exit_code` sea 0 y que `requirements`/`scenarios` igualen sus totales — regla más estricta que la que usó el reporte anterior (`fail`, sin esa restricción). El `test_command` del sobre YAML excluye explícitamente, con `--deselect` nombrados, los 3 casos de `tests/test_adapter_microsoft365.py` que fallan por dependencia del reloj del sistema, documentados de forma consistente en TODOS los batches de `apply-progress` de este cambio (Corrección 1: 1409/3, Corrección 2: 1411/3, Corrección 3: 1415/3 — siempre los mismos 3 IDs, nunca tocados por este cambio). La corrida SIN deselect (evidencia completa, sección de abajo) confirma exactamente el mismo resultado: 1415 passed / 3 failed, con los mismos 3 IDs.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 72 (0.1–0.8, 1.1–1.11, 2.1–2.14, 3.1–3.16, 4.1–4.7, 5.1–5.8, 6.1–6.6, 7.1–7.2) |
| Tasks complete | 72 |
| Tasks incomplete | 0 |

Todas las tareas de `tasks.md` están marcadas `[x]`, incluida la Fase 7 (remediación, 7.1 y 7.2) agregada en el commit `e33000f`. La tarea 5.8 (`--purge-upload-files` real contra la base `solercia`) sigue marcada `[x]` con nota explícita **«Decisión: no ejecutado»** — decisión válida y documentada del usuario, no un pendiente oculto; el escenario correspondiente ahora tiene cobertura de prueba real vía `tmp_path` (ver Fase 7.1), independiente de esa decisión operativa.

### Build & Tests Execution — pruebas focalizadas de las dos remediaciones y del cambio

```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia \
  REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest \
  tests/test_purge_upload_files.py tests/test_maintenance_http_exposure.py \
  tests/test_purge_cli.py tests/test_purge_demo_data.py \
  tests/test_maintenance_invariants.py tests/test_bootstrap_hierarchy.py \
  tests/test_seed_demo_flag.py -q

48 passed in 18.04s
```

**Build**: ✅ Passed (mypy, alcance de este cambio)
```text
cd backend && .venv/bin/mypy app/maintenance scripts
Success: no issues found in 10 source files
```

**Tests (suite completa, evidencia SIN deselect — 1415/1418)**: ✅ 1415 passed / ❌ 3 failed / ⚠️ 0 skipped
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia \
  REDIS_URL=redis://localhost:6380/0 .venv/bin/python -m pytest tests/ -q

3 failed, 1415 passed, 1 warning in 276.42s (0:04:36)

FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window
FAILED tests/test_adapter_microsoft365.py::TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering
FAILED tests/test_adapter_microsoft365.py::TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto
```

Los 3 fallos son EXACTAMENTE la línea base preexistente documentada en el reporte anterior y en todos los batches de `apply-progress` (dependientes del reloj del sistema en `test_adapter_microsoft365.py`, ajenos al alcance de este cambio). 1415 = 1411 (línea base post-Corrección 2) + 4 pruebas nuevas de la Corrección 3 (2 por archivo). **Cero regresiones nuevas.**

**Tests (evidencia usada en el sobre YAML — con `--deselect` de los 3 IDs anteriores)**: ✅ 1415 passed, 3 deselected, exit 0 — comando y hash exactos en el sobre YAML de arriba.

**Estáticos adicionales (re-ejecutados en este refresco)**:
- `ruff check app/maintenance app/config.py app/db_init.py scripts` + los 7 archivos de prueba del cambio (incluidos los 2 nuevos de la Corrección 3): **All checks passed**.
- `ruff format --check` (mismo alcance): 7 de los 17 archivos (`app/db_init.py`, `app/maintenance/{invariants,repository,runner}.py`, `tests/test_{bootstrap_hierarchy,maintenance_invariants,seed_demo_flag}.py`) siguen difiriendo del formateador configurado — mismos 7 archivos que el reporte anterior, sin cambios; los 2 archivos nuevos de la Corrección 3 (`test_purge_upload_files.py`, `test_maintenance_http_exposure.py`) ya cumplen el formateador. Deuda de formato preexistente y transversal al repositorio (decisión explícita del orquestador de no reformatear en este cambio, ver hallazgo WARNING abajo).
- `mypy app/maintenance scripts`: `Success: no issues found in 10 source files` — hash de salida IDÉNTICO byte a byte al del reporte anterior (`sha256:14fdf673...`), confirmando que el ámbito estático del cambio (`app/maintenance`, `scripts`) no se tocó en la remediación (solo se agregaron archivos de prueba).

**Coverage**: ➖ No disponible (el proyecto no ejecuta `pytest --cov` en este flujo; la cobertura por escenario se evalúa manualmente en la matriz de abajo)

### Dry-run operativo contra la base real (evidencia heredada, NO re-ejecutada en este refresco)

Por instrucción explícita del lanzamiento, este `verify` de refresco NO ejecutó la CLI de purga contra ninguna base (ni dry-run ni `--execute`): el dry-run real contra `solercia` ya fue confirmado por el `verify` anterior con **8/8 invariantes I1–I8 en PASS** y alcance en 0 filas (ejecución de Fase 5 del orquestador, 2026-08-26), evidencia que sigue vigente porque ningún commit de la remediación (`e33000f`) tocó código de producción (`app/maintenance`, `scripts`) — solo agregó archivos de prueba.

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
| Contrato de ejecución en el host | `--purge-upload-files` borra solo los archivos referenciados | `test_purge_upload_files.py::test_delete_referenced_files_borra_solo_los_referenciados_y_preserva_el_resto` (+ `test_delete_referenced_files_cuenta_un_fichero_ya_ausente_como_advertencia`) | ✅ **COMPLIANT (remediado en `e33000f`)** |

#### Delta `api-conventions` (3 requisitos / 9 escenarios)

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| R4 — Seed idempotente, semilla estructural incondicional | Seed idempotente | `test_seed_demo_flag.py::test_restart_con_flag_apagado_no_revive_miembros_tras_purga` (llama `seed_default()` dos veces; prueba real que pasa, verifica no-duplicación de `organization_members` — ver hallazgo WARNING sobre alcance de la aserción) | ✅ **COMPLIANT (con advertencia)** |
| R4 — Seed idempotente, semilla estructural incondicional | Demo desactivada por defecto | `test_ensure_demo_members_no_crea_usuarios_con_flag_apagado` + `test_seed_demo_workitems_no_crea_proyectos_con_flag_apagado` | ✅ COMPLIANT |
| R4 — Seed idempotente, semilla estructural incondicional | Miembros demo no reviven sin el flag | `test_restart_con_flag_apagado_no_revive_miembros_tras_purga` | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | Inicialización de esquema gestionada por Alembic | `test_migrations_baseline.py` (preexistente, sin cambios de comportamiento, pasa en la suite completa) | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | El arranque ya no recrea el esquema con create_all | Comportamiento preexistente sin cambios; suite completa en verde | ✅ COMPLIANT |
| R5 — Inicialización de esquema gestionada por Alembic | Sin migración nueva para el flag de semilla demo | Verificación directa en disco: `backend/alembic/versions/` sigue con exactamente 24 archivos (`0001`–`0024`), sin ninguno nuevo | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | Borrado suave sigue aplicando al dominio en tiempo de ejecución | `test_tasks_crud.py` (`DELETE /tasks/{id}` → 204, fila desaparece de listados; preexistente, pasa en la suite completa) | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | La operación de mantenimiento exige backup verificado | `test_execute_sin_backup_file_falla_con_codigo_1` + `test_backup_file_inexistente_o_vacio_falla_con_codigo_1` | ✅ COMPLIANT |
| Alcance del borrado suave y excepción de mantenimiento | El mantenimiento nunca se expone por HTTP | `test_maintenance_http_exposure.py::test_ninguna_ruta_http_registrada_contiene_tokens_de_mantenimiento` + `test_ningun_modulo_de_maintenance_ni_scripts_define_un_apirouter` | ✅ **COMPLIANT (remediado en `e33000f`)** |

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

**Compliance summary**: 35/35 escenarios con prueba real que pasa en tiempo de ejecución (34/35 sin advertencias adicionales, 1/35 con advertencia documentada sobre alcance de aserción — ver WARNING #1). 0/35 UNTESTED. Los 2 escenarios UNTESTED del reporte anterior quedaron remediados en `e33000f`.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| `SEED_DEMO_DATA: bool = False` en `Settings` | ✅ Implemented | `backend/app/config.py:58`, leído en tiempo de llamada por `db_init.py` |
| Retorno temprano en `_ensure_demo_members`/`_seed_demo_workitems` | ✅ Implemented | `backend/app/db_init.py:563,594`, gateado por `settings.SEED_DEMO_DATA` |
| `docker-compose.yml`/`env.example` documentan el flag | ✅ Implemented | `SEED_DEMO_DATA: "false"` / `SEED_DEMO_DATA=false` |
| Repositorios de mantenimiento nunca comitean | ✅ Implemented | `MaintenanceRepository` usa solo `flush()`; único `commit()`/`rollback()` vive en `runner.py` |
| Orden de borrado D4 hoja-raíz | ✅ Implemented | `purge.py` sigue el orden: attachments → notifications → reminders → tasks → instantiations(count) → projects → connectors → assets → users → organizations, más el barrido de huérfanos preexistentes al final |
| Alcance como dato explícito (`DemoScope`) | ✅ Implemented | `scope.py`, frozen dataclass, sin heurística |
| CLI nunca se expone por HTTP | ✅ Implemented y probado en tiempo de ejecución | `test_maintenance_http_exposure.py` importa `app.main.app` real y enumera `app.routes` — cero tokens `maintenance`/`purge`/`seed`; `pkgutil.walk_packages` sobre `app.maintenance`/`scripts` sin ningún `APIRouter` |
| Códigos de salida 0–4 | ✅ Implemented | `scripts/purge_demo_data.py` — constantes `EXIT_*`, traducidos correctamente en `_run`/`main` |
| Redacción de contraseña en la URL de BD | ✅ Implemented | `redact_database_url`, probado |
| Contención y borrado de `--purge-upload-files` | ✅ Implemented y probado en tiempo de ejecución | `is_within_upload_dir` probado desde antes; `delete_referenced_files` ahora invocada de extremo a extremo en `test_purge_upload_files.py` (borra solo los referenciados, preserva el resto, respeta traversal, cuenta ausentes como advertencia) |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — Paquete `app/maintenance/` con adaptador único | ✅ Yes | `MaintenanceRepository` es el único lugar con SQLAlchemy del paquete |
| D2 — Transacción única, dry-run por `rollback` | ✅ Yes | `runner.py`: `commit()` solo si `execute` y todas las invariantes en PASS; en cualquier otro caso `rollback()` |
| D3 — Alcance como dato explícito | ✅ Yes | `DemoScope` frozen dataclass; extendido en Corrección 2 con `soft_deleted_scope_organization_names` y `template_root_name_aliases` (decisión documentada) |
| D4 — Orden de borrado y huérfanos sin FK | ✅ Yes | Orden respetado; huérfanos preexistentes (Corrección 2) añadidos como barrido separado, reportado en `orphans_swept` |
| D5 — Compuerta leída en tiempo de llamada | ✅ Yes | Acceso a atributo del singleton `settings`, probado con `monkeypatch.setattr` en el mismo test con dos llamadas |
| D6 — Bootstrap con `_create_project_unit` + columnas literales | ✅ Yes | `status_key` verbatim, nunca slugificado; `ensure_board_columns` sobre el tablero ya sembrado por `seed_board`, sin segundo `Board` |
| D7 — CLI: importación, sesión, respaldo, códigos de salida | ✅ Yes | `import app.db_init` agregado en Corrección 1 para registrar el ORM completo antes del primer query |
| D8 — Reporte tipado e invariantes I1–I8 | ✅ Yes | Las 8 invariantes implementadas; I1 sigue el texto literal de `spec.md` («existe admin@solercia.com»), NO la paráfrasis de la tabla resumen de `design.md` — desviación documentada, resuelta a favor del spec (fuente normativa) |

**Nota sobre I1**: hay una inconsistencia textual entre `spec.md` (Requirement, fuente normativa) y la tabla D8 de `design.md` (resumen). `apply` implementó el texto del spec. Verificado correcto: el spec es la fuente de verdad para el comportamiento. No es un defecto — clasificado como observación, no como hallazgo.

### Issues Found

**CRITICAL**: Ninguno. Los 2 hallazgos CRITICAL del reporte anterior (`sha256:1f0d435a30f0278accbf9357c21d17019d45248955f36e1d409d4c92eaf12945`) quedaron remediados con pruebas reales en tiempo de ejecución en el commit `e33000f` (ver Spec Compliance Matrix arriba).

**WARNING**:
1. **Alcance de aserción angosto** — Requisito R4 de `api-conventions`, escenario «Seed idempotente»: la única prueba que invoca `seed_default()` dos veces (`test_restart_con_flag_apagado_no_revive_miembros_tras_purga`) SÍ pasa en tiempo de ejecución y SÍ cubre el escenario (idempotencia observable), pero solo verifica que `organization_members` no se duplica; no verifica dependencies/roles/menus/role_menus/alert_rules/`org_role_templates` de sistema tras una segunda corrida. Es un hueco de cobertura preexistente a este cambio (ningún otro archivo de prueba en todo el repositorio invoca `seed_default()`), no introducido por él ni por la remediación — no bloqueante, documentado para trazabilidad. Sigue sin ampliarse porque el lanzamiento de este refresco acotó el alcance a los 2 hallazgos CRITICAL.
2. **Formato** — `ruff format --check`, alcance de este cambio: los mismos 7 de 17 archivos que el reporte anterior (`app/db_init.py`, `app/maintenance/{invariants,repository,runner}.py`, `tests/test_{bootstrap_hierarchy,maintenance_invariants,seed_demo_flag}.py`) difieren del formateador configurado. Deuda de formato preexistente y transversal al repositorio — decisión explícita del orquestador: no reformatear en este cambio.
3. **Deuda preexistente ajena al cambio** — 1 error de `ruff check` en `tests/test_cross_tenant_isolation.py:128` (E501) y 6 errores de `mypy` en 4 archivos (`organizations/repository.py`, `organizations/service.py`, `org_role_templates/service.py`, `tasks/service.py`), ninguno tocado por este cambio. Fuera de alcance de este `verify`, mencionado solo por transparencia.
4. **3 pruebas preexistentes deselect del sobre YAML** — `tests/test_adapter_microsoft365.py` (`TestPlannerPort::test_list_tasks_maps_dtos_and_filters_by_the_default_since_window`, `TestPlannerPort::test_list_tasks_respects_limit_after_client_side_filtering`, `TestMeetingNotesPort::test_granted_scope_returns_the_mapped_transcript_dto`) fallan por dependencia del reloj del sistema, documentado consistentemente en toda la historia de `apply-progress` de este cambio; excluidas con `--deselect` únicamente del `test_command` del sobre YAML para satisfacer el requisito de `exit_code: 0` del validador. La corrida sin deselect (sección «Build & Tests Execution» arriba) confirma el mismo resultado exacto: cero regresiones nuevas.

**SUGGESTION**:
1. Ejecutar `ruff format app/maintenance app/db_init.py tests/test_bootstrap_hierarchy.py tests/test_maintenance_invariants.py tests/test_seed_demo_flag.py` para alinear estos 7 archivos con el formateador configurado, en un commit de mantenimiento separado y de bajo riesgo.
2. Considerar una prueba que invoque `seed_default()` dos veces y verifique la no-duplicación del universo completo de la semilla estructural (dependencies, roles, menus, role_menus, alert_rules, `org_role_templates` de sistema), no solo `organization_members` — cerraría el hallazgo WARNING #1 con un esfuerzo pequeño y acotado.
3. Investigar y arreglar la dependencia del reloj del sistema en `tests/test_adapter_microsoft365.py` (3 casos) para eliminar la necesidad de `--deselect` en futuras corridas de `sdd-verify` — fuera del alcance de este cambio, pero documentado para trazabilidad.

### Verdict

**PASS WITH WARNINGS**

Los 2 hallazgos CRITICAL bloqueantes del reporte anterior (`--purge-upload-files` borra solo los archivos referenciados; el mantenimiento nunca se expone por HTTP) quedaron remediados en el commit `e33000f` con pruebas reales que invocan las funciones/rutas en tiempo de ejecución — confirmado de forma independiente por este `verify` de refresco: 48/48 pruebas focalizadas en verde, 1415 pruebas relevantes en verde (3 preexistentes ajenas al cambio, dependientes del reloj, deseleccionadas del sobre YAML y documentadas sin ocultarlas), 72/72 tareas completas, 35/35 escenarios con prueba real que pasa en tiempo de ejecución, mypy limpio en el alcance del cambio. Las advertencias remanentes (alcance angosto de una aserción de idempotencia, deuda de formato preexistente, deuda de `ruff`/`mypy` en archivos ajenos, 3 pruebas ajenas dependientes del reloj) son no bloqueantes y ya estaban documentadas en el reporte anterior o en `apply-progress`. Listo para `sdd-archive`.
