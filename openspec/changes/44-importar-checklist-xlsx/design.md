# Design: 44 · Importador idempotente de `CHECKLIST_TAREAS.xlsx`

> Fase `sdd-design`. Store híbrido: espejo de Engram `sdd/44-importar-checklist-xlsx/design`.
> Entradas: `proposal.md`, `exploration.md`, `state.yaml` y los cinco deltas de
> `specs/{checklist-import,project-hierarchy,boards,tasks,dashboard-executive}/spec.md`
> — **40 requisitos / 108 escenarios**, contados en disco.
> Decisiones cerradas que este diseño **implementa sin reabrir**: D1–D9 del orquestador y las
> técnicas D-MIG, D-DDL, D-CSV, D-CSV-DEF, D-LBL, D-PSPI, D-REC, D-CNT, D-DESC y D-BADGE.
> Extensión confirmada por el orquestador (`spec_notes`): el denominador del roll-up de
> `project-hierarchy` excluye **tanto** las columnas `excluded_from_progress` **como** las tareas con
> `context_group IS NOT NULL`; el dashboard excluye contexto en `_build_by_assignee`,
> `_build_workload` y el conteo de volumen de `_build_totals`, y **nunca** en `_build_at_risk` ni en
> los contadores de riesgo `totals.overdue`/`totals.at_risk`.
> Referencias de código verificadas en disco el 2026-08-26.
>
> **Pasada correctiva 2026-08-26** sobre el veredicto `PASS_WITH_NOTES` del validador independiente
> (21 hallazgos: 1 ALTO, 10 MEDIO, 10 BAJO). Resueltos H1–H21 con las decisiones del orquestador;
> las secciones afectadas llevan la marca correspondiente. Decisiones nuevas de esta pasada:
> **D-EXIT**, **D-LBL-IO**, **D-VAL** y **D-USERS**.

## Enfoque técnico

Siete rebanadas encadenadas sobre tres capas ya existentes y **un paquete nuevo**. A, B y C son
costuras de esquema y de caso de uso sobre módulos publicados (`boards`, `projects`, `tasks`,
`dashboard`, `maintenance`); D, E, F y G son un importador por lotes que **no agrega un solo endpoint
HTTP** y que consume esas costuras desde fuera de `app/modules/`.

El idioma es el del propio repositorio: migraciones aditivas al estilo de `0022_add_project_kind.py`,
espejado en `__table_args__` porque el harness construye el esquema con `Base.metadata.create_all`
(`tests/conftest.py:74-80`), sembrado idempotente con `MaintenanceRepository.ensure_board_columns`
(`maintenance/repository.py:392-419`), caso de uso dueño de la transacción al estilo de
`maintenance/runner.py:19-61`, CLI calcada de `backend/scripts/purge_demo_data.py` y lector XLSX
calcado de `integrations/adapters/jira/file_parser.py:109-148`.

Tres reglas irrenunciables atraviesan el diseño:

1. **El importador nunca inventa un camino de escritura.** Toda lectura por ancla pasa por
   `TaskRepository.get_by_external_key`; toda creación por
   `TaskService.create_task(..., external_origin=('checklist_xlsx', id))`. Es el contrato que
   entrega el cambio 43.
2. **La consolidación no se decide en código.** El importador *propone* en un CSV; el usuario
   *decide*; `--execute` **exige** `--csv-in`.
3. **El denominador de avance se define por bandera de columna, nunca por literales de estado.** El
   vocabulario de un tenant no entra en el SQL genérico del roll-up.

---

## Decisiones de arquitectura

### D-TX · La transacción única se construye con `join_transaction_mode="create_savepoint"`, no pidiéndole al repositorio que deje de comitear

**El problema, verificado**: `TaskRepository.create` **comitea** (`tasks/repository.py:229-235`), igual
que `save` (`:237-242`). El requisito «Transacción única propiedad del caso de uso» de
`checklist-import` exige lo contrario: un fallo a mitad de corrida revierte todo y un `--dry-run` no
deja ni una fila. Con la sesión ordinaria, la primera tarea creada queda comiteada de forma
irreversible.

**Elección**: el importador **no** usa la sesión inyectada del `get_db` de la aplicación. Construye su
propia frontera:

```python
async with engine.connect() as connection:
    outer = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",   # conftest.py:99-105
        expire_on_commit=False,
    )
    try:
        # MISMO camino en los dos modos: en --dry-run las decisiones vienen de
        # las semillas (D-SEEDS); en --execute, del CSV revisado (D-CSV).
        report = await run_checklist_import(session, plan=plan, execute=execute)
        if execute and report.ok:
            await outer.commit()
        else:
            await outer.rollback()
    finally:
        await session.close()
```

Cada `session.commit()` que `TaskRepository.create` dispara **libera y reabre un SAVEPOINT**; la
transacción externa solo se cierra en un punto del código, exactamente con la semántica de
`run_maintenance` (`maintenance/runner.py:48-51`).

**Camino único de `--dry-run` (H1)**: `--dry-run` **no** es una rama corta que se detiene en el CSV.
Ejecuta la secuencia completa —parsear → mapear → aplicar las semillas de `seeds.py` → escribir el
CSV de consolidación → **ejecutar `importer.py` con esas decisiones sembradas dentro de la
transacción** → `rollback()`— y su reporte muestra los conteos que **se habrían escrito** (creadas,
actualizadas, fusionadas, contexto, omitidas), medidos sobre la base real, no estimados sobre el
archivo. Consecuencias, ambas normativas:

1. **`--dry-run` exige conexión a la base de datos.** Sin `--database-url` (o sin la variable de
   entorno equivalente) termina con el código de uso `1` (D-EXIT), igual que cualquier otro
   argumento faltante. Queda escrito en la tabla de la CLI y en el runbook.
2. **El reporte de `--dry-run` es comparable con el de `--execute`.** Es lo que hace exigible el
   requisito «Reporte de `--execute` muestra los conteos reales aplicados»: si el `--dry-run` no
   tocara la base, no podría distinguir «crear» de «ya existe» y sus conteos serían ficción.

El precio aceptado es que un `--dry-run` no corre contra una máquina sin base. La alternativa —un
`--dry-run` puramente offline— se rechaza porque produce exactamente el fallo del que este cambio
protege: un informe que promete 135 creaciones cuando la base ya tiene 130 de ellas ancladas.

| Alternativa | Por qué se rechaza |
|---|---|
| Quitar el `commit()` de `TaskRepository.create`/`save` | Cambio transversal a todo el módulo `tasks`: cada router y cada servicio que hoy depende de ese commit tendría que auditarse. Está fuera del alcance del 44 y rompería la línea base de pruebas de otros cambios en curso |
| Escribir las filas con un repositorio propio del importador, sin pasar por `create_task` | Viola el contrato del 43 (`toda-lectura-por-ancla…toda-escritura-por-create-task`, `state.yaml:100`) y duplicaría la validación de metodología, jerarquía, `assignee`, `sprint` y `task_number` |
| Aceptar commits parciales y compensar con un «deshacer» posterior | Un deshacer que corre después de un fallo es otro camino que también puede fallar; el requisito dice *rollback completo*, no *compensación* |

**Precedente**: es literalmente el patrón que `tests/conftest.py:88-110` usa para aislar cada prueba, con el
mismo comentario normativo («whatever the code under test does — including calling
`session.commit()` — only releases/reopens the SAVEPOINT»). No es una invención de este cambio.

### D-REV · Numeración sin reservas y gate de cabeza en vivo antes de escribir la migración

**Hecho verificado**: la cabeza en disco hoy es `0024_add_work_calendar.py`; no existen `0025` ni
`0026`. Un esquema anterior **reservaba `0026` al cambio 40** (planificado, sin `apply` en esta ola) y
fijaba `0027` con `down_revision="0026"`. Eso es un error: Alembic encadena por `down_revision`, y una
migración del 44 apuntando a una revisión que nadie ha escrito rompe `alembic upgrade head` con
«Can't locate revision identified by '0026'» **en despliegue**, no en revisión.

**Elección**: **no se reserva ningún número**. La cadena es consecutiva sobre lo que realmente
aterriza: `43 → 0025`; `44 → 0026` (`board_columns`, `down_revision="0025"`) y `0027` (`tasks`,
`down_revision="0026"`); `45a → 0028` (`down_revision="0027"`). El cambio 40, cuando le llegue su
propio `apply`, toma el **siguiente consecutivo libre en ese momento**, verificado igual que aquí.

**Gate, con los dos comandos que NO significan lo mismo (H14)**: la primera unidad de la rebanada A
es una compuerta ejecutada inmediatamente antes de escribir el archivo, y comprueba **dos cosas
distintas**:

| Comando | Qué lee | Qué debe devolver antes de escribir `0026` |
|---|---|---|
| `alembic heads` | El **directorio** `backend/alembic/versions/`: qué revisiones existen como archivo | `0025` como única cabeza (el archivo del 43 ya está en el repositorio) |
| `alembic current` | La **base de datos** objetivo: qué revisión tiene aplicada `alembic_version` | `0025` (el 43 ya migró esa base) |

Confundirlos es el error que el gate existe para impedir: `heads` puede decir `0025` con la base
todavía en `0024`, y entonces `0026` se escribiría contra una cadena que ese despliegue no tiene. Se
cuentan además las revisiones reclamadas por los cambios pendientes que aún no han escrito su archivo.

**Si hay que re-anclar** (la cabeza real no es `0025`), el mismo commit corrige el número, el
`down_revision` y **los tres deltas de spec** que quedan desalineados:

| Delta | Qué menciona hoy |
|---|---|
| `specs/boards/spec.md` | La revisión `0026` por su número (`:5`, `:20`, `:21`, `:26`) |
| `specs/tasks/spec.md` | Las revisiones `0026` y `0027` por su número (`:4`, `:25`, `:26`, `:31`, `:32`) |
| `specs/project-hierarchy/spec.md` | No cita números, pero su denominador **depende** de la bandera que entrega esa migración: si el par de revisiones cambia, su nota de dependencia se revisa en el mismo commit |

Re-anclar cuesta dos literales, un docstring y esas tres revisiones de texto.

**Justificación**: la alternativa —fijar `down_revision` desde el artefacto y confiar— es exactamente
el fallo que el 43 documentó al reanclar el 40 (`43/design.md`, «Unidad de artefactos»). Aquí no se
cita el encabezado de `0025` porque **ese archivo todavía no existe en disco**: el 43 está en
`apply: pending` y el gate D-REV es justamente lo que lo verifica en vivo. Un `down_revision`
inventado no rompe en la revisión: rompe en el despliegue.

### D-SEED · El sembrado de PANDORA y sus banderas viven en `maintenance/bootstrap.py`, no en el importador

**Elección**: `PANDORA_COLUMNS` se declara junto a `SEGURIDAD_COLUMNS` (`bootstrap.py:25-33`),
`bootstrap_sdmujer` llama `ensure_board_columns` también para `PAN`, y a continuación marca las
banderas con un método nuevo del adaptador,
`MaintenanceRepository.mark_columns_excluded_from_progress(board_id, status_keys)`. La invariante
nueva (`_i9_pandora_columns`) entra en `collect_invariants` (`invariants.py:37-49`). El importador
**no siembra columnas** y **no lleva `--ensure-boards`**.

| Alternativa | Por qué se rechaza |
|---|---|
| Sembrar desde el importador (`--ensure-boards`) | La invariante que la spec de `boards` exige debe reportarse «con código de salida distinto de cero en el script de mantenimiento que la evalúa» — es decir `purge_demo_data.py` vía `run_maintenance`. Con el sembrado fuera de `bootstrap`, `run_maintenance` quedaría **rojo en I9 en toda máquina donde el importador no haya corrido**, y `EXIT_INVARIANT_FAILED` (`purge_demo_data.py:53`) pasaría a ser el estado normal del 42 |
| Dos caminos de sembrado (bootstrap **y** importador) | Dos fuentes de literales para el mismo board: la primera divergencia de una tildes o de una mayúscula produce ocho columnas en vez de siete, y `ensure_board_columns` no puede distinguirlas porque compara `status_key` exacto |
| Una invariante fuera de `collect_invariants` | El gate de commit del runner es `all(result.passed for result in invariants)` (`runner.py:48`); una invariante que no está en esa tupla no bloquea nada |

**Consecuencia operativa** (queda en el runbook): el sembrado se aplica corriendo
`python -m scripts.purge_demo_data --execute --backup-file <pg_dump>` una vez. `--execute` exige el
respaldo verificado (`purge_demo_data.py:100-109`, código 1 si falta), y la purga es idempotente
sobre un alcance demo ya vacío.

**Banderas sin invariante propia**: las tres escenas del requisito «Banderas de exclusión en Removida
y Gestionada aparte» se cubren con pruebas sobre `bootstrap`, no con una I10. `collect_invariants` no
crece sin un requisito de spec que lo pida.

**Nota para `sdd-archive` (H18)**: `_i9_pandora_columns` **amplía el conjunto de invariantes que
describe la capacidad `data-maintenance`**, y esa spec está **archivada**. El 44 no la reabre: el
requisito que respalda la invariante vive en el delta de `boards` de este cambio (la invariante y su
código de salida distinto de cero en el script de mantenimiento). Al archivar el 44 debe registrarse
que `data-maintenance` queda con una invariante más de la que su texto publicado enumera, y que la
actualización de ese texto es **un delta futuro propio**, nunca una edición silenciosa de una spec
archivada. Es el mismo patrón de nota que el delta de `project-hierarchy` ya usa para la bala
obsoleta del estado `cancelled`.

### D-CTE · El roll-up necesita un `JOIN` **nuevo** a `BoardColumn`, y el `NULL` de `board_column_id` no puede excluir filas

**Corrección de un supuesto de la exploración**: §3.3 afirma que «el `JOIN` a `BoardColumn` ya está
ahí». No lo está para este propósito. El `JOIN` existente (`projects/repository.py:309-328`) une
`BoardColumn` a `Board` dentro de la subconsulta `last_status`, con `DISTINCT ON (board.project_id)`,
y solo expone la **última** `status_key` del tablero. La bandera que hace falta es la de la columna
**de cada tarea**, que exige un `outerjoin` nuevo sobre `BoardColumn.id == Task.board_column_id`.

**Elección**: `outerjoin` explícito con alias, y predicado tolerante al `NULL`:

```python
# projects/repository.py — reemplaza el literal `not_cancelled`, DEFINIDO en :330
# (`:329` está en blanco; la subconsulta `last_status` cierra en :328) y consumido
# en DOS sitios: :335 (término `total`) y :337 (término `done`).
task_column = aliased(BoardColumn, name="task_column")
# `board_column_id` es NULLABLE (tasks/models.py:83-88): una tarea sin columna NO se excluye.
# Con outerjoin, `not_(task_column.excluded_from_progress)` sería NULL -> filtra la fila.
in_denominator = sa.not_(
    sa.func.coalesce(task_column.excluded_from_progress, sa.false())
)
# Rebanada B añade el segundo término a ESTA misma expresión:
# in_denominator = sa.and_(in_denominator, Task.context_group.is_(None))

# H15 — `in_denominator` sustituye a `not_cancelled` en LOS DOS términos, no solo en `total`:
func.count(Task.id).filter(in_denominator).label("total"),
func.count(Task.id)
    .filter(in_denominator, Task.status == last_status.c.status_key)
    .label("done"),
```

**Los dos términos, no uno (H15)**: `not_cancelled` se consume hoy en `total` (`:335`) **y** en
`done` (`:337`), y `in_denominator` lo sustituye en ambos. Si solo se filtrara `total`, una tarea en
`Removida` que además fuera el último `status_key` del tablero saldría del denominador pero seguiría
sumando en el numerador, y un proyecto podría reportar `done > total`. El requisito de spec habla del
**denominador**, pero la corrección es aritméticamente inseparable del numerador: ambos cuentan sobre
el mismo conjunto de filas.

**Secuenciación A → B sin romper la suite intermedia**: A entrega solo el término de la bandera; B
añade el término de contexto a la misma expresión. La regla que lo hace seguro está escrita como
restricción de pruebas: **ninguna prueba de A puede fijar la forma del SQL ni la lista de términos
del filtro** — todas afirman conteos (`done`/`total`) sobre datos sembrados. Por eso el escenario
«Tareas de contexto excluidas del denominador» nace en B (RED) y no deja a A en rojo, y los tres
escenarios preexistentes del requisito (ejemplo de negocio, metodologías mixtas, aislamiento de
tenant) son **guardias** que deben seguir verdes en las dos rebanadas.

**Migración de datos: ninguna.** `excluded_from_progress` nace `NOT NULL DEFAULT false`, así que toda
columna existente entra al `upgrade` con el valor correcto. El estado final —`Removida` y
`Gestionada aparte` en `true`— lo fija el **sembrado idempotente** de D-SEED, no un `UPDATE` dentro de
la migración. Motivo: un `UPDATE ... WHERE status_key IN ('Removida','Gestionada aparte')` dentro de
`0026` marcaría esas columnas en **toda organización** de cualquier despliegue futuro, incluidas las
que usen esos rótulos con otro significado; y sería irreversible en el `downgrade` sin guardar el
estado previo. La bandera es configuración de tenant, no forma del esquema.

### D-COL · `context_group` y `merge_into_task_id` sin índice

**Elección**: ninguna de las dos columnas lleva índice, ni total ni parcial.

**Justificación**: `context_group` se consulta siempre como `IS NULL` dentro de una consulta ya
acotada por `Project.id IN (subtree)`; un índice parcial `WHERE context_group IS NOT NULL` sirve a la
selección **contraria** (la minoría) y ninguna consulta la hace. La exclusión del dashboard ni
siquiera llega al motor: `DashboardService` itera en Python una lista ya cargada por
`list_for_org` (`dashboard/service.py:79`). `merge_into_task_id` solo se lee por `id` de la fila que
lo contiene. Es la misma regla que el 43 aplicó para no indexar `source` por separado.
`ondelete="SET NULL"` sí crea la FK, con la misma forma que `parent_task_id`
(`tasks/models.py:72-76`).

### D-ERR · Errores tipados propios del importador, sin `AppException` y sin reutilizar los de Jira

**Elección**: `backend/app/importers/checklist/errors.py` con una jerarquía propia:
`ChecklistImportError` (base, con `code: str` y `row_id: str | None`) y las subclases
`ChecklistFileError`, `ChecklistSheetError`, `ChecklistHeaderError`, `ChecklistTooLargeError`,
`ChecklistRowError` (lleva siempre su `ID`) y `ChecklistConsolidationError`. La CLI las traduce a
códigos de salida.

| Alternativa | Por qué se rechaza |
|---|---|
| Reutilizar `integrations/adapters/jira/errors.py` | Acopla un importador de negocio al vocabulario de un conector (`jira_file_too_large`) y arrastra códigos HTTP a un proceso por lotes |
| Heredar de `AppException` | `AppException` lleva `status_code` (`shared/exceptions.py:20`), que en una CLI es un dato falso: no hay respuesta HTTP que devolver |

`ChecklistRowError` **siempre** transporta el `ID` de la fila: es lo que hacen exigibles D-DESC
(descripción > 4000) y los mensajes de validación del CSV.

### D-EXIT · Tabla definitiva de códigos de salida, alineada con la spec

**El problema, verificado (H2)**: el diseño traía una tabla (`2` = archivo no analizable, `3` = CSV
inválido) que **contradecía** el requisito «Contrato de la CLI `import_checklist.py`»
(`specs/checklist-import/spec.md:527`), donde `2` es la validación del CSV y `3` el error de base de
datos. Dos artefactos del mismo cambio no pueden fijar dos contratos de salida distintos: el que
manda es la spec.

**Elección**: la tabla de la spec, con el reparto explícito de cada error tipado de D-ERR.

| Código | Significado | Errores tipados que lo producen |
|---|---|---|
| `0` | Éxito (`--dry-run` o `--execute`) | — |
| `1` | **Uso o argumentos**: `--execute` sin `--csv-in`; `--dry-run` o `--execute` sin conexión a BD declarada (D-TX: `--dry-run` también la exige); `--file` inexistente; **XLSX no analizable** (hoja ausente, encabezado faltante o reordenado, guarda antibomba, bytes que no son XLSX); `Solicitante` que nombra a un miembro sin correo mapeado por `--member` (D-USERS) | `ChecklistFileError`, `ChecklistSheetError`, `ChecklistHeaderError`, `ChecklistTooLargeError` y los errores de `argparse` |
| `2` | **CSV de consolidación inválido**: fila sin decidir, `action` fuera del vocabulario cerrado, referencia a un `ID` inexistente, ciclo o anidamiento encadenado en `subtask_of:`, enlace entre proyectos, referencia a una fila `skip` o `merge_into:` (D-VAL), y **codificación no decodificable** (D-CSVIO) | `ChecklistConsolidationError` |
| `3` | **Error de conexión o de base de datos** antes o durante la corrida | Excepciones de conexión de SQLAlchemy/asyncpg |
| `4` | **Fallo de una fila individual** (descripción > 4000 caracteres, dato imposible de mapear) **o excepción inesperada** — en ambos casos la transacción ya quedó revertida | `ChecklistRowError` y cualquier `Exception` no clasificada |

**Por qué `1` absorbe el XLSX no analizable**: para el operador, un archivo que no se puede abrir es
del mismo género que una ruta equivocada —se corrige cambiando la invocación, no el contenido del
CSV—, y así lo enuncia el requisito publicado. El precio es que la causa exacta no viaja en el
código, sino en el mensaje tipado, que **siempre** nombra la hoja, el encabezado o el límite
incumplido.

**Distinguibilidad exigida por el escenario 68**: `2` (CSV) y `3` (base de datos) son los dos que el
escenario obliga a distinguir entre sí, y la prueba de la CLI los afirma por código, no por texto.

### D-CFG · Límites antibomba propios: `CHECKLIST_FILE_MAX_ROWS` / `CHECKLIST_FILE_MAX_CELLS`

**Elección**: dos ajustes nuevos en `app/config.py`, junto a `JIRA_FILE_MAX_ROWS`/`JIRA_FILE_MAX_CELLS`
(`config.py:249-250`), con valores propios y más ajustados (`10_000` / `200_000`). La guarda replica
`_guard_limits` (`jira/file_parser.py:70-76`): se evalúa **dentro** del bucle de `iter_rows`, de modo
que la iteración se detiene antes de materializar la hoja completa.

**Justificación**: reutilizar los de Jira ataría el techo de este importador a la afinación de un
conector ajeno; el día que alguien suba `JIRA_FILE_MAX_ROWS` para un export grande, movería en
silencio la guarda de un proceso que escribe en la base de producción.

### D-CSVIO · El CSV se escribe y se lee con `utf-8-sig`

**Elección**: `--csv-out` se escribe con `encoding="utf-8-sig"` (BOM) y `newline=""`; `--csv-in` se lee
con el mismo `utf-8-sig`, que descarta el BOM si está y no estorba si no está. Delimitador `,` (el de
`csv` por defecto); `csv.writer` entrecomilla solo lo que lo necesita, y `notes` casi siempre lo
necesita.

**Lectura tolerante, con techo explícito (H9)**: el CSV vuelve de Excel, y Excel puede haberlo
guardado en la página de códigos local. La lectura de `--csv-in` es, en este orden exacto:

1. `utf-8-sig`. Es el caso normal —es lo que el propio importador escribió—, y descarta el BOM.
2. Ante `UnicodeDecodeError`, **un solo reintento** con `cp1252` (la página de códigos que Excel usa
   en Windows en español) y una **advertencia** en el reporte que nombra la codificación usada, para
   que el operador sepa que su archivo no volvió como UTF-8.
3. Si `cp1252` tampoco decodifica, `ChecklistConsolidationError` tipado —**salida 2** (D-EXIT)—
   nombrando la codificación intentada y la posición del byte que falló. Nunca se decodifica con
   `errors="replace"`: una ñ convertida en `?` dentro de una nota de consolidación es una decisión
   del usuario corrompida en silencio, y este importador existe para lo contrario.

**Nota de configuración regional (va al runbook)**: en es-CO, Excel suele usar `;` como separador de
lista, así que un «Guardar como CSV» puede devolver un archivo que el `csv` estándar lee como **una
sola columna**. El runbook indica: guardar como **«CSV UTF-8 (delimitado por comas)»**, y para
abrirlo usar **Datos → Desde texto/CSV** eligiendo coma como delimitador y UTF-8 como origen, en vez
de un doble clic. La validación detecta el caso —una fila con menos de siete columnas es un CSV
inválido, salida `2`— y el mensaje lo dice con esas palabras.

**Justificación**: el CSV existe para que **el usuario lo abra en Excel** y decida. Sin BOM, Excel en
Windows interpreta el archivo en la página de códigos local y destruye las tildes y la ñ de los 27
valores de `area:` y de las notas. El precedente está en el repositorio: `jira/file_parser.py:87` ya
decodifica con `utf-8-sig`. Rechazado el delimitador `;` (más cómodo para Excel en español, pero
dependiente de la configuración regional y ajeno al `csv` estándar con el que se relee).

### D-SEEDS · Los valores por defecto del CSV son **datos versionados y advisorios**

**Elección**: los veredictos verificados de la exploración §1 viven en
`backend/app/importers/checklist/seeds.py` como una estructura de datos inmutable, no como `if` en
`consolidation.py`:

```python
@dataclass(frozen=True, slots=True)
class SeedDecision:
    action: str                 # "import" | "merge_into:T-05" | "subtask_of:T-77" | "context_group:…"
    note: str = ""              # SIEMPRE poblada cuando la acción no es evidente por sí sola

CONSOLIDATION_DEFAULTS: Final[Mapping[str, SeedDecision]] = { ... }
```

Dos propiedades obligatorias:

- **Advisoria, nunca autoritativa.** Para cada `ID` presente en el XLSX se aplica su semilla si
  existe; una semilla cuyo `ID` **no** aparece en la hoja produce una **advertencia** en el reporte,
  nunca un error. La hoja es un documento vivo (D-CNT) y una semilla obsoleta no puede tumbar un
  `--dry-run`.
- **No viola D-CNT.** D-CNT prohíbe *conteos esperados de filas*, no referencias a filas concretas.
  `CONSOLIDATION_DEFAULTS` no contiene ni un solo número de filas, y ninguna prueba afirma su
  tamaño.

**Cómo se prueban las semillas sin el archivo real (H10)**: los escenarios 41–45 afirman veredictos
sobre `ID` concretos (`T-81 → merge_into:T-05`, `T-23 → subtask_of:T-77`, el bloque PSPI, `T-74`
fuera de contexto, contradicciones como notas). Probarlos exige que esos `ID` **existan en la
entrada**, y el archivo institucional no entra al repositorio (guardia 73). La regla es:

- Las pruebas `K` de 41–45 construyen con `openpyxl` en `tmp_path` un **XLSX sintético** que incluye
  exactamente los `ID` que el escenario necesita —`T-23`, `T-74`, `T-81`, el rango `T-82…T-106` del
  bloque PSPI y `T-38`, `T-124`, `T-34`, `T-35`, `T-62`, `T-72` de las contradicciones— con
  **títulos, detalles y observaciones ficticios**. El `ID` es el único dato que importa para la
  aserción; el texto real no aporta nada y sí filtraría información institucional.
- Ese fixture es la única excepción al «6 a 10 filas» del escenario 74, que gobierna el fixture de
  **integración** (`I`), no el de semillas. Sigue sin violar D-CNT: ninguna prueba afirma cuántas
  filas tiene, solo que cada `ID` consultado recibe su veredicto.
- Las `note` de `CONSOLIDATION_DEFAULTS` **no reproducen texto institucional literal**. Son
  redacciones propias y cortas del criterio («la fuente deja la tarea abierta», «cobertura parcial»,
  «contradicción de fechas con `T-124`»), nunca una cita de la celda `Observaciones` del archivo
  real. Ese módulo sí entra al repositorio, así que es la superficie por la que el texto de la
  entidad podría colarse al historial de git sin que nadie lo note.

*Nota de nomenclatura*: el encargo pedía `seeds/consolidation_defaults.py`; hay exactamente una tabla
de semillas, así que se entrega como el módulo `seeds.py`. Si aparece una segunda, pasa a paquete sin
cambiar la superficie de importación.

### D-INTENT · Cuatro dataclasses congeladas marcan las fronteras del importador

```python
@dataclass(frozen=True, slots=True)
class ChecklistRow:      # parser.py — lo que el archivo DICE, verbatim
    row_number: int; id: str; estado: str; urgencia: str; categoria: str
    tarea: str; detalle: str; fecha_limite: str | date | datetime | None
    solicitante: str; apoyo_ia: str; observaciones: str

@dataclass(frozen=True, slots=True)
class RowIntent:         # mapping.py — lo que se PRETENDE escribir (puro, sin BD)
    external_key: str; project_code: str          # "SEG" | "PAN"
    status_key: str; priority: Priority; title: str; description: str
    # H19: SIEMPRE tz-aware en UTC. Nunca un datetime ingenuo.
    due_date: datetime | None; completed_at: datetime | None
    labels: tuple[str, ...]; solicitante: str

@dataclass(frozen=True, slots=True)
class Decision:          # consolidation.py — lo que el USUARIO decidió
    id: str; action: str; project: str; status: str
    labels: tuple[str, ...]; plan_links: tuple[str, ...]; notes: str

@dataclass(frozen=True, slots=True)
class PlannedWrite:      # importer.py — lo que se VA a hacer, ya resuelto
    intent: RowIntent; decision: Decision
    operation: str       # "create" | "update" | "skip" | "link_parent" | "link_merge"
```

**Justificación**: la frontera entre «lo que el archivo dice» y «lo que se pretende escribir» es
justo donde vive el riesgo de este cambio, y es la única forma de probar D y E **sin base de datos y
sin `@skip_no_db`**, como exige el criterio de aceptación de la propuesta. Congeladas para que una
etapa posterior no pueda mutar la conclusión de una anterior.

**Fechas con zona horaria, sin excepción (H19)**: `RowIntent.due_date` y `RowIntent.completed_at`
son **`datetime` tz-aware en UTC**. `openpyxl` con `data_only=True` devuelve `datetime` **ingenuos**
(sin `tzinfo`) para las celdas de fecha, y el texto ISO de la hoja tampoco trae zona; `mapping.py` es
el único punto donde se normaliza, con `.replace(tzinfo=UTC)` sobre la fecha civil declarada, y una
prueba pura lo afirma para las dos formas de celda (escenario 6). Un ingenuo que llegue hasta la base
produce dos fallos silenciosos: comparaciones `due_date < now()` que lanzan `TypeError` contra el
`datetime.now(UTC)` del dashboard (`dashboard/service.py:76`), y un `completed_at` histórico que
`_resolve_completed_at` guarda tal cual y que luego se lee como si fuera UTC sin serlo. La hoja
declara fechas civiles sin hora: se fija el inicio del día en UTC y se documenta que ese es el
criterio, en vez de inventar una conversión desde `America/Bogota` que la fuente nunca expresó.

### D-PASS · Orden de escritura: usuarios → tareas → enlaces, con los enlaces escritos directamente

**Elección**, dentro de la única transacción de D-TX:

1. `ensure_users` — los miembros declarados con `--member "Nombre=correo"` (D-USERS), creados con
   `hashed_password=None`, `is_active=True` y `OrganizationMember(role=viewer)`, reconciliados
   **por correo**; más la resolución de `admin@solercia.com` como responsable por defecto.
2. Resolución de lectura: proyectos `SEG`/`PAN` por `code`, sus boards y sus columnas.
3. **Pasada 1** — para cada fila decidida, en el orden del XLSX: `get_by_external_key` y, si devuelve
   `None`, `create_task(..., external_origin=('checklist_xlsx', id), completed_at_override=…)`. Las
   filas `merge_into:` se crean igual que cualquier otra, con `status="Removida"`.
4. **Pasada 2** — los cinco atributos que ningún esquema de la API expone: `parent_task_id`,
   `task_type`, `merge_into_task_id`, `context_group` y la nota de consolidación en `description`.
5. `ensure_label` + `assign_label`/`unassign_label` por tarea (D-LBL-IO, D-UPD).
6. Invariantes de corrida e informe; `commit()` solo si `execute` y no hubo error.

**Por qué la pasada 2 escribe el atributo directamente**: `TaskUpdate` **no declara**
`parent_task_id` (`tasks/schemas.py:62-82`), así que no existe camino de servicio para enlazar
después. Y `create_task` exige que el padre ya exista y esté en el mismo proyecto
(`service.py:282-290`), lo que impide enlazar en la pasada 1 cuando el hijo precede al padre en la
hoja. El requisito de spec ordena explícitamente dos pasadas, así que la 2 escribe sobre la entidad
ORM dentro de la transacción del importador, replicando el resultado que `_resolve_child_type` daría
para un padre que no es épica (`service.py:345-366`, rama «cualquier otro padre → `subtask`»). El
importador nunca crea épicas ni asigna `estimation_points`, así que las otras dos reglas de esa
función son vacuas aquí y quedan documentadas como tales.

**Los cinco atributos de la pasada 2, y su regla de no-op (H11)**: la pasada 2 no es «el enlace de
padres»; es **todo lo que la API no puede escribir**. Se enumeran para que ninguna quede implícita:

| Atributo | Origen | Regla de no-op en reejecución |
|---|---|---|
| `parent_task_id` | `subtask_of:T-xx` | Si ya apunta a esa misma tarea, no se asigna |
| `task_type` | Derivado del anterior (`"subtask"`) | Si ya es `"subtask"`, no se asigna |
| `merge_into_task_id` | `merge_into:T-xx` | Si ya apunta a esa misma superviviente, no se asigna |
| `context_group` | `context_group:<nombre>` | Si ya es ese mismo nombre, no se asigna |
| `description` | La nota «Consolidada en `SEG-N` (T-xx)», que solo puede escribirse aquí porque `SEG-N` (el `task_key` de la superviviente) no existe hasta después de la pasada 1 | Si la descripción ya termina con esa nota exacta, no se reescribe |

**La nota cuenta para el límite de 4000 (D-DESC)**: la longitud que se verifica es la de la
descripción compuesta **más** la nota de consolidación, medida antes de escribir; si el total supera
4000 caracteres, la fila falla con su `ID` (`ChecklistRowError`, salida `4`) y **nunca** se trunca.
Verificarla solo en el mapeo dejaría pasar filas que revientan al enlazarse.

**Auditoría e historial**: la pasada 2 fija `task.updated_by = actor_id`, como cualquier mutación del
sistema, y **no** registra `TaskHistory`. No es una omisión: `_HISTORY_TRACKED_FIELDS`
(`service.py:387-394`) es exactamente `("status", "assignee_id", "estimation_points",
"estimation_hours", "sprint_id", "priority")`, y **ninguno** de los cinco atributos de esta pasada
está en esa tupla. El servicio, por el camino de la API, tampoco registraría nada para ellos:
escribir filas de historial aquí produciría entradas que la aplicación nunca genera y que el frontend
de actividad no sabe renderizar. Si algún día `parent_task_id` entra a esa tupla, esta pasada la
sigue por el mismo `_record_history_diff` (`service.py:510-535`) y no por una copia propia.

**Rechazado**: ordenar topológicamente y crear con `TaskCreate(parent_task_id=…)` en una sola pasada.
Es técnicamente posible (el grafo es acíclico, lo garantiza la validación de E) y usaría el camino
legítimo, pero contradice el requisito «Enlace de subtareas en dos pasadas», que es texto de spec.

**Cruce de proyectos**: `merge_into:` y `subtask_of:` **no pueden cruzar** SEGURIDAD y PANDORA. Se
rechaza en la validación de E, **antes de escribir**, usando la función pura de ruteo de `mapping.py`
(no hace falta base de datos para saber a qué proyecto va una fila). Un enlace cruzado sería un
`invalid_parent_task` 422 en mitad de la corrida, es decir un rollback completo por un dato que se
podía ver en el CSV.

### D-UPD · `--update-existing` reconcilia cuatro campos; `completed_at` solo se deriva, nunca se sobrescribe

**Elección**: la lista blanca operativa es `status`, `priority`, `due_date` y las etiquetas derivadas,
aplicadas con `TaskService.update_task(TaskUpdate(...))`. `completed_at` **no** se escribe
directamente: `update_task` ya lo deriva al mover de columna, y lo hace conservando el valor previo
(`task.completed_at = self._resolve_completed_at(strategy, task.status, task.completed_at)`,
`service.py:440-442`, con `current or datetime.now(UTC)` en `:862-863`). Es decir: la fecha histórica
que la creación fijó con `completed_at_override` **sobrevive** a cualquier `--update-existing`.

**Caso residual y su tratamiento**: una tarea importada abierta que en una corrida posterior cierra, y
cuyas `Observaciones` traen «CERRADA el YYYY-MM-DD», recibiría `now()` en vez de la fecha histórica.
El importador **no la sobrescribe**: emite una **advertencia** en el reporte con el `ID` y las dos
fechas.

**Cómo se reconcilian las etiquetas, y cuáles NUNCA se retiran (H4)**: «reconciliar etiquetas» no es
un campo de `TaskUpdate` —`TaskUpdate` no las declara— sino una operación aparte sobre `TaskLabel`:

1. Se calcula el conjunto **derivado** que la fila del XLSX produce hoy (D-LBL, D-PSPI, D-REC).
2. Para cada etiqueta de ese conjunto: `ensure_label` (D-LBL-IO) y luego `assign_label`, que es
   idempotente (`labels/service.py:120-122`).
3. Para retirar, `unassign_label` (`labels/service.py:125`), **y solo sobre etiquetas derivadas**,
   reconocidas por su forma: `area:*`, `apoyo-ia:*`, `recurrente` y `pspi:*`.

Una etiqueta que el usuario agregó a mano en la aplicación —`bloqueada`, `revisar-con-juridica`,
cualquier nombre fuera de esos cuatro patrones— **nunca** se retira, aunque no esté en el conjunto
derivado. El importador no sabe nada de ella y no tiene autoridad para borrarla; borrarla sería el
mismo fallo que sobrescribir un título editado, con la agravante de ser invisible en el reporte si no
se cuenta. El reporte enumera cada `unassign_label` aplicado, con `ID` y nombre.

**Idempotencia real de `--update-existing` (H17)**: antes de invocar `update_task`, el importador
**compara** los valores destino (`status`, `priority`, `due_date`) con los de la tarea ya anclada, y
el conjunto derivado de etiquetas con el conjunto actual. Si no hay diferencia, **no llama a
`update_task`** y cuenta la fila como «sin cambios». Es lo que hace verdadero el escenario 52
(«segunda corrida idéntica reporta cero cambios») incluso con `--update-existing`: `update_task`
escribe `updated_at` y `updated_by` en cada invocación y, cuando `status` cambia, registra
`TaskHistory` (`service.py:501-509`), así que llamarlo «por si acaso» produciría 135 mutaciones de
auditoría y un historial lleno de cambios que nadie hizo. La comparación es la única forma de que
«0 actualizadas» signifique de verdad que nada se tocó.

| Alternativa | Por qué se rechaza |
|---|---|
| Añadir `completed_at_override` también a `update_task` | Amplía el alcance más allá del delta de `tasks`, que solo pide el parámetro en `create_task`, y agrega una segunda superficie de escritura de un campo que D-INM del 43 mantiene deliberadamente cerrada |
| Escribir `task.completed_at` a mano tras el `update_task` | Es exactamente el «`UPDATE` posterior» que D8 rechazó: abre una ventana en la que la fila ya es visible con `completed_at = now()` |
| Meter `completed_at` en la lista blanca y no advertir nada | Deriva silenciosa entre la hoja y la base — el fallo del que este cambio existe para proteger |

Los tres escenarios del requisito («título editado se conserva», «status se actualiza», «etiquetas se
reconcilian») quedan cubiertos: la lista blanca de la spec es una **cota superior**, no un mandato de
escribir los cinco campos.

**Advertencia operativa que el runbook DEBE llevar (H21)**: con `--update-existing`, **el XLSX manda
sobre el `status`**. Una tarea que el equipo completó en la aplicación pero que en la hoja sigue
`PENDIENTE` vuelve a «Sin iniciar» en la siguiente corrida, y con ella se pierde su `completed_at`
derivado. No es un defecto: es la semántica pedida —la hoja es la fuente— pero es exactamente el
tipo de sorpresa que arruina la confianza en un importador. El runbook lo dice con esas palabras y
recomienda `--update-existing` solo cuando la hoja se acaba de actualizar contra la realidad; sin la
bandera, una tarea ya anclada es intocable.

### D-LBL-IO · `ensure_label` busca sin filtro de estado y **reactiva** antes de crear

**El problema, verificado (H5)**: `uq_labels_project_name` (`labels/models.py:30`) es un
`UniqueConstraint("project_id", "name")` **total**, sin `postgresql_where`. Una etiqueta borrada de
forma lógica —el proyecto usa borrado lógico universal: `is_active`, `deleted_at`— **sigue ocupando
el nombre**. Un `ensure_label` que buscara con `is_active.is_(True)` no la encontraría, intentaría
crearla y recibiría un `IntegrityError` que, dentro de la frontera de D-TX, aborta la corrida entera
por una etiqueta que ya existía.

**Elección**: `ensure_label(project_id, name)` hace, en este orden:

1. `SELECT` por `(project_id, name)` **sin ningún filtro de `is_active` ni de `deleted_at`**.
2. Si la fila existe y está inactiva, la **reactiva** (`is_active=True`, `deleted_at=None`) y la
   devuelve.
3. Si la fila existe y está activa, la devuelve tal cual.
4. Solo si no existe, la crea.

**Prueba de apoyo** (rebanada F): `test_ensure_label_reactivates_a_soft_deleted_label_instead_of_creating`.

**Rechazado**: capturar el `IntegrityError` y reintentar. Dentro de una transacción con SAVEPOINT,
un error de integridad invalida el savepoint activo y obliga a un `rollback` parcial cuyo alcance es
justo lo que este diseño se propuso hacer explícito; buscar bien cuesta una condición menos.

### D-VAL · `validate()` cierra dos huecos más del grafo de decisiones

**Elección (H6)**: además de las cuatro reglas ya escritas (toda fila decidida, toda referencia
existente, sin ciclos, sin enlaces entre proyectos), `validate()` rechaza **antes de escribir**:

| Regla nueva | Qué rechaza | Por qué |
|---|---|---|
| **Anidamiento encadenado** | `A → subtask_of:B` cuando `B` es a su vez `subtask_of:C` | El servicio no admite sub-subtareas: `_resolve_child_type` lanza 422 `subtask_nesting_not_allowed` (`service.py:361-366`). El CSV usa **el mismo código de error** en su mensaje, para que el operador reconozca la regla del producto y no crea que es una limitación del importador. Detectarlo en el CSV evita un rollback total a mitad de la pasada 2 |
| **Referencia a una fila que no sobrevive** | `merge_into:`/`subtask_of:` que apunta a una fila decidida como `skip`, o a una fila que a su vez es `merge_into:` | Apuntar a una fila `skip` produce una referencia a una tarea que nunca se crea; apuntar a una fusionada crea una cadena `A → B → C` en la que `A` queda colgando de una tarea que ya está en `Removida`. Ambos casos son visibles en el CSV y no requieren base de datos |

**Dos pruebas de apoyo** (rebanada E, puras, sin BD):
`test_chained_subtask_of_is_rejected_with_the_service_error_code` y
`test_reference_to_a_skipped_or_merged_row_is_rejected_before_any_write`.

**Rechazado**: resolver la cadena automáticamente (colapsar `A → B → C` en `A → C`, o redirigir a la
superviviente). Es exactamente la clase de decisión que D-CSV le devuelve al usuario: el importador
propone y valida, no adivina qué quiso decir el CSV.

### D-USERS · Los correos institucionales **nunca** entran al repositorio: llegan por `--member`

**El problema (H8)**: el diseño y la spec nombran a dos personas reales de una entidad pública. Si
sus correos se escriben en `seeds.py`, en `importer.py` o en una prueba, quedan en el historial de
git para siempre —el mismo fallo que la guardia 73 impide para el XLSX, por una puerta más pequeña.

**Elección**: la CLI acepta `--member "Nombre Apellido=correo@dominio"`, **repetible**, y esa es la
única fuente de la correspondencia nombre → correo.

- `ensure_users` crea o reconcilia **solo** los miembros declarados por `--member`, por correo.
- Si el CSV o el XLSX asigna una fila a un nombre que **no** tiene correo mapeado, el importador
  termina con **salida `1`** (D-EXIT, argumento faltante) nombrando el nombre sin mapear, y no
  escribe nada. No se inventa un correo derivando del nombre y no se cae silenciosamente al
  responsable por defecto: `admin@solercia.com` es el destino de un `Solicitante` **no reconocible**
  (texto libre, cargo, área), no de una persona que el operador olvidó declarar.
- El repositorio contiene, como mucho, el **nombre** de la persona en un ejemplo de la ayuda de la
  CLI; los valores reales viven en el runbook operativo, fuera del repositorio, y en la invocación.
- Las pruebas usan correos ficticios de dominio de ejemplo.

**Rechazado**: un archivo de configuración versionado (`members.yaml`). Mueve el problema de sitio
sin resolverlo —sigue siendo el repositorio— y añade un formato más que mantener.

### D-BADGE-UI · La insignia **compone** el `sol-badge` de `@solercia/ui` y vive en `entities/task/ui/`

**Corrección de dos afirmaciones falsas del diseño anterior (H3)**: (1) decía que no existía
ningún componente de insignia, citando una búsqueda `*badge*` con «cero resultados»; existe
`SolBadgeComponent` en `@solercia/ui`, y lo consume medio frontend, incluido el propio
`task-detail-panel` (`:30`, `:67`, `:265`). (2) ubicaba el componente en
`frontend/src/shared/ui/`, que **no aloja componentes**: es un barril puro de una sola línea
(`export * from '@solercia/ui'`, `shared/ui/index.ts:1-14`) y su comentario normativo dice que el
`sol-drawer` app-local se eliminó precisamente para no duplicar símbolos por ese barril.

**Elección**: `frontend/src/entities/task/ui/origin-badge/origin-badge.component.ts` — standalone,
entradas `source` y `externalKey`, sin `output`, sin `click`, sin `routerLink`, y **componiendo** el
componente de la librería:

```html
@if (externalKey()) {
  <sol-badge variant="neutral" size="sm" [attr.aria-label]="originAria()">
    {{ externalKey() }}
  </sol-badge>
}
```

Se renderiza en los dos sitios donde hoy se muestra el `task_key`: la tabla de trabajo
(`widgets/project-workspace/project-workspace.component.ts:285-291`) y el detalle
(`widgets/task-detail-panel/task-detail-panel.component.ts:93-95`).

**Por qué `entities/task/ui/` y no `shared/ui/`**: por FSD, la insignia conoce el vocabulario de la
entidad `task` (`source`, `external_key`), así que no es un átomo compartido: es una pieza de esa
entidad. `entities/task/` ya existe (`task-detail.model.ts`, `task-detail.service.ts`); este
componente estrena el subdirectorio `ui/` allí, que es el sitio que FSD reserva para presentación
propia de la entidad. `shared/ui/` queda como lo que es hoy: un puente al design system.

**Por qué componer y no pintar un `<span>`**: el tono, el radio, la tipografía y el contraste en tema
claro y oscuro los resuelve `sol-badge` con los tokens de la librería. Un `<span>` propio los
reimplementa y se desincroniza en la primera versión de `@solercia/ui`.

**Descartado**: `widgets/task-modal/task-modal.component.ts` — no renderiza `task_key`, así que no hay
dónde colgar la insignia; y la tarjeta de tablero (`project-workspace.component.ts:994-1002`) muestra
un botón «abrir detalle», no la clave.

**Checklist `ux-psicologia` aplicado (gate obligatorio antes de cerrar B)**:

| Regla | Cómo la cumple |
|---|---|
| Nada arranca vacío | La insignia **no existe** cuando `external_key` es nulo; nunca se pinta un contenedor vacío ni un guion de relleno |
| Los 5 estados | La insignia es una hoja presentacional sin carga de datos propia: no introduce estados de cargando/vacío/error nuevos. Los cinco estados siguen siendo responsabilidad de las dos pantallas anfitrionas, que ya los tienen |
| No confundir «sin dato» con «falló» | Ausencia de insignia significa «tarea creada a mano», y esa lectura se documenta en el texto de ayuda, no se deja a la inferencia |
| Accesibilidad | `aria-label` con el sistema de origen y la clave («Origen: checklist_xlsx T-05»), a través del mismo canal `text.*` que ya usan las dos plantillas anfitrionas |
| Contraste y tema | Los resuelve `sol-badge` con los tokens de `@solercia/ui` (`variant="neutral"`, `size="sm"`); no se declara ni un color propio. Se verifica en tema claro y oscuro |

---

## Estructura de módulos

| Archivo | Acción | Rebanada |
|---|---|---|
| `backend/alembic/versions/0026_add_board_column_progress_flag.py` | Crear | A |
| `backend/app/modules/boards/models.py` | Modificar · 1 columna | A |
| `backend/app/modules/projects/repository.py:290-350` | Modificar · CTE del roll-up | A |
| `backend/app/maintenance/bootstrap.py` | Modificar · `PANDORA_COLUMNS` + banderas | A |
| `backend/app/maintenance/repository.py` | Modificar · `mark_columns_excluded_from_progress` | A |
| `backend/app/maintenance/invariants.py` | Modificar · `_i9_pandora_columns` | A |
| `backend/alembic/versions/0027_add_task_context_and_merge.py` | Crear | B |
| `backend/app/modules/tasks/models.py` | Modificar · 2 columnas | B |
| `backend/app/modules/tasks/schemas.py` | Modificar · 2 campos en `TaskRead` | B |
| `backend/app/modules/dashboard/service.py` | Modificar · `_build_by_assignee`, `_build_workload`, `_build_totals` | B |
| `frontend/src/entities/workspace/workspace.model.ts` | Modificar · 2 campos | B |
| `frontend/src/entities/task/ui/origin-badge/origin-badge.component.ts` | Crear · compone `sol-badge` | B |
| `frontend/src/widgets/{project-workspace,task-detail-panel}/*.component.ts` | Modificar · 2 usos | B |
| `backend/app/modules/tasks/service.py:252-335` | Modificar · `completed_at_override` | C |
| `backend/app/config.py` | Modificar · 2 ajustes antibomba | D |
| `backend/app/importers/checklist/{__init__,errors,parser,mapping}.py` | Crear | D |
| `backend/app/importers/checklist/{seeds,consolidation}.py` | Crear | E |
| `backend/app/importers/checklist/{importer,report}.py` | Crear | F |
| `backend/scripts/import_checklist.py` | Crear | G |

### Migración `0026_add_board_column_progress_flag.py`

```python
"""add_board_column_progress_flag

Revision ID: 0026
Revises: 0025        # D-REV: verificar `alembic heads` EN VIVO antes de fijarlo.
                     # Debe ser 0025 (cambio 43 aplicado). Sin números reservados:
                     # si la cabeza real es otra, se re-ancla número y padre, y el
                     # delta de boards se corrige en el mismo commit.

Cambio 44 (design.md D-CTE/D-SEED). Estrictamente aditiva y SIN backfill: la
columna nace NOT NULL DEFAULT false, así que toda fila existente entra con el
valor correcto. Marcar `Removida`/`Gestionada aparte` NO es trabajo de esta
migración: es configuración de tenant y la aplica el sembrado idempotente de
`maintenance/bootstrap.py` (design.md D-SEED).
"""

def upgrade() -> None:
    op.add_column(
        "board_columns",
        sa.Column(
            "excluded_from_progress",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

def downgrade() -> None:
    op.drop_column("board_columns", "excluded_from_progress")
```

Espejo en `BoardColumn` (`boards/models.py`, tras `wip_limit`, `:73`):

```python
# Cuando es true, TODA tarea asignada a esta columna queda fuera del
# DENOMINADOR del roll-up de avance (projects/repository.py rollup_progress,
# cambio 44). Bandera por columna y no literales de estado en el SQL genérico:
# el vocabulario de un tenant nunca entra al roll-up (design.md D6 del 44).
excluded_from_progress: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default=sa.false(), default=False
)
```

> **Gotcha verificado**: en esta tabla `order` se mapea al nombre físico `column_order`
> (`boards/models.py:69-71`). La invariante y el sembrado ordenan por `BoardColumn.order`, nunca por
> un literal `"order"`.

### Sembrado y banderas de PANDORA (`maintenance/bootstrap.py`)

```python
# Literal, status_key verbatim, "Done" ÚLTIMA (cambio 44, D4): allowed_statuses()[-1]
# es el estado de cierre y de él dependen _resolve_completed_at y el término
# `done` del roll-up.
PANDORA_COLUMNS: tuple[str, ...] = (
    "Backlog", "Doing", "Diferida", "Recurrente",
    "Gestionada aparte", "Removida", "Done",
)
# Fuera del denominador de avance en AMBOS proyectos (D2). `Diferida` y
# `Recurrente` NO están aquí: cuentan como pendientes, tal como comprometió
# data-maintenance/spec.md:142.
EXCLUDED_FROM_PROGRESS_COLUMNS: tuple[str, ...] = ("Removida", "Gestionada aparte")
```

`bootstrap_sdmujer` repite para `PAN` el bloque que hoy solo corre para `SEG`
(`bootstrap.py:76-81`) y añade, para los dos boards,
`await repo.mark_columns_excluded_from_progress(board_id, EXCLUDED_FROM_PROGRESS_COLUMNS)`. Ese
método vive en el adaptador, hace un `UPDATE` acotado por `board_id` y `status_key IN (...)`, es
idempotente y devuelve cuántas filas cambió. Sigue sin `commit`: el dueño de la transacción es
`runner.py`.

Invariante nueva, con la forma de `_i4_seguridad_columns` (`invariants.py:101-125`):

```python
async def _i9_pandora_columns(session) -> InvariantResult:
    """PANDORA tiene exactamente 7 columnas, en orden, verbatim, Done la última."""
    # keys = [status_key ORDER BY column_order ASC]  (mismo SELECT que _i4)
    passed = tuple(keys) == PANDORA_COLUMNS
```

La comparación es de **tupla completa**, no `len(keys) == 7 and keys[-1] == "Done"`: eso cubre en una
sola aserción el conteo, el orden, la posición final de `Done` y el `status_key` **verbatim** (un
`"diferida"` slugificado por `BoardService.add_column` rompe la igualdad).

### Migración `0027_add_task_context_and_merge.py`

```python
"""add_task_context_and_merge — Revision 0027, Revises 0026.

Cambio 44 (design.md D-COL). Aditiva, ambas columnas NULLABLE, sin backfill.
`merge_into_task_id` replica la forma exacta de `parent_task_id`
(tasks/models.py:72-76): auto-FK a tasks.id con ondelete="SET NULL".
Sin índice en ninguna de las dos (design.md D-COL).
"""

def upgrade() -> None:
    op.add_column("tasks", sa.Column("context_group", sa.String(length=80), nullable=True))
    op.add_column("tasks", sa.Column("merge_into_task_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_merge_into_task_id", "tasks", "tasks",
        ["merge_into_task_id"], ["id"], ondelete="SET NULL",
    )

def downgrade() -> None:
    op.drop_constraint("fk_tasks_merge_into_task_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "merge_into_task_id")
    op.drop_column("tasks", "context_group")
```

Espejo en `Task` y exposición de solo lectura:

```python
# tasks/models.py
# NOT NULL = "esta tarea es de contexto"; el valor es el nombre del grupo
# (cambio 44, D5). NO tiene relación alguna con el `is_context` TRANSITORIO de
# TaskRead (schemas.py:149-153), que es un artefacto de paginación bajo el
# filtro assignee_id y sigue intacto.
context_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
merge_into_task_id: Mapped[uuid.UUID | None] = mapped_column(
    Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
)

# tasks/schemas.py — SOLO en TaskRead. TaskCreate y TaskUpdate NO se tocan.
context_group: str | None = None
merge_into_task_id: uuid.UUID | None = None
```

### `completed_at_override` en `create_task` (rebanada C)

```python
async def create_task(
    self, organization_id, project_id, data: TaskCreate, *,
    actor_id: uuid.UUID | None = None,
    external_origin: tuple[str, str] | None = None,      # cambio 43
    completed_at_override: datetime | None = None,       # cambio 44, D8
) -> TaskRead: ...

# Reemplaza `completed_at=self._resolve_completed_at(strategy, status, None)` (:328):
completed_at=self._resolve_completed_at(strategy, status, completed_at_override),
```

**Una sola línea, y es exacta**: `_resolve_completed_at` ya devuelve `current or datetime.now(UTC)`
**solo** cuando `status == allowed[-1]` (`service.py:854-864`). Pasar el override como `current`
produce literalmente el comportamiento que la spec pide —se aplica en el estado de cierre, se ignora
en cualquier otro— sin una sola rama nueva. `TaskCreate` y `router.py` no cambian, así que el
parámetro es inalcanzable por HTTP; una prueba pura lo afirma sobre la firma del router.

### `backend/app/importers/checklist/` — responsabilidades

| Módulo | Entra | Sale | BD |
|---|---|---|---|
| `parser.py` | `Path` del XLSX | `tuple[ChecklistRow, ...]` | No |
| `mapping.py` | `ChecklistRow` | `RowIntent` | No |
| `seeds.py` | — | `CONSOLIDATION_DEFAULTS` | No |
| `consolidation.py` | `RowIntent` + `Path` del CSV (escribe en `--dry-run`, lee y valida en `--execute`) | `tuple[Decision, ...]` validadas | No |
| `importer.py` | `session` + intenciones + decisiones | `ChecklistReport` | Sí, dueño de la transacción · **corre en LOS DOS modos** (D-TX/H1) |
| `report.py` | `ChecklistReport` | texto formateado | No |
| `errors.py` | — | jerarquía tipada | No |

**Sobre la columna «BD» (H1)**: «No» significa que ese módulo es puro y probable sin base, no que el
modo `--dry-run` pueda prescindir de ella. `importer.py` es el único que toca la base, y **lo hace en
los dos modos**: en `--dry-run` con las decisiones sembradas y terminando en `rollback()`. Un
`--dry-run` que no llegara a `importer.py` no podría distinguir «crear» de «ya existe».

`parser.py` sigue el molde de `jira/file_parser.py:109-148`: `load_workbook(read_only=True,
data_only=True)` dentro de un `try/except Exception → error tipado`, `sheet = workbook["Checklist
Tareas"]` con `KeyError → ChecklistSheetError`, validación de los 11 encabezados en orden,
`_guard_limits` dentro del bucle y `finally: workbook.close()`.

### CLI `backend/scripts/import_checklist.py`

Calcada de `purge_demo_data.py`: `import app.db_init` antes de nada (`purge_demo_data.py:43`), engine
propio con `dispose()`, `redact_database_url` reutilizado, `--dry-run` por defecto.

| Bandera | Obligatoriedad | Nota |
|---|---|---|
| `--file` | Obligatoria | Ruta al XLSX real, fuera del repositorio |
| `--dry-run` | Por defecto | **Exige conexión a base de datos** (D-TX/H1): recorre el camino completo y termina en `rollback()` |
| `--csv-out` | Opcional | Por defecto `checklist_consolidation.csv` |
| `--execute` | Opcional | **Exige `--csv-in`** |
| `--csv-in` | Obligatoria con `--execute` | CSV revisado por el usuario |
| `--update-existing` | Opcional | Lista blanca de D-UPD; el XLSX manda sobre `status` |
| `--member "Nombre=correo"` | **Repetible** | Única fuente de la correspondencia nombre → correo (D-USERS). Cero correos en el repositorio |
| `--database-url` | Obligatoria en ambos modos | Se imprime siempre redactada (`redact_database_url`) |

Códigos de salida — la tabla vive en **D-EXIT** y es la de la spec (`1` uso o argumentos, incluido el
XLSX no analizable; `2` CSV inválido, incluida la codificación; `3` conexión o base de datos; `4`
fallo de fila o excepción inesperada). Aquí no se repite para que no vuelvan a divergir.

---

## Flujo de datos

**Un solo camino, dos orígenes de decisiones y dos finales** (D-TX/H1). Lo único que cambia entre
`--dry-run` y `--execute` es de dónde salen las decisiones y si la transacción externa se comitea:

```
CHECKLIST_TAREAS.xlsx ─▶ parser.py ─▶ mapping.py ─▶ ┌── DECISIONES ──┐
   (fuera del repo)      ChecklistRow   RowIntent   │                │
                          (sin BD)      (sin BD)    │                │
                                                    │                │
        --dry-run (por defecto) ────────────────────┤ seeds.py       │  y ADEMÁS escribe
                                                    │ (advisorio)    │  checklist_consolidation.csv
                                                    │                │        │
        --execute --csv-in ─────────────────────────┤ consolidation. │        ▼
                                                    │ read()         │  EL USUARIO DECIDE
                                                    └────────┬───────┘  (y reinvoca con --execute)
                                                             ▼
                                          consolidation.validate()  ── falla ──▶ salida 2,
                                             │ toda fila decidida                CERO escrituras
                                             │ toda referencia existe
                                             │ sin ciclos ni anidamiento encadenado (D-VAL)
                                             │ sin referencias a skip/merge_into (D-VAL)
                                             │ sin enlaces entre proyectos
                                             ▼
                         importer.py — UNA transacción (D-TX, SAVEPOINT)
                              ── LOS DOS MODOS ENTRAN AQUÍ ──
                                             │
   ensure_users ─▶ resolver SEG/PAN ─▶ pasada 1 ─▶ pasada 2 ─▶ etiquetas ─▶ report
   (--member)                                │           │
              get_by_external_key(org,'checklist_xlsx',T-xx)  parent_task_id · task_type
                       │        └─ None ─▶ create_task(..., external_origin=,   merge_into_task_id
                       │                                completed_at_override=)  context_group
                       └─ Task ─▶ sin --update-existing: intacta                 nota en description
                                  con --update-existing: compara y, solo si difiere,
                                  status/priority/due_date/etiquetas derivadas
                                             │
        --execute y sin error ─▶ outer.commit()   │   --dry-run o cualquier fallo ─▶ rollback()
                                                  │
        el reporte de --dry-run muestra los conteos que SE HABRÍAN escrito ◀────┘
```

Efecto de A y B sobre las lecturas ya publicadas:

```
GET /projects/{id}/progress ─▶ rollup_progress   AMBOS términos (done y total, H15):
                                                   MENOS columna.excluded_from_progress   (A)
                                                   MENOS context_group IS NOT NULL        (B)

GET /dashboard/executive ──▶ _build_by_assignee ─┐ excluyen context_group IS NOT NULL     (B)
                            _build_workload     ─┤  (H7: by_assignee y workload cuentan
                            _build_totals.tasks ─┘   lo mismo; discrepar era el defecto)
                            _build_at_risk           ─── NO excluye: una vencida es una vencida
                            totals.overdue/at_risk   ─── NO excluyen: espejan la lista at_risk
                            _build_projects_progress ─── sin cambio en este delta
```

---

## Cambios de archivos

| Archivo | Acción | Descripción |
|---|---|---|
| `backend/alembic/versions/0026_add_board_column_progress_flag.py` | Crear | `board_columns.excluded_from_progress`; `down_revision="0025"`, confirmado por el gate D-REV |
| `backend/alembic/versions/0027_add_task_context_and_merge.py` | Crear | `tasks.context_group` + `tasks.merge_into_task_id` + auto-FK; `down_revision="0026"` |
| `backend/app/modules/boards/models.py` | Modificar | 1 columna espejada |
| `backend/app/modules/projects/repository.py` | Modificar | `outerjoin` a `BoardColumn` + `in_denominator` (A) y término de contexto (B) |
| `backend/app/maintenance/bootstrap.py` | Modificar | `PANDORA_COLUMNS`, `EXCLUDED_FROM_PROGRESS_COLUMNS`, sembrado de `PAN` y marcado en ambos |
| `backend/app/maintenance/repository.py` | Modificar | `mark_columns_excluded_from_progress` |
| `backend/app/maintenance/invariants.py` | Modificar | `_i9_pandora_columns` en `collect_invariants` |
| `backend/app/modules/tasks/models.py` | Modificar | 2 columnas + auto-FK espejada |
| `backend/app/modules/tasks/schemas.py` | Modificar | 2 campos en `TaskRead`; `TaskCreate`/`TaskUpdate` intactos |
| `backend/app/modules/tasks/service.py` | Modificar | `completed_at_override` keyword-only (1 parámetro + 1 línea) |
| `backend/app/modules/dashboard/service.py` | Modificar | Exclusión de contexto en `_build_by_assignee` (`:184-220`), `_build_workload` (`:234-259`) y el conteo `tasks` de `_build_totals` (`:297-316`); `overdue` y `at_risk` de `totals` NO cambian |
| `backend/app/config.py` | Modificar | `CHECKLIST_FILE_MAX_ROWS` / `CHECKLIST_FILE_MAX_CELLS` |
| `backend/app/importers/checklist/*.py` | Crear | 7 módulos (D-INTENT, D-ERR, D-SEEDS) |
| `backend/scripts/import_checklist.py` | Crear | CLI, 5 códigos de salida (D-EXIT) y `--member` repetible (D-USERS) |
| `frontend/src/entities/workspace/workspace.model.ts` | Modificar | `context_group?`, `merge_into_task_id?` |
| `frontend/src/entities/task/ui/origin-badge/origin-badge.component.ts` | Crear | Insignia presentacional que **compone** `<sol-badge variant="neutral" size="sm">` de `@solercia/ui` |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modificar | 1 uso junto al `task_key` (`:285-291`) |
| `frontend/src/widgets/task-detail-panel/task-detail-panel.component.ts` | Modificar | 1 uso junto al `task_key` (`:93-95`) |
| `backend/tests/test_bootstrap_hierarchy.py` | Modificar | Sembrado, orden, verbatim, banderas e invariante de PANDORA |
| `backend/tests/test_*.py` (10 nuevos) | Crear | Ver «Estrategia de pruebas» |

**No se toca**: `sprints`, `checklists`, `comments`, `attachments`, `alerts`, `intake`, `connectors`,
`task_links`, `labels/service.py` (el importador trae su propio `ensure_label`),
`backend/tests/test_migrations_baseline.py`, `backend/app/ai/`,
`openspec/changes/48-puerto-llm/`, `openspec/changes/45a-planes-modelo-api/`.

---

## Estrategia de pruebas (TDD estricto: rojo antes que código)

`openspec/config.yaml:26-30` fija `tdd: true`. **Tipo**: `RED` = debe fallar antes del código y pasar
después; `guardia` = verde desde el primer momento, existe para que **siga** siéndolo (una guardia que
arranca roja delata que el supuesto ya estaba roto y es un hallazgo, no un paso del TDD).

**Archivos**: `test_checklist_parser.py` (P), `test_checklist_mapping.py` (M),
`test_checklist_consolidation.py` (K), `test_checklist_importer.py` (I), `test_import_checklist_cli.py`
(C), `test_migration_board_progress_flag.py` (MA), `test_migration_task_context.py` (MB),
`test_progress_rollup_exclusions.py` (R), `test_dashboard_context_exclusion.py` (X),
`test_task_completed_at_override.py` (O), `test_tasks_context_fields.py` (T, ver nota),
`test_bootstrap_hierarchy.py` (B, existente) y `test_project_hierarchy_endpoints.py`
(endpoints, **existente**: aloja las guardias del roll-up 75, 78 y 79).

### Cobertura escenario → prueba (108 / 108)

| # | Requisito · Escenario | Prueba | Tipo | Arch. · Reb. |
|---|---|---|---|---|
| 1 | Hoja y encabezados · Lectura exitosa | `test_parses_rows_when_sheet_and_headers_match_exactly` | RED | P · D |
| 2 | Hoja y encabezados · Hoja inexistente | `test_missing_sheet_raises_typed_error_before_reading_rows` | RED | P · D |
| 3 | Hoja y encabezados · Encabezado faltante o reordenado | `test_missing_or_reordered_header_raises_typed_error` | RED | P · D |
| 4 | Antibomba · Archivo corrupto o no XLSX | `test_non_xlsx_bytes_raise_a_typed_importer_error_not_openpyxl` | RED | P · D |
| 5 | Antibomba · Excede el límite de tamaño | `test_row_or_cell_limit_stops_iteration_with_a_typed_error` | RED | P · D |
| 6 | Fechas · `datetime` igual que texto ISO | `test_date_cell_as_date_and_as_iso_string_produce_the_same_due_date` | RED | P · D |
| 7 | Fechas · Celdas mixtas en la misma columna | `test_mixed_cell_types_in_one_column_parse_without_error` | RED | P · D |
| 8 | Sin conteos · Procesa exactamente las filas presentes | `test_parser_processes_exactly_the_rows_present` | RED | P · D |
| 9 | Sin conteos · Dos archivos de distinto tamaño | `test_two_files_with_different_row_counts_both_parse` | RED | P · D |
| 10 | Estado→columna · 7 estados en SEGURIDAD | `test_seven_states_map_to_seguridad_columns` | RED | M · D |
| 11 | Estado→columna · 7 estados en PANDORA | `test_seven_states_map_to_pandora_columns` | RED | M · D |
| 12 | Estado→columna · Función pura y determinista | `test_status_mapping_is_pure_and_deterministic` | RED | M · D |
| 13 | Urgencia · Las 4 nombradas | `test_four_named_urgencies_map_to_priority` | RED | M · D |
| 14 | Urgencia · Vacía o `-` → `low` | `test_empty_or_dash_urgency_maps_to_low` | RED | M · D |
| 15 | Fecha Límite · ISO → `due_date` | `test_iso_date_maps_to_due_date` | RED | M · D |
| 16 | Fecha Límite · Literal `Recurrente` | `test_literal_recurrente_leaves_due_date_null_and_adds_the_text_line` | RED | M · D |
| 17 | Fecha Límite · Literal `Sin fecha (…)` | `test_literal_sin_fecha_leaves_due_date_null_and_adds_the_text_line` | RED | M · D |
| 18 | Fecha Límite · Literal `-` | `test_literal_dash_leaves_due_date_null_and_adds_the_text_line` | RED | M · D |
| 19 | `recurrente` · Estado RECURRENTE con fecha ISO | `test_state_recurrente_with_iso_date_gets_the_label` | RED | M · D |
| 20 | `recurrente` · Fecha literal con otro estado | `test_literal_recurrente_date_with_another_state_gets_the_label` | RED | M · D |
| 21 | `recurrente` · Ninguna condición | `test_neither_condition_never_gets_the_label` | RED | M · D |
| 22 | `area:` · Variantes de caja y espacio | `test_case_and_spacing_variants_normalize_to_the_same_area_label` | RED | M · D |
| 23 | `area:` · La categoría completa nunca es etiqueta | `test_full_category_never_becomes_a_label_name` | RED | M · D |
| 24 | `apoyo-ia:` · Valor `-` no genera etiqueta | `test_dash_apoyo_ia_produces_no_label` | RED | M · D |
| 25 | `apoyo-ia:` · Valores nombrados | `test_named_apoyo_ia_values_produce_their_label` | RED | M · D |
| 26 | `pspi:` · Prefijo `[PSPI x.y]` | `test_pspi_prefix_produces_the_matching_label` | RED | M · D |
| 27 | `pspi:` · Declarada en `plan_links` | `test_plan_links_in_the_csv_produces_the_pspi_label` | RED | I · F |
| 28 | `pspi:` · Sin prefijo ni `plan_links` | `test_row_without_prefix_or_plan_links_gets_no_pspi_label` | RED | M · D |
| 29 | Ruteo · «Pandora» en la categoría | `test_pandora_in_category_routes_to_pandora` | RED | M · D |
| 30 | Ruteo · Prefijo `HU-` | `test_hu_prefix_routes_to_pandora` | RED | M · D |
| 31 | Ruteo · `T-69/T-70/T-73` con etiqueta cruzada | `test_forced_ids_route_to_pandora_with_their_cross_area_label` | RED | M · D |
| 32 | Ruteo · Sin coincidencias → SEGURIDAD | `test_row_without_signals_routes_to_seguridad` | RED | M · D |
| 33 | Descripción · Composición en orden | `test_description_composes_in_the_specified_order` | RED | M · D |
| 34 | Descripción · Sin `Observaciones` | `test_row_without_observaciones_omits_the_section` | RED | M · D |
| 35 | Descripción · > 4000 caracteres falla con su `ID` | `test_description_over_4000_chars_fails_naming_the_row_id_without_creating_the_task` | RED | I · F |
| 36 | `completed_at` · Patrón en fila cerrada | `test_closed_row_with_the_pattern_sets_completed_at_override` | RED | I · F |
| 37 | `completed_at` · Patrón en fila no cerrada | `test_same_pattern_on_a_non_closed_row_is_not_applied` | RED | I · F |
| 38 | `completed_at` · Sin patrón | `test_row_without_the_pattern_uses_the_default_completed_at` | RED | I · F |
| 39 | CSV · Una fila por fila del origen, 7 columnas | `test_dry_run_csv_has_one_row_per_source_row_and_seven_columns` | RED | K · E |
| 40 | CSV · `action` fuera del vocabulario | `test_action_outside_the_closed_vocabulary_is_rejected` | RED | K · E |
| 41 | Defaults · `T-81 → merge_into:T-05` | `test_t81_defaults_to_merge_into_t05` | RED | K · E |
| 42 | Defaults · `T-23 → subtask_of:T-77` | `test_t23_defaults_to_subtask_of_t77` | RED | K · E |
| 43 | Defaults · `T-94`/`T-99` fusión, resto PSPI import | `test_t94_and_t99_default_to_merge_into_and_the_rest_of_pspi_to_import` | RED | K · E |
| 44 | Defaults · `T-74` nunca en contexto | `test_t74_is_never_proposed_as_context_group` | RED | K · E |
| 45 | Defaults · Contradicciones solo como notas | `test_detected_contradictions_are_recorded_as_notes_only` | RED | K · E |
| 46 | Validación · Fila sin decidir | `test_undecided_row_aborts_before_any_write` | RED | K · E |
| 47 | Validación · Referencia a un `ID` inexistente | `test_reference_to_an_unknown_id_aborts_before_any_write` | RED | K · E |
| 48 | Validación · Ciclo en el grafo | `test_a_cycle_in_the_subtask_graph_aborts_before_any_write` | RED | K · E |
| 49 | `--execute` · Sin `--csv-in` termina con error | `test_execute_without_csv_in_exits_nonzero_without_touching_the_database` | RED | C · G |
| 50 | `--execute` · Con `--csv-in` válido procede | `test_execute_with_a_valid_csv_in_applies_the_decisions` | RED | C · G |
| 51 | Idempotencia · Primera corrida crea con ancla | `test_first_run_creates_tasks_anchored_by_external_key` | RED | I · F |
| 52 | Idempotencia · Segunda corrida, cero cambios | `test_second_identical_run_reports_zero_changes` | RED | I · F |
| 53 | Solo faltantes · Tarea existente intacta | `test_existing_anchored_task_is_untouched_without_update_existing` | RED | I · F |
| 54 | `--update-existing` · Título editado se conserva | `test_manually_edited_title_survives_update_existing` | RED | I · F |
| 55 | `--update-existing` · `status` se actualiza | `test_status_is_reconciled_with_update_existing` | RED | I · F |
| 56 | `--update-existing` · Etiquetas se reconcilian | `test_labels_are_reconciled_with_update_existing` | RED | I · F |
| 57 | Fusión · Se crea con su propio ancla en `Removida` | `test_merged_row_is_created_with_its_own_anchor_in_removida` | RED | I · F |
| 58 | Fusión · Segunda corrida no la recrea | `test_second_run_does_not_recreate_the_merged_row` | RED | I · F |
| 59 | Dos pasadas · Hijo antes que el padre | `test_subtask_row_preceding_its_parent_is_created_without_error` | RED | I · F |
| 60 | Dos pasadas · Enlace en la segunda pasada | `test_second_pass_links_every_subtask_to_its_parent_in_the_same_project` | RED | I · F |
| 61 | Usuarios · Crea a Jason y Santiago como `viewer` | `test_first_import_creates_the_two_viewer_users_without_password` | RED | I · F |
| 62 | Usuarios · Segunda corrida no los duplica | `test_second_run_does_not_duplicate_those_users` | RED | I · F |
| 63 | Usuarios · Login rechazado genéricamente | `test_login_with_a_passwordless_account_is_rejected_generically` (`auth/service.py:27` ya lo hace) | **guardia** | I · F |
| 64 | Responsable por defecto · `admin@solercia.com` | `test_unresolvable_solicitante_falls_back_to_the_admin_user` | RED | I · F |
| 65 | `ensure_label` · Dos filas, una sola `Label` | `test_two_rows_with_the_same_area_reuse_one_label_row` | RED | I · F |
| 66 | `ensure_label` · Reasignar no duplica el vínculo | `test_reassigning_the_same_label_creates_no_second_link` (`assign_label` YA es idempotente, `labels/service.py:120-122`) | **guardia** | I · F |
| 67 | CLI · Invocación mínima corre en `--dry-run` | `test_minimal_invocation_runs_in_dry_run_and_writes_the_csv` | RED | C · G |
| 68 | CLI · Códigos de salida distinguibles | `test_exit_codes_distinguish_csv_validation_from_database_failure` | RED | C · G |
| 69 | Reporte · `--dry-run` muestra lo previsto | `test_dry_run_report_shows_the_planned_counts` | RED | I · F |
| 70 | Reporte · `--execute` muestra lo aplicado | `test_execute_report_shows_the_counts_actually_applied` | RED | I · F |
| 71 | Transacción · Fallo a mitad revierte todo | `test_a_mid_run_failure_rolls_back_the_whole_transaction` | RED | I · F |
| 72 | Transacción · `--dry-run` nunca comitea | `test_dry_run_never_commits` | RED | I · F |
| 73 | Fixtures · La suite no referencia el archivo real | `test_no_test_references_the_real_checklist_file` (unidad pura sobre `tests/`) | **guardia** | P · D |
| 74 | Fixtures · El sintético cubre los casos en 6-10 filas | `test_the_synthetic_fixture_covers_the_relevant_cases_in_few_rows` | **guardia** | I · F |
| 75 | Roll-up · Reproduce el ejemplo de negocio | `test_progress_endpoint_reproduces_the_18_of_20_business_example` — **ya existe** en `test_project_hierarchy_endpoints.py:106` | **guardia** | endpoints · A |
| 76 | Roll-up · Columnas excluidas fuera; Diferida/Recurrente dentro | `test_tasks_in_excluded_columns_leave_the_denominator` (reemplaza a `test_progress_endpoint_excludes_cancelled_tasks_from_denominator`, `:141`) | RED | R · A |
| 77 | Roll-up · Tareas de contexto fuera del denominador | `test_context_tasks_leave_the_denominator` | RED | R · B |
| 78 | Roll-up · Metodologías mixtas en el subárbol | `test_mixed_methodologies_use_each_projects_last_status` — guardia **añadida al archivo existente** `test_project_hierarchy_endpoints.py`, no al archivo nuevo | **guardia** | endpoints · A |
| 79 | Roll-up · Aislamiento de tenant | `test_progress_endpoint_of_another_org_project_returns_404` — **ya existe** en `test_project_hierarchy_endpoints.py:219` | **guardia** | endpoints · A |
| 80 | Bandera · `upgrade` agrega sin afectar filas | `test_upgrade_adds_the_flag_defaulting_to_false_without_touching_rows` | RED | MA · A |
| 81 | Bandera · `downgrade` sin pérdida de filas | `test_downgrade_removes_the_flag_without_losing_rows` | RED | MA · A |
| 82 | Bandera · `create_all` ≡ migración | `test_create_all_and_migration_declare_the_same_flag_ddl` | RED | MA · A |
| 83 | Sembrado · Primera siembra agrega las 4 faltantes | `test_first_seed_adds_the_four_missing_pandora_columns_in_order` | RED | B · A |
| 84 | Sembrado · Segunda siembra es no-op | `test_second_seed_on_a_complete_board_is_a_noop` | RED | B · A |
| 85 | Sembrado · `status_key` verbatim | `test_new_pandora_status_keys_are_verbatim` | RED | B · A |
| 86 | Invariante · PANDORA correcta pasa | `test_pandora_with_its_seven_columns_passes_the_invariant` | RED | B · A |
| 87 | Invariante · `Done` fuera del final falla | `test_done_out_of_last_position_fails_the_invariant_and_the_runner_exits_nonzero` — afirma la invariante en rojo **y** el `EXIT_INVARIANT_FAILED` de `purge_demo_data.py:53`, como exige el delta de `boards` | RED | B · A |
| 88 | Invariante · `status_key` slugificado falla | `test_a_slugified_status_key_fails_the_invariant_and_the_runner_exits_nonzero` — misma aserción doble: invariante roja **y** código de salida distinto de cero | RED | B · A |
| 89 | Banderas · SEGURIDAD excluye las dos columnas | `test_seguridad_removida_and_gestionada_aparte_are_excluded` | RED | B · A |
| 90 | Banderas · PANDORA excluye las dos columnas | `test_pandora_removida_and_gestionada_aparte_are_excluded` | RED | B · A |
| 91 | Banderas · Diferida/Recurrente permanecen dentro | `test_diferida_and_recurrente_stay_in_the_denominator_in_both_projects` | RED | B · A |
| 92 | `0027` · Agrega ambas columnas sin afectar tareas | `test_upgrade_adds_both_nullable_columns_without_touching_tasks` | RED | MB · B |
| 93 | `0027` · `downgrade` conserva las filas | `test_downgrade_removes_both_columns_without_losing_rows` | RED | MB · B |
| 94 | `0027` · Borrar la superviviente libera el puntero | `test_deleting_the_surviving_task_nulls_the_merge_pointer` | RED | MB · B |
| 95 | `0027` · `is_context` transitorio intacto | `test_is_context_transient_behaves_identically_after_the_migration` — vive en `T`, no en `MB`: se afirma sobre la **API** bajo `assignee_id` (cliente in-process), no sobre `information_schema` | **guardia** | T · B |
| 96 | Exposición · El detalle expone `context_group` | `test_context_task_detail_exposes_context_group` | RED | T · B |
| 97 | Exposición · `POST` con `context_group` no persiste | `test_post_with_context_group_in_the_body_does_not_persist_it` | RED | T · B |
| 98 | Exposición · `PATCH` no altera `merge_into_task_id` | `test_patch_with_merge_into_task_id_never_alters_the_link` | RED | T · B |
| 99 | Override · En la columna de cierre fija la fecha | `test_create_in_the_closing_column_with_override_persists_the_exact_date` | RED | O · C |
| 100 | Override · Fuera del cierre se ignora | `test_override_is_ignored_outside_the_closing_column` | RED | O · C |
| 101 | Override · Sin override, igual que hoy | `test_create_without_override_behaves_exactly_as_today` | **guardia** | O · C |
| 102 | Insignia · Tarea importada la muestra | `npm run build` + revisión `ux-psicologia` del diff (D-BADGE-UI) | RED | build · B |
| 103 | Insignia · Tarea manual no la muestra | Mismo comando y misma revisión; `@if (task.external_key)` | RED | build · B |
| 104 | Dashboard · Contexto fuera de `workload` | `test_context_task_is_excluded_from_workload` | RED | X · B |
| 105 | Dashboard · Contexto fuera de `totals` | `test_context_task_is_excluded_from_totals` | RED | X · B |
| 106 | Dashboard · Contexto vencido sigue en `at_risk` | `test_overdue_context_task_still_appears_in_at_risk` (y `totals.at_risk == len(at_risk)`) | RED | X · B |
| 107 | R1 · Contexto fuera de `by_assignee` | `test_context_task_is_excluded_from_by_assignee` | RED | X · B |
| 108 | R1 · Colaborador con solo contexto desaparece de `by_assignee` | `test_assignee_with_only_context_tasks_disappears_from_by_assignee` | RED | X · B |

**Escenarios sin prueba automatizada: ninguno de backend.** Los dos de frontend (102, 103) se cierran
con la compilación existente más la revisión `ux-psicologia`, por la misma razón que el 43 documentó
en su D-H: `frontend/package.json` no define runner de pruebas y `tsconfig.app.json` solo compila lo
alcanzable desde `main.ts`.

**Guardias** (verdes desde el primer momento): 63, **66**, 73, 74, 75, 78, 79, 95, 101. Las tres del
roll-up (75, 78, 79) viven en el archivo **existente** `test_project_hierarchy_endpoints.py`, no en
`test_progress_rollup_exclusions.py`, que aloja solo los dos escenarios en rojo (76 y 77): una
guardia que ya existe no se reescribe en un archivo nuevo, se deja donde el equipo la busca.

**Pruebas de apoyo, sin escenario propio** (no cuentan en 108/108, pero son unidades exigidas por el
diseño):

| Prueba | Decisión | Rebanada |
|---|---|---|
| `test_completed_at_override_is_absent_from_taskcreate_and_the_router` | D8 (el router no expone el parámetro) | C |
| `test_seed_ids_absent_from_the_sheet_produce_a_warning_not_an_error` | D-SEEDS | E |
| `test_cross_project_links_are_rejected_before_any_write` | D-PASS | E |
| `test_chained_subtask_of_is_rejected_with_the_service_error_code` | D-VAL (H6a) | E |
| `test_reference_to_a_skipped_or_merged_row_is_rejected_before_any_write` | D-VAL (H6b) | E |
| `test_ensure_label_reactivates_a_soft_deleted_label_instead_of_creating` | D-LBL-IO (H5) | F |
| `test_a_member_without_mapped_email_exits_one_before_writing` | D-USERS (H8) | G |
| `test_csv_in_cp1252_is_read_with_a_warning_and_undecodable_bytes_exit_two` | D-CSVIO (H9) | E |
| `test_update_existing_without_differences_does_not_call_update_task` | D-UPD (H17) | F |

*Nota sobre la lista de archivos*: el encargo enumeró diez archivos de prueba. Se añade un
**undécimo**, `test_tasks_context_fields.py`, por el precedente del 43: los archivos
`test_migration_*` alojan solo pruebas de migración (síncronas, `asyncio.run`, base desechable) y las
de API viven aparte (`asyncio` con `loop_scope="session"` y cliente in-process). Mezclarlas en
`test_migration_task_context.py` obligaría a dos estilos de fixture en el mismo módulo.

### Andamiaje de los archivos nuevos

| Archivo | Molde |
|---|---|
| `test_migration_board_progress_flag.py`, `test_migration_task_context.py` | Calco de `test_migration_project_kind.py:73-244`: `_sync_dsn`/`_admin_dsn`/`_recreate_*`/`_drop_*`/`_alembic_config`/`_run_against`, base desechable propia, `upgrade` a la revisión anterior → siembra por SQL crudo con `asyncpg` → `upgrade` → aserciones sobre `information_schema` → `downgrade` y aserción de no pérdida. La equivalencia de DDL levanta una **segunda** base y ejecuta `CREATE EXTENSION pg_trgm` → **`import app.db_init`** → `Base.metadata.create_all` (sin ese import, `create_all` construye un esquema incompleto y la comparación es vacua) |
| `test_progress_rollup_exclusions.py`, `test_dashboard_context_exclusion.py`, `test_tasks_context_fields.py`, `test_task_completed_at_override.py` | Calco de `test_task_filters.py:1-64`: helpers `_auth`/`_create_project`/`_create_task`, API real in-process con `httpx`, `@skip_no_db` + `@pytest.mark.asyncio(loop_scope="session")` |
| `test_checklist_parser.py`, `test_checklist_mapping.py`, `test_checklist_consolidation.py` | **Puras**: sin `@skip_no_db`, sin BD, sin `pytest.mark.asyncio`. El XLSX se genera con `openpyxl` en `tmp_path`; el CSV, con `csv.writer` en `tmp_path` |
| `test_checklist_importer.py` | Integración sobre la fixture `session`, que **ya** es una sesión con SAVEPOINT (`conftest.py:88-110`): el importador prueba su propia frontera D-TX con un `outer` inyectado |
| `test_import_checklist_cli.py` | Calco de `test_purge_cli.py`: parseo de argumentos y códigos de salida **sin BD** (sustituyendo el caso de uso por un doble), más **una** prueba extremo a extremo que lanza `python -m scripts.import_checklist` como subproceso fresco contra `TEST_DATABASE_URL`, como `test_dry_run_real_via_subprocess_registra_el_orm_completo` (`test_purge_cli.py:1-16`) |

### Comandos y línea base

```
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  .venv/bin/python -m pytest -q
cd frontend && npm run build
```

**Línea base**: la vigente **en el tracker al iniciar cada rebanada**, re-medida, nunca congelada. La
suite está en deriva (1411 → 1415 → 1429 → **1451/3** con el cambio 48 escribiendo pruebas en
paralelo) y `43/tasks.md` tarea 0.6 ya obliga a re-medirla por rebanada. Los 3 fallos preexistentes
viven en `tests/test_adapter_microsoft365.py` y dependen del reloj: se heredan, no se arreglan aquí.
La línea base **solo** vale con `TEST_DATABASE_URL` puesta.

---

## Threat Matrix

La matriz estándar cubre enrutamiento, shell, subprocesos, automatización de VCS/PR y clasificación
de ejecutables. Este cambio **sí** cruza dos de esas fronteras (proceso por lotes que lee un archivo
suministrado por ruta, y una prueba que lanza un subproceso), así que se marcan explícitamente:

| Frontera estándar | Aplicabilidad |
|---|---|
| Rutas de archivo suministradas por el operador (`--file`, `--csv-out`, `--csv-in`) | **Aplicable** — ver filas 1 y 2 abajo |
| Subprocesos | **Aplicable** — la prueba extremo a extremo lanza `python -m scripts.import_checklist`; argumentos fijos, sin `shell=True`, sin interpolación de entrada del usuario |
| Clasificación de ejecutables | N/A — el importador no clasifica ni ejecuta el archivo de entrada; `openpyxl` lo abre como zip de datos |
| Selección de repositorio git · commit · push · comandos de PR | N/A — sin automatización de VCS/PR |

Las fronteras propias de este cambio:

| # | Caso adversario | Comportamiento seguro | Prueba en rojo |
|---|---|---|---|
| 1 | **El archivo institucional real entra al repositorio** como fixture: 135 filas de datos de seguridad de una entidad pública quedan en el historial de git para siempre | Toda prueba genera su XLSX con `openpyxl` en `tmp_path`; una guardia pura recorre `backend/tests/` y falla si alguna ruta menciona `CHECKLIST_TAREAS` | 73, 74 |
| 2 | **Traversal por ruta**: `--csv-out ../../etc/algo` o `--file` apuntando fuera del árbol previsto | El operador de la CLI es el dueño de la máquina y de la base, así que la ruta **no** se restringe a un directorio; lo que se garantiza es que ninguna ruta se **interpola** en un comando ni se concatena a mano: `Path(...)`, apertura directa y `--file` inexistente → salida `1` antes de tocar la base | 67, 68 |
| 3 | **Bomba de descompresión XLSX**: un archivo pequeño que expande a millones de celdas y agota la memoria del proceso que va a escribir en producción | `load_workbook(read_only=True, data_only=True)` (stream) + `_guard_limits` **dentro** del bucle con `CHECKLIST_FILE_MAX_ROWS`/`CHECKLIST_FILE_MAX_CELLS` propios (D-CFG): se aborta antes de materializar la hoja | 5 |
| 4 | **Excepción cruda de `openpyxl`** propagada hasta el operador (traza ilegible, sin `ID`, sin causa) | `try/except Exception → ChecklistFileError` (molde `jira/file_parser.py:116-125`); jerarquía tipada propia (D-ERR) | 4 |
| 5 | **`--execute` sin CSV**: el importador adivina las consolidaciones y aplica fusiones que el usuario nunca aprobó | `--execute` exige `--csv-in`; sin él, salida distinta de cero **antes** de abrir conexión | 49 |
| 6 | **Sobrescritura silenciosa de trabajo del usuario**: una segunda corrida pisa títulos, descripciones y responsables editados en la aplicación | Sin `--update-existing` una tarea anclada es intocable; con él, lista blanca de cuatro campos (D-UPD) y `title`/`description`/`assignee_id` explícitamente fuera | 53, 54 |
| 7 | **Ciclos de subtareas** (`A → B → A`): recursión infinita o jerarquía imposible ya escrita en la base | Detección de ciclos en la validación del CSV, **antes** de la primera escritura; aborta identificando el ciclo | 48 |
| 8 | **Enlace entre proyectos**: `subtask_of:`/`merge_into:` cruzando SEGURIDAD y PANDORA → `invalid_parent_task` 422 a mitad de corrida y rollback total por un dato visible en el CSV | Rechazo en la validación de E con la función pura de ruteo (D-PASS) | `test_cross_project_links_are_rejected_before_any_write` (apoyo) |
| 9 | **Cuentas sin contraseña iniciando sesión**: `hashed_password=NULL` + SSO. `auth/sso_service.py:159-173` autoaprovisiona o vincula por correo verificado con `SSO_AUTO_PROVISION` activo | Hoy: `auth/service.py:27` rechaza `hashed_password is None` con el mismo mensaje genérico que una contraseña errónea, y Keycloak no está habilitado. Futuro: queda escrito como riesgo R10 del cambio que habilite SSO — no se mitiga aquí y no se finge que sí | 63 (guardia) |
| 10 | **`Done` deja de ser la última columna de PANDORA** (un `add_column` posterior, un reordenamiento manual): `allowed_statuses()[-1]` deja de ser el estado de cierre y `_resolve_completed_at` más el término `done` del roll-up se rompen **en silencio** | `_i9_pandora_columns` compara la **tupla completa** contra `PANDORA_COLUMNS`, así que falla ante conteo, orden, posición final o `status_key` slugificado; `run_maintenance` no comitea con una invariante roja (`runner.py:48`) | 86, 87, 88 |
| 11 | **Mezcla de `add_column` (slugifica) con `ensure_board_columns` (verbatim)**: `Diferida` y `diferida` conviviendo en el mismo board | Solo `ensure_board_columns` siembra PANDORA (D-SEED, camino único) y la invariante verifica `status_key` verbatim | 85, 88 |
| 12 | **Fuga de la contraseña de la base** en el reporte impreso o en un log | `redact_database_url` reutilizado de `purge_demo_data.py:112-116` | 68 |
| 13 | **Commit parcial** tras un fallo a mitad de corrida, con `TaskRepository.create` comiteando por su cuenta | Frontera D-TX: SAVEPOINT sobre una transacción externa que solo se comitea en un punto | 71, 72 |

---

## Rebanadas y carga de revisión

Estrategia `auto-chain` con **feature branch chain** sobre el tracker `feat/44-importar-checklist-xlsx`;
A apunta al tracker y cada rebanada siguiente a la rama de la anterior.

| # | Rama | Contenido | ≈ líneas | Presupuesto | Escenarios | Reversa |
|---|---|---|---|---|---|---|
| **A** | `feat/44-a-avance` | `0026` + espejo · `outerjoin` y `in_denominator` (los dos términos) en el roll-up · `PANDORA_COLUMNS`, banderas y `_i9` · pruebas | 300–360 | **500** | 75, 76, 78–91 (**16**; el 77 es de B) | `alembic downgrade -1` **solo mientras B no esté aplicada**; con `0027` encima es `alembic downgrade -2` (H20). Más revert; la CTE vuelve al literal `cancelled`, que hoy no excluye nada: **cero efecto observable** |
| **B** | `feat/44-b-contexto` | `0027` + espejo · `TaskRead` · exclusión de contexto en el roll-up y en el dashboard (`by_assignee`, `workload`, `totals.tasks`) · tipo, insignia y sus dos usos · pruebas | 280–340 | **400** | 77, 92–98, 102–108 (**15**) | `alembic downgrade -1` + revert; A permanece |
| **C** | `feat/44-c-completado` | `completed_at_override` keyword-only · pruebas | 100–140 | **200** | 99–101 (3) | Revert; sin la costura las cerradas nacen con `now()`: dato inexacto, no corrupción |
| **D** | `feat/44-d-parser` | `errors.py`, `parser.py`, `mapping.py`, 2 ajustes de `config.py` · pruebas puras sin BD | 400–460 | **600** | 1–26, 28–34, 73 (34) | Revert; no toca el esquema |
| **E** | `feat/44-e-consolidacion` | `seeds.py`, `consolidation.py`: escritura, lectura y validación del CSV · pruebas puras | 380–440 | **600** | 39–48 (10) | Revert; no toca el esquema |
| **F** | `feat/44-f-importador` | `importer.py`, `report.py`: frontera D-TX (también en `--dry-run`), `ensure_users` por `--member`, `ensure_label` con reactivación, dos pasadas con sus cinco atributos, fusiones, contexto, informe · integración | 440–500 | **600** | 27, 35–38, 51–66, 69–72, 74 (26) | Revert; no toca el esquema |
| **G** | `feat/44-g-cli` | `scripts/import_checklist.py` + extremo a extremo de idempotencia | 260–320 | **400** | 49, 50, 67, 68 (4) | Revert; no toca el esquema |

Total estimado **≈2160–2560 líneas** (`additions + deletions`), ~55 % pruebas; presupuesto acumulado
**3300** (estimación de la exploración × 1,2 + ≈50 líneas de marcas de `tasks.md`, redondeado a la
centena). El pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`,
`400-line budget risk`) lo emite `sdd-tasks`, no este diseño.

**Contingencia declarada para B**: la rebanada absorbe el término de contexto en el roll-up (escenario
77), la exclusión del dashboard en **tres** constructores (D3 + H7, escenarios 104–108), la migración
y la insignia. Si al desglosar supera su presupuesto de 400, se aplica la contingencia que el 43 ya
usó: **la insignia sale a una rebanada propia** (`feat/44-b2-insignia`, escenarios 102 y 103, ≈80
líneas), que puede posponerse sin bloquear a C–G porque nada del importador depende de ella. El
criterio de corte no cambia: lo que desbloquea a D–G son las columnas y `completed_at_override`, no
la interfaz.

---

## Migración / despliegue

Tres pasos, en este orden:

1. **`alembic upgrade head`** tras A (`0026`) y tras B (`0027`). Ambas aditivas, sin retrollenado, sin
   ventana de mantenimiento. Reversa: `alembic downgrade -1` deshace **la última** revisión aplicada,
   así que revertir **A** cuesta `-1` solo mientras B no esté aplicada; con `0027` encima, revertir A
   exige `alembic downgrade -2` (H20). Escribir «`-1` para cada una» era la receta con la que se
   deshace la migración equivocada.
2. **Sembrado de PANDORA y banderas** (una sola vez, tras A):
   `pg_dump ... > respaldo.sql` y
   `cd backend && .venv/bin/python -m scripts.purge_demo_data --execute --backup-file respaldo.sql --database-url <host>`.
   `--execute` exige el respaldo verificado (`purge_demo_data.py:100-109`); la purga es idempotente
   sobre un alcance demo ya vacío y el bootstrap reutiliza por `code`.
3. **Fase operativa manual del importador** — runbook, fuera de `pytest`, después del `apply` y antes
   del `archive`:

   ```
   cd backend
   # Los correos reales NO están en el repositorio (D-USERS): se pasan aquí, y el
   # runbook operativo —fuera del repositorio— guarda los valores de la entidad.
   MEMBERS=(--member "Jason Rizo=<correo real>" --member "Santiago Carreño=<correo real>")

   # 1) --dry-run: EXIGE base de datos (D-TX/H1). Recorre TODO el camino con las
   #    decisiones sembradas y termina en rollback(): no deja ni una fila.
   .venv/bin/python -m scripts.import_checklist --file <ruta al XLSX real> \
       --dry-run --csv-out checklist_consolidation.csv \
       --database-url <host> "${MEMBERS[@]}"
   # → EL USUARIO revisa y ajusta el CSV: fusiones, subtareas, grupos de contexto, notas
   #   Al guardarlo desde Excel: «CSV UTF-8 (delimitado por comas)». Para ABRIRLO,
   #   Datos → Desde texto/CSV con delimitador coma y origen UTF-8: en es-CO el doble
   #   clic puede interpretar «;» y dejar el archivo en una sola columna (D-CSVIO/H9).
   .venv/bin/python -m scripts.import_checklist --file <ruta> \
       --execute --csv-in checklist_consolidation.csv \
       --database-url <host> "${MEMBERS[@]}"
   # → Verificación en http://localhost:4242: tablero de SEGURIDAD y de PANDORA, avance
   #   consolidado, vista ejecutiva (by_assignee y workload sin contexto, at_risk con él)
   #   y filtros area:*
   .venv/bin/python -m scripts.import_checklist --file <ruta> \
       --execute --csv-in checklist_consolidation.csv \
       --database-url <host> "${MEMBERS[@]}"   # → 0 creadas, 0 actualizadas, 0 cambios
   ```

   El XLSX real **nunca** entra al repositorio: se pasa por ruta y el CSV generado se trata como
   dato operativo, no como artefacto versionado. Los correos tampoco: viven en la invocación y en
   el runbook operativo.

   **Advertencia sobre `--update-existing` (H21)**: con esa bandera **el XLSX manda**. Una tarea que
   el equipo completó en la aplicación pero que en la hoja sigue `PENDIENTE` **vuelve a «Sin
   iniciar»** en la siguiente corrida. Úsala solo cuando la hoja acabe de actualizarse contra la
   realidad; sin ella, toda tarea ya anclada es intocable.

**Precondiciones duras**: el cambio 43 archivado (entrega `external_origin`, `get_by_external_key` y
`checklist_xlsx` en `KNOWN_TASK_SOURCES`) y el 42 archivado (ya lo está). **Gate D-REV**: antes de
escribir `0026`, `alembic heads` (el directorio de versiones) y `alembic current` (la base objetivo)
deben devolver **ambos** `0025`.

**Desbloqueo hacia adelante**: al cerrar B, el cambio 45 encuentra las etiquetas `pspi:x.y` como punto
de partida de sus tablas de vínculos de plan; el 44 no crea ninguna de esas tablas.

---

## Riesgos abiertos

| Riesgo | Mitigación en este diseño |
|---|---|
| **`TaskRepository.create` comitea** y rompería la transacción única del importador | D-TX: sesión con `join_transaction_mode="create_savepoint"` sobre una transacción externa, patrón ya probado en `conftest.py:88-110`. Escenarios 71 y 72 |
| Un `down_revision` que apunte a una revisión inexistente rompe `alembic upgrade head` **en despliegue**, no en revisión (fue el defecto del esquema con `0026` reservado al 40) | D-REV: numeración sin reservas (`0026`←`0025`, `0027`←`0026`) más gate doble como primera unidad de A —`alembic heads` (directorio) **y** `alembic current` (base)—; si la cabeza real no es `0025`, se re-anclan número y padre y se corrigen **los tres deltas** (`boards`, `tasks`, `project-hierarchy`) en el mismo commit |
| La exploración afirmaba que el `JOIN` a `BoardColumn` ya estaba en la CTE del roll-up; **no lo está** para la columna de la tarea | D-CTE: `outerjoin` nuevo y aliasado, con `coalesce(..., false)` para que `board_column_id IS NULL` no expulse tareas del denominador |
| **`completed_at` histórico en `--update-existing`**: una tarea que cierra en una corrida posterior recibiría `now()` | D-UPD: no se sobrescribe y se emite **advertencia** con el `ID` y las dos fechas. El caso es de segundo orden: el runbook parte de una base sin tareas |
| El sembrado de PANDORA solo es alcanzable por `purge_demo_data.py --execute`, que exige `pg_dump` | Documentado como paso 2 del despliegue. Alternativa descartada: un `--bootstrap-only` que crearía un segundo camino hacia `run_maintenance` con garantías distintas |
| **Semillas obsoletas**: la hoja es un documento vivo y un `ID` de `CONSOLIDATION_DEFAULTS` puede desaparecer | D-SEEDS: las semillas son **advisorias**; un `ID` ausente produce advertencia, nunca error. Prueba de apoyo dedicada |
| `alembic check` da falsa sensación de cobertura sobre el espejado | Igual que el 43 (D-B): el gate real es la prueba de equivalencia de DDL entre `create_all` y `upgrade head` (escenario 82). Aquí el riesgo es menor —`0026` y `0027` no traen `postgresql_where` ni `CheckConstraint`, que es justo lo que el gate no compara— pero la prueba se escribe igual porque un `server_default` divergente sí es invisible en la suite |
| Importar el checklist completo distorsiona la vista ejecutiva de golpe (muchas vencidas desde marzo) | D3 + H7 acotan la exclusión a `by_assignee`, `workload` y `totals.tasks`; `at_risk` y los contadores de riesgo de `totals` los siguen mostrando **a propósito**. Se verifica con el conjunto real en el paso 3 del despliegue, antes del `--execute` |
| **R10 heredado del 43**: no existe ruta de restauración de tareas; si alguna vez se agrega, debe comprobar el ancla antes de reactivar | Sin cambios aquí: el 44 no crea ninguna ruta de restauración |
| **`--dry-run` deja de correr en una máquina sin base de datos** (H1): antes prometía ser offline | Aceptado y documentado en la tabla de la CLI y en el runbook. Es el precio de un informe verdadero: sin base no se puede distinguir «crear» de «ya existe», y ese informe es lo que el usuario usa para decidir |
| **Una etiqueta añadida a mano podría perderse** al reconciliar con `--update-existing` | D-UPD/H4: `unassign_label` solo actúa sobre las etiquetas **derivadas** (`area:*`, `apoyo-ia:*`, `recurrente`, `pspi:*`); cualquier otro nombre es intocable, y cada retiro se enumera en el reporte |
| **Una etiqueta borrada lógicamente bloquea la creación** por `uq_labels_project_name`, que es total | D-LBL-IO/H5: `ensure_label` busca sin filtro de estado y reactiva antes de crear. Prueba de apoyo dedicada |
| **Correos institucionales filtrados al historial de git** si se codificaran en `seeds.py` o en una prueba | D-USERS/H8: llegan por `--member` repetible, las pruebas usan correos ficticios y un nombre sin correo mapeado termina con salida `1` sin escribir nada |

## Preguntas abiertas

- [ ] **Ninguna que requiera al usuario.** Las decisiones de alcance quedaron cerradas como D1–D9 en la
      propuesta, la extensión del denominador de `project-hierarchy` la confirmó el orquestador antes
      de esta fase, y las **diecisiete** decisiones técnicas de este documento (D-TX, D-REV, D-SEED,
      D-CTE, D-COL, D-ERR, **D-EXIT**, D-CFG, D-CSVIO, D-SEEDS, D-INTENT, D-PASS, D-UPD,
      **D-LBL-IO**, **D-VAL**, **D-USERS**, D-BADGE-UI) se cierran aquí. Las cuatro en negrita nacen
      de la pasada correctiva del validador (H2, H5, H6 y H8) con las decisiones del orquestador.
- [ ] La revisión del CSV de consolidación es una **fase operativa** posterior al `apply` (paso 3 del
      despliegue), no un vacío de diseño.
- [ ] Anotado y **no bloqueante**: castellanizar los rótulos de PANDORA (`Backlog → Sin iniciar`) es
      posible con `BoardService.rename_column` **sin tocar `status_key`**; se decide durante la fase
      operativa, no aquí.

## Referencias

- `openspec/changes/44-importar-checklist-xlsx/{exploration,proposal,state}.{md,yaml}` y los cinco
  deltas de `specs/`.
- `openspec/changes/43-tareas-origen-externo/design.md` — `external_origin`, `get_by_external_key`,
  `sources.py`, patrón keyword-only y equivalencia de DDL frente a `alembic check` 1.14.0.
- `agents/rules/solercia-persistence.md` — repositorios sin commit, transacción del caso de uso,
  tenant obligatorio, SQL en adaptadores.
- `openspec/config.yaml:20-30` — `rules.design` (decisiones con justificación,
  `router → service → repository`) y `rules.apply.tdd: true`.
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` §5.4, §5.5 (idempotencia obligatoria en
  la ingestión), §6.5, §7.
- `~/.claude/rules/ux-front.md` — checklist `ux-psicologia`, aplicado en D-BADGE-UI y obligatorio
  antes de cerrar la rebanada B.
- Código citado: `backend/app/modules/tasks/{models,schemas,repository,service}.py`,
  `backend/app/modules/projects/repository.py:290-350`, `backend/app/modules/boards/models.py`,
  `backend/app/modules/dashboard/service.py:79-103,222-316,438-451`,
  `backend/app/maintenance/{bootstrap,invariants,repository,runner}.py`,
  `backend/scripts/purge_demo_data.py`,
  `backend/app/integrations/adapters/jira/file_parser.py:70-148`, `backend/app/config.py:245-253`,
  `backend/tests/{conftest.py,test_migration_project_kind.py,test_purge_cli.py,test_bootstrap_hierarchy.py}`,
  `frontend/src/entities/workspace/workspace.model.ts:9-38`,
  `frontend/src/widgets/{project-workspace,task-detail-panel}/*.component.ts`.
