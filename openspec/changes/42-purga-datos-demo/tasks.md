# Tasks: 42 · Purga de datos demo y bootstrap de la jerarquía SDMUJER

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2 170 (`additions + deletions`), repartidas en 4 rebanadas |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Rebanada 1 → 2a → 2b → 3 (feature-branch-chain, cada una sobre la anterior) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

| Rebanada | Contenido | ≈ líneas |
|---|---|---|
| 1 | Compuerta `SEED_DEMO_DATA` + `docker-compose.yml`/`env.example` + `test_seed_demo_flag.py` | 150 |
| 2a | `maintenance/{scope,report,repository,purge}.py` (ruta de purga) + `test_purge_demo_data.py` (7/8 casos) | 750 |
| 2b | `repository.py` (bootstrap) + `maintenance/{bootstrap,invariants,runner}.py` + `test_bootstrap_hierarchy.py` + `test_maintenance_invariants.py` + caso 8 de `test_purge_demo_data.py` | 830 |
| 3 | `backend/scripts/{__init__,purge_demo_data}.py` + `test_purge_cli.py` + runbook en `backend/README.md` | 440 |

El total (~2 170) roza el presupuesto de sesión (2 000): vigilar 2b, es la rebanada más grande.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Compuerta `SEED_DEMO_DATA` cierra la semilla demo por defecto | PR 1 (base: tracker `feat/42-purga-datos-demo`) | `cd backend && pytest tests/test_seed_demo_flag.py -v` | `docker compose up -d --build backend` con `SEED_DEMO_DATA=false`; confirmar que ana/carlos/diana no aparecen | Revertir `config.py`/`db_init.py`/`docker-compose.yml`/`env.example`; sin dependencias de `maintenance/` |
| 2a | Purga idempotente y guardas de fallo cerrado (sin bootstrap ni runner) | PR 2a (base: rama de PR 1) | `cd backend && pytest tests/test_purge_demo_data.py -v` (7/8 casos) | N/A — sin CLI aún; se prueba contra la `session` SAVEPOINT | Revertir `maintenance/{scope,report,repository,purge}.py`; `bootstrap`/`runner` aún no existen |
| 2b | Bootstrap SDMUJER, invariantes I1-I8 y `runner.py` (dueño de la transacción) | PR 2b (base: rama de PR 2a) | `cd backend && pytest tests/test_bootstrap_hierarchy.py tests/test_maintenance_invariants.py tests/test_purge_demo_data.py -v` | N/A — sin CLI aún | Revertir `maintenance/{bootstrap,invariants,runner}.py`; `purge.py` de 2a sigue intacto |
| 3 | CLI delgada, códigos de salida 0-4 y runbook operativo | PR 3 (base: rama de PR 2b) | `cd backend && pytest tests/test_purge_cli.py -v` | `cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia` (dry-run contra la base real) | Revertir `backend/scripts/` + sección del runbook; `maintenance/` sigue intacto |

Diagrama de dependencia: `tracker feat/42-purga-datos-demo → PR1 (compuerta) → PR2a (purga) → PR2b (bootstrap+invariantes+runner) → PR3 (CLI+runbook)`. Solo el tracker se integra a `preview`.

## Fase 0: Verificación previa (gate)

- [x] 0.1 Verificar `alembic heads` en disco: la cadena `0001→…→0024_add_work_calendar` es la única punta; este cambio NO agrega ninguna revisión nueva bajo `backend/alembic/versions/`.
- [x] 0.2 Confirmar en disco que `db_init.py` no importa `app.config`; `_seed_demo_workitems` (línea 562) y `_ensure_demo_members` (línea 586) siguen sin compuerta; `seed_default` (341-379) las invoca sin condición salvo el `COUNT(tasks)==0` (367-369).
- [x] 0.3 Confirmar en disco que `config.py` no declara `SEED_DEMO_DATA`; `docker-compose.yml` (bloque `environment:` del backend, 36-41) y `env.example` no la incluyen.
- [x] 0.4 Confirmar en disco: `ProjectService._create_project_unit` (`projects/service.py:128`); `BoardService.add_column` slugifica (`boards/service.py:203`) y comitea por columna (`:221`); `boards/models.py` con `uq_board_column_status_key` (:51) y `status_key String(60)` (:66).
- [x] 0.5 Confirmar en disco: `IntakeService._ensure_default_project` (`intake/service.py:581`) y `IntakeSettingsRepository.get_or_create` comitea (`intake/repository.py:265`).
- [x] 0.6 Confirmar en disco: `attachments/models.py` `target_type`/`target_id` sin FK (:29,32); `connectors/models.py` `connected_accounts.user_id` con `ondelete="CASCADE"` (:92); `tasks/service.py._resolve_completed_at` (:855).
- [x] 0.7 Confirmar que `backend/tests/test_intake_classifier_endpoints.py::test_first_use_creates_default_project_and_second_use_reuses_it` (línea 359) ya cubre el escenario «sin bootstrap previo, el comportamiento perezoso original sigue vigente» de la spec `intake-classifier` — no requiere una prueba nueva.
- [x] 0.8 Confirmar que `backend/app/maintenance/` y `backend/scripts/` no existen todavía en disco (paquetes nuevos de este cambio).

## Fase 1: Compuerta `SEED_DEMO_DATA` [Rebanada 1]

> Spec: Requirement «Compuerta de la semilla demo por SEED_DEMO_DATA»; deltas `multi-tenancy` R4, `api-conventions` R4/R5. Design: D5.

- [x] 1.1 RED — `backend/tests/test_seed_demo_flag.py::test_ensure_demo_members_no_crea_usuarios_con_flag_apagado`: con `settings.SEED_DEMO_DATA=False` (valor por defecto) y BD vacía, `_ensure_demo_members` no crea usuarios demo.
- [x] 1.2 RED — `test_ensure_demo_members_crea_usuarios_con_flag_encendido`: `monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)`; `_ensure_demo_members` crea ana/carlos/diana.
- [x] 1.3 RED — `test_seed_demo_workitems_no_crea_proyectos_con_flag_apagado`: flag apagado, `_seed_demo_workitems` no crea proyectos ni tareas.
- [x] 1.4 RED (inclusión obligatoria #1) — `test_seed_demo_workitems_crea_proyectos_tareas_y_sprint_con_flag_encendido`: flag encendido, `_seed_demo_workitems` crea los proyectos demo, las tareas demo y el sprint scrum (assert conteos > 0 en las tres entidades, no solo miembros).
- [x] 1.5 RED — `test_compuerta_se_lee_en_tiempo_de_llamada`: cambia `settings.SEED_DEMO_DATA` entre dos llamadas dentro del mismo test; cada llamada respeta el valor vigente (nunca una constante capturada al importar).
- [x] 1.6 RED — `test_restart_con_flag_apagado_no_revive_miembros_tras_purga`: BD ya purgada (sin ana/carlos/diana) y `seed_default()` corre de nuevo con el flag apagado; la cuenta de usuarios de «Solercia» permanece en 1.
- [x] 1.7 GREEN — agregar `SEED_DEMO_DATA: bool = False` a `backend/app/config.py` (`Settings`).
- [x] 1.8 GREEN — `db_init.py`: importar `from app.config import settings`; retorno temprano `if not settings.SEED_DEMO_DATA: return []` al inicio de `_ensure_demo_members` (:586) y `return` al inicio de `_seed_demo_workitems` (:562).
- [x] 1.9 GREEN — `docker-compose.yml`: agregar `SEED_DEMO_DATA: "false"` al bloque `environment:` del backend (:36-41).
- [x] 1.10 GREEN — `env.example`: documentar `SEED_DEMO_DATA=false`.
- [x] 1.11 Verificar en verde: `cd backend && pytest tests/test_seed_demo_flag.py -v`.

## Fase 2: Ruta de purga [Rebanada 2a]

> Spec: «Purga idempotente con dry-run por defecto», «Orden de borrado de hoja a raíz…», «Protección del catálogo de sistema y de conectores reales», «Fallo cerrado si una connected_account pertenece a un usuario a borrar». Design: D1, D3, D4. `purge_demo_data` nunca comitea (D2) — el `commit()` llega con `runner.py` en la Fase 3.

- [x] 2.1 Crear helper `_seed_demo_fixture(session)` (local en `test_purge_demo_data.py`, inspirado en `_seed_org_data` de `conftest.py:376-460`): organización `Acme Consultores`, admin/org `Solercia`, ana/carlos/diana, proyectos con subárbol, adjuntos/notificaciones/recordatorios huérfanos, conector `fake`.
- [x] 2.2 RED — `test_purga_borra_org_demo_usuarios_y_proyectos`.
- [x] 2.3 RED — `test_purga_conserva_admin_org_solercia_y_plantillas_de_sistema`.
- [x] 2.4 RED — `test_purga_borra_adjuntos_notificaciones_y_recordatorios_huerfanos`.
- [x] 2.5 RED — `test_purga_borra_subarbol_completo_de_hoja_a_raiz`.
- [x] 2.6 RED — `test_purga_borra_conector_fake_y_conserva_los_reales`.
- [x] 2.7 RED — `test_purga_falla_cerrado_si_una_cuenta_conectada_pertenece_a_un_usuario_demo`.
- [x] 2.8 RED — `test_purga_es_idempotente_en_segunda_corrida`.
- [x] 2.9 GREEN — crear `backend/app/maintenance/__init__.py` (paquete).
- [x] 2.10 GREEN — crear `backend/app/maintenance/scope.py`: `DemoScope` (frozen dataclass, D3) con `organization_names`, `user_emails`, `project_names`, `include_template_instantiations`, `connector_providers`, `asset_names`, `protected_*`.
- [x] 2.11 GREEN — crear `backend/app/maintenance/report.py` (parcial): `InventoryRow`, `PlannedDeletion`, `DeletionResult`, `PurgeOutcome`.
- [x] 2.12 GREEN — crear `backend/app/maintenance/repository.py` (parcial, `MaintenanceRepository`): `resolve_demo_scope` (CTE recursivo sobre `parent_project_id`), `find_connected_accounts_owned_by`, `count_inventory` (parcial), y los métodos de borrado del orden D4 (checklists → logs/historial/comentarios/labels/asset_tasks → `attachments` por `target_id` → `notification_deliveries`→`notifications` por `target_id` → `reminders`/`reminder_rules` → intake del alcance → `tasks` → sprints/board_columns/boards/labels → `org_role_template_instantiations` → `projects` de hoja a raíz → conector `fake` → usuarios demo → organización). Ningún método comitea.
- [x] 2.13 GREEN — crear `backend/app/maintenance/purge.py`: `purge_demo_data(session, scope) -> PurgeOutcome` — resuelve alcance, aplica guardas de fallo cerrado (admin/org/códigos/proveedores protegidos + cuentas conectadas), ejecuta el orden D4 vía `MaintenanceRepository`, retorna el reporte.
- [x] 2.14 Verificar en verde: `cd backend && pytest tests/test_purge_demo_data.py -v` (7/8 casos; `test_dry_run_no_deja_cambios_visibles` se agrega en la Fase 3).

## Fase 3: Bootstrap, invariantes y `runner.py` [Rebanada 2b]

> Spec: «Bootstrap idempotente de la jerarquía SDMUJER», «Invariantes post-ejecución con código de salida no cero». Design: D2, D6, D8.

- [x] 3.1 RED — `test_bootstrap_crea_sdmujer_seguridad_pandora_con_codigos_y_metodologias`.
- [x] 3.2 RED — `test_seguridad_tiene_siete_columnas_y_completada_es_la_de_mayor_order`.
- [x] 3.3 RED — `test_status_key_de_las_columnas_es_literal_no_slug` (contraste con `BoardService.add_column`).
- [x] 3.4 RED — `test_pandora_recibe_las_columnas_por_defecto_de_kanban`.
- [x] 3.5 RED — `test_bootstrap_es_idempotente_y_reutiliza_proyectos_por_codigo`.
- [x] 3.6 RED — `test_intake_settings_apunta_a_seguridad_sin_crear_tareas_outlook`.
- [x] 3.7 GREEN — extender `backend/app/maintenance/repository.py`: `find_project_by_code`, `ensure_board_columns` (sin slugificar, sin commit — D6), `upsert_intake_default_project` (upsert ORM directo, nunca `IntakeSettingsRepository.get_or_create`).
- [x] 3.8 GREEN — crear `backend/app/maintenance/bootstrap.py`: `bootstrap_sdmujer(session, *, organization_id, actor_id)` vía `ProjectService._create_project_unit` (`# noqa: SLF001`, precedente `org_role_templates/service.py:295`) para SDMUJER/SEGURIDAD/PANDORA, `ensure_board_columns` para SEGURIDAD (7 columnas, `order` 0-6), `upsert_intake_default_project`.
- [x] 3.9 Verificar en verde: `cd backend && pytest tests/test_bootstrap_hierarchy.py -v`.
- [x] 3.10 RED (inclusión obligatoria #2, I1-I8) — en `test_maintenance_invariants.py`: `test_invariante_i1_falla_si_no_existe_admin`, `_i2_falla_si_existe_acme_consultores`, `_i3_falla_si_falta_codigo_o_padre_esperado`, `_i4_falla_si_completada_no_es_la_ultima_columna`, `_i5_falla_si_default_project_id_no_apunta_a_seguridad`, `_i6_falla_si_quedan_adjuntos_huerfanos`, `_i7_falla_si_hay_instantiations_del_alcance_demo`, `_i8_falla_si_sobrevive_un_conector_fake` — un caso de fallo inyectado por cada invariante.
- [x] 3.11 GREEN — extender `backend/app/maintenance/report.py`: `InvariantResult`, `MaintenanceReport` (`ok = all(i.passed …)`).
- [x] 3.12 GREEN — crear `backend/app/maintenance/invariants.py`: `collect_invariants(session) -> tuple[InvariantResult, ...]` con las 8 verificaciones I1-I8 (D8).
- [x] 3.13 Verificar en verde: `cd backend && pytest tests/test_maintenance_invariants.py -v`.
- [x] 3.14 RED (carry-over de Fase 2) — agregar a `test_purge_demo_data.py::test_dry_run_no_deja_cambios_visibles`: `run_maintenance(execute=False)` no deja cambios visibles tras `rollback`.
- [x] 3.15 GREEN — crear `backend/app/maintenance/runner.py`: `run_maintenance(session, *, execute, scope) -> MaintenanceReport` — llama `purge_demo_data` → `bootstrap_sdmujer` → `collect_invariants`; `commit()` solo si `execute` y todas las invariantes en PASS; en cualquier otro caso `rollback()` (D2).
- [x] 3.16 Verificar en verde: `cd backend && pytest tests/test_purge_demo_data.py tests/test_bootstrap_hierarchy.py tests/test_maintenance_invariants.py -v`.

## Fase 4: CLI, códigos de salida y runbook [Rebanada 3]

> Spec: «Respaldo obligatorio y verificado antes de cualquier borrado», «Contrato de ejecución en el host». Design: D7.

- [x] 4.1 RED (inclusión obligatoria #3, sin BD) — crear `backend/tests/test_purge_cli.py`: `test_dry_run_es_el_modo_por_defecto`, `test_execute_sin_backup_file_falla_con_codigo_1`, `test_backup_file_inexistente_o_vacio_falla_con_codigo_1`, `test_purge_upload_files_esta_apagado_por_defecto`, `test_purge_upload_files_rechaza_rutas_fuera_de_upload_dir`, `test_la_url_de_base_de_datos_se_redacta_en_la_salida` — parseo de argumentos y verificación de backup, sin conexión real.
- [x] 4.2 RED (inclusión obligatoria #3, traducción vía fakes) — en el mismo archivo: `test_dry_run_exitoso_retorna_codigo_0`, `test_execute_exitoso_con_invariantes_en_pass_retorna_codigo_0`, `test_guarda_de_seguridad_retorna_codigo_2_sin_escribir`, `test_invariante_en_fail_retorna_codigo_3`, `test_excepcion_inesperada_retorna_codigo_4` — con `run_maintenance` reemplazado por un fake/mock, sin BD.
- [x] 4.3 GREEN — crear `backend/scripts/__init__.py` (paquete explícito, requerido para `python -m scripts.purge_demo_data`).
- [x] 4.4 GREEN — crear `backend/scripts/purge_demo_data.py`: `argparse` (`--dry-run` por defecto, `--execute`, `--backup-file`, `--database-url`, `--purge-upload-files`); `create_async_engine`/`async_sessionmaker` propios con `dispose()`; verifica backup (existe + tamaño > 0) antes de tocar la base; ejecuta `run_maintenance`; imprime INVENTARIO/BORRADOS/INVARIANTES con la URL de base redactada; traduce el resultado a los códigos 0-4 (D7); borra archivos de `UPLOAD_DIR` referenciados solo después del `commit` si `--purge-upload-files`, con `resolve()` + `is_relative_to(UPLOAD_DIR)`.
- [x] 4.5 Verificar en verde: `cd backend && pytest tests/test_purge_cli.py -v`.
- [x] 4.6 Documentar en `backend/README.md`: agregar `SEED_DEMO_DATA` a la tabla «Variables de entorno» y una sección «Scripts operativos» con el runbook completo — respaldo (`pg_dump` desde el host contra `gestion_proyectos-postgres-1`), dry-run con `--database-url`, revisión humana, `--execute --backup-file`, invariantes, reinicio con reconstrucción de imagen y reverificación, y los comandos exactos de rollback (`docker compose stop backend`; `DROP SCHEMA public CASCADE` + `CREATE SCHEMA public` + `GRANT`; restauración del volcado; `docker compose start backend`).
- [x] 4.7 Verificar en verde: `cd backend && pytest tests/ -v` (suite completa del paquete `maintenance`/`scripts` antes de tocar la base real).

## Fase 5: Ejecución operativa sobre la base real [MANUAL — orquestador, no `pytest`]

> Runbook de `proposal.md`; corre contra `gestion_proyectos-postgres-1`/`solercia`. Requiere las Fases 0-4 en verde.

- [ ] 5.1 [MANUAL] Respaldo: `mkdir -p /Users/camilocalderont/Proyectos/SOLERCIA/backups && docker exec gestion_proyectos-postgres-1 pg_dump -U app solercia > /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql`; confirmar tamaño > 0.
- [ ] 5.2 [MANUAL] Compuerta primero: desplegar con `SEED_DEMO_DATA=false` — `docker compose up -d --build backend`; confirmar que ana/carlos/diana no reaparecen tras el reinicio.
- [ ] 5.3 [MANUAL] Dry-run: `cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia`; revisar el reporte impreso (inventario, conectores con propietario, advertencias).
- [ ] 5.4 [MANUAL] Revisión humana explícita del reporte del dry-run antes de continuar (punto de no retorno).
- [ ] 5.5 [MANUAL] Ejecución real: agregar `--execute --backup-file <ruta del paso 5.1>`; confirmar código de salida 0 e invariantes I1-I8 en PASS.
- [ ] 5.6 [MANUAL] Reinicio con reconstrucción de imagen (obligatorio para que el código nuevo y `SEED_DEMO_DATA` tomen efecto): `docker compose up -d --build backend`.
- [ ] 5.7 [MANUAL] Reverificación post-reinicio: repetir el dry-run/invariantes y confirmar que ningún dato demo reaparece (ana/carlos/diana, org `Acme Consultores`, conector `fake`).
- [ ] 5.8 [MANUAL, opcional] `--purge-upload-files` solo si se decide limpiar `backend/uploads/` referenciados — fuera del runbook obligatorio salvo decisión explícita del usuario.

## Fase 6: Suite completa y cierre

- [x] 6.1 Ejecutar `cd backend && pytest tests/ -v` completo; comparar contra la línea base (1397 passed / 3 fallos preexistentes en `tests/test_adapter_microsoft365.py`); confirmar cero regresiones nuevas. Resultado de esta rebanada: **1408 passed, 3 failed** — los mismos 3 fallos preexistentes dependientes del reloj (sin tocar), +11 = exactamente las pruebas nuevas de `test_purge_cli.py`.
- [x] 6.2 Confirmar que `test_first_use_creates_default_project_and_second_use_reuses_it` (`test_intake_classifier_endpoints.py:359`) sigue en verde sin modificarse. Verificado: 1 passed.
- [x] 6.3 Confirmar que `backend/alembic/versions/` sigue con exactamente los archivos `0001`-`0024` — sin migración nueva. Verificado: 24 archivos, sin ninguno nuevo.
- [ ] 6.4 [sdd-archive, NO de apply] Nota: la fusión de `specs/data-maintenance/` y los deltas hacia `openspec/specs/{api-conventions,multi-tenancy,org-role-templates,intake-classifier}/` es trabajo de `sdd-archive`.
- [x] 6.5 Commits convencionales en español por unidad de trabajo — de esta rebanada (1, como indica la tabla de arriba): `feat(maintenance): agrega CLI de purga y runbook operativo`. Las unidades de las rebanadas 1/2a/2b ya están comiteadas en el tracker (`d5328c1`, `5590963`, `5beca2a`).
- [ ] 6.6 [orquestador, NO de apply] Ramas hijas sobre el tracker `feat/42-purga-datos-demo` (feature-branch-chain): `…--01-compuerta` (base: tracker) → `…--02a-purga` (base: 01) → `…--02b-bootstrap-invariantes` (base: 02a) → `…--03-cli-runbook` (base: 02b, esta rama `feat/42-s3-cli`). Solo el tracker se integra a `preview`.
