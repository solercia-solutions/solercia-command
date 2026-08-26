# Proposal: 42 · Purga de datos demo y bootstrap de la jerarquía SDMUJER

## Intent

**Problema de negocio.** La base de Solercia Command sigue siendo una demo: 4 usuarios sintéticos (`ana@`, `carlos@`, `diana@`, `verify-smoke-11@`), la organización `Acme Consultores`, proyectos y tareas de muestra, un árbol OAP-TI instanciado y un conector `fake`. Sobre esos datos no se puede operar el trabajo real ni confiar en la vista ejecutiva: el avance, la carga por persona y las alertas mezclan ficción con realidad. La Ola 5 (cambios 43–49) importa el checklist real, los planes institucionales y el correo; **ninguna de esas importaciones puede empezar sobre datos sucios**.

**Urgencia.** La semilla es activa, no inerte. `_ensure_demo_members` corre **sin condición** en cada arranque (`db_init.py:360`) y `_seed_demo_workitems` se dispara con `COUNT(tasks) == 0` **global** (`db_init.py:367-369`). Tras una purga sin compuerta, el siguiente `docker compose restart` no recrearía la demo: **inyectaría 12 tareas dentro de los proyectos reales**, con estados `todo/doing/done` inexistentes en un tablero `custom` (`db_init.py:692-693`). La ventana es real mientras la base tenga 0 tareas, es decir entre este cambio y el 44.

**Éxito.** Una base con un solo usuario (`admin@solercia.com`), una organización (`Solercia`), la jerarquía `SDMUJER > {SEGURIDAD, PANDORA}` lista para recibir el checklist, y la garantía verificada de que reiniciar el backend no reintroduce nada.

## Scope

### In Scope

- `SEED_DEMO_DATA: bool = False` en `Settings`, leído **en tiempo de llamada** para cerrar `_ensure_demo_members` y `_seed_demo_workitems`. La semilla estructural (org, admin, roles, menús, dependencias, `alert_rules`, `ensure_system_templates`) sigue siendo incondicional.
- Casos de uso de mantenimiento en `backend/app/maintenance/` (`purge.py`, `bootstrap.py`): dueños de la transacción, repositorios sin `commit`.
- CLI delgada `backend/scripts/purge_demo_data.py`: `--dry-run` por defecto, `--execute` explícito, `--backup-file` obligatorio y verificado, `--database-url`, `--purge-upload-files` opcional.
- Borrado **físico** del alcance demo, incluidos los huérfanos sin FK (`attachments`, `notifications`, `notification_deliveries`, `reminders`) y el conector `fake`.
- Bootstrap idempotente de `SDMUJER` (area, `planner`, `SDM`), `SEGURIDAD` (proyecto, `custom`, `SEG`) y `PANDORA` (proyecto, `kanban`, `PAN`), tablero de 7 columnas literales en SEGURIDAD e `intake_settings.default_project_id → SEGURIDAD`.
- Invariantes post-ejecución impresas por el propio script.

### Out of Scope

- **Excluir `Removida` / `Gestionada aparte` del denominador de avance → diferido al cambio 44**, donde llegan las tareas con esos estados y el efecto se vuelve observable. Entre el 42 y el 44 el avance de SEGURIDAD **sub-reporta** de forma conocida y aceptada.
- Importación del checklist, usuarios Jason/Santiago, planes, `tasks.source` / `external_key` (cambio 43), frontend.
- Migraciones Alembic: este cambio **no toca el esquema**.
- Borrado genérico del directorio de subidas: `--purge-upload-files` solo elimina archivos referenciados por las filas de `attachments` borradas.

## Capabilities

### New Capabilities

- `data-maintenance`: compuerta de la semilla demo, operación de purga idempotente con dry-run/execute y respaldo obligatorio, invariantes post-purga y bootstrap de la jerarquía operativa.

### Modified Capabilities

- `api-conventions`: **MODIFIED** R4/R5 (la semilla demo pasa a estar condicionada por `SEED_DEMO_DATA`; la estructural sigue incondicional) + **ADDED** requisito que acota R3 (borrado suave) al dominio en tiempo de ejecución y autoriza el borrado físico como operación de mantenimiento con respaldo previo y confirmación explícita.
- `multi-tenancy`: **MODIFIED** R4 — los miembros demo son condicionales; la organización `Solercia` y el admin siguen siendo incondicionales.
- `org-role-templates`: **ADDED** escenario — la purga borra instancias y su ledger, nunca el catálogo de sistema.
- `intake-classifier`: **ADDED** escenario — con `default_project_id` apuntado, no se crea el proyecto perezoso «Tareas Outlook».

## Approach

### Correcciones al plan aprobado

El plan de la Ola 5 (§2 y §3) es viable, pero tres supuestos no resisten la evidencia del código y esta propuesta los corrige:

| № | Supuesto del plan | Evidencia | Corrección |
|---|---|---|---|
| 1 | «Basta desactivar la semilla demo en `seed_default()`» | `_ensure_demo_members` es **incondicional** (`db_init.py:360`) y `_seed_demo_workitems` se activa por `COUNT(tasks) == 0` **global** (`:367-369`), no por «la org no tiene proyectos» | La compuerta va **dentro de ambos helpers**, con retorno temprano leyendo `settings.SEED_DEMO_DATA` en tiempo de llamada. Se aplica y se verifica con un reinicio real **antes** de la purga |
| 2 | Orden de columnas `… Completada, Diferida, … Removida` | El estado terminal es **posicional**: `allowed_statuses()[-1]` (`tasks/service.py:854-864`, `sprints/service.py:271`, `projects/repository.py:322-326`) | Orden definitivo con `Completada` **última**: `Sin iniciar, En curso, Diferida, Recurrente, Gestionada aparte, Removida, Completada`. Cero cambios en Strategy, roll-up, dashboard ni sprints |
| 3 | «Borrar `org_role_templates(+nodes)`» | Son catálogo de sistema (`organization_id IS NULL`, `is_system=true`), exigidas por `specs/org-role-templates/spec.md:29` y recreadas por `ensure_system_templates` en cada arranque | **No se borran.** Se borra el árbol OAP-TI instanciado y sus 12 `org_role_template_instantiations` |

### Piezas

1. **Compuerta** (`config.py`, `db_init.py`, `docker-compose.yml`, `env.example`): seguro por defecto (`False`); la demo se pide explícitamente. Probable con la sesión SAVEPOINT del `conftest` y `monkeypatch.setattr(settings, …)` (precedentes `test_menu_seed.py`, `test_email_outbox.py`).
2. **`maintenance/purge.py`**: recibe una `AsyncSession`, calcula el inventario previo, ejecuta el borrado de hoja a raíz (checklists → logs/historial/comentarios → `attachments` por `target_id` → `notification_deliveries` → `notifications` → `reminders` → intake → `tasks` → sprints/tableros/etiquetas → instanciaciones → `projects` de hoja a raíz → conector `fake` → usuarios demo → org `Acme Consultores`) y devuelve un reporte estructurado. **El caso de uso hace el `commit`.**
3. **`maintenance/bootstrap.py`**: usa `ProjectService._create_project_unit` (precedente `org_role_templates/service.py:295`) porque `create_project` fuerza `project_kind=proyecto`; añade las 7 `BoardColumn` literales al tablero vacío de SEGURIDAD con persistencia estilo `BoardRepository.create_for_project` — **nunca** `BoardService.add_column`, que slugifica y hace `commit` por columna.
4. **CLI**: sin flag `--include-connectors`. El conector `fake` se borra por `provider`; `google`, `microsoft365` y `jira` (cuenta real «Cristian Camilo Calderon Tapia») se conservan y el script **se niega** a tocarlos. Antes de borrar usuarios verifica que ninguna `connected_account` les pertenezca (hoy todas son de `admin@`) y **falla cerrado** si aparece alguna.

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `backend/app/config.py` | Modified | `SEED_DEMO_DATA: bool = False` |
| `backend/app/db_init.py` | Modified | Compuerta en `_ensure_demo_members` (:586) y `_seed_demo_workitems` (:562) |
| `docker-compose.yml`, `env.example` | Modified | `SEED_DEMO_DATA=false` explícito y documentado |
| `backend/app/maintenance/` | New | `purge.py`, `bootstrap.py` (dueños de la transacción) |
| `backend/scripts/purge_demo_data.py` | New | CLI delgada (primer script operativo del repo) |
| `backend/app/modules/projects/service.py`, `.../boards/repository.py` | Consumido | `_create_project_unit` y creación de columnas literales, **sin modificarlos** |
| `backend/tests/test_seed_demo_flag.py`, `test_purge_demo_data.py`, `test_bootstrap_hierarchy.py` | New | TDD estricto |
| `openspec/specs/data-maintenance/` + deltas | New/Modified | Ver Capabilities |

## Runbook

Ejecutar en este orden, desde el host. La imagen del backend **no trae `pg_dump`** (`backend/Dockerfile:10-12`) y `DATABASE_URL` por defecto apunta a `postgres:5432`, que no resuelve desde el host.

| # | Paso | Comando / verificación |
|---|---|---|
| 1 | Compuerta primero | Desplegar `SEED_DEMO_DATA=false`, `docker compose restart backend` y confirmar que no reaparecen `ana@`/`carlos@`/`diana@` |
| 2 | Respaldo | `mkdir -p /Users/camilocalderont/Proyectos/SOLERCIA/backups && docker exec gestion_proyectos-postgres-1 pg_dump -U app solercia > /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql` |
| 3 | Dry-run | `python backend/scripts/purge_demo_data.py --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia` → conteos antes/después previstos, conectores con propietario, advertencias |
| 4 | Revisión humana | Confirmar el reporte del dry-run antes de continuar |
| 5 | Ejecución | Añadir `--execute --backup-file <ruta del paso 2>`. El script verifica que el archivo existe y no está vacío **antes de borrar nada** |
| 6 | Invariantes | El script las imprime al cerrar la transacción (ver Success Criteria) |
| 7 | Reinicio | `docker compose restart backend` |
| 8 | Verificación final | Repetir las invariantes: el reinicio **no** recrea datos demo |

## Rollback Plan

| Escenario | Reversa |
|---|---|
| La purga corrompe o borra de más | `docker compose stop backend`; `docker exec gestion_proyectos-postgres-1 psql -U app -d solercia -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'`; `docker exec -i gestion_proyectos-postgres-1 psql -U app -d solercia < /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql`; `docker compose start backend`. El backend debe estar detenido para que la semilla no corra a mitad de la restauración |
| Se necesita la demo de vuelta | `SEED_DEMO_DATA=true` + reinicio. Reversible por variable de entorno, sin desplegar código |
| El código introduce regresiones | Revertir los commits del cambio. **No hay migración Alembic que bajar**: el esquema no se toca |
| Archivos de subida borrados con `--purge-upload-files` | **Sin reversa desde la base.** El respaldo SQL no contiene los binarios; por eso el flag está apagado por defecto y se ejecuta solo tras copiar `backend/uploads/` |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Irreversibilidad del borrado físico sobre la única base con datos reales incipientes | Alta | `--dry-run` por defecto, `--backup-file` verificado (existe y no vacío) antes de tocar nada, confirmación humana entre el paso 4 y el 5 |
| El orden de columnas convierte `Removida` en «hecho» silenciosamente | Alta | Orden con `Completada` última + prueba que fija el invariante «la columna de mayor `order` de SEGURIDAD es `Completada`» |
| Ventana de la semilla: con 0 tareas, un reinicio inyecta 12 tareas demo con estados inválidos en proyectos reales | Media | La compuerta es el **paso 1** del runbook y se valida con un reinicio real antes de purgar |
| Huérfanos sin FK (`attachments` 81, `notifications` 29, `reminders` 2) | Media | Borrado explícito por `target_id` y verificación de cero huérfanos al cerrar |
| Se borra un conector real | Media | Se borra únicamente el `provider='fake'`; el script se niega a tocar `google`, `microsoft365` y `jira`; el dry-run lista provider, cuenta y propietario |
| CASCADE desde `users` destruye cuentas conectadas | Baja (verificado: todas son de `admin@`) | Aserción previa: si alguna `connected_account` pertenece a un usuario a borrar, el script **falla cerrado** |
| Entorno de ejecución (sin `pg_dump` en el backend, `DATABASE_URL` interna) | Media | Runbook con los comandos exactos y `--database-url` explícito |
| Deltas destructivos de spec (`api-conventions` R3/R4, `multi-tenancy` R4) | Baja | `archive` exige advertir antes de fusionar (`openspec/config.yaml:36`) |
| El respaldo contiene datos reales y hashes de contraseña | Media | Vive fuera del repositorio (`/Users/…/SOLERCIA/backups/`), nunca se versiona |

## Dependencies

- Etapa 0 del plan de Ola 5: línea base git de Command (rama `feat/42-purga-datos-demo`, commit `b5b0399`).
- Bloquea al cambio 43 (`tareas-origen-externo`) y, en cadena, al 44 (importación del checklist).

## Success Criteria

Medibles contra la base real (`gestion_proyectos-postgres-1` / `solercia`). Estado previo verificado el 2026-08-26.

- [ ] `SEED_DEMO_DATA=false` y un `restart` del backend **no** recrean `ana@`, `carlos@` ni `diana@`; con `true` sí los recrea (prueba de doble sentido).
- [ ] Sobreviven `admin@solercia.com` y la organización `Solercia`; no existe ningún otro usuario ni la organización `Acme Consultores`.
- [ ] Existen `SDMUJER` (`area`/`planner`/`SDM`), `SEGURIDAD` (`proyecto`/`custom`/`SEG`, padre SDMUJER) y `PANDORA` (`proyecto`/`kanban`/`PAN`, padre SDMUJER).
- [ ] SEGURIDAD tiene **exactamente 7** `board_columns` con `status_key` = `Sin iniciar, En curso, Diferida, Recurrente, Gestionada aparte, Removida, Completada` y `Completada` con el `order` mayor.
- [ ] `intake_settings.default_project_id` apunta a SEGURIDAD y no existe ningún proyecto «Tareas Outlook».
- [ ] Cero huérfanos: `attachments` (eran 81), `notifications` (29), `notification_deliveries` (0), `reminders` (2), `assets`/`asset_licenses`/`asset_tasks` (1 «Verify Test Asset») quedan en 0; `tasks`, `task_comments` (73) y `task_history` (145) quedan en 0.
- [ ] Se conservan los 5 `org_role_templates` de sistema y sus nodos; los 12 `org_role_template_instantiations` quedan en 0.
- [ ] Conectores: queda `provider='fake'` en 0; sobreviven `google`, `microsoft365` y `jira` con la cuenta «Cristian Camilo Calderon Tapia» intacta.
- [ ] Re-ejecutar el script completo es idempotente: segunda corrida sin borrados nuevos y con las mismas invariantes.
- [ ] TDD estricto: pruebas en rojo antes del código para compuerta, purga (incluidos huérfanos y fallo cerrado por cuentas conectadas) y bootstrap. `cd backend && pytest tests/ -v` en verde.

## Carga de revisión

Estimado: **≈1 300 líneas** (`additions + deletions`), bajo el presupuesto de sesión de 2 000 pero muy por encima del umbral por defecto de 400. Estrategia `auto-chain` — se sugieren tres rebanadas encadenadas, cada una con verificación y reversa propias:

| Rebanada | Contenido | ≈ líneas |
|---|---|---|
| 1 | Compuerta `SEED_DEMO_DATA` + compose/env + pruebas + delta `multi-tenancy` | 150 |
| 2 | `maintenance/purge.py` + CLI con `--dry-run` + pruebas de purga y huérfanos | 700 |
| 3 | `maintenance/bootstrap.py` + invariantes + `--execute` + spec `data-maintenance` y deltas restantes | 450 |

El pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`) lo emite `sdd-tasks`.

## Proposal question round

Estas preguntas afinan reglas de negocio antes de fijar el spec; no reabren las decisiones ya tomadas (opciones A1+B1+C1, catálogo de plantillas, conectores, usuarios demo, respaldo). Puedes responderlas, corregir el encuadre, saltarlas o pedir una segunda ronda.

1. **Avance sub-reportado entre el 42 y el 44**: con `Completada` como única columna terminal, `Removida` y `Gestionada aparte` seguirán contando como pendientes en `/projects/{id}/progress` y en la vista ejecutiva. ¿Aceptas convivir con ese sub-reporte hasta el cambio 44? *Supuesto: sí, y se documenta en la spec como limitación conocida.*
2. **Archivos de subida no referenciados**: hay ≈1 963 archivos en `backend/uploads/` y solo 81 filas de `attachments`. El script solo borra los referenciados. ¿Qué hacemos con el resto — se quedan, se archivan fuera del proyecto, o se agenda una limpieza posterior? *Supuesto: se quedan; limpieza fuera de alcance.*
3. **Capacidad de demo**: tras la purga, activar `SEED_DEMO_DATA=true` sembraría tareas dentro de los proyectos reales con estados inválidos para un tablero `custom`. ¿La demo debe seguir siendo un modo usable (y por tanto arreglable más adelante) o basta con que quede apagada y cubierta por pruebas? *Supuesto: apagada; se conserva el código y la prueba de doble sentido, sin arreglar la siembra.*
4. **`verify-smoke-11@solercia.com` y «Verify Test Asset»**: se tratan como artefactos de verificación desechables. ¿Confirmas que ninguno tiene valor de auditoría antes de borrarlos físicamente? *Supuesto: desechables.*
5. **Custodia del respaldo**: el volcado incluye datos reales y hashes de contraseña. ¿Basta con dejarlo en `SOLERCIA/backups/` fuera del repositorio, o quieres cifrado y una fecha de caducidad para borrarlo? *Supuesto: fuera del repositorio, sin cifrar, borrado manual tras cerrar la Ola 5.*
