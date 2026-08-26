# data-maintenance Specification

## Propósito

Mantenimiento operativo de datos: compuerta de la semilla demo por variable de entorno, purga idempotente de datos demo con respaldo obligatorio, y bootstrap idempotente de la jerarquía operativa `SDMUJER > {SEGURIDAD, PANDORA}`. Ninguna de estas operaciones se expone por HTTP; corren como casos de uso en `backend/app/maintenance/` invocados por una CLI delgada en `backend/scripts/`. Los casos de uso son dueños de la transacción; los repositorios que invocan NUNCA hacen `commit`.

## Requirements

### Requirement: Compuerta de la semilla demo por SEED_DEMO_DATA

`Settings` DEBE declarar `SEED_DEMO_DATA: bool = False`. `_ensure_demo_members` y `_seed_demo_workitems` DEBEN leer `settings.SEED_DEMO_DATA` EN TIEMPO DE LLAMADA (nunca una constante de módulo capturada al importar) y retornar temprano sin crear nada cuando el valor sea `false`. La semilla estructural (organización "Solercia", dependencias, roles, menús, role_menus, `admin@solercia.com`, alert rules, catálogo de `org_role_templates` de sistema) DEBE seguir ejecutándose SIN condición, sin importar el valor del flag.

#### Scenario: Con el flag en false no se crean usuarios demo
- DADO `settings.SEED_DEMO_DATA = false` y una base de datos vacía
- CUANDO corre `seed_default()` (probado contra la `session` de SAVEPOINT de `conftest.py`, siguiendo el precedente de `test_menu_seed.py`)
- ENTONCES existen la organización "Solercia" y `admin@solercia.com`, pero `ana@`, `carlos@` y `diana@` NO existen

#### Scenario: Con el flag en true la semilla demo funciona en base vacía
- DADO `settings.SEED_DEMO_DATA = true` (vía `monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)`) y una base de datos vacía
- CUANDO corre `seed_default()`
- ENTONCES existen `ana@`, `carlos@`, `diana@`, los proyectos y tareas demo, y el sprint demo, igual que antes de este cambio

#### Scenario: Con el flag en false un restart no revive miembros demo tras la purga
- DADO una base ya purgada (sin `ana@`/`carlos@`/`diana@`) y `settings.SEED_DEMO_DATA = false`
- CUANDO `seed_default()` corre de nuevo (simulando un restart)
- ENTONCES ningún miembro demo se crea y la cuenta de usuarios de "Solercia" permanece en 1 (`admin@solercia.com`)

### Requirement: Purga idempotente con dry-run por defecto

La purga DEBE vivir en `backend/app/maintenance/purge.py` como caso de uso dueño de su propia transacción. Por defecto (sin `--execute`) DEBE ejecutarse en modo dry-run: calcula e imprime el inventario (conteos antes/después previstos) SIN borrar ninguna fila. Solo con `--execute` explícito DEBE aplicar el borrado. Ejecutarla dos veces seguidas con `--execute` DEBE ser un no-op la segunda vez.

#### Scenario: Dry-run no modifica la base
- DADO una base con datos demo (4 usuarios demo, proyectos, tareas, conector `fake`)
- CUANDO se invoca la purga SIN `--execute`
- ENTONCES el reporte impreso lista los conteos previstos, pero ningún conteo real cambia tras la llamada

#### Scenario: Execute borra y una segunda corrida es no-op
- DADO la misma base tras un `--execute` exitoso
- CUANDO se ejecuta la purga por segunda vez con `--execute`
- ENTONCES el reporte indica cero filas adicionales borradas en cada tabla del alcance demo

### Requirement: Orden de borrado de hoja a raíz y huérfanos sin FK explícitos

El borrado físico DEBE seguir el orden de hoja a raíz: subestructuras de tarea (checklists, time logs, history, comments, dependencies, labels, asset_tasks) → `attachments` con `target_id` en el alcance (SIN FK, borrado explícito por `target_id`) → `notification_deliveries` → `notifications` con `target_id` en el alcance (SIN FK, borrado explícito) → `reminders`/`reminder_rules` → `intake_items`/`intake_rules`/`intake_settings`/`intake_runs` del alcance → `tasks` → `sprints`, `board_columns`→`boards`, `labels` → `org_role_template_instantiations` → `projects` de hoja a raíz → `connected_accounts`/`connectors` (solo `provider='fake'`) → filas dependientes de `users` → `users` demo → `organizations` "Acme Consultores". Los proyectos padre NUNCA DEBEN borrarse antes que sus hijos, porque `parent_project_id` es `SET NULL` y no cascadea.

#### Scenario: Attachments y notifications huérfanos quedan en cero
- DADO 81 `attachments` y 29 `notifications` cuyo `target_id` apunta a tareas del alcance demo, sin FK declarada
- CUANDO se ejecuta la purga con `--execute`
- ENTONCES `attachments` y `notifications` con esos `target_id` quedan en 0, sin filas huérfanas remanentes

#### Scenario: Un proyecto padre no se borra antes que su hijo activo
- DADO un proyecto demo padre con un hijo demo activo
- CUANDO se calcula el orden de borrado
- ENTONCES el hijo se borra antes que el padre, nunca al revés

### Requirement: Protección del catálogo de sistema y de conectores reales

La purga NUNCA DEBE borrar filas de `org_role_templates` ni `org_role_template_nodes` (catálogo de sistema, `organization_id IS NULL`, `is_system=true`), ni la organización "Solercia", ni `admin@solercia.com`, ni `dependencies`, `roles`, `menus`, `role_menus`, `alert_rules`. De los `connectors`, DEBE borrar ÚNICAMENTE las filas con `provider='fake'` y su(s) `connected_account(s)`; DEBE dejar intactos `google`, `microsoft365` y `jira`.

#### Scenario: El catálogo de plantillas sobrevive a la purga
- DADO 5 `org_role_templates` de sistema sembradas
- CUANDO se ejecuta la purga con `--execute`
- ENTONCES las 5 filas siguen existiendo con `is_system=true` sin cambios

#### Scenario: Solo el conector fake se borra
- DADO conectores `fake` (demo), `google`, `microsoft365` y `jira` (con una cuenta real)
- CUANDO se ejecuta la purga con `--execute`
- ENTONCES el conector `fake` y su cuenta quedan en 0, y `google`/`microsoft365`/`jira` permanecen con sus filas intactas

### Requirement: Fallo cerrado si una connected_account pertenece a un usuario a borrar

Antes de borrar cualquier fila, la purga DEBE verificar si alguna `connected_account` pertenece a un usuario del alcance demo (`ana@`, `carlos@`, `diana@`, `verify-smoke-11@`). Si existe al menos una, la operación DEBE detenerse SIN borrar ninguna fila y DEBE reportar el `provider`, `display_name` y propietario de la cuenta en riesgo.

#### Scenario: Cuenta conectada de un usuario demo bloquea la purga
- DADO que `carlos@` tiene una `connected_account` con `provider='jira'`
- CUANDO se invoca la purga con `--execute`
- ENTONCES la operación se rechaza antes de borrar cualquier fila, y el reporte identifica la cuenta y su propietario

#### Scenario: Sin cuentas de usuarios demo la purga procede
- DADO que ninguna `connected_account` pertenece a un usuario demo (caso real verificado 2026-08-26)
- CUANDO se invoca la purga con `--execute`
- ENTONCES la verificación pasa y el borrado continúa normalmente

### Requirement: Respaldo obligatorio y verificado antes de cualquier borrado

`--execute` DEBE exigir `--backup-file <ruta>`. Antes de borrar cualquier fila, el script DEBE verificar que el archivo existe en disco y que su tamaño es mayor a cero bytes; NO DEBE verificar el contenido ni la integridad del volcado. Si la verificación falla, la operación DEBE abortar sin borrar nada.

#### Scenario: Backup ausente aborta la ejecución
- DADO `--execute` sin `--backup-file`, o con una ruta inexistente
- CUANDO se invoca el script
- ENTONCES la operación se rechaza antes de tocar la base de datos

#### Scenario: Backup vacío aborta la ejecución
- DADO `--backup-file` apuntando a un archivo de 0 bytes
- CUANDO se invoca `--execute`
- ENTONCES la operación se rechaza con un error explícito, sin borrar ninguna fila

### Requirement: Bootstrap idempotente de la jerarquía SDMUJER

`backend/app/maintenance/bootstrap.py` DEBE crear, vía `ProjectService._create_project_unit`, la sombrilla "SDMUJER" (`project_kind=area`, `methodology=planner`, `code=SDM`), y como hijos "SEGURIDAD" (`project_kind=proyecto`, `methodology=custom`, `code=SEG`) y "PANDORA" (`project_kind=proyecto`, `methodology=kanban`, `code=PAN`). DEBE añadir al `Board` ya sembrado de SEGURIDAD exactamente 7 `BoardColumn` literales, en este orden y con `order` 0 a 6: "Sin iniciar", "En curso", "Diferida", "Recurrente", "Gestionada aparte", "Removida", "Completada" ("Completada" DEBE quedar en `order=6`, la posición mayor). DEBE apuntar `intake_settings.default_project_id` a SEGURIDAD. Ejecutar el bootstrap una segunda vez sobre una base ya bootstrapeada DEBE ser un no-op.

#### Scenario: Primera ejecución crea la jerarquía completa
- DADO una base sin SDMUJER/SEGURIDAD/PANDORA
- CUANDO se ejecuta el bootstrap
- ENTONCES existen los 3 proyectos con los `code`, `project_kind` y `methodology` esperados, SEGURIDAD tiene 7 `BoardColumn` y "Completada" tiene el `order` mayor de todas

#### Scenario: Segunda ejecución es un no-op
- DADO la jerarquía ya bootstrapeada
- CUANDO se ejecuta el bootstrap de nuevo
- ENTONCES no se crea ningún proyecto ni columna adicional, y `intake_settings.default_project_id` sigue apuntando al mismo `id` de SEGURIDAD

### Requirement: Invariantes post-ejecución con código de salida no cero

Al finalizar un `--execute`, el script DEBE imprimir un reporte de invariantes que verifique: existe `admin@solercia.com`; existe "Solercia"; existen SDMUJER/SEGURIDAD/PANDORA con sus `code` esperados; SEGURIDAD tiene exactamente 7 columnas con "Completada" en el `order` mayor; `intake_settings.default_project_id` apunta a SEGURIDAD; cero huérfanos en `attachments`/`notifications`/`notification_deliveries`/`reminders` del alcance demo; las 5 `org_role_templates` de sistema están intactas y sus `org_role_template_instantiations` del alcance demo están en 0; el conector `fake` está en 0 con `google`/`microsoft365`/`jira` intactos. Si CUALQUIER invariante falla, el proceso DEBE terminar con código de salida distinto de cero.

#### Scenario: Todas las invariantes en verde terminan con código 0
- DADO una purga y bootstrap exitosos
- CUANDO el script evalúa las invariantes
- ENTONCES el proceso termina con código de salida 0 y el reporte marca cada invariante como cumplida

#### Scenario: Una invariante rota termina con código distinto de cero
- DADO que, por un fallo inyectado en prueba, SEGURIDAD queda con 6 columnas en vez de 7
- CUANDO el script evalúa las invariantes
- ENTONCES el proceso termina con código de salida distinto de cero y el reporte señala cuál invariante falló

### Requirement: Contrato de ejecución en el host

El script DEBE aceptar `--database-url` para ejecutarse desde el host contra el Postgres publicado (el valor por defecto `postgres:5432` de `Settings` solo resuelve dentro de la red de Docker). El respaldo (`pg_dump`) DEBE tomarse desde el host contra el contenedor de Postgres, NUNCA desde el contenedor del backend (no incluye `pg_dump`). `--purge-upload-files` (opcional, apagado por defecto) DEBE borrar ÚNICAMENTE los archivos de `UPLOAD_DIR` referenciados por las filas de `attachments` que la purga elimina; NUNCA DEBE hacer un borrado genérico del directorio.

#### Scenario: --database-url permite ejecutar desde el host
- DADO el script invocado desde el venv del host con `--database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia`
- CUANDO corre en modo dry-run
- ENTONCES se conecta correctamente y reporta el inventario, sin depender del DNS interno de Docker

#### Scenario: --purge-upload-files borra solo los archivos referenciados
- DADO `--purge-upload-files` activo y 81 `attachments` con `stored_name` en `UPLOAD_DIR`
- CUANDO se ejecuta `--execute`
- ENTONCES se borran exactamente los archivos de esos 81 `stored_name`, y los demás archivos no referenciados en `UPLOAD_DIR` permanecen intactos

## Limitaciones y deuda conocida

- Entre este cambio y el cambio 44, `Removida` y `Gestionada aparte` cuentan como pendientes en el denominador de avance de `GET /projects/{id}/progress` (opción C1: "Completada" es la última columna, sin tocar la Strategy). Limitación conocida y aceptada, no un defecto de esta capability.
- Los archivos de `backend/uploads/` no referenciados por `attachments` quedan fuera de alcance de `--purge-upload-files`.

## Referencias

- backend/app/config.py, backend/app/db_init.py
- backend/app/maintenance/ (purge.py, bootstrap.py)
- backend/scripts/purge_demo_data.py
- backend/tests/conftest.py (harness SAVEPOINT), backend/tests/test_menu_seed.py (precedente de siembra probada)
- openspec/specs/org-role-templates/spec.md (catálogo de sistema)
- openspec/specs/project-hierarchy/spec.md (roll-up, estado terminal posicional)
