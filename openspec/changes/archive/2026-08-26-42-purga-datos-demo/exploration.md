# Exploración — 42-purga-datos-demo

> Fase `sdd-explore`. Investigación de solo lectura sobre `/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command`.
> Store híbrido: este contenido está también en Engram (`sdd/42-purga-datos-demo/explore`, observación #3687).

## Resumen ejecutivo

El plan aprobado es viable, pero tres de sus supuestos NO resisten la evidencia del código y deben corregirse antes de la propuesta:

1. **La compuerta de la semilla es más urgente de lo previsto**: `seed_default()` condiciona la siembra demo a `COUNT(tasks) == 0` **global** (`db_init.py:367-369`), no a «la organización no tiene proyectos». Tras la purga, el siguiente arranque no recrearía los proyectos demo (ya existirían SDMUJER/SEGURIDAD/PANDORA), sino que **inyectaría 12 tareas demo dentro de los proyectos reales**, con estados inválidos para un tablero `custom` (`db_init.py:692-693` cae al literal `["todo","doing","done"]`). Además `_ensure_demo_members` corre **incondicionalmente** en cada arranque (`db_init.py:360`), así que ana/carlos/diana reviven aunque haya tareas.
2. **El orden de columnas propuesto rompe `completed_at` y el avance**: el estado terminal se resuelve como `allowed_statuses()[-1]` (`tasks/service.py:854-864`, `sprints/service.py:271`, `projects/repository.py:322-326`). Con el orden `… Gestionada aparte, Removida`, el sistema trataría **`Removida` como «hecho»** y `Completada` como pendiente. Se requiere decisión explícita (opción C1 recomendada).
3. **Las 5 `org_role_templates` NO deben borrarse**: son catálogo de sistema (`organization_id IS NULL`, `is_system=true`), lo exige `specs/org-role-templates/spec.md:29` y `ensure_system_templates` las recrea en cada arranque (`org_role_templates/seeder.py:91-118`, invocado en `db_init.py:365`). Lo que sí se borra es el **árbol de proyectos instanciado** (OAP-TI) y su ledger, que cae por CASCADE al borrar los proyectos.

Recomendación: A1 (flag por `Settings`, compuerta dentro de los helpers) + B1 (caso de uso en `app/maintenance/` con CLI delgada en `backend/scripts/`) + C1 (`Completada` como última columna, sin tocar la Strategy) y **diferir al cambio 44** la exclusión de `Removida`/`Gestionada aparte` del denominador de avance.

---

## Estado actual — evidencia

### 1. La semilla demo y su compuerta

| Elemento | Evidencia | Consecuencia |
|---|---|---|
| Punto de arranque | `backend/app/main.py:104` (`await seed_default()`), tras `alembic upgrade head` en `backend/docker/entrypoint.sh:8-9` | La semilla corre en cada `docker compose up`/`restart` |
| Semilla estructural (se conserva) | `db_init.py:350-365`: `_ensure_organization` (org `Solercia`, slug `solercia`, :498-509), `_ensure_dependencies`, `_ensure_roles`, `_ensure_menus`, `_ensure_role_menus`, `_ensure_admin` (`admin@solercia.com`, :512-535), `_ensure_alert_rules`, `ensure_system_templates` | Nada de esto se toca |
| Miembros demo | `_DEMO_MEMBERS` (`db_init.py:104-108`) → `_ensure_demo_members` (:586-614), llamado **sin condición** en :360 | ana/carlos/diana renacen en cada arranque |
| Work items demo | `_seed_demo_workitems` (:562-583) llamado solo si `COUNT(tasks) == 0` (:367-369, sin filtro `is_active` ni de organización) | Ventana peligrosa entre el 42 y el 44 |
| Proyectos demo | `_DEMO_PROJECTS` (:166-170) → `_ensure_demo_projects` (:617-650): si la organización ya tiene proyectos activos **los devuelve tal cual** | Los proyectos reales se convierten en destino de las tareas demo |
| Tareas demo | `_seed_demo_tasks` (:665-756); `statuses = strategy.allowed_statuses() or ["todo","doing","done"]` (:692-693) usa la Strategy **base**, no `BoardAwareStrategy` | En `SEGURIDAD` (`custom`, `allowed_statuses()==[]`) generaría tareas con estado `todo`, inexistente en el tablero |
| Sprint demo | `_seed_scrum_sprint` (:775-839): retorna si no hay proyecto `scrum` | Inerte tras la purga, pero se cierra igual por coherencia |

`db_init.py` **no importa** `app.config` hoy. Las settings son un singleton cacheado (`config.py:317-324`, `@lru_cache` + `settings = get_settings()`), y la convención de pruebas del repo es parchear el atributo del singleton: `monkeypatch.setattr(settings, "EMAIL_ENABLED", True)` (`tests/test_email_outbox.py:39`). Por eso la compuerta debe leer `settings.SEED_DEMO_DATA` **en tiempo de llamada**, nunca ligarlo a una constante de módulo.

Entrega de variables de entorno: `docker-compose.yml:36-41` (`environment:` del servicio `backend`) y `env.example`. El compose fija el nombre de proyecto `gestion_proyectos` (`docker-compose.yml:1`) y publica Postgres en `127.0.0.1:5434` (:16-17), mientras el backend usa `postgres:5432` por DNS de Docker (`config.py:24`).

### 2. Metodología `custom`, columnas y estado terminal

- `CustomStrategy.default_columns() == []` y `allowed_statuses() == []` (`methodology/custom.py:12-16`). Un proyecto `custom` nace con **tablero vacío**: `ProjectService._create_project_unit` siempre llama `BoardService.seed_board` (`projects/service.py:202`), que crea el `Board` con cero columnas (`boards/service.py:46-59`).
- Los estados vivos salen de `board_columns.status_key` vía `BoardAwareStrategy` (`methodology/board_aware.py:39-51`, `resolve_board_strategy` :66-85). Confirmado el supuesto del plan: **para validar estados no hace falta cambiar la Strategy**.
- **Pero el estado terminal sí es posicional**: `TaskService._resolve_completed_at` toma `allowed[-1]` (`tasks/service.py:854-864`); `SprintService` hace lo mismo (`sprints/service.py:271`); `DashboardService._bounds_for` usa `resolve_board_strategy` (`dashboard/service.py:438-445`); y `ProjectRepository.rollup_progress` reproduce la regla en SQL con `ORDER BY column_order DESC, created_at DESC` (`projects/repository.py:309-338`). El orden de lectura de columnas es ascendente por `order` (`boards/repository.py:88` y `:124`), así que «último permitido» = columna de mayor `order`.
- El denominador de avance excluye **solo el literal `cancelled`** (`projects/repository.py:330`), y eso es normativo: `specs/project-hierarchy/spec.md:113` y su escenario `:121-125`.
- `status_key` es inmutable tras crearse (`boards/models.py:62-65`), único por tablero (`uq_board_column_status_key`, :50-52), `String(60)` (:66). `boards.project_id` es **UNIQUE** (:36-37): un proyecto tiene exactamente un tablero.

**Consecuencia dura**: con el orden del plan (`Sin iniciar, En curso, Completada, Diferida, Recurrente, Gestionada aparte, Removida`), `Removida` sería el estado terminal: marcaría `completed_at`, contaría como `done` en `/projects/{id}/progress` y en la vista ejecutiva, y `Completada` contaría como pendiente.

### 3. Creación de proyectos, áreas y tableros

- `ProjectService.create_project` **fuerza** `project_kind = proyecto` y `lead_user_id = None` (`projects/service.py:117-119`), por diseño defensivo del cambio 27. **SDMUJER (`area`) no se puede crear por esa vía.**
- El seam correcto ya existe y tiene precedente en el repo: `ProjectService._create_project_unit` (`projects/service.py:128-204`, sin commit, valida padre, deriva `code`, siembra tablero), invocado directamente por `OrgRoleTemplateService` para árboles todo-o-nada (`org_role_templates/service.py:295`, con `# noqa: SLF001`).
- Para columnas con `status_key` **literal** («Sin iniciar», no `sin_iniciar`) hay una sola vía: `BoardRepository.create_for_project(project_id, [(name, name), ...])` (`boards/repository.py:26-52`, persiste `order` 0..N-1 y no hace commit). La API pública `BoardService.add_column` **no sirve**: slugifica (`boards/service.py:203` + `_slugify` :27-37) y **hace `commit()` por columna** (:221), rompiendo la atomicidad del script.
  - Como `seed_board` ya creó un `Board` vacío para el proyecto `custom` y `boards.project_id` es UNIQUE, el caso de uso debe **añadir las 7 `BoardColumn` al tablero existente** (no crear un segundo tablero), o bien construir el proyecto sin pasar por `seed_board`.
- `intake_settings.default_project_id` es FK a `projects` con `ON DELETE SET NULL` (`intake/models.py:164-166`). Si queda nulo, `IntakeService._ensure_default_project` (`intake/service.py:581-599`) crea perezosamente el proyecto «Tareas Outlook» (`config.py:313`). Apuntarlo a SEGURIDAD, como pide el plan, es la forma correcta de evitarlo.

### 4. Grafo de FK y orden de borrado físico

Se derivó de los modelos (no fue posible consultar la base: este ejecutor no tiene herramienta de shell). Los `ON DELETE` citados son los declarados en el ORM.

**Trampa 1 — tablas sin FK que NO caen por CASCADE:**

| Tabla | Vínculo | Riesgo |
|---|---|---|
| `attachments` | `target_type ∈ {task, comment}` + `target_id`, **sin FK** (`attachments/models.py:29-32`) | Filas huérfanas tras borrar tareas/comentarios; además quedan archivos huérfanos en `UPLOAD_DIR` (`config.py:48`) referenciados por `stored_name` |
| `notifications` | `target_type`/`target_id` **sin FK** (`notifications/models.py:24-27`) y `dedup_key` del tipo `"task_overdue:{task_id}"` (:26) | Notificaciones apuntando a tareas inexistentes |
| `notification_deliveries` | `notification_id` **SET NULL** (`notify/models.py:35-36`) | Entregas huérfanas si se borran notificaciones sin borrarlas antes |
| `projects.parent_project_id` | **SET NULL** (`projects/models.py:78-83`) | Borrar un padre NO cascadea: los hijos quedarían como raíces. Obliga a borrar de hoja a raíz |
| `reminders.task_id` | **SET NULL** (`reminders/models.py:41`) | Recordatorios sobrevivientes sin tarea |
| `intake_items.created_task_id` / `matched_rule_id`, `intake_rules.target_project_id`, `intake_settings.default_project_id` | **SET NULL** (`intake/models.py:79,82,111,165`) | Hoy las tablas están vacías, pero el script debe ser robusto |

**Trampa 2 — CASCADE al borrar usuarios demo** (`connected_accounts.user_id` es `ON DELETE CASCADE`, `connectors/models.py:91-93`): si alguna de las 2 `connected_accounts` pertenece a un usuario demo, **se destruye aunque el usuario no active el flag de conectores**. También caen por CASCADE desde `users`: `organization_members`, `user_roles`, `federated_identities`, `notifications`, `glpi_user_links`, `org_role_template_instantiations.lead_user_id`.

**Orden propuesto (de hoja a raíz), para el conjunto `T` = tareas demo, `P` = proyectos demo:**

1. `checklist_items` → `task_checklists` (CASCADE desde `tasks`)
2. `task_time_logs`, `task_history`, `task_comments`, `task_dependencies`, `task_labels`, `asset_tasks` (todas CASCADE desde `tasks`; se listan explícitas para no depender del motor)
3. `attachments` con `target_id ∈ T ∪ {ids de task_comments}` — **explícito, no hay FK**
4. `notification_deliveries` de las notificaciones afectadas → `notifications` con `target_id ∈ T` — **explícito, no hay FK**
5. `reminders` / `reminder_rules` del alcance demo
6. `intake_items`, `intake_rules`, `intake_settings`, `intake_runs` del alcance demo
7. `tasks` (self-FK `parent_task_id` SET NULL, `sprint_id` SET NULL)
8. `sprints`, `board_columns` → `boards`, `labels` (CASCADE desde `projects`)
9. `org_role_template_instantiations` (CASCADE desde `projects.id`, `org_role_templates/models.py:147-151`)
10. `projects` **de hoja a raíz**
11. `connected_accounts` / `connection_credentials` / `connectors` — **solo con flag explícito**
12. `organization_members`, `user_roles`, `federated_identities`, `notification_preferences`, `glpi_user_links` (CASCADE desde `users`)
13. `users` demo (`ana@`, `carlos@`, `diana@`, `verify-smoke-11@`) — **nunca `admin@solercia.com`**
14. `organizations` = `Acme Consultores` (CASCADE limpia todo lo tenant-scoped, `shared/base_model.py:55`)

**NO se borran**: `org_role_templates` + `org_role_template_nodes` (catálogo de sistema, reseedeado), `dependencies`, `roles`, `menus`, `role_menus`, `alert_rules`, org `Solercia`, `admin@solercia.com`.

**Pendiente de decisión**: el único `asset` existente es tenant-scoped (`organization_id`), no cuelga de un proyecto; no lo alcanza ninguna cascada de la purga. Debe decidirse explícitamente si se borra.

### 5. Convenciones de scripts operativos

- **No existe `backend/scripts/`**: sería el primer script operativo del repo. No hay precedente de CLI ni objetivo de `Makefile` para tareas de datos: el `Makefile` delega el ciclo de vida en `gestion.sh` y solo agrega calidad de frontend (`Makefile:27-98`); no hay objetivos de backend.
- El único punto de entrada no-HTTP hoy es `backend/docker/entrypoint.sh` (alembic + uvicorn) y las revisiones de Alembic.
- Sesión y settings para un proceso fuera de FastAPI: `AsyncSessionLocal` / `engine` (`backend/app/database.py:15-29`) y `app.config.settings` (`config.py:324`). `app/dependencies.py` es solo inyección HTTP; no aplica.
- **`pg_dump` NO está disponible dentro del contenedor backend**: la imagen es `python:3.12-slim` e instala únicamente `gcc`, que además se elimina (`backend/Dockerfile:10-12`). El respaldo tiene que tomarse desde el host contra el contenedor de Postgres (`docker exec gestion_proyectos-postgres-1 pg_dump …`) o con un cliente del host.
- **`DATABASE_URL` por defecto apunta a `postgres:5432`** (`config.py:24`), válido solo dentro de la red de Docker. Si el script se ejecuta con el venv del host (`backend/.venv`, Python 3.13), necesita `--database-url` o `DATABASE_URL=…@127.0.0.1:5434/solercia`.

### 6. Harness de pruebas

`backend/tests/conftest.py`:
- `skip_no_db` (:36-40): sin `TEST_DATABASE_URL` los tests de integración se saltan.
- `engine` de sesión con `NullPool` y `create_all` (:43-84).
- `session` aislada por **SAVEPOINT** con `join_transaction_mode="create_savepoint"`, revertida en teardown incluso si el código bajo prueba hace `commit()` (:87-110). Es el harness natural para probar un caso de uso destructivo sin ensuciar la BD de test.
- `client` ASGI en proceso con `get_db` sobrescrito (:113-138); `tenant`, `user`, `make_member`, `rbac_admin`, `two_orgs` (aislamiento multi-tenant obligatorio, :463-475).
- **Precedente exacto para probar la semilla**: `tests/test_menu_seed.py:13,26-29` importa helpers privados de `db_init` y los ejecuta contra la `session` de SAVEPOINT. `seed_default()` en cambio abre su propia `AsyncSessionLocal` (`db_init.py:349`), fuera del SAVEPOINT: por eso la compuerta debe vivir en helpers que reciban la sesión.
- Precedente de parcheo de settings: `monkeypatch.setattr(settings, "EMAIL_ENABLED", True)` (`tests/test_email_outbox.py:39`).
- Ningún test invoca `seed_default()` hoy.

### 7. Specs afectadas y delta requerido

| Spec | Requisito vigente | Delta |
|---|---|---|
| `api-conventions` | R3 `:32` «El borrado de entidades de dominio DEBE ser suave»; R4 `:33` y R5 `:34` sobre `seed_default`; descripción `:20` que enumera «admin + 3 usuarios demo, proyectos/tareas demo» | **MODIFIED** R4/R5 (la semilla demo queda condicionada por `SEED_DEMO_DATA`; la estructural es incondicional) + **ADDED** requisito que acota R3 al dominio en tiempo de ejecución y autoriza el borrado físico como operación de mantenimiento con respaldo previo y confirmación explícita |
| `multi-tenancy` | R4 `:31` «El seed inicial DEBE ser idempotente y crear la organización "Solercia" con sus miembros demo» | **MODIFIED**: los miembros demo pasan a ser condicionales; la organización y el admin siguen siendo incondicionales |
| `org-role-templates` | `:29` exige las 5 plantillas de sistema sembradas | **Sin cambios** — es la razón por la que no se borran; conviene un escenario que fije que la purga borra instancias, no el catálogo |
| `intake-items` / `intake-classifier` | proyecto por defecto perezoso «Tareas Outlook» (`intake/service.py:581-599`) | **ADDED** escenario: con `default_project_id` ya apuntado, no se crea el proyecto por defecto |
| `projects` / `project-hierarchy` | `create_project` fuerza `proyecto`; roll-up por `allowed_statuses()[-1]` excluyendo solo `cancelled` (`project-hierarchy:113`) | Con la opción C1 **no requieren delta**. Con C2 habría que MODIFICAR `project-hierarchy` R de roll-up, `methodology-strategies`, `boards` y `dashboard-executive` |
| Nueva capacidad | — | **ADDED** `openspec/specs/data-maintenance/` (o `demo-seed`): flag de semilla, script de purga idempotente con dry-run/execute, respaldo obligatorio, invariantes post-purga y bootstrap de la jerarquía |

---

## Áreas afectadas

| Ruta | Por qué |
|---|---|
| `backend/app/config.py` | Nuevo `SEED_DEMO_DATA: bool = False` |
| `backend/app/db_init.py` | Compuerta en `_ensure_demo_members` (:586) y `_seed_demo_workitems` (:562); import de `settings` |
| `docker-compose.yml`, `env.example` | `SEED_DEMO_DATA=false` explícito y documentado |
| `backend/app/maintenance/` (nuevo) | Casos de uso `purge_demo_data` y `bootstrap_sdmujer_hierarchy`, probables con la `session` de SAVEPOINT |
| `backend/scripts/purge_demo_data.py` (nuevo) | CLI delgada: argparse, `--dry-run` por defecto, `--execute`, `--backup-file`, `--include-connectors`, `--database-url` |
| `backend/app/modules/projects/service.py` | Se consume `_create_project_unit` (sin modificarlo) para crear el `area` |
| `backend/app/modules/boards/repository.py` | Se consume `create_for_project` / se insertan `BoardColumn` literales (sin modificarlo) |
| `backend/tests/test_seed_demo_flag.py`, `test_purge_demo_data.py`, `test_bootstrap_hierarchy.py` (nuevos) | TDD estricto |
| `openspec/specs/{api-conventions,multi-tenancy}/spec.md` + nueva capacidad | Deltas |

Fuera de alcance: frontend, importación del checklist, usuarios Jason/Santiago, planes, `tasks.source/external_key` (cambio 43).

---

## Opciones comparadas

### Decisión A — mecanismo de la compuerta

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **A1 (recomendada)** `SEED_DEMO_DATA: bool = False` en `Settings`, compuerta con retorno temprano dentro de `_ensure_demo_members` y `_seed_demo_workitems` | Seguro por defecto; probable directamente con la `session` de SAVEPOINT (precedente `test_menu_seed.py`); no cambia la firma de `seed_default()`; reversible con una variable de entorno | Cambia el comportamiento por defecto de un arranque limpio (hay que pedir la demo explícitamente) — intencional, exige delta de spec | Bajo |
| A2 Igual pero con default `True` y `false` solo en el compose | Conserva el comportamiento as-built | Deja la trampa armada en cualquier entorno nuevo; depende de recordar la variable; contradice el plan aprobado | Bajo |
| A3 Eliminar el código de semilla demo | Diff conceptualmente más limpio | Pierde la capacidad de demo; borra requisitos vigentes de dos specs; diff grande e irreversible | Medio |

### Decisión B — dónde vive la purga

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **B1 (recomendada)** Caso de uso en `app/maintenance/` + CLI delgada `backend/scripts/purge_demo_data.py` | Cumple la regla de persistencia (el caso de uso es dueño de la transacción, el repositorio no hace commit); testeable con fakes y con la BD real; el dry-run es el mismo código que el execute | Introduce un directorio nuevo (`backend/scripts/`) sin precedente en el repo | Medio |
| B2 Script monolítico con SQL en línea | Rápido de escribir | No testeable ⇒ incompatible con `tdd: true` de `openspec/config.yaml:29`; duplica el conocimiento del grafo de FK | Bajo |
| B3 Endpoint HTTP de mantenimiento | Reutiliza auth y tenant | Expone una operación destructiva en la API; contradice `api-conventions` R3 en la superficie equivocada | Medio |
| B4 Migración Alembic de datos | Se ejecuta sola en el arranque | Borrado masivo irreversible dentro de una migración; rompe «migraciones = esquema» (`dev-tooling` R4/R5) y no admite dry-run ni confirmación | Bajo |

### Decisión C — los 7 estados de SEGURIDAD

| Opción | Pros | Contras | Esfuerzo |
|---|---|---|---|
| **C1 (recomendada)** 7 columnas con `Completada` **última**: `Sin iniciar, En curso, Diferida, Recurrente, Gestionada aparte, Removida, Completada` | Cero cambios en Strategy, roll-up, dashboard y sprints; `completed_at` correcto; ninguna spec MODIFIED por este eje; la columna terminal al final es la convención habitual de tablero | `Removida` y `Gestionada aparte` siguen contando en el denominador de avance (sub-reporta el progreso); el orden visual no es el del Excel | Bajo |
| C2 Orden del plan + `terminal_status_keys` y estados excluidos en la Strategy | Semántica completa y correcta del avance | Toca `MethodologyStrategy`, `BoardAwareStrategy`, `_resolve_completed_at`, `rollup_progress`, `_bounds_for` y `sprints/service.py`; obliga a MODIFICAR 4 specs; amplía mucho el radio de un cambio que debía ser pequeño | Alto |
| C3 Orden del plan sin cambios de código | Coincide con el Excel | **Incorrecto**: `Removida` sería el estado terminal — corrompe `completed_at`, el avance y la vista ejecutiva de forma silenciosa | Bajo (y descartada) |

---

## Recomendación

**A1 + B1 + C1**, con la exclusión de `Removida`/`Gestionada aparte` del denominador **diferida al cambio 44** (que es donde llegan las tareas con esos estados y donde el efecto se vuelve observable y verificable con datos reales).

Forma concreta sugerida para el cambio 42:

1. `SEED_DEMO_DATA: bool = False` en `config.py`; `db_init.py` lee `settings.SEED_DEMO_DATA` en tiempo de llamada y ambos helpers demo retornan temprano; `docker-compose.yml` y `env.example` lo declaran explícito.
2. `app/maintenance/purge.py` — caso de uso idempotente que recibe una `AsyncSession`, calcula el inventario (conteos antes), ejecuta el borrado en el orden de la §4 y devuelve un reporte estructurado. El `commit` lo hace el caso de uso, nunca los repositorios.
3. `app/maintenance/bootstrap.py` — crea `SDMUJER` (`area`, `planner`, `SDM`) vía `ProjectService._create_project_unit`, luego `SEGURIDAD` (`proyecto`, `custom`, `SEG`, padre SDMUJER) y `PANDORA` (`proyecto`, `kanban`, `PAN`, padre SDMUJER); añade las 7 `BoardColumn` literales al tablero vacío de SEGURIDAD con `order` 0..6; apunta `intake_settings.default_project_id` a SEGURIDAD. Todo en la misma transacción que la purga, o como segundo paso igualmente idempotente.
4. `backend/scripts/purge_demo_data.py` — CLI: `--dry-run` por defecto, `--execute` explícito, `--backup-file <ruta>` **obligatorio y verificado (existe y no está vacío) antes de cualquier borrado**, `--include-connectors` opcional, `--database-url` opcional. El respaldo `pg_dump` se toma fuera del contenedor backend y se documenta como paso previo del runbook.
5. El dry-run imprime: conteos antes/después previstos, lista de conectores y cuentas conectadas con `provider`, `display_name` y **usuario propietario**, y la advertencia de las cuentas que morirían por CASCADE al borrar usuarios demo.
6. Verificación post-ejecución en el propio script: existe `admin@solercia.com`, existe la organización `Solercia`, existen SDMUJER/SEGURIDAD/PANDORA, `SEGURIDAD` tiene exactamente 7 columnas con los `status_key` esperados y `Completada` con el `order` mayor, y `intake_settings.default_project_id` apunta a SEGURIDAD.

---

## Riesgos

1. **Alto — cuentas conectadas destruidas por CASCADE**: `connected_accounts.user_id ON DELETE CASCADE` (`connectors/models.py:91-93`). Si una de las 2 cuentas pertenece a un usuario demo, se pierde aunque el flag de conectores esté apagado. *Mitigación*: el dry-run lista propietarios; si hay cuentas de usuarios demo, el script se detiene y exige un flag adicional.
2. **Alto — irreversibilidad**: borrado físico sobre la única base con datos reales incipientes. *Mitigación*: `--backup-file` verificado antes de tocar nada; `--dry-run` por defecto; confirmación explícita del usuario antes del `--execute`.
3. **Alto — el orden de columnas define el estado terminal** (§2). Si se ignora, `Removida` se convierte en «hecho». *Mitigación*: opción C1 y una prueba que fije el invariante «la columna de mayor `order` de SEGURIDAD es `Completada`».
4. **Medio — huérfanos sin FK**: `attachments`, `notifications`, `notification_deliveries` (§4). *Mitigación*: borrado explícito por `target_id`/`dedup_key`, más una verificación de cero huérfanos al final. Los ficheros en `UPLOAD_DIR` quedan fuera del alcance del script y deben decidirse aparte.
5. **Medio — la ventana de la semilla**: entre el 42 y el 44 la base queda con 0 tareas; sin el flag, cualquier reinicio inyecta 12 tareas demo con estados inválidos en los proyectos reales. *Mitigación*: el flag va **primero** y se verifica con un reinicio real antes de cerrar el cambio.
6. **Medio — `ensure_system_templates` recrea el catálogo**: intentar borrar las 5 plantillas es futil y contradice `specs/org-role-templates/spec.md:29`. *Mitigación*: la propuesta corrige la decisión #3682 en este punto.
7. **Medio — entorno de ejecución del script**: `pg_dump` no existe en la imagen del backend (`Dockerfile:10-12`) y `DATABASE_URL` por defecto no resuelve desde el host (`config.py:24`). *Mitigación*: runbook con los dos comandos exactos y `--database-url` explícito.
8. **Bajo — deltas de spec destructivos**: `multi-tenancy` R4 y `api-conventions` R3/R4 se tocan; `archive` exige advertir antes de fusionar deltas destructivos (`openspec/config.yaml:36`).
9. **Bajo — el `asset` huérfano**: no lo alcanza ninguna cascada; requiere decisión explícita del usuario.

---

## Verificaciones pendientes antes de `sdd-apply`

Este ejecutor no dispone de herramienta de shell, así que quedan pendientes (solo lectura, sin mutaciones):

1. Identidad de conectores y cuentas conectadas, incluido el propietario:
   `docker exec gestion_proyectos-postgres-1 psql -U app -d solercia -At -c "SELECT c.provider, c.status, ca.display_name, ca.external_account_id, u.email FROM connectors c LEFT JOIN connected_accounts ca ON ca.connector_id = c.id LEFT JOIN users u ON u.id = ca.user_id ORDER BY c.provider;"`
2. Confirmar los `ON DELETE` reales en la base (el ORM y las migraciones podrían divergir):
   `docker exec gestion_proyectos-postgres-1 psql -U app -d solercia -At -c "SELECT conrelid::regclass, conname, confrelid::regclass, confdeltype FROM pg_constraint WHERE contype='f' ORDER BY 1;"`
3. Inventario de `attachments` y `notifications` que apuntan a tareas de proyectos demo.
4. Propietario del único `asset` y decisión del usuario sobre su destino.

## ¿Listo para propuesta?

**Sí**, con tres correcciones al plan que la propuesta debe recoger explícitamente: (a) la compuerta de la semilla es por `COUNT(tasks)` global y `_ensure_demo_members` es incondicional; (b) el orden de las 7 columnas define el estado terminal, así que `Completada` va última; (c) las 5 `org_role_templates` no se borran (se borra el árbol instanciado). Además, la propuesta debe declarar la exclusión de `Removida`/`Gestionada aparte` del denominador como trabajo diferido al cambio 44.

---

## Verificaciones resueltas por el orquestador (2026-08-26, solo lectura sobre la base real)

1. **Conectores y cuentas**: `fake` (activo, cuenta `fake-account-qa-demo-1` soft-deleted, dueño `admin@`) → demo, se borra. `google` y `microsoft365` (activos, sin cuentas) y `jira` (cuenta «Cristian Camilo Calderon Tapia», `jira-5b18044e…`, dueño `admin@`) → **reales, se conservan**. Ninguna cuenta pertenece a usuarios demo: el CASCADE desde `users` no destruye cuentas.
2. **Huérfanos**: `attachments` = 81 (todas `target_type = task`) y ≈1963 archivos en `backend/uploads/` (host) / `/app/uploads` (contenedor); `notifications` = 29 (`asset_license`, `sprint`, `task`); `notification_deliveries` = 0; `reminders` = 2; `alert_rules` = 7 (semilla estructural, se conservan).
3. **Asset**: único registro «Verify Test Asset» (org Solercia, responsable `admin@`, soft-deleted 2026-07-12) → artefacto de verificación, **se borra** junto con sus `asset_licenses`.
4. **Otros conteos**: 17 tareas asignadas a usuarios demo; `org_role_template_instantiations` = 12 (ledger del árbol OAP-TI); `user_roles` = 6; `board_columns` = 86; `task_comments` = 73; `task_history` = 145.
5. Decisión de alcance adicional: el script acepta `--purge-upload-files` para borrar **solo** los archivos referenciados por las filas de `attachments` eliminadas (nunca un `rm` genérico del directorio).
