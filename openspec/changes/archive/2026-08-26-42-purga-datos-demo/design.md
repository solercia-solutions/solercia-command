# Design: 42 · Purga de datos demo y bootstrap de la jerarquía SDMUJER

> Fase `sdd-design`. Store híbrido: este contenido está también en Engram (`sdd/42-purga-datos-demo/design`).
> Entradas: `proposal.md` (Engram #3693) y `exploration.md` (Engram #3687). Decisiones A1 + B1 + C1 ya cerradas por el usuario.

## Technical Approach

Un **paquete de mantenimiento** nuevo (`backend/app/maintenance/`) con la separación que ya usa el
resto del backend (`router → service → repository`), donde el papel del router lo hace una **CLI
delgada** (`backend/scripts/purge_demo_data.py`). Toda la mecánica SQLAlchemy vive en un único
adaptador (`maintenance/repository.py`); los casos de uso (`purge`, `bootstrap`, `invariants`) sólo
orquestan y devuelven un reporte tipado; **un solo caso de uso compuesto** (`runner.py`) es dueño de
la **única transacción**. Ningún repositorio hace `commit`.

El alcance demo es **dato explícito** (`maintenance/scope.py`), nunca heurística: nombres, correos,
códigos y proveedores literales, más el subárbol de proyectos resuelto por CTE. El dry-run ejecuta
**el mismo código** y termina en `rollback`, así que lo que el humano revisa es exactamente lo que
el `--execute` hará. La compuerta `SEED_DEMO_DATA` va primero y se verifica con un reinicio real
antes de purgar nada.

## Architecture Decisions

### D1 — Paquete `app/maintenance/` con adaptador único

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| SQL en línea dentro del script | Rápido, pero intesteable y contradice `tdd: true` (`openspec/config.yaml:29`) | Rechazada |
| Repositorio por módulo tocado (tasks, projects, users…) | 12 repositorios nuevos para una operación de una sola vez | Rechazada |
| **`maintenance/repository.py` como adaptador único con métodos semánticos** | Un solo lugar conoce el grafo de FK; los casos de uso quedan puros y testeables | **Elegida** |

```
backend/app/maintenance/
├── scope.py        # DemoScope: alcance literal (frozen dataclass, sin I/O)
├── report.py       # dataclasses del reporte (sin I/O)
├── repository.py   # MaintenanceRepository — ÚNICO lugar con SQLAlchemy; nunca commit
├── purge.py        # caso de uso: resuelve alcance, ordena, delega el borrado
├── bootstrap.py    # caso de uso: jerarquía + columnas + intake_settings
├── invariants.py   # caso de uso de verificación (sólo lectura)
└── runner.py       # caso de uso compuesto: DUEÑO de la transacción
backend/scripts/purge_demo_data.py   # CLI: argparse, guardas, impresión, códigos de salida
```

### D2 — Transacción única y dry-run por `rollback`

`run_maintenance(session, *, execute, scope)` abre nada y cierra todo: llama purga → bootstrap →
invariantes y, al final, `commit()` **sólo si** `execute` es verdadero **y** todas las invariantes
están en PASS; en cualquier otro caso `rollback()`.

| Opción de dry-run | Tradeoff | Decisión |
|---|---|---|
| Inventario de sólo lectura, sin escrituras | Barato, pero duplica la lógica de conteo y **no detecta violaciones de FK** antes del día real | Rechazada |
| **Mismo código + `rollback` final** | Cero divergencia entre lo previsto y lo ejecutado; el dry-run falla igual que fallaría el execute; la base es pequeña, el costo es irrelevante | **Elegida** |

**Idempotencia.** Purga: el alcance resuelto vuelve vacío en la segunda corrida y todos los borrados
son `no-op` con conteo 0. Bootstrap: busca por `code` dentro de la organización y **reutiliza** el
proyecto existente; inserta sólo las `BoardColumn` faltantes y reasigna `order` al índice canónico
(escritura convergente, nunca duplicada); `intake_settings.default_project_id` se fija sólo si es
`NULL` o distinto de SEGURIDAD.

### D3 — Alcance como dato explícito

`DemoScope` (frozen dataclass, valores por defecto = el alcance acordado):

| Campo | Valor | Resolución |
|---|---|---|
| `organization_names` | `("Acme Consultores",)` | borrado completo por CASCADE de tenant |
| `user_emails` | `ana@`, `carlos@`, `diana@`, `verify-smoke-11@solercia.com` | por `users.email` exacto |
| `project_names` | `Plataforma Web`, `Soporte Técnico`, `Mejoras Internas` | en la org `Solercia`, activos **y** con borrado suave |
| `include_template_instantiations` | `True` | proyectos con fila en `org_role_template_instantiations` (árbol OAP-TI) |
| `connector_providers` | `("fake",)` | por `connectors.provider` |
| `asset_names` | `("Verify Test Asset",)` | por `assets.name` + su `asset_licenses`/`asset_tasks` |
| `protected_*` | `admin@solercia.com`, slug `solercia`, códigos `SDM/SEG/PAN`, proveedores `jira/google/microsoft365` | listas negras verificadas ANTES de borrar |

Los proyectos semilla se resuelven por **nombre**, no por código: `_ensure_demo_projects`
(`db_init.py:632-641`) los crea sin `code` y `_backfill_project_codes` lo deriva después. El conjunto
se cierra con el **subárbol descendiente completo** (CTE recursivo sobre `parent_project_id`), porque
esa FK es `SET NULL` (`projects/models.py:78-83`) y borrar un padre dejaría a los hijos como raíces
huérfanas. El reporte imprime la lista resuelta (`id`, `code`, `name`, `project_kind`, `is_active`)
antes de cualquier borrado: el alcance es auditable, no adivinado.

**Guardas de fallo cerrado** (antes de escribir, salida 2 sin tocar nada): el alcance no puede
contener `admin@solercia.com`, la org `Solercia`, ningún código protegido, ni un proveedor protegido;
y si alguna `connected_accounts.user_id` pertenece a un usuario a borrar, el script se detiene
(`connectors/models.py:92`, `ON DELETE CASCADE`).

### D4 — Orden de borrado y huérfanos sin FK

Borrado **físico**, de hoja a raíz, con `delete()` masivo y `synchronize_session=False`:

| № | Tabla(s) | Mecanismo |
|---|---|---|
| 1 | `checklist_items`, `task_checklists`, `task_time_logs`, `task_history`, `task_comments`, `task_dependencies`, `task_labels`, `asset_tasks` | explícito (CASCADE existe; se lista para no depender del motor) |
| 2 | `attachments` con `target_id ∈ tareas ∪ comentarios` | **explícito — no hay FK** (`attachments/models.py:29-32`) |
| 3 | `notification_deliveries` de las notificaciones afectadas → luego `notifications` con `target_id ∈ tareas` | **explícito — `SET NULL`** (`notify/models.py:35-36`); las entregas van primero |
| 4 | `reminders` / `reminder_rules` del alcance | **explícito — `task_id` es `SET NULL`** (`reminders/models.py:41`) |
| 5 | `intake_items`, `intake_rules`, `intake_runs`; `intake_settings.default_project_id → NULL` | explícito (todas `SET NULL`) |
| 6 | `tasks` | explícito |
| 7 | `sprints`, `board_columns`, `boards`, `labels` | CASCADE desde `projects` |
| 8 | `org_role_template_instantiations` | CASCADE desde `projects.id` |
| 9 | `projects` **de hoja a raíz** (orden topológico por profundidad descendente) | explícito |
| 10 | `asset_licenses` → `assets` | explícito |
| 11 | `connection_credentials` → `connected_accounts` → `connectors` (`provider='fake'`, incluidas filas con borrado suave) | explícito |
| 12 | `organization_members`, `user_roles`, `federated_identities`, `notification_preferences`, `glpi_user_links` → `users` demo | CASCADE desde `users`, listado explícito |
| 13 | `organizations` = `Acme Consultores` | CASCADE de tenant |

**No se borran**: `org_role_templates` + `org_role_template_nodes` (catálogo de sistema reseedeado por
`ensure_system_templates`), `dependencies`, `roles`, `menus`, `role_menus`, `alert_rules`, la org
`Solercia` y `admin@solercia.com`.

### D5 — Compuerta de la semilla, leída en tiempo de llamada

| Archivo | Cambio exacto |
|---|---|
| `backend/app/config.py` | `SEED_DEMO_DATA: bool = False` (la semilla estructural sigue incondicional) |
| `backend/app/db_init.py` | `from app.config import settings` (hoy no lo importa) + retorno temprano `if not settings.SEED_DEMO_DATA: return []` al inicio de `_ensure_demo_members` (`:586`) y `return` al inicio de `_seed_demo_workitems` (`:562`) |
| `docker-compose.yml` | `SEED_DEMO_DATA: "false"` en `environment:` del servicio `backend` (`:36-41`) |
| `env.example` | `SEED_DEMO_DATA=false` documentado como «encender sólo para demos» |

La lectura es **acceso a atributo del singleton** (`config.py:317-324`), nunca una constante de
módulo: así `monkeypatch.setattr(settings, "SEED_DEMO_DATA", True)` funciona, siguiendo el precedente
`tests/test_email_outbox.py:39`. La compuerta va **dentro de los helpers**, no en `seed_default()`,
porque `seed_default` abre su propia `AsyncSessionLocal` (`db_init.py:349`) fuera del SAVEPOINT de
pruebas; los helpers reciben la sesión y son testeables (precedente `tests/test_menu_seed.py:26-29`).

`COUNT(tasks) == 0` (`db_init.py:367-369`) **no se toca**: con el flag apagado, `_seed_demo_workitems`
retorna de inmediato y la consulta queda como una lectura inocua. Cambiar esa condición ampliaría el
diff sin ganar seguridad.

### D6 — Bootstrap: `_create_project_unit` + columnas literales + `intake_settings`

```python
_HIERARCHY = (  # (code, name, kind, methodology, parent_code)
    ("SDM", "SDMUJER",   ProjectKind.area,     Methodology.planner, None),
    ("SEG", "SEGURIDAD", ProjectKind.proyecto, Methodology.custom,  "SDM"),
    ("PAN", "PANDORA",   ProjectKind.proyecto, Methodology.kanban,  "SDM"),
)
_SEGURIDAD_COLUMNS = ("Sin iniciar", "En curso", "Diferida", "Recurrente",
                      "Gestionada aparte", "Removida", "Completada")  # order 0..6
```

Creación con `ProjectService(session)._create_project_unit(org_id, ProjectCreate(...), actor_id=admin_id)`
y `# noqa: SLF001`, mismo precedente que `org_role_templates/service.py:295`. Es la **única** vía
posible: `create_project` fuerza `project_kind = proyecto` y `lead_user_id = None`
(`projects/service.py:117-119`), así que SDMUJER (`area`) no se puede crear por ahí. `_create_project_unit`
valida el padre, fija el `code` explícito, hace `add + flush` y **no comitea**.

**Las 7 columnas.** `_create_project_unit` siempre llama `BoardService.seed_board`
(`projects/service.py:202`), que para `custom` crea un `Board` con **cero** columnas
(`CustomStrategy.default_columns() == []`), y `boards.project_id` es UNIQUE (`boards/models.py:36-37`):
hay que **añadir las columnas al tablero existente**, no crear otro. Método del adaptador:

```python
async def ensure_board_columns(self, board_id, columns: Sequence[str]) -> int:
    existing = {c.status_key: c for c in await self._list_columns(board_id)}
    for order, name in enumerate(columns):
        column = existing.get(name)
        if column is None:
            self.db.add(BoardColumn(board_id=board_id, name=name,
                                    status_key=name, order=order))  # status_key LITERAL
        elif column.order != order:
            column.order = order
    await self.db.flush()
```

| Opción para las columnas | Tradeoff | Decisión |
|---|---|---|
| `BoardService.add_column` | Slugifica (`_slugify`, `boards/service.py:27-37`) → `sin_iniciar`, y **comitea por columna** (`:221`): rompe la atomicidad | Rechazada |
| `BoardRepository.create_for_project` | Crea un **segundo** `Board` y viola el UNIQUE de `boards.project_id` | Rechazada |
| **`ensure_board_columns` sobre el tablero ya sembrado** | `status_key == name` verbatim (misma convención que `seed_board`), respeta `uq_board_column_status_key`, idempotente y sin commit | **Elegida** |

`Completada` con `order = 6` es un requisito **funcional**, no cosmético: el estado terminal se
resuelve como `allowed_statuses()[-1]` (`tasks/service.py:854-864`, `sprints/service.py:271`,
`projects/repository.py:322-326`) sobre columnas leídas en orden ascendente de `order`
(`boards/repository.py:88,124`). PANDORA no necesita nada: `seed_board` le siembra las columnas
kanban por defecto.

`intake_settings`: **upsert directo por ORM** dentro de la misma sesión. Se rechaza
`IntakeSettingsRepository.get_or_create` por la misma razón que `add_column`: **hace `commit()`**
(`intake/repository.py:265`). Con `default_project_id` apuntado, `IntakeService._ensure_default_project`
(`intake/service.py:581-599`) nunca crea el proyecto «Tareas Outlook».

### D7 — CLI: importación, sesión, respaldo y códigos de salida

Ejecución en el host: `cd backend && .venv/bin/python -m scripts.purge_demo_data …`. Se usa **`-m`
y no la ruta del archivo** de forma deliberada: con `-m`, `sys.path[0]` es el cwd (`backend/`), así
que `import app.*` y `scripts.purge_demo_data` resuelven sin ningún parche de `sys.path`; ejecutar
`python scripts/purge_demo_data.py` pondría `backend/scripts/` en la ruta y `app` no sería importable.
`backend/scripts/__init__.py` existe para que el paquete sea explícito.

La CLI construye **su propio** `create_async_engine(args.database_url or settings.DATABASE_URL)` +
`async_sessionmaker(expire_on_commit=False)` y lo libera con `dispose()`. El `engine` de módulo de
`app.database` (`:15-20`) se crea al importar los modelos pero **nunca conecta** (la construcción del
engine es perezosa), así que apuntar por defecto a `postgres:5432` no molesta desde el host.

Banderas: `--dry-run` (por defecto), `--execute`, `--backup-file <ruta>` (**obligatoria con
`--execute`**), `--database-url`, `--purge-upload-files` (apagada por defecto).

| Código | Significado |
|---|---|
| 0 | Éxito (dry-run o execute) con todas las invariantes en PASS |
| 1 | Error de uso: `--execute` sin `--backup-file`, o respaldo inexistente/de tamaño 0 |
| 2 | Guarda de seguridad activada (cuenta conectada de un usuario a borrar, alcance que toca lo protegido) — no se escribió nada |
| 3 | Alguna invariante en FAIL — transacción revertida, sin `commit` |
| 4 | Excepción inesperada — transacción revertida |

**Archivos de subida.** Con `--purge-upload-files`, se borran **sólo** los ficheros
`Path(settings.UPLOAD_DIR) / stored_name` de las filas de `attachments` efectivamente borradas,
tras `resolve()` y verificando `is_relative_to(UPLOAD_DIR resuelto)`. Se hace **después del `commit`**,
nunca dentro de la transacción: el `pg_dump` no lleva binarios, así que un rollback no podría
restaurarlos. Un fichero ausente es advertencia, no error. Los ≈1963 ficheros no referenciados **no
se tocan**.

### D8 — Reporte tipado e invariantes

```python
@dataclass(frozen=True) class InventoryRow:   table: str; before: int; after: int
@dataclass(frozen=True) class PlannedDeletion: table: str; ids: tuple[UUID, ...]; reason: str
@dataclass(frozen=True) class DeletionResult:  table: str; deleted: int
@dataclass(frozen=True) class InvariantResult: key: str; description: str; passed: bool; detail: str
@dataclass(frozen=True) class MaintenanceReport:
    mode: Literal["dry-run", "execute"]
    inventory: tuple[InventoryRow, ...]; planned: tuple[PlannedDeletion, ...]
    deleted: tuple[DeletionResult, ...]; bootstrap: tuple[str, ...]
    invariants: tuple[InvariantResult, ...]
    @property def ok(self) -> bool: return all(i.passed for i in self.invariants)
```

| № | Invariante |
|---|---|
| I1 | Existe `admin@solercia.com` y es el único usuario |
| I2 | Existe la org `Solercia`; no existe `Acme Consultores` |
| I3 | SDM/SEG/PAN existen con `code`, `project_kind`, `methodology` y padre esperados |
| I4 | SEGURIDAD tiene exactamente 7 columnas activas y la de mayor `order` es `Completada` |
| I5 | `intake_settings.default_project_id` = SEGURIDAD y no existe proyecto «Tareas Outlook» |
| I6 | Cero huérfanos: `attachments` (81→0), `notifications` (29→0), `reminders` (2→0), `asset_tasks` (→0) |
| I7 | 5 `org_role_templates` de sistema intactas; 0 `org_role_template_instantiations` |
| I8 | 0 conectores `fake`; `jira`/`google`/`microsoft365` presentes con sus cuentas |

Salida por consola: tabla de ancho fijo en tres bloques (`INVENTARIO`, `BORRADOS`, `INVARIANTES`) y
un encabezado con modo, base de datos **con la contraseña redactada** (`app:***@host:puerto/db`),
ruta y tamaño del respaldo. Nunca se imprimen credenciales, `connection_credentials`, tokens ni el
`JWT_SECRET`.

## Data Flow

```mermaid
sequenceDiagram
    participant CLI as scripts/purge_demo_data.py
    participant R as maintenance/runner.py
    participant P as maintenance/purge.py
    participant B as maintenance/bootstrap.py
    participant I as maintenance/invariants.py
    participant A as MaintenanceRepository
    participant DB as PostgreSQL

    CLI->>CLI: argparse; --execute exige --backup-file existente y > 0 bytes
    CLI->>CLI: crea engine propio (--database-url) y abre AsyncSession
    CLI->>R: run_maintenance(session, execute=True, scope=DemoScope())
    R->>P: purge_demo_data(session, scope)
    P->>A: resolve_demo_scope(scope)  → ids + subárbol CTE
    A->>DB: SELECT (inventario + resolución)
    P->>P: guardas: admin/org/códigos/proveedores protegidos + cuentas conectadas
    loop pasos 1..13 del orden de borrado
        P->>A: delete_<tabla>(ids)
        A->>DB: DELETE ... (sin commit)
    end
    R->>B: bootstrap_sdmujer(session)
    B->>A: find_project_by_code / ProjectService._create_project_unit
    B->>A: ensure_board_columns(board_seg, 7 columnas)
    B->>A: upsert_intake_default_project(org, seguridad_id)
    R->>I: collect_invariants(session)
    I->>DB: SELECT (I1..I8)
    alt execute y todas PASS
        R->>DB: COMMIT
    else dry-run o alguna FAIL
        R->>DB: ROLLBACK
    end
    R-->>CLI: MaintenanceReport
    CLI->>CLI: imprime tablas; si --purge-upload-files y hubo commit → borra ficheros
```

## File Changes

| Archivo | Acción | Descripción | ≈ líneas |
|---|---|---|---|
| `backend/app/config.py` | Modificar | `SEED_DEMO_DATA: bool = False` | 4 |
| `backend/app/db_init.py` | Modificar | Import de `settings` + compuerta en `_ensure_demo_members` y `_seed_demo_workitems` | 8 |
| `docker-compose.yml` | Modificar | `SEED_DEMO_DATA: "false"` | 1 |
| `env.example` | Modificar | Variable documentada | 3 |
| `backend/app/maintenance/scope.py` | Crear | `DemoScope` literal | 70 |
| `backend/app/maintenance/report.py` | Crear | Dataclasses del reporte | 80 |
| `backend/app/maintenance/repository.py` | Crear | Adaptador único (resolución + borrados + columnas + intake) | 330 |
| `backend/app/maintenance/purge.py` | Crear | Caso de uso de purga + guardas | 140 |
| `backend/app/maintenance/bootstrap.py` | Crear | Caso de uso de jerarquía | 130 |
| `backend/app/maintenance/invariants.py` | Crear | I1..I8 | 120 |
| `backend/app/maintenance/runner.py` | Crear | Dueño de la transacción | 60 |
| `backend/scripts/{__init__,purge_demo_data}.py` | Crear | CLI, guardas, impresión, códigos de salida, ficheros | 210 |
| `backend/tests/test_seed_demo_flag.py` | Crear | Compuerta | 90 |
| `backend/tests/test_purge_demo_data.py` | Crear | Alcance, orden, huérfanos, idempotencia | 300 |
| `backend/tests/test_bootstrap_hierarchy.py` | Crear | Jerarquía, columnas, intake | 180 |
| `backend/tests/test_maintenance_invariants.py` | Crear | Invariantes en rojo | 90 |
| `backend/tests/test_purge_cli.py` | Crear | argparse/guardas sin base de datos | 110 |
| `openspec/specs/data-maintenance/spec.md` + deltas `api-conventions`, `multi-tenancy`, `org-role-templates`, `intake-classifier` | Crear/Modificar | Capacidad nueva + 4 deltas | 190 |

`backend/app/modules/projects/service.py` y `boards/*` se **consumen sin modificarse**.

## Interfaces / Contracts

```python
# maintenance/runner.py — ÚNICO dueño de la transacción
async def run_maintenance(session: AsyncSession, *, execute: bool,
                          scope: DemoScope) -> MaintenanceReport: ...

# maintenance/purge.py / bootstrap.py / invariants.py — nunca comitean
async def purge_demo_data(session: AsyncSession, scope: DemoScope) -> PurgeOutcome: ...
async def bootstrap_sdmujer(session: AsyncSession, *, organization_id: UUID,
                            actor_id: UUID) -> tuple[str, ...]: ...
async def collect_invariants(session: AsyncSession) -> tuple[InvariantResult, ...]: ...

# maintenance/repository.py — métodos semánticos, con alcance de tenant explícito
class MaintenanceRepository:
    def __init__(self, db: AsyncSession) -> None: ...
    async def resolve_demo_scope(self, scope: DemoScope) -> ResolvedScope: ...
    async def find_connected_accounts_owned_by(self, user_ids) -> list[AccountOwner]: ...
    async def count_inventory(self) -> tuple[InventoryRow, ...]: ...
    async def delete_attachments_for_targets(self, task_ids, comment_ids) -> int: ...
    async def delete_notifications_for_tasks(self, task_ids) -> int: ...   # entregas primero
    async def delete_projects_leaf_first(self, ordered_project_ids) -> int: ...
    async def find_project_by_code(self, organization_id, code) -> Project | None: ...
    async def ensure_board_columns(self, board_id, columns) -> int: ...
    async def upsert_intake_default_project(self, organization_id, project_id) -> None: ...
```

## Testing Strategy

TDD estricto (`openspec/config.yaml:26-30`), `cd backend && pytest tests/ -v`. La `session` de
SAVEPOINT (`conftest.py:87-110`) revierte incluso los `commit()` internos, así que es el harness
natural para un caso de uso destructivo. El dataset demo en miniatura se construye con un helper
local `_seed_demo_fixture(session)` inspirado en `_seed_org_data` (`conftest.py:376-460`), que ya
crea org + usuario + proyecto + tarea + notificación con `dedup_key` y `target_id`.

| Capa | Qué se prueba | Archivo · pruebas clave |
|---|---|---|
| Compuerta | Retorno temprano y lectura en tiempo de llamada | `test_seed_demo_flag.py`: `test_ensure_demo_members_no_crea_usuarios_con_flag_apagado`, `test_ensure_demo_members_crea_usuarios_con_flag_encendido`, `test_seed_demo_workitems_no_crea_proyectos_con_flag_apagado`, `test_compuerta_se_lee_en_tiempo_de_llamada` |
| Purga (BD real) | Alcance, orden, huérfanos, guardas, idempotencia | `test_purge_demo_data.py`: `test_purga_borra_org_demo_usuarios_y_proyectos`, `test_purga_conserva_admin_org_solercia_y_plantillas_de_sistema`, `test_purga_borra_adjuntos_notificaciones_y_recordatorios_huerfanos`, `test_purga_borra_subarbol_completo_de_hoja_a_raiz`, `test_purga_borra_conector_fake_y_conserva_los_reales`, `test_purga_falla_cerrado_si_una_cuenta_conectada_pertenece_a_un_usuario_demo`, `test_purga_es_idempotente_en_segunda_corrida`, `test_dry_run_no_deja_cambios_visibles` |
| Bootstrap (BD real) | Jerarquía, columnas, intake, idempotencia | `test_bootstrap_hierarchy.py`: `test_bootstrap_crea_sdmujer_seguridad_pandora_con_codigos_y_metodologias`, `test_seguridad_tiene_siete_columnas_y_completada_es_la_de_mayor_order`, `test_status_key_de_las_columnas_es_literal_no_slug`, `test_pandora_recibe_las_columnas_por_defecto_de_kanban`, `test_bootstrap_es_idempotente_y_reutiliza_proyectos_por_codigo`, `test_intake_settings_apunta_a_seguridad_sin_crear_tareas_outlook` |
| Invariantes | Detectan el estado corrupto | `test_maintenance_invariants.py`: `test_invariantes_fallan_si_completada_no_es_la_ultima_columna`, `test_invariantes_fallan_si_quedan_adjuntos_huerfanos` |
| CLI (sin BD) | argparse, guardas, redacción, contención de rutas | `test_purge_cli.py`: `test_dry_run_es_el_modo_por_defecto`, `test_execute_sin_backup_file_falla_con_codigo_1`, `test_backup_file_inexistente_o_vacio_falla_con_codigo_1`, `test_purge_upload_files_esta_apagado_por_defecto`, `test_purge_upload_files_rechaza_rutas_fuera_de_upload_dir`, `test_la_url_de_base_de_datos_se_redacta_en_la_salida` |

Se prueban contra PostgreSQL real (no se simulan los `delete()` masivos ni el CTE recursivo), como
exige el contrato de pruebas de adaptadores.

## Threat Matrix

Aplicabilidad: este cambio **no** toca enrutamiento HTTP, composición de comandos de shell,
automatización de Git/PR ni clasificación de ficheros ejecutables. Sí introduce una **frontera de
proceso nueva** (CLI destructiva) y una **frontera de sistema de ficheros**, que se añaden como filas
propias.

| Frontera | Casos adversarios mínimos | Aplicabilidad | Respuesta de diseño | Pruebas RED planificadas |
|---|---|---|---|---|
| Rutas tipo documentación | `requirements.txt`, Markdown ejecutable | N/A: el cambio no clasifica ni ejecuta ficheros por su extensión | — | — |
| Selección de repositorio Git | `git -C`, rutas relativas/absolutas | N/A: no hay automatización de Git | — | — |
| Estado de commit | staged, `commit -a`, índice vacío | N/A: no hay automatización de Git | — | — |
| Estado de push | rama de seguimiento, primer push | N/A: no hay automatización de Git | — | — |
| Comandos de PR | `--head`, prefijo de entorno | N/A: no hay automatización de PR | — | — |
| **Entrada de proceso destructiva** | `--execute` sin respaldo; respaldo vacío; `--database-url` a otra base; segunda corrida | **Aplicable** | `--dry-run` por defecto; `--backup-file` obligatorio, existente y > 0 bytes; guardas de alcance protegido; `commit` sólo con invariantes en PASS; idempotencia | `test_execute_sin_backup_file_falla_con_codigo_1`, `test_backup_file_inexistente_o_vacio_falla_con_codigo_1`, `test_purga_es_idempotente_en_segunda_corrida` |
| **Borrado en sistema de ficheros** | `stored_name` con `../`, ruta absoluta, symlink, fichero ausente | **Aplicable** | `resolve()` + `is_relative_to(UPLOAD_DIR)`; sólo `stored_name` de filas borradas; ejecución posterior al `commit`; ausencia = advertencia | `test_purge_upload_files_rechaza_rutas_fuera_de_upload_dir`, `test_purge_upload_files_esta_apagado_por_defecto` |

## Migration / Rollout

Sin migración Alembic: **este cambio no toca el esquema**. Runbook alineado con `proposal.md`:

1. Compuerta primero: desplegar `SEED_DEMO_DATA=false`, `docker compose restart backend`, confirmar
   que `ana@`/`carlos@`/`diana@` no reaparecen. Nada más avanza hasta que esto esté verificado.
2. Respaldo desde el host (`pg_dump` no existe en la imagen del backend, `Dockerfile:10-12`):
   `mkdir -p /Users/camilocalderont/Proyectos/SOLERCIA/backups && docker exec gestion_proyectos-postgres-1 pg_dump -U app solercia > /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql`
3. Dry-run: `cd backend && .venv/bin/python -m scripts.purge_demo_data --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia`
4. Revisión humana del reporte (alcance resuelto + conteos + invariantes previstas).
5. Ejecución: añadir `--execute --backup-file <ruta>`.
6. `docker compose restart backend` y repetir el dry-run: las invariantes deben seguir en PASS y no
   debe reaparecer nada demo.

**Rollback (secuencia exacta y segura).** El backend debe estar **detenido** para que la semilla no
corra a mitad de la restauración:

```bash
docker compose stop backend
docker exec gestion_proyectos-postgres-1 psql -U app -d solercia -v ON_ERROR_STOP=1 \
  -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO app; GRANT ALL ON SCHEMA public TO public;'
docker exec -i gestion_proyectos-postgres-1 psql -U app -d solercia -v ON_ERROR_STOP=1 \
  < /Users/camilocalderont/Proyectos/SOLERCIA/backups/solercia-command-pre-ola5-<fecha>.sql
docker compose start backend
```

El `DROP SCHEMA public CASCADE` también elimina la extensión `pg_trgm`; el volcado la recrea
(`CREATE EXTENSION`). Recuperar la demo: `SEED_DEMO_DATA=true` + reinicio. Regresiones de código:
revertir commits; no hay migración que bajar. Los ficheros borrados con `--purge-upload-files` **no
son recuperables** desde el volcado: esa es la razón de que esté apagada por defecto.

**Carga de revisión.** ≈1 900 líneas de autoría (código ≈1 160, pruebas ≈770, specs ≈190) — por
encima del presupuesto de 400 líneas por PR y cerca del presupuesto de sesión de 2 000. Estrategia
`auto-chain` en tres rebanadas: (1) compuerta + compose/env + pruebas ≈160; (2) `scope`/`report`/
`repository`/`purge`/`runner` + CLI en dry-run + pruebas ≈1 080; (3) `bootstrap` + invariantes +
`--execute` + ficheros + specs ≈660. La rebanada 2 sigue siendo grande: `sdd-tasks` debería evaluar
partirla en 2a (`scope` + `report` + `repository` + pruebas de resolución) y 2b (`purge` + `runner`
+ CLI). El pronóstico formal lo emite `sdd-tasks`.

## Open Questions

- [ ] Ninguna que bloquee. Las cinco preguntas abiertas de `proposal.md` (avance sub-reportado hasta
      el cambio 44, ficheros no referenciados, demo apagada sin arreglar, `verify-smoke-11@` y
      «Verify Test Asset» desechables, custodia del respaldo) ya están resueltas por las decisiones
      del orquestador y quedan incorporadas arriba.
