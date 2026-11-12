# Design: 45a · Planes institucionales (Decreto 612) — modelo y API

> Fase `sdd-design`. Store híbrido: espejo de Engram `sdd/45a-planes-modelo-api/design`.
> Entradas: `exploration.md`, `proposal.md`, `specs/institutional-plans/spec.md`
> (**14 requisitos / 32 escenarios**, contados en disco) y `state.yaml`.
> Decisiones cerradas que este diseño **implementa sin reabrir**: D1 (`code` + `activity_key`
> derivado, sin `public_id`), D2 (modelo de cinco tablas con `external_codes` plural,
> `resolution`/`source_reference`, `CHECK` anti-autorreferencia y tenant transitivo), D3 (doble
> avance con `null ≠ 0`), D4 (sin dependencias nuevas), D5 (frontera ADR 0009), D6 (conflictos
> registrados, nunca resueltos), D7 (`activity_key` como token del CSV del 44), D8 (migración
> `0028`, `down_revision="0027"` — **re-anclada por el orquestador el 2026-08-26**, ver D-A),
> D9 (sin `TaskRead`), D10 (escritura por costura de repositorio,
> sin `POST /plans`), D11 (`PUT` idempotente del reporte), D12 (vocabularios como `String(n)`
> validados en servicio), D13 (menú diferido al 45c) y D14 (`resolution='manual'` impuesto),
> más P1, P3 y P7.
> Referencias de código verificadas en disco el 2026-08-26.
>
> Este diseño agrega **catorce decisiones técnicas propias**, `D-A … D-N`, con letra para no
> colisionar con las numéricas ya ratificadas.
>
> **Pasada correctiva del 2026-08-26** — validación independiente `PASS_WITH_NOTES` con 16
> hallazgos (5 medios, 11 bajos), todos resueltos. Cambios de fondo: D2 corregida por D-F en el
> punto del avance reportado (H1); la rebanada A se parte en **A1** y **A2** con estimaciones
> re-medidas contra evidencia de disco (H2, H5); `is_confirmed` derivado en el esquema de enlaces
> (H3); `ActivityTaskRead` con consulta única sin N+1 (H4); el inventario de índices se unifica en
> **nueve** (H6); y la Threat Matrix suma dos filas (carrera en el `POST` de enlaces, H10; borrado
> físico de enlaces sin `deleted_by`, H16). Total de rebanadas: **siete**.

## Enfoque técnico

Módulo nuevo y autónomo. No hay agregado existente que modificar: cinco tablas nuevas, cinco
modelos nuevos, un repositorio, un servicio y un router, cableados en los tres puntos de siempre
(`main.py`, `db_init.py`, y **nada** en `_MENU_SEED`, D13). Ni una tabla preexistente cambia de
forma; el único punto de contacto con lo vigente es la FK `task_plan_activities.task_id → tasks.id`.

El idioma es el del propio repositorio: migración aditiva al estilo de `0019_add_intake.py:43-134`
(`op.create_table` + `op.create_index(op.f(...))`, sin `batch_alter_table`), espejo literal en
`__table_args__` al estilo de `projects/models.py:36-53`, cadena de tres saltos
`router → service → repository` (`openspec/config.yaml:20-22`), paginación opt-in de
`shared/pagination.py:73-135`, errores `AppException(code=..., status_code=...)`
(`shared/exceptions.py:14-26`) y `require_role` como singleton de módulo
(`intake/router.py:30-34`).

Tres reglas irrenunciables atraviesan el diseño:

1. **`plan_activities` no tiene `organization_id` y no lo va a tener** (P7). El tenant es transitivo
   por `plan_id → plans.organization_id`. Es el mismo precedente que `tasks`, que resuelve su tenant
   por `project_id`. Consecuencia arquitectónica directa: el `JOIN plans` no puede ser una
   convención que cada consulta recuerda, tiene que ser **un solo punto compuesto por todas**
   (D-D).
2. **`null` no es `0`** (D3). Una actividad sin evidencia enlazada no dice «cero por ciento»; dice
   «no hay con qué sustentarlo». La frontera entre esas dos afirmaciones se define en **una** regla
   (`primary_total == 0 ⇒ None`) y se prueba en tres capas (D-F).
3. **El criterio de exclusión del avance está en movimiento** (R6): el 44 sustituye
   `Task.status != 'cancelled'` por `board_columns.excluded_from_progress` más
   `tasks.context_group IS NULL`. El 45a no lo redefine: lo consume desde **un único punto
   reemplazable** que además puede declarar los `JOIN` que el criterio nuevo necesite (D-E).

---

## Decisiones de arquitectura

### D-A · Migración `0028`: cinco `op.create_table` en orden de dependencia, cero `batch_alter_table`

**Cadena de revisiones vigente** (re-anclada por el orquestador el 2026-08-26):

| Cambio | Revisiones que reclama |
|---|---|
| 43-tareas-origen-externo | `0025` |
| 44-importar-checklist-xlsx | `0026` (`board_columns`) **y** `0027` (`tasks`) |
| **45a-planes-modelo-api** | **`0028`**, con `down_revision="0027"` |
| 40-jira-import-usuario | El siguiente consecutivo libre **en el momento de aplicarse** |

Se **elimina la reserva de `0026` para el 40**: ese cambio no entra en esta ola, y un
`down_revision` apuntando a una revisión que nadie va a crear rompería `alembic upgrade` en
despliegue, no en la prueba. Un número reservado para un cambio que no se aplica es un hueco en la
cadena, y la cadena de Alembic no tolera huecos. El 40 toma el consecutivo libre cuando llegue su
turno; el 45a se mueve de `0029` a `0028` sin renegociar una sola decisión de diseño (R2: el número
es una **reclamación**, no una promesa, y ya se ha movido dos veces).

**Elección**: un solo archivo, `0028_add_institutional_plans.py`, que crea las cinco tablas en
orden de dependencia (`plans` → `plan_activities` → `plan_activity_reports` →
`plan_activity_links` → `task_plan_activities`), declara **dentro** de cada `op.create_table` sus
`ForeignKeyConstraint`, `PrimaryKeyConstraint`, `UniqueConstraint` y el `CheckConstraint`, y crea
después los índices con `op.create_index(op.f(...))`. `downgrade()` invierte exactamente:
`drop_index` en orden inverso y `drop_table` de la quinta a la primera.

| Alternativa | Por qué se rechaza |
|---|---|
| Cinco migraciones, una por tabla | Cinco números reclamados en vez de uno multiplica por cinco la superficie de R2, y las cinco tablas no tienen valor por separado: `plan_activities` sin `plans` no es un estado de esquema útil |
| `op.create_check_constraint` después del `create_table` | La tabla es **nueva**: declarar el `CHECK` dentro del `create_table` produce el mismo `pg_get_constraintdef` y hace el espejo con `__table_args__` literal, no analógico |
| `batch_alter_table` | Cero apariciones en las 24 migraciones en disco; el proyecto es PostgreSQL exclusivo |
| Omitir los `op.drop_index` porque `drop_table` ya los borra | Cierto pero contra convención: `0019:293-320` los declara explícitamente y el diseño no introduce un dialecto propio en el archivo más sensible del cambio |

**Atomicidad (R10)**: Alembic corre la migración dentro de una transacción en PostgreSQL. Las cinco
tablas entran juntas o no entra ninguna; no existe un estado intermedio observable.

**Gotcha de `is_active`**: `SoftDeleteMixin` (`shared/base_model.py:39-43`) declara `is_active` con
`default=True` **de Python**, sin `server_default`. Igual que `intake_items` (`0019:102`), la
columna sale `nullable=False` sin valor por defecto en el motor. Toda siembra por SQL crudo dentro
de la prueba de migración **debe** informar `is_active` explícitamente o el `INSERT` falla.

### D-B · El gate real del espejado es la equivalencia de DDL, no `alembic check`

Se hereda literal la lección del 43 (D-B), verificada sobre `alembic==1.14.0`: `compare.py` no
contiene ni una aparición de `CheckConstraint`, y `ddl/postgresql.py:322-380` no compara
`postgresql_where`. El riesgo es un **falso negativo silencioso**: `ck_plan_activity_links_no_self`
podría existir solo en la migración, `alembic check` seguiría en verde y el arnés de pruebas —que
construye el esquema con `Base.metadata.create_all` (`tests/conftest.py:74-80`)— estaría validando
una regla distinta de la de producción, que es exactamente el escenario 4 de la spec.

**Elección**: `test_create_all_and_migration_declare_the_same_plans_ddl` levanta **dos** bases
desechables y compara, normalizadas, las cadenas que devuelven `pg_get_indexdef(indexrelid)` para
los **nueve** índices y `pg_get_constraintdef(oid)` para los cinco únicos y el `CHECK`. La cifra
es nueve en todo el documento —inventario, cobertura, rebanadas y `state.yaml`—: la novena entrada
es `ix_plans_organization_id`, que genera `TenantMixin` con `index=True` (H6).

El orden de la base construida por el ORM es **obligatorio y no opcional**:

```
CREATE EXTENSION IF NOT EXISTS pg_trgm   →   import app.db_init   →   Base.metadata.create_all
```

`import app.db_init` es lo que puebla `Base.metadata` con **todos** los modelos
(`db_init.py:41-96`; `conftest.py:66-69` lo hace por la misma razón). Sin él, `create_all`
construiría un esquema incompleto —sin `tasks`, sin `organizations`, sin `users`— y las FKs de las
cinco tablas nuevas ni siquiera podrían crearse: la comparación no sería laxa, sería imposible.
`pg_trgm` es obligatorio porque `projects`/`tasks` declaran índices GIN con `gin_trgm_ops`.

`alembic check` se conserva **solo** como guardia de existencia por nombre, con su alcance escrito.

### D-C · Las tres tablas hijas no llevan `SoftDeleteMixin`: desenlazar borra la fila

**Elección**: `plans` y `plan_activities` llevan los cinco mixins
(`PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin` + `TenantMixin` solo en `plans`).
`plan_activity_reports`, `plan_activity_links` y `task_plan_activities` llevan
`PkMixin, TimestampMixin, AuditMixin` y **no** `SoftDeleteMixin`: el `DELETE` de un enlace es
físico.

**Precedente exacto en el repositorio**: `TaskLabel` (`labels/models.py:43-55`) —«a surrogate
`PkMixin` id + a `UniqueConstraint`, no `SoftDeleteMixin` — unlinking a task/label pair removes the
row outright (hard delete), it is never soft-deleted itself»—. `TaskDependency`
(`task_links/models.py:23-35`) sí lo lleva, y la diferencia es reveladora: una dependencia entre
tareas es un hecho de negocio con historia; una fila de asociación no lo es.

> **Discrepancia documentada de la línea base (H8)**: `openspec/specs/labels/spec.md:12` describe
> `TaskLabel` como «Pk + Timestamp + SoftDelete», pero el código en disco
> (`labels/models.py:43`, `class TaskLabel(PkMixin, TimestampMixin, Base)`) **no** lleva
> `SoftDeleteMixin` y su propio docstring dice lo contrario. **El precedente que este diseño
> invoca es el código, no esa spec.** La corrección de `specs/labels/spec.md` es un cambio aparte:
> el 45a no toca una capacidad que no modifica.

**Razón técnica para los dos enlaces, no solo de convención**: con `SoftDeleteMixin`, el único
`uq_task_plan_activities_task_activity` retendría el par `(task, activity)` después de desenlazar,
y el siguiente `POST` del mismo par produciría un `UniqueViolation` → 500. Es el fallo que el 43
tuvo que corregir con su D-I. Aquí no se corrige: no se introduce. Lo mismo vale para
`uq_plan_activity_links_from_to_type`.

**Razón distinta para `plan_activity_reports` (H9)**: esa tabla **no tiene ninguna operación de
desenlace**, así que el argumento del único retenido no le aplica. Su justificación es otra y hay
que leerla aparte: **no existe `DELETE` de reportes en toda la superficie del cambio**. El único
camino de escritura es el `PUT` idempotente (D11), que reemplaza el valor del periodo **en la misma
fila** —`uq_plan_activity_reports_activity_period` garantiza que solo hay una—. Un
`SoftDeleteMixin` protegería un borrado que nunca ocurre y además abriría la puerta a que un
reporte «desactivado» conviviera con uno activo del mismo periodo, que es exactamente lo que la
spec (`:35`, «a lo sumo un reporte por combinación de actividad y periodo») prohíbe. `AuditMixin`
sí se conserva: `updated_by` y `updated_at` registran quién hizo la última afirmación y cuándo, que
es la trazabilidad que el reporte necesita.

| Alternativa | Por qué se rechaza |
|---|---|
| `SoftDeleteMixin` + único parcial `WHERE is_active` en las tres | Tres objetos de esquema más, tres predicados más que espejar y probar (D-B), y ningún requisito de la spec pide historial de enlaces. El 45a entrega el modelo, no una bitácora |
| `SoftDeleteMixin` sin tocar el único | El fallo descrito arriba, garantizado en el primer re-enlace legítimo |
| Quitar también `AuditMixin` de las tres | `plan_activity_reports` **necesita** `created_by`/`updated_by`: es la firma de quién afirmó el avance ante el SIG. Y la pregunta 1 de la ronda de propuesta depende de que exista |

La regla «NUNCA delete físico» de `CLAUDE.md` gobierna **agregados**, no filas de asociación; el
propio repositorio ya la interpreta así con `TaskLabel` y `UserRole`. Queda escrito para que nadie
lo lea como una desviación.

### D-D · El alcance de tenant es **una** función compuesta por todas las consultas, no una convención

**Elección**: el repositorio expone un único constructor de alcance y **ninguna** consulta escribe
su `JOIN plans` a mano.

```python
def _activity_scope(self, organization_id: uuid.UUID) -> Select[Any]:
    """The ONLY way this module reaches a `plan_activities` row.

    `plan_activities` has NO `organization_id` (P7): the tenant arrives
    transitively through `plan_id -> plans.organization_id`, exactly like
    `tasks` reaches it through `project_id`. Forgetting this JOIN in ONE
    read leaks rows across organizations (R5), so it is not a convention
    every query remembers — it is a single composable point.
    """
    return (
        select(PlanActivity)
        .join(Plan, Plan.id == PlanActivity.plan_id)
        .where(
            Plan.organization_id == organization_id,
            Plan.is_active.is_(True),
            PlanActivity.is_active.is_(True),
        )
    )
```

Toda lectura de actividad (`list_activities`, `get_activity`, `list_activity_tasks`,
`count_activities_by_group`, `list_links`) y **toda escritura** (`upsert_report`, `upsert_task_link`, `upsert_activity_link`,
`delete_*`) parte de aquí o de su gemelo puntual `_require_activity(organization_id, activity_id)`,
que devuelve `None` cuando la actividad no existe **o no es del tenant** — el servicio traduce las
dos situaciones al mismo `plan_activity_not_found` 404, que es lo que el escenario 16 exige.

| Alternativa | Por qué se rechaza |
|---|---|
| Denormalizar `organization_id` en `plan_activities` | **No lo exige ninguna regla** (H15): `agents/rules/solercia-persistence.md:42` pide «`organization_id` **or an equivalent tenant scope**», y el `JOIN plans` es exactamente ese alcance equivalente. El precedente as-built lo confirma: `openspec/specs/multi-tenancy/spec.md:24` — «Task, Sprint y User NO llevan `organization_id`; su scope se deriva por join (Task/Sprint → Project)». Denormalizar sería la desviación, no cumplir la regla, y crearía la posibilidad de que la columna y el plan discrepen: dos verdades sobre el mismo hecho |
| Recordar el `JOIN` en cada consulta | Es exactamente el modo de fallo de R5. **Once** consultas de lectura —`list_plans`, `get_plan`, `count_activities_by_group` (H13), `list_activities`, `get_activity`, `list_activity_tasks` (H4), `list_links`, `rollup_activity_progress`, `list_reports_for_period`, `_require_activity` y `get_link`— × un olvido = una fuga |
| Un filtro global de SQLAlchemy (`with_loader_criteria`) | Invisible en el punto de uso, no aplica a `select()` explícitos con `join()` manual y ninguna otra parte del repositorio lo usa: introduciría un mecanismo propio en el módulo más sensible |

La prueba de aislamiento **por endpoint** (P7, R5) se conserva igual: centralizar reduce la
probabilidad del fallo, no autoriza a dejar de comprobarlo.

### D-E · El criterio de exclusión del avance es un punto único que puede traer sus propios `JOIN`

**Elección**: `backend/app/modules/plans/progress.py` con **una** función y un valor de retorno que
lleva predicado **y** joins:

```python
@dataclass(frozen=True)
class ProgressDenominator:
    """What "counts toward plan progress" — predicate AND the joins it needs."""

    predicate: ColumnElement[bool]
    extra_joins: tuple[tuple[Any, ColumnElement[bool]], ...] = ()


def progress_denominator() -> ProgressDenominator:
    """THE single definition of a countable `primary` task (design.md D-E).

    Current criterion, mirroring `projects/repository.py:330,335-338` at the
    time this module was written: a task counts unless its status is the
    literal ``'cancelled'``.

    Change 44 replaces that literal with `board_columns.excluded_from_progress`
    plus `tasks.context_group IS NULL` (44/specs/project-hierarchy/spec.md).
    That criterion needs a LEFT JOIN this one does not, which is WHY this
    returns joins together with the predicate: whoever applies 44 edits THIS
    function and nothing else, and `test_progress_denominator_matches_the_
    current_criterion` is the single test that must change with it.
    """
    return ProgressDenominator(predicate=Task.status != "cancelled")
```

| Alternativa | Por qué se rechaza |
|---|---|
| Repetir el literal `'cancelled'` dentro del CTE | R6 se materializa como una divergencia silenciosa: el 44 cambia `projects` y el avance de planes queda midiendo otra cosa que el avance de proyectos, sin que nada falle |
| Importar el predicado desde `projects/repository.py` | Crea la dependencia `plans → projects` para una constante, y el punto que el 44 edita es una consulta, no un símbolo exportable |
| Devolver solo el predicado (`ColumnElement[bool]`) | El criterio del 44 necesita `LEFT JOIN board_columns ON board_columns.id = tasks.board_column_id` (nulable: hay tareas fuera de tablero). Un retorno solo-predicado obligaría a editar además el CTE, y el «único punto» dejaría de serlo justo cuando importa |
| Esperar al 44 | Ninguno bloquea al otro (R6). El 45a usa el criterio **vigente al momento de su apply** y lo deja aislado |

**Nota de coordinación cruzada**: queda escrita en ambos cambios. Quien aplique segundo edita
`progress_denominator()` (si es el 44) o el CTE de `projects` (si es el 45a), no ambos a ciegas.

### D-F · Doble avance: una sola regla para `null`, y el periodo no se adivina

**Elección**:

| Valor | Regla exacta |
|---|---|
| `primary_task_count` | Enlaces `role='primary'` cuya tarea está activa, su proyecto activo y del tenant, y satisface `progress_denominator()` |
| `calculated_progress` | `None` cuando `primary_task_count == 0`; en cualquier otro caso `done / primary_task_count` como `float` |
| `done` | De ese mismo conjunto, las tareas cuyo `status` coincide con el `status_key` de la última columna activa del board **del proyecto de esa tarea** |
| `contributing_task_count` | Enlaces `role='contributes'` con tarea activa. **No** pasa por `progress_denominator()`: es un conteo informativo, no un denominador |
| `reported_progress` | El valor del periodo **consultado**; `None` si ese periodo no tiene fila |
| `reported_period` | Eco del periodo al que corresponde el valor; `None` cuando no se consultó ninguno |

Tres consecuencias que hay que leer despacio:

1. **`primary_task_count == 0` cubre dos casos y devuelve `None` en ambos**: la actividad sin
   ningún enlace `primary` (escenario 12) y la actividad cuyos enlaces `primary` existen pero
   ninguno es contable (todas sus tareas inactivas o excluidas). Los dos significan lo mismo —«no
   hay evidencia contable»— y colapsar el segundo a `0` sería la misma afirmación falsa que R7
   describe. Además elimina por construcción la división por cero.
2. **Sin `?period=`, `reported_progress` es `None`; el sistema no elige un periodo por el usuario.**
   La spec lo respalda literalmente (`specs/institutional-plans/spec.md:86`): «El avance reportado
   DEBE ser el valor registrado para **el periodo consultado**, o ausencia de dato si ese periodo no
   tiene reporte». Devolver «el último periodo con reporte» sería inventar una semántica que ningún
   requisito pide y que ante Control Interno equivale a presentar el dato del cuatrimestre I como si
   fuera el del II. `reported_period` viaja en la respuesta para que el 45c nunca tenga que suponer
   de dónde salió el número.

   > **Corrección declarada de D2 (H1)**. La redacción de D2 en la exploración decía que «el avance
   > reportado vigente se calcula como **el último periodo con reporte**». Esa frase queda
   > **corregida por D-F**: sin `?period=` no hay avance reportado, es `null`. D2 sigue vigente en
   > todo lo demás —cinco tablas, `external_codes` plural, sin `reported_progress` redundante en
   > `plan_activities`, sin `reported_at`/`reported_by`, `resolution`/`source_reference`, `CHECK`
   > anti-autorreferencia y tenant transitivo—; lo único que cae es la regla de selección
   > automática de periodo, porque contradice `spec.md:86`. El texto de D2 en `state.yaml` queda
   > actualizado en consecuencia.

3. **El `period` recibido se valida contra el vocabulario cerrado y contra nada más.** No se
   contrasta con `scheduled_periods` de la actividad ni con el `plan_type` de su plan: ningún
   requisito de la spec lo pide y hacerlo convertiría un dato descriptivo de la fuente en una
   restricción de escritura que el importador del 45b no puede garantizar. Queda como **riesgo
   aceptado y escrito** (R14, H12), no como omisión.

### D-G · Roll-up cruzado: **una** consulta por lote, con `FILTER` en vez de tres consultas

**Elección**: `rollup_activity_progress(organization_id, activity_ids)` resuelve los tres
agregados de N actividades en **una** consulta agregada, con el CTE `last_column` unido por
`board.project_id = task.project_id` (no filtrado a un proyecto).

```python
async def rollup_activity_progress(
    self,
    organization_id: uuid.UUID,
    activity_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int, int, int]]:
    """Return ``{activity_id: (done, primary_total, contributing_total)}``.

    ONE query for the WHOLE batch (R8): the 62 real activities (25 PSPI + 26
    PTR + 11 PAI) cost one round trip, not 62. Activities with no countable
    link simply DO NOT APPEAR in the mapping; the SERVICE turns absence into
    ``calculated_progress = None``, never ``0`` (design.md D-F).

    This is NEW SQL, not a reuse of ``projects/repository.py:290-350``: that
    roll-up is bound to ONE project's subtree (``Board.project_id.in_(
    subtree_ids)``), while a plan activity groups tasks from DIFFERENT
    projects, each with its own board and its own last column (R3). The CTE
    below keeps the ``DISTINCT ON (board.project_id) ... ORDER BY
    column_order DESC, created_at DESC`` rule verbatim and joins it by
    ``last_column.project_id = task.project_id``.

    Tenant is transitive and DOUBLE-checked: through ``plans`` for the
    activity side and through ``projects`` for the task side. Does NOT commit.
    """

    last_column = (
        select(
            Board.project_id.label("project_id"),
            BoardColumn.status_key.label("status_key"),
        )
        .distinct(Board.project_id)
        .select_from(Board)
        .join(BoardColumn, BoardColumn.board_id == Board.id)
        .where(Board.is_active.is_(True), BoardColumn.is_active.is_(True))
        .order_by(
            Board.project_id,
            BoardColumn.order.desc(),
            BoardColumn.created_at.desc(),
        )
        .subquery("last_column")
    )

    denominator = progress_denominator()          # design.md D-E
    is_primary = TaskPlanActivity.role == "primary"
    countable = and_(is_primary, denominator.predicate)

    stmt = (
        select(
            TaskPlanActivity.plan_activity_id.label("activity_id"),
            func.count(Task.id)
            .filter(countable, Task.status == last_column.c.status_key)
            .label("done"),
            func.count(Task.id).filter(countable).label("primary_total"),
            func.count(Task.id)
            .filter(TaskPlanActivity.role == "contributes")
            .label("contributing_total"),
        )
        .select_from(TaskPlanActivity)
        .join(PlanActivity, PlanActivity.id == TaskPlanActivity.plan_activity_id)
        .join(Plan, Plan.id == PlanActivity.plan_id)
        .join(Task, Task.id == TaskPlanActivity.task_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(last_column, last_column.c.project_id == Task.project_id)
        .where(
            TaskPlanActivity.plan_activity_id.in_(activity_ids),
            Plan.organization_id == organization_id,
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
            Task.is_active.is_(True),
        )
        .group_by(TaskPlanActivity.plan_activity_id)
    )
    for target, onclause in denominator.extra_joins:
        stmt = stmt.outerjoin(target, onclause)
    ...
```

`func.count(...).filter(...)` genera `count(...) FILTER (WHERE ...)`, que es lo que ya usa
`rollup_progress` (`projects/repository.py:335-338`): no es una construcción nueva para el
repositorio.

**El roll-up no lee `plan_activity_links` (H3).** Sus únicas tablas son `task_plan_activities`,
`plan_activities`, `plans`, `tasks`, `projects` y el CTE `last_column`. Es la razón estructural —no
una disciplina— por la que un enlace actividad↔actividad con `resolution='conflict'` **no puede**
alterar ningún avance: la consulta que calcula el avance ni siquiera visita esa tabla. La spec
(`:49`) exige que un enlace en conflicto sea consultable pero nunca cuente como confirmado; aquí
«no cuenta» está garantizado por el `FROM`, y «confirmado» se expone como el campo derivado
`is_confirmed` del esquema de lectura (D-I).

**Coste total de un listado de N actividades: tres consultas fijas**, no `1 + 3N`:

| # | Consulta | Devuelve |
|---|---|---|
| 1 | Página de actividades (`_activity_scope` + filtros + paginación opt-in) | Las filas y `plans.code` para el `activity_key` |
| 2 | `rollup_activity_progress(org, ids)` | `(done, primary_total, contributing_total)` por actividad |
| 3 | `list_reports_for_period(org, ids, period)` — **solo si viene `?period=`** | `reported_progress` por actividad |

| Alternativa | Por qué se rechaza |
|---|---|
| Una consulta por actividad | R8 literal: 62 idas y vueltas para pintar una vista |
| Tres consultas agregadas separadas (una por métrica) | Tres recorridos del mismo `JOIN` de cinco tablas para lo que `FILTER` resuelve en uno |
| Reutilizar `ProjectRepository.rollup_progress` | Su CTE filtra `Board.project_id.in_(subtree_ids)`: por construcción no puede ver dos proyectos no emparentados (R3). Y crearía la dependencia `plans → projects` sobre una firma que no encaja |
| Vista materializada o columna calculada | El avance calculado es una **lectura derivada**: no hay dato que invalidar ni que reparar (plan de reversa de la propuesta). Persistirlo introduce el problema de la coherencia sin resolver ninguno |

### D-H · Cero `relationship()` en los cinco modelos

**Elección**: ningún modelo del módulo declara `relationship()`. Toda navegación entre las cinco
tablas es un `JOIN` explícito del repositorio.

**Justificación**, en tres hechos concretos:

1. El `JOIN plans` **nunca es opcional** (D-D): el tenant obliga a escribirlo en toda lectura. Una
   `relationship()` que nadie puede usar sin repetir ese `JOIN` no ahorra nada.
2. En SQLAlchemy async, un acceso perezoso a una `relationship()` no cargada **falla en ejecución**
   (`MissingGreenlet`). Es el mismo argumento que D9 usó para no embeber planes en `TaskRead`:
   una relación declarada y no cargada es un arma cargada apuntando a cada camino de lectura.
3. El borrado en cascada lo declara PostgreSQL en la FK (`ON DELETE CASCADE`), no el ORM: no hace
   falta `cascade="all, delete-orphan"` para que la semántica exista.

**Consecuencia sobre el cableado**: el import en `db_init.py:41-96` con `# noqa: F401` **sigue
siendo obligatorio**, pero por la razón correcta —poblar `Base.metadata` para `create_all`
(`conftest.py:66-69`)—, no «para que las `relationship()` por cadena resuelvan», que es como lo
describía la propuesta. Es una precisión declarada, no un cambio de alcance.

### D-I · Esquemas Pydantic: campos derivados transitorios sobre `from_attributes`, sin relaciones embebidas

**Elección**: cada esquema de lectura declara `ConfigDict(from_attributes=True)` y se construye con
`model_validate(orm_row)`; los campos derivados se asignan **después**, en el servicio, con valor
por defecto en el esquema. Es literalmente el patrón `task_key` (`tasks/schemas.py:126-127` +
`tasks/service.py:965-968`).

```python
class PlanActivityRead(BaseModel):
    """One plan activity as the API exposes it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    code: str
    group_code: str | None = None
    group_name: str | None = None
    name: str
    deliverable: str | None = None
    evidence_expected: str | None = None
    responsible: str | None = None
    is_mine: bool = False
    due_date: date | None = None
    target_from: Decimal | None = None
    target_to: Decimal | None = None
    iso_controls: list[str] | None = None
    external_codes: list[str] | None = None      # PLURAL (D2)
    scheduled_periods: list[str] | None = None
    sort_order: int = 0
    created_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None

    # --- Derived, NEVER columns. Set transiently by PlansService, same
    # --- pattern as TaskRead.task_key (tasks/service.py:965-968).
    activity_key: str | None = None              # "PSPI-2026/1.1"  (D1)
    calculated_progress: float | None = None     # None != 0        (D3, D-F)
    primary_task_count: int = 0
    contributing_task_count: int = 0
    reported_progress: Decimal | None = None     # of `reported_period`
    reported_period: str | None = None
```

`PlanActivityDetailRead(PlanActivityRead)` agrega `reports`, `links_out` y `links_in`, y **solo se
usa en el detalle**: el listado devuelve `PlanActivityRead` sin colecciones, para que ninguna
respuesta de lista pueda degradarse en N+1 por la forma del esquema (R8, D9).

#### `PlanActivityLinkRead.is_confirmed` — el conflicto se lee, no se interpreta (H3)

```python
class PlanActivityLinkRead(BaseModel):
    """One activity<->activity link, with its resolution kept readable."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID
    link_type: str
    source_reference: str | None = None
    resolution: str

    # --- Derived, NEVER a column. Assigned by PlansService right after
    # --- model_validate, same transient pattern as activity_key.
    #     is_confirmed = resolution != "conflict"
    is_confirmed: bool = True
```

La regla es **una sola línea y vive en un solo sitio**: `is_confirmed = resolution != "conflict"`.
Los cuatro valores del vocabulario se reparten así: `exact`, `by_external_code` y `manual` son
enlaces confirmados; `conflict` es el único que no lo es. Se expone como campo derivado y no se
deja al cliente comparar cadenas, porque «no contarlo como confirmado» es una regla de dominio y
el 45c no debe reimplementarla en TypeScript. La spec (`:49`) exige exactamente las dos mitades:
**visible** (el enlace aparece en `links_out`/`links_in` con su `resolution`) y **no confirmado**
(`is_confirmed=false`). El escenario 8 se ancla a este campo: un enlace `conflict` se lista con
`is_confirmed=false`, y el 45c lo pintará con distintivo de advertencia. Ningún cálculo de avance
lo consulta, porque el roll-up no visita `plan_activity_links` (D-G).

#### `ActivityTaskRead` — el lado de la tarea, en **una** consulta (H4)

```python
class ActivityTaskRead(BaseModel):
    """One task linked to a plan activity, as `GET .../tasks` exposes it."""

    model_config = ConfigDict(from_attributes=True)

    task_id: uuid.UUID
    task_key: str | None = None          # "SDM-7"  (tasks/service.py:965-968)
    project_code: str
    project_name: str
    status: str
    role: str                            # `primary` | `contributes`
    note: str | None = None
    # True when this task is `primary` AND satisfies progress_denominator():
    # i.e. it is one of the rows the ratio of D-F actually counts.
    counts_toward_progress: bool = False
```

`GET /plans/activities/{activity_id}/tasks` se resuelve con **una** consulta del repositorio,
`list_activity_tasks(organization_id, activity_id, role=None)`, no con un listado de enlaces más
una lectura de tarea por fila. La consulta parte de `_require_activity` (D-D) y añade:

- `JOIN Task ON Task.id = TaskPlanActivity.task_id`;
- `JOIN Project ON Project.id = Task.project_id`, con **`Project.organization_id` en el `WHERE`**
  —el tenant se comprueba dos veces, igual que en el roll-up (D-G)—, y `Project.code` /
  `Project.name` seleccionados para armar `task_key` y las dos columnas de proyecto sin una segunda
  ida a la base;
- `outerjoin` del mismo CTE `last_column` unido por `last_column.project_id = Task.project_id`, que
  es lo que permite decidir `counts_toward_progress` **con el board de cada tarea** y no con el de
  un proyecto elegido de antemano (R3);
- el predicado y los `extra_joins` de `progress_denominator()` (D-E), de modo que
  `counts_toward_progress` sea **por construcción** el mismo conjunto que el denominador de D-F: si
  el 44 mueve el criterio, las dos cifras se mueven juntas o ninguna.

La prueba que lo protege no es de resultado sino de **forma**: `test_list_activity_tasks_is_a_single_query`
cuenta las sentencias emitidas con un `before_cursor_execute` de SQLAlchemy sobre la conexión de la
fixture y exige exactamente una, además de comprobar que `counts_toward_progress` coincide, tarea a
tarea, con lo que `progress_denominator()` deja dentro del denominador. Sin esa prueba, un N+1
introducido después no rompería ninguna aserción de valor.

#### `PlanDetailRead` — el conteo por grupo es del repositorio, no del servicio (H13)

```python
class PlanRead(BaseModel):
    """One institutional plan as the API exposes it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    plan_type: str
    period_year: int
    version: str | None = None
    source_document: str | None = None
    status: str
    created_at: datetime


class PlanActivityGroupCount(BaseModel):
    """Activity count of ONE group inside a plan."""

    group_code: str | None = None
    group_name: str | None = None
    activity_count: int


class PlanDetailRead(PlanRead):
    """`GET /plans/{plan_id}`: the plan plus its per-group activity counts."""

    activity_count: int = 0
    groups: list[PlanActivityGroupCount] = []
```

El escenario 1 se ancla aquí: «la respuesta expone el código, el tipo, el año y **el conteo de
actividades por grupo**» (`spec.md:16`). El conteo lo produce `count_activities_by_group(org,
plan_id)` en el repositorio —un `GROUP BY (group_code, group_name)` con `count(*)` sobre
`_activity_scope`—, **no** el servicio contando en Python sobre una lista de actividades cargada
entera: un plan de 110 actividades no se trae a memoria para responder seis números.

Esquemas de escritura: `PlanActivityReportUpsert`, `TaskLinkCreate`, `ActivityLinkCreate`.
Esquemas **solo de costura**, sin ruta HTTP: `PlanUpsert`, `PlanActivityUpsert` (D10).

**`ActivityLinkCreate` no declara `resolution`** (D14). Pydantic v2 usa `extra="ignore"` por
defecto, así que un cliente que envíe `{"to_activity_id": ..., "link_type": ...,
"resolution": "exact"}` recibe su enlace creado con `resolution='manual'` y sin error de
validación. Es el mismo comportamiento que el 43 razonó en su D-F: rechazar con 422 cambiaría el
contrato para *cualquier* campo desconocido, y la protección estructural —el campo no existe en el
esquema, así que nunca llega al `dict`— es más fuerte que una defensa explícita.

### D-J · Vocabularios cerrados en `plans/vocabularies.py`, no en `service.py` ni en `shared/enums.py`

**Elección**: un módulo pequeño con seis `frozenset[str]` y sus validadores puros.

**Precedentes, separando lo que está en disco de lo que todavía no (H7)**:

| Precedente | Estado | Qué respalda exactamente |
|---|---|---|
| `backend/app/modules/search/schemas.py:15` — `ENTITY_TYPES: frozenset[str] = frozenset({"task", "project", "comment"})` | **Vigente, en disco** | La forma literal: vocabulario cerrado como `frozenset[str]` de módulo, anotado y sin `Enum` |
| `backend/app/modules/activity/recorder.py:23-24` — `ACTOR_TYPE_USER` / `ACTOR_TYPE_SYSTEM` | **Vigente, en disco** | Que un módulo puede tener archivos **fuera** del quinteto `models/schemas/repository/service/router`, y que ese archivo extra es un sitio legítimo para las constantes de un vocabulario cerrado |
| `backend/app/modules/tasks/sources.py` (43, D-C) | **Planificado, cero archivos en disco** | La agrupación de varios vocabularios de un mismo módulo en un archivo propio. Se cita como convergencia con un cambio hermano, **no** como precedente ya establecido |

La distinción importa: si el 43 se archivara sin entregar `sources.py`, D-J seguiría en pie sobre
los dos precedentes vigentes.

| Vocabulario | Valores | Dónde se valida |
|---|---|---|
| `PLAN_TYPES` | `pspi`, `ptr`, `pai`, `ptep` (P1: los cuatro desde el día uno) | Costura de escritura + filtro `?plan_type=` |
| `PLAN_STATUSES` | `active`, `archived` | Costura + filtro `?status=` |
| `REPORT_PERIODS` | `I`, `II`, `III`, `ANUAL` | `PUT .../reports/{period}` y filtro `?period=` |
| `TASK_LINK_ROLES` | `primary`, `contributes` | `POST .../tasks` y filtro `?role=` |
| `ACTIVITY_LINK_TYPES` | `contributes_to`, `derives_from`, `duplicates` | `POST .../links` |
| `LINK_RESOLUTIONS` | `exact`, `by_external_code`, `conflict`, `manual` | **Solo** la costura; la API nunca lo acepta (D14) |

Más `validate_reported_progress(value)`, que exige `0 ≤ value ≤ 100` y lanza
`plan_progress_out_of_range` (422).

| Alternativa | Por qué se rechaza |
|---|---|
| `SAEnum` / enum nativo de PostgreSQL | D12: una migración por cada valor nuevo. `connectors.provider` lo declara explícitamente como antipatrón en su propio comentario |
| Constantes dentro de `service.py` | El importador del 45b tendría que importar el servicio completo —con su sesión y sus dependencias— para leer un `frozenset` |
| `app/shared/enums.py` | Ese archivo aloja `Enum` de Python usados como `SAEnum`; estos no son enumerados sino vocabularios abiertos por diseño |
| `ge=0, le=100` en el esquema Pydantic en lugar de `validate_reported_progress` | El código de error sería `validation_error`, no uno estable y propio; y la costura de escritura del 45b no pasa por el esquema HTTP, así que el rango quedaría sin defender justo donde entran 62 valores de golpe |
| Un `CHECK (reported_progress BETWEEN 0 AND 100)` en la base | El alcance ratificado fija **un** `CHECK` (`state.yaml.boundary`). Agregar un sexto objeto de esquema no pedido por ningún requisito se sale del alcance; `Numeric(5,2)` ya acota la magnitud. Queda anotado como mejora barata para el 45b si la práctica lo exige |

### D-K · Códigos de error estables en `lower_snake_case`

Convención del repositorio verificada (`shared/exceptions.py:20`, valor por defecto `app_error`;
los 25 códigos de `tasks/service.py` son todos `lower_snake_case`). El ejemplo en mayúsculas de
`CLAUDE.md` no coincide con el código real; manda el código.

| Código | HTTP | Cuándo |
|---|---|---|
| `plan_not_found` | 404 | Plan inexistente o de otra organización |
| `plan_activity_not_found` | 404 | Actividad inexistente o de otra organización (escenario 16). **También cuando el `to_activity_id` de un enlace lo es** (H11) |
| `plan_task_not_found` | 404 | La tarea a enlazar no existe o no es del tenant (escenario 18) |
| `plan_task_link_not_found` | 404 | `DELETE` de un enlace tarea↔actividad inexistente |
| `plan_activity_link_not_found` | 404 | `DELETE` de un enlace actividad↔actividad inexistente |
| `plan_task_link_duplicate` | 409 | Segundo `POST` del mismo par `(task, activity)` |
| `plan_activity_link_duplicate` | 409 | Segundo `POST` del mismo `(from, to, link_type)` |
| `plan_activity_self_link` | 422 | `to_activity_id == activity_id` |
| `plan_period_invalid` | 422 | `period` fuera de `{I, II, III, ANUAL}` |
| `plan_progress_out_of_range` | 422 | `reported_progress` fuera de `[0, 100]` |
| `plan_task_link_role_invalid` | 422 | `role` fuera de `{primary, contributes}` |
| `plan_activity_link_type_invalid` | 422 | `link_type` fuera del vocabulario |
| `plan_type_invalid` · `plan_status_invalid` · `plan_resolution_invalid` | 422 | Filtros y costura de escritura |
| `invalid_sort_field` | 422 | Reutilizado de `shared/pagination.py:88-103` |

**El 409 es un error de dominio, y la carrera cae en el mismo 409 (H10).** El mecanismo de
detección es el servicio: consulta el enlace antes de insertar y lanza el `AppException`. Pero
«consultar y luego insertar» no es atómico, y dos peticiones concurrentes del mismo par pasan las
dos la consulta y solo una gana el `INSERT`. La perdedora recibiría un `IntegrityError` de
SQLAlchemy —`UniqueViolation` de `asyncpg` por debajo— que, sin capturar, sale como **500**: un
fallo del servidor por una petición perfectamente válida del cliente.

Por eso el servicio envuelve el `flush`/`commit` de los dos `POST` de enlace:

```python
try:
    await self.repo.upsert_task_link(activity_id, data)
    await self.db.commit()
except IntegrityError as exc:                      # design.md D-K (H10)
    # Lost the race: another request inserted the SAME pair between our
    # SELECT and our INSERT. It is the SAME business fact as the check
    # above, so it MUST surface as the SAME domain error — never a 500.
    await self.db.rollback()
    raise AppException(
        "La tarea ya está enlazada a esta actividad.",
        code="plan_task_link_duplicate",
        status_code=409,
    ) from exc
```

Idéntico para `plan_activity_link_duplicate`. La consulta previa **no** se elimina: sigue siendo el
camino normal y el que produce el mensaje correcto sin ensuciar la transacción; el `except` es la
red de seguridad. Prueba nombrada: `test_concurrent_duplicate_link_surfaces_409_not_500`, que
simula la carrera insertando el par por una segunda sesión entre la comprobación y la escritura.

**El 422 de autorreferencia también es de servicio.** El `CHECK` del motor existe (escenario 7 lo
exige en el esquema y la prueba de migración lo ejercita con `asyncpg.exceptions.CheckViolation`),
pero la API responde `plan_activity_self_link` sin llegar a la base.

**El destino de un enlace actividad↔actividad se valida como el origen (H11).** `to_activity_id`
**no** se acepta por existir: pasa por el mismo `_require_activity(organization_id, to_activity_id)`
que el origen (D-D), así que una actividad de otra organización —o inexistente— responde
`plan_activity_not_found` 404 y jamás se crea el enlace. Sin esa comprobación, `plan_activity_links`
sería el único camino del módulo capaz de cruzar la frontera de tenant, porque el `CHECK` solo
prohíbe la autorreferencia y las dos FK apuntan a la misma tabla sin decir nada del plan
propietario. La aserción se añade a la prueba del escenario 24
(`test_api_forces_resolution_manual_whatever_the_client_sends`), que ya construye un enlace por
API: se le suma el caso de un `to_activity_id` ajeno respondiendo 404.

### D-L · Router: el orden de declaración es una decisión de diseño, no un detalle

**Elección**: la familia completa `/plans/activities…` se declara **antes** de `/plans/{plan_id}`.
FastAPI resuelve por orden de declaración: con el orden inverso, `GET /plans/activities` entraría
por `/plans/{plan_id}`, intentaría convertir `"activities"` en `UUID` y devolvería 422 en lugar de
la lista. Es el escenario 21 de la spec y por eso tiene prueba propia, no solo un comentario.

Orden literal del archivo:

```
1  GET    /plans/activities                                   (miembro)
2  GET    /plans/activities/{activity_id}                     (miembro)
3  GET    /plans/activities/{activity_id}/tasks               (miembro)
4  PUT    /plans/activities/{activity_id}/reports/{period}    (admin·manager)
5  POST   /plans/activities/{activity_id}/tasks               (admin·manager)
6  DELETE /plans/activities/{activity_id}/tasks/{task_id}     (admin·manager)
7  POST   /plans/activities/{activity_id}/links               (admin·manager)
8  DELETE /plans/activities/{activity_id}/links/{link_id}     (admin·manager)
9  GET    /plans                                              (miembro)
10 GET    /plans/{plan_id}                                    (miembro)
```

`require_role(MemberRole.admin, MemberRole.manager)` se declara **una vez** como singleton de
módulo (`intake/router.py:30-34`, mismo motivo: `ruff B008`). Lectura con
`Depends(get_current_membership)`. Todo endpoint lleva docstring para Swagger
(`CLAUDE.md`, «Todo endpoint debe tener docstring»). Los dos `DELETE` responden **204** sin cuerpo.

Envelope `{data, message?, meta?}` y paginación opt-in (`shared/pagination.py:1-9`): sin `page` ni
`sort` la respuesta es la colección completa con `meta={"total": n}`. **Gotcha**: el repositorio
construye el `Select` **sin** `order_by` y decide después —orden natural en el camino no paginado,
`paginate(...)` en el paginado—, porque `stmt.order_by(...)` **agrega** cláusulas en vez de
reemplazarlas y encadenar ambas produciría un `ORDER BY` contradictorio.

| Listado | Orden natural (sin paginar) | `SORTABLE_FIELDS` (primera clave = orden por defecto al paginar) |
|---|---|---|
| `GET /plans` | `period_year desc, code asc` | `period_year`, `code`, `name`, `created_at` |
| `GET /plans/activities` | `sort_order asc, code asc` | `sort_order`, `code`, `due_date`, `created_at` |
| `GET /plans/activities/{id}/tasks` | `role asc, created_at asc` | No pagina: colección acotada por construcción. Se sirve con **una** consulta, `list_activity_tasks` (D-I/H4), y devuelve `ActivityTaskRead` con `counts_toward_progress` |

### D-M · La costura de escritura vive en el repositorio y **no** hace commit

**Elección**: cinco métodos de creación-o-actualización idempotente en `PlansRepository`, ninguno
con `commit`, `rollback` ni `flush` autónomo: `upsert_plan`, `upsert_activity`, `upsert_report`,
`upsert_activity_link`, `upsert_task_link`. El **servicio** (caso de uso) es quien confirma.

```python
async def upsert_activity(
    self,
    plan_id: uuid.UUID,
    data: PlanActivityUpsert,
) -> PlanActivity:
    """Create or update the activity identified by ``(plan_id, code)``.

    THE write seam of the aggregate (design.md D10): there is no HTTP route
    that creates a plan or an activity, because the authority of a Decreto
    612 plan is its source document, not a form. Change 45b's importer is the
    only consumer; delivering the seam HERE means its tests exercise the same
    path production uses (the mistake change 43 fixed with its D-G).

    Idempotent by ``uq_plan_activities_plan_code``: running it twice with the
    same data creates NO second row and raises NO error.

    NEVER commits (agents/rules/solercia-persistence.md:41): the caller owns
    the transaction, which is what lets an importer write a whole plan —
    activities, reports and links — atomically.
    """
```

**Desviación observada y no propagada**: `TaskRepository.create` sí comitea
(`tasks/repository.py:229-242`, documentado en el 43, D-D). Es una desviación preexistente de ese
módulo; `plans` nace cumpliendo la regla y no la hereda.

| Alternativa | Por qué se rechaza |
|---|---|
| `POST /plans` + `POST /plans/{id}/activities` | D10, dos razones: crea una segunda ruta de autoría que divergiría del documento fuente, y choca con la idempotencia por `(plan.code, activity.code)` del importador. La spec lo prueba (escenario 29) |
| Dejar la costura para el 45b | Las pruebas del 45a tendrían que sembrar por `INSERT` crudo, es decir, probar contra un camino que la aplicación no usa. Es el error que el 43 corrigió con D-G |
| `ON CONFLICT DO UPDATE` de PostgreSQL | Requiere `postgresql.insert` y devuelve la fila sin sesión ORM detrás; el `SELECT`-luego-`INSERT/UPDATE` dentro de la transacción del caso de uso es suficiente para un importador de 62 filas y es legible. Si el volumen creciera, el cambio queda confinado al adaptador (`solercia-persistence.md:45`) |

### D-N · Frontera ADR 0009 escrita en el esquema, no solo en la prosa

**Elección**: `PlanActivityReportUpsert` declara exactamente cinco campos —`reported_progress`,
`qualitative_summary`, `evidence_refs`, `is_met`, `met_on_time`— y `plan_activity_reports` tiene
exactamente esas cinco columnas de negocio. Las columnas `AA` (monitoreo cualitativo), `AB`
(evaluación independiente) y `AC` (observaciones-recomendaciones) del PAI **no existen** en el
modelo.

`docs/adr/0009-solercia-command-connect-data-conventions.md:78-80,238-240` reserva a Solercia
Security la autoridad sobre cumplimiento, validación y cierre de evidencia. Command guarda la
**primera línea de defensa**: lo que el responsable afirma. La segunda y la tercera son de otro
producto.

La guardia es una prueba de unidad pura sobre los campos del esquema (escenario 30), no un
comentario: R9 describe exactamente la tentación de agregarlas «porque están en la misma hoja».

---

## Estructura de módulos

| Archivo | Acción | Contenido |
|---|---|---|
| `backend/alembic/versions/0028_add_institutional_plans.py` | Crear | 5 tablas, 10 FKs `ON DELETE CASCADE`/`SET NULL`, 5 únicos, 9 índices, 1 `CHECK` |
| `backend/app/modules/plans/__init__.py` | Crear | Módulo |
| `backend/app/modules/plans/models.py` | Crear | 5 modelos, espejo literal en `__table_args__`, cero `relationship()` (D-H) |
| `backend/app/modules/plans/vocabularies.py` | Crear | 6 `frozenset` + validadores puros (D-J) |
| `backend/app/modules/plans/progress.py` | Crear | `ProgressDenominator` + `progress_denominator()` (D-E) |
| `backend/app/modules/plans/schemas.py` | Crear | Lectura, escritura y esquemas de costura (D-I) |
| `backend/app/modules/plans/repository.py` | Crear | `_activity_scope`, `_require_activity`, roll-up por lote, `list_activity_tasks` en una consulta (D-I/H4), `count_activities_by_group` (D-I/H13), `list_reports_for_period`, 5 `upsert_*`, `delete_*`, `SORTABLE_FIELDS` |
| `backend/app/modules/plans/service.py` | Crear | `activity_key`, doble avance, `is_confirmed`, vocabularios, `resolution='manual'`, captura de `IntegrityError` → 409 (H10), transacción |
| `backend/app/modules/plans/router.py` | Crear | 10 endpoints en el orden de D-L + `require_role` singleton |
| `backend/app/main.py:14-53,158-192` | Modificar | 1 import + 1 `include_router(plans_router, prefix=API_PREFIX)` **después** de `assistant_router` (`:192`, del 48) |
| `backend/app/db_init.py:41-96` | Modificar | Import de los 5 modelos con `# noqa: F401` |
| `backend/tests/test_migration_institutional_plans.py` | Crear | Base desechable + `downgrade` + equivalencia de DDL |
| `backend/tests/test_plans_repository.py` | Crear | Roll-up cruzado, costura idempotente y JSONB contra PostgreSQL real |
| `backend/tests/test_plans_service.py` | Crear | Fakes: `activity_key`, `null ≠ 0`, vocabularios, `resolution` |
| `backend/tests/test_plans_endpoints.py` | Crear | Los 10 endpoints, RBAC, tenant, 404/409/422, orden de rutas |

**Conteo exacto del módulo (H14)**: `backend/app/modules/plans/` contiene **siete módulos sin
contar `__init__.py`** —`models`, `vocabularies`, `progress`, `schemas`, `repository`, `service`,
`router`—, es decir **ocho archivos `.py`** en total. Dos más que el quinteto fijo del repositorio
(`models/schemas/repository/service/router`): `vocabularies.py` (D-J) y `progress.py` (D-E). La
prueba del escenario 31 se escribe con esa frase literal para que nadie tenga que decidir si
`__init__.py` cuenta.

**No se toca**: `tasks`, `boards`, `projects`, `dashboard`, `sprints`, `intake`, `connectors`,
`db_init._MENU_SEED` / `_ROLE_MENU_SEED` (D13), `frontend/`, `requirements.txt` (D4) ni
`backend/tests/test_migrations_baseline.py` (es el gate; no cambia una línea).

**Nombres de archivo de prueba**: `test_plans_repository.py` / `test_plans_service.py` /
`test_plans_endpoints.py` reemplazan al `test_plans_api.py` único que anunciaba `proposal.md:142`.
Razón: es la convención vigente del repositorio para un módulo con las tres capas —
`test_project_hierarchy_repository.py` y `test_project_hierarchy_endpoints.py` conviven hoy en
`backend/tests/`— y separar servicio (fakes, sin base) de endpoints (PostgreSQL real) es lo que
exige `agents/rules/solercia-persistence.md:44`. `state.yaml.verification.test_command` queda
actualizado en consecuencia.

### Migración `0028_add_institutional_plans.py`

```python
"""add_institutional_plans

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-26 00:00:00.000000

Change 45a-planes-modelo-api (design.md "Migración 0028"). Revision number and
``down_revision`` VERIFIED LIVE (``alembic heads`` + inventory of
``alembic/versions/`` + how many revisions each pending change CLAIMS)
immediately before authoring this file — Fase 0 gate, tasks.md.

The number is a CLAIM, not a promise, and it has already moved TWICE
(design.md R2): first from ``0028`` to ``0029`` when change 44 went from
claiming one revision to claiming two, then back to ``0028`` when the
reservation of ``0026`` for change 40 was dropped — that change is not part of
this wave, and a ``down_revision`` pointing at a revision nobody will ever
create breaks ``alembic upgrade`` in DEPLOYMENT, not in a test. Current chain:
43 -> ``0025``; 44 -> ``0026`` (board_columns) + ``0027`` (tasks); THIS ->
``0028``; 40 takes the next free consecutive whenever it is applied.

Strictly additive: FIVE brand-new tables, ZERO pre-existing tables touched, so
no row of the current schema changes on upgrade OR on downgrade. Same additive
pattern as ``0019_add_intake.py`` (``op.create_table`` with the constraints
declared INSIDE, then ``op.create_index(op.f(...))``), without
``batch_alter_table`` — zero occurrences in the 24 revisions on disk, the
project is PostgreSQL-only.

``plan_activities`` deliberately has NO ``organization_id``: tenant scope is
transitive through ``plan_id -> plans.organization_id``, exactly like ``tasks``
reaches it through ``project_id`` (design.md D-D / P7).

The ``ck_plan_activity_links_no_self`` CHECK and every UNIQUE below are mirrored
BYTE-IDENTICALLY in ``app/modules/plans/models.py`` ``__table_args__`` because
the test harness builds the schema with ``Base.metadata.create_all``
(tests/conftest.py:74-80), NOT with Alembic. ``alembic check`` 1.14.0 does NOT
compare CheckConstraints, so the equality is enforced by
``test_migration_institutional_plans.py`` comparing ``pg_get_indexdef`` /
``pg_get_constraintdef`` between the two schemas (design.md D-B).

``downgrade()`` drops indexes and tables in strict reverse creation order. The
five tables are new and no pre-existing table references them, so dropping them
loses no business data of any other aggregate.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- 1. plans (TenantMixin + Pk + Timestamp + SoftDelete + Audit) --------
    op.create_table(
        "plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan_type", sa.String(length=20), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=True),
        sa.Column("source_document", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "code", name="uq_plans_org_code"),
    )
    op.create_index(op.f("ix_plans_organization_id"), "plans", ["organization_id"])
    op.create_index(
        "ix_plans_org_type_year",
        "plans",
        ["organization_id", "plan_type", "period_year"],
    )

    # -- 2. plan_activities (NO organization_id — D-D / P7) -----------------
    op.create_table(
        "plan_activities",
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("group_code", sa.String(length=20), nullable=True),
        sa.Column("group_name", sa.String(length=255), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("deliverable", sa.Text(), nullable=True),
        sa.Column("evidence_expected", sa.Text(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("is_mine", sa.Boolean(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("target_from", sa.Numeric(5, 2), nullable=True),
        sa.Column("target_to", sa.Numeric(5, 2), nullable=True),
        sa.Column("iso_controls", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        # PLURAL: PSPI 2.4 carries OM-05 AND OM-08 (D2, spec scenario 2).
        sa.Column("external_codes", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("scheduled_periods", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "code", name="uq_plan_activities_plan_code"),
    )
    op.create_index(op.f("ix_plan_activities_plan_id"), "plan_activities", ["plan_id"])
    op.create_index(
        "ix_plan_activities_plan_is_mine", "plan_activities", ["plan_id", "is_mine"]
    )

    # -- 3. plan_activity_reports (NO SoftDeleteMixin — D-C) ----------------
    op.create_table(
        "plan_activity_reports",
        sa.Column("plan_activity_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("reported_progress", sa.Numeric(5, 2), nullable=True),
        sa.Column("qualitative_summary", sa.Text(), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("is_met", sa.Boolean(), nullable=True),
        sa.Column("met_on_time", sa.Boolean(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["plan_activity_id"], ["plan_activities.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_activity_id", "period",
                            name="uq_plan_activity_reports_activity_period"),
    )
    op.create_index(
        op.f("ix_plan_activity_reports_plan_activity_id"),
        "plan_activity_reports",
        ["plan_activity_id"],
    )

    # -- 4. plan_activity_links (the only CHECK of this change) -------------
    op.create_table(
        "plan_activity_links",
        sa.Column("from_activity_id", sa.Uuid(), nullable=False),
        sa.Column("to_activity_id", sa.Uuid(), nullable=False),
        sa.Column("link_type", sa.String(length=20), nullable=False),
        sa.Column("source_reference", sa.String(length=50), nullable=True),
        sa.Column("resolution", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["from_activity_id"], ["plan_activities.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_activity_id"], ["plan_activities.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_activity_id", "to_activity_id", "link_type",
                            name="uq_plan_activity_links_from_to_type"),
        sa.CheckConstraint("from_activity_id <> to_activity_id",
                           name="ck_plan_activity_links_no_self"),
    )
    op.create_index(
        op.f("ix_plan_activity_links_from_activity_id"),
        "plan_activity_links",
        ["from_activity_id"],
    )
    op.create_index(
        op.f("ix_plan_activity_links_to_activity_id"),
        "plan_activity_links",
        ["to_activity_id"],
    )

    # -- 5. task_plan_activities (the ONLY touch point with `tasks`) --------
    op.create_table(
        "task_plan_activities",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("plan_activity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_activity_id"], ["plan_activities.id"],
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "plan_activity_id",
                            name="uq_task_plan_activities_task_activity"),
    )
    op.create_index(
        op.f("ix_task_plan_activities_task_id"), "task_plan_activities", ["task_id"]
    )
    op.create_index(
        op.f("ix_task_plan_activities_plan_activity_id"),
        "task_plan_activities",
        ["plan_activity_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_task_plan_activities_plan_activity_id"),
                  table_name="task_plan_activities")
    op.drop_index(op.f("ix_task_plan_activities_task_id"),
                  table_name="task_plan_activities")
    op.drop_table("task_plan_activities")

    op.drop_index(op.f("ix_plan_activity_links_to_activity_id"),
                  table_name="plan_activity_links")
    op.drop_index(op.f("ix_plan_activity_links_from_activity_id"),
                  table_name="plan_activity_links")
    op.drop_table("plan_activity_links")

    op.drop_index(op.f("ix_plan_activity_reports_plan_activity_id"),
                  table_name="plan_activity_reports")
    op.drop_table("plan_activity_reports")

    op.drop_index("ix_plan_activities_plan_is_mine", table_name="plan_activities")
    op.drop_index(op.f("ix_plan_activities_plan_id"), table_name="plan_activities")
    op.drop_table("plan_activities")

    op.drop_index("ix_plans_org_type_year", table_name="plans")
    op.drop_index(op.f("ix_plans_organization_id"), table_name="plans")
    op.drop_table("plans")
```

**Inventario de objetos de esquema a espejar y a probar**: 5 tablas · 5 únicos · 1 `CHECK` ·
**9 índices** (H6), enumerados: (1) `ix_plans_organization_id` —la genera `TenantMixin` con
`index=True`—, (2) `ix_plans_org_type_year`, (3) `ix_plan_activities_plan_id`,
(4) `ix_plan_activities_plan_is_mine`, (5) `ix_plan_activity_reports_plan_activity_id`,
(6) `ix_plan_activity_links_from_activity_id`, (7) `ix_plan_activity_links_to_activity_id`,
(8) `ix_task_plan_activities_task_id`, (9) `ix_task_plan_activities_plan_activity_id`. **Nueve es
la cifra en todo el cambio**: D-B, este inventario, el escenario 4 de la tabla de cobertura, la
rebanada A2 y `state.yaml`. El
identificador más largo es `ix_plan_activity_reports_plan_activity_id` (41 caracteres) seguido de
`uq_plan_activity_reports_activity_period` (40): ambos muy por debajo del límite de 63 de
PostgreSQL. `Base` no declara `naming_convention` (`app/database.py:32-33`), así que **toda**
restricción se nombra explícitamente (R11).

### Espejo literal en `__table_args__`

```python
class PlanActivityLink(PkMixin, TimestampMixin, AuditMixin, Base):
    """Link between two plan activities, with its resolution kept traceable.

    No ``SoftDeleteMixin`` (design.md D-C), same convention as ``TaskLabel``
    (labels/models.py:43-55): unlinking removes the row outright. With soft
    delete, ``uq_plan_activity_links_from_to_type`` would keep holding the
    tuple after an unlink and the next legitimate link would raise
    ``UniqueViolation`` -> 500 (the failure change 43 had to fix in its D-I).
    """

    __tablename__ = "plan_activity_links"
    __table_args__ = (
        # Declared HERE and not only in migration 0028 because the test
        # harness builds the schema with `Base.metadata.create_all`
        # (tests/conftest.py:74-80). KEPT BYTE-IDENTICAL to 0028:
        # `alembic check` 1.14.0 does NOT compare CheckConstraints
        # (autogenerate/compare.py has zero occurrences of the class), so the
        # equality is asserted by test_migration_institutional_plans.py
        # comparing pg_get_constraintdef, NOT by the gate (design.md D-B).
        UniqueConstraint(
            "from_activity_id",
            "to_activity_id",
            "link_type",
            name="uq_plan_activity_links_from_to_type",
        ),
        CheckConstraint(
            "from_activity_id <> to_activity_id",
            name="ck_plan_activity_links_no_self",
        ),
    )

    from_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("plan_activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Closed vocabulary validated at the SERVICE layer, deliberately NOT a PG
    # enum (design.md D12/D-J, same rationale as `connectors.provider`).
    link_type: Mapped[str] = mapped_column(
        String(20), default="contributes_to", nullable=False
    )
    # Literal text of the source that produced the link, e.g. "4.5 (OM-03)".
    source_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # `exact` | `by_external_code` | `conflict` | `manual`. The API NEVER
    # accepts this from a client: every HTTP-created link is `manual` by
    # construction (design.md D14/D-I). Only change 45b's importer may emit
    # the other three, because they are assertions about READING A SOURCE.
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
```

Los otros cuatro modelos siguen el mismo patrón: mixins declarados en el orden canónico del
repositorio (`PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base`, como
`projects/models.py:32`), `__table_args__` con el único y los índices compuestos, e
`index=True` en las FK simples.

---

## Flujo de datos

**Lectura de un listado de actividades — tres consultas fijas, nunca `1 + 3N`:**

```
GET /api/v1/plans/activities?plan_type=pspi&is_mine=true&period=I
        │
        ▼
router.list_activities ──▶ service.list_activities ──▶ repository
  (Query + require nada,       (vocabularios, activity_key,      │
   membership de lectura)       null != 0, armado del Read)      │
                                                                 │
   ┌─────────────────────────────────────────────────────────────┤
   │ 1) _activity_scope(org)  JOIN plans  WHERE plans.organization_id = :o
   │       + filtros + paginación opt-in   ──▶ filas + plans.code
   │
   │ 2) rollup_activity_progress(org, ids)   UNA consulta agregada
   │       CTE last_column: DISTINCT ON (board.project_id)
   │                        ORDER BY column_order DESC, created_at DESC
   │       JOIN por  last_column.project_id = task.project_id   ◀── D-G
   │       count(...) FILTER (primary, progress_denominator())  ◀── D-E
   │       ──▶ {activity_id: (done, primary_total, contributing_total)}
   │
   │ 3) list_reports_for_period(org, ids, "I")   solo si vino ?period=
   │       ──▶ {activity_id: reported_progress}
   └─────────────────────────────────────────────────────────────┐
                                                                 ▼
   servicio:  read = PlanActivityRead.model_validate(row)
              read.activity_key = f"{plan_code}/{row.code}"          (D1)
              done, total, contrib = rollup.get(row.id, (0, 0, 0))
              read.calculated_progress = None if total == 0 else done / total
              read.primary_task_count = total
              read.contributing_task_count = contrib
              read.reported_progress, read.reported_period = reports.get(...)
                                                                 │
              {"data": [...], "meta": {"total": n}}  ◀────────────┘
```

**Escritura del reporte del periodo — idempotente por construcción (D11):**

```
PUT /api/v1/plans/activities/{id}/reports/I     require_role(admin, manager)
        │
        ▼
service.upsert_report
        ├─ validate_period("I")               ── 422 plan_period_invalid
        ├─ validate_reported_progress(v)      ── 422 plan_progress_out_of_range
        ├─ repo._require_activity(org, id)    ── 404 plan_activity_not_found
        │        (JOIN plans, tenant transitivo — D-D)
        ├─ repo.upsert_report(activity_id, "I", data)   SIN commit — D-M
        │        SELECT ... WHERE (plan_activity_id, period)
        │        ├─ existe ──▶ UPDATE   (segunda escritura, escenario 22)
        │        └─ no      ──▶ INSERT
        └─ await self.db.commit()             ── el caso de uso cierra
                                                 la transacción
```

**Costura de escritura que consume el 45b — sin superficie HTTP (D10):**

```
Importador 45b                 plans/repository.py                 PostgreSQL
      │                               │                                 │
      │ upsert_plan(org, PlanUpsert)  │ SELECT por (organization_id, code)
      ├──────────────────────────────▶│ ──────────────────────────────▶ │
      │  Plan                         │ INSERT o UPDATE  (idempotente)
      │ upsert_activity(plan.id, ...) │ SELECT por (plan_id, code)
      ├──────────────────────────────▶│
      │ upsert_activity_link(...)     │ resolution = exact|by_external_code|
      ├──────────────────────────────▶│              conflict   (D6, D14)
      │ upsert_task_link(...)         │
      ├──────────────────────────────▶│
      │                               │
      └─ el CASO DE USO hace commit ──┴──▶ un plan entero entra o no entra
```

---

## Estrategia de pruebas (TDD estricto: rojo antes que código)

`openspec/config.yaml:26-30` fija `tdd: true`. Cada uno de los 32 escenarios tiene prueba nombrada.

Columna **Tipo**: `RED` = debe fallar antes del código y pasar después; `guardia` = verde desde el
primer momento, existe para que **siga** siéndolo. Una guardia que arrancara en rojo delataría que
el supuesto que protege ya está roto: sería un hallazgo, no un paso del TDD.

### Cobertura escenario → prueba (32 / 32)

| # | Requisito · Escenario | Prueba | Tipo | Archivo · rebanada |
|---|---|---|---|---|
| 1 | Modelo · Un plan con actividades queda persistido y es consultable | `test_plan_detail_exposes_code_type_year_and_group_counts` (`PlanDetailRead` con `groups: list[PlanActivityGroupCount]` alimentado por `count_activities_by_group`, D-I/H13 — el conteo lo hace un `GROUP BY`, no Python) | RED | endpoints · E |
| 2 | Modelo · Una actividad admite más de un código externo | `test_activity_keeps_both_external_codes_after_roundtrip` (`["OM-05","OM-08"]` leídos desde JSONB) | RED | repository · C |
| 3 | Modelo · La migración no toca tablas existentes ni pierde datos al revertir | `test_downgrade_drops_the_five_tables_without_losing_seeded_rows` (siembra por SQL crudo con `asyncpg` → `upgrade 0028` → `downgrade` → las cinco ausentes, `organizations`/`projects`/`tasks` intactas) | RED | migración · **A1** |
| 4 | Modelo · El esquema migrado es equivalente al construido en pruebas | `test_create_all_and_migration_declare_the_same_plans_ddl` (`pg_get_indexdef` × **9**, `pg_get_constraintdef` × 5 únicos + el `CHECK`) | RED | modelos · **A2** |
| 5 | Reporte · Un periodo sin reporte no tiene fila | `test_a_period_without_a_report_has_no_row` | RED | repository · C |
| 6 | Reporte · Un segundo reporte del mismo periodo reemplaza al anterior | `test_upsert_report_replaces_the_period_value_without_duplicating` | RED | repository · C |
| 7 | Enlace act↔act · Una actividad no puede enlazarse consigo misma | `test_self_link_raises_check_violation` (`asyncpg.exceptions.CheckViolation`, migración · A1) **más** `test_self_link_is_rejected_with_plan_activity_self_link` (422 sin llegar al motor, service · D) | RED | migración · **A1** + service · D |
| 8 | Enlace act↔act · Un enlace en conflicto es visible pero no confirmado | `test_conflict_link_is_listed_but_never_counted_as_confirmed` (repository · C: el enlace `conflict` aparece en `links_out`/`links_in` con su `resolution`, y el roll-up del avance devuelve lo mismo con y sin él —no lee esa tabla, D-G) **más** `test_conflict_link_serializes_is_confirmed_false` (service · D: el campo derivado `is_confirmed = resolution != "conflict"` de D-I/H3, que es lo que el 45c pintará con distintivo de advertencia) | RED | repository · C + service · D |
| 9 | Enlace tarea↔act · Una tarea aporta a varias actividades como `primary` | `test_a_task_can_be_primary_of_two_activities` | RED | repository · C |
| 10 | Enlace tarea↔act · Un par duplicado se rechaza | `test_duplicate_task_activity_pair_raises_unique_violation` (motor, migración · A1) **más** `test_duplicate_task_link_returns_409_plan_task_link_duplicate` (dominio, endpoints · F) | RED | migración · **A1** + endpoints · F |
| 11 | Identificador · La clave derivada se calcula, no se guarda | `test_activity_key_is_derived_and_is_not_a_column` (unidad pura: `"code" in PlanActivity.__table__.columns` y `"activity_key" not in …`, más el armado en el servicio) | RED | service · D |
| 12 | Doble avance · Sin enlaces `primary` el avance calculado es ausencia de dato | `test_calculated_progress_is_none_without_primary_links` (repository · C) **más** `test_activity_without_primary_links_serializes_calculated_progress_as_null` (endpoints · E: `null`, no `0`, en el JSON) | RED | repository · C + endpoints · E |
| 13 | Doble avance · El avance calculado cruza proyectos distintos | `test_rollup_uses_each_tasks_own_board_last_column` (**dos** proyectos con boards de columnas distintas, dos tareas `primary` de la misma actividad) | RED | repository · C |
| 14 | Doble avance · Los enlaces `contributes` no alteran la razón | `test_contributes_links_stay_out_of_the_ratio_and_only_feed_the_count` (1 `primary` completa + 3 `contributes` sin completar ⇒ `1.0` y `contributing_task_count == 3`) | RED | repository · C |
| 15 | Doble avance · Un periodo sin reporte no inventa un avance reportado | `test_reported_progress_is_none_for_a_period_without_report` (incluye el caso sin `?period=`: `reported_progress` y `reported_period` ambos `None`, D-F) | RED | service · D |
| 16 | Tenant · Una actividad de otra organización responde como inexistente | `test_activity_of_another_organization_returns_404` | RED | endpoints · E |
| 17 | Tenant · Un listado nunca mezcla organizaciones | `test_no_read_endpoint_ever_returns_rows_of_another_organization` — **paramétrica sobre los 5 endpoints de lectura**, no una sola aserción global (R5/P7) | RED | endpoints · E |
| 18 | Tenant · No se puede enlazar una tarea a una actividad de otra organización | `test_cross_tenant_task_link_is_rejected` (los dos sentidos: actividad ajena ⇒ `plan_activity_not_found`; tarea ajena ⇒ `plan_task_not_found`) | RED | endpoints · F |
| 19 | Lectura · Un miembro sin rol de escritura puede leer | `test_member_can_read_every_plans_endpoint` | RED | endpoints · E |
| 20 | Lectura · El lado de la tarea se consulta desde `plans`, nunca desde `tasks` | `test_activities_filtered_by_task_id_return_both_links` **más** `test_task_read_declares_no_plan_field` (unidad pura sobre `TaskRead.model_fields`, **guardia** de D9) | RED + guardia | endpoints · E |
| 21 | Lectura · La ruta de actividades no colisiona con el detalle de un plan | `test_activities_route_is_declared_before_plan_detail` (índice en `app.routes` **y** `GET /plans/activities` respondiendo 200, no 422) | RED | endpoints · E |
| 22 | Escritura reporte · Dos escrituras consecutivas del mismo periodo dejan una sola fila | `test_two_consecutive_puts_leave_one_report_row_with_the_second_value` | RED | endpoints · F |
| 23 | Escritura reporte · Un porcentaje fuera de rango se rechaza | `test_reported_progress_out_of_range_is_rejected` (`150` ⇒ 422 `plan_progress_out_of_range`, sin fila creada) | RED | endpoints · F |
| 24 | Escritura enlaces · La API impone `resolution` manual | `test_api_forces_resolution_manual_whatever_the_client_sends` (cuerpo con `"resolution": "exact"` ⇒ fila con `manual`, sin error de validación, D-I) **más la aserción de destino ajeno (H11)**: un `to_activity_id` de otra organización responde `plan_activity_not_found` 404 y no crea fila, porque el destino pasa por el mismo `_require_activity` que el origen (D-K) | RED | endpoints · F |
| 25 | Escritura enlaces · Duplicado o inexistente falla de forma explícita | `test_duplicate_task_link_conflicts_and_deleting_a_missing_link_returns_404` | RED | endpoints · F |
| 26 | Autorización · Un `member` no puede escribir | `test_member_is_forbidden_on_every_write_endpoint` — paramétrica sobre los 5 de escritura, con `member` **y** `viewer` | RED | endpoints · F |
| 27 | Autorización · Un `manager` puede escribir | `test_manager_can_write_a_period_report` | RED | endpoints · F |
| 28 | Costura · Reejecutar la costura sin cambios no crea filas nuevas | `test_reupserting_plan_and_activity_creates_no_new_rows` (conteo antes y después; verifica además que el repositorio **no** comiteó, D-M) | RED | repository · C |
| 29 | Costura · No existe creación de planes por HTTP | `test_no_registered_route_creates_a_plan_or_an_activity` (recorre `app.routes` bajo `/api/v1/plans`: ningún `POST` cuyo `path` termine en `/plans` o `/activities`) | RED | endpoints · E |
| 30 | Frontera ADR 0009 · El reporte no admite campos de segunda o tercera línea | `test_report_schema_has_no_second_or_third_line_fields` (unidad pura: `PlanActivityReportUpsert.model_fields` tiene exactamente los cinco, y `PlanActivityReport.__table__.columns` no contiene monitoreo/evaluación/observaciones) | RED → guardia | schemas · B |
| 31 | Alcance excluido · No hay importadores ni CLI de planes | `test_plans_module_has_no_importer_or_cli` (el módulo contiene exactamente **siete módulos sin contar `__init__.py`** —`models`, `vocabularies`, `progress`, `schemas`, `repository`, `service`, `router`— es decir ocho archivos `.py` en total; cero `zipfile`, `openpyxl`, `docx` o `argparse`) | guardia | schemas · B |
| 32 | Alcance excluido · No hay entrada de menú ni vista de planes | `test_no_plans_menu_entry_and_no_frontend_route` (`_MENU_SEED` sin «Planes» y `frontend/src` sin ruta `/plans`, D13) | guardia | schemas · B |

**Escenarios sin prueba automatizada: ninguno.** 32 de 32.

**Guardias** (verdes desde el primer momento): 31, 32, y la mitad `test_task_read_declares_no_plan_field`
de la 20. Casos mixtos `RED → guardia`: la 30 nace roja porque el esquema no existe y **queda** como
guardia permanente de la frontera ADR 0009 (R9).

**Pruebas de apoyo, sin escenario propio** (cuatro):

| Prueba | Rebanada | Qué protege |
|---|---|---|
| `test_progress_denominator_matches_the_current_criterion` | B | Fija el criterio vigente; es la **única** prueba que cambia cuando el 44 mueve la definición (D-E) |
| `test_migrations_baseline.py::test_alembic_check_reports_no_diff_after_upgrade` | A2 | Guardia de existencia por nombre (D-B). Archivo sin cambios |
| `test_list_activity_tasks_is_a_single_query` (H4) | C | Cuenta las sentencias emitidas con `before_cursor_execute` y exige **una**; además comprueba que `counts_toward_progress` coincide tarea a tarea con `progress_denominator()`. Sin ella, un N+1 introducido después no rompería ninguna aserción de valor |
| `test_concurrent_duplicate_link_surfaces_409_not_500` (H10) | F | La carrera entre la consulta previa y el `INSERT` sale como el **mismo** 409 de dominio, no como 500 (D-K) |

### Estructura de los archivos nuevos

| Archivo | Andamiaje | Rebanadas |
|---|---|---|
| `test_migration_institutional_plans.py` | **Un archivo, dos rebanadas.** **A1** lo crea con el calco de `test_migration_project_kind.py` (244 líneas en disco): `_sync_dsn` / `_admin_dsn` / `_recreate_*_database` / `_alembic_config`, base desechable `solercia_test_institutional_plans_migration`, `command.upgrade(cfg, "0027")` → siembra por SQL crudo con `asyncpg` (organización + usuario + proyecto + tarea, **con `is_active` explícito**, D-A) → `command.upgrade(cfg, "0028")` → aserciones sobre `information_schema` → `command.downgrade(cfg, "0027")`. Todas síncronas con `asyncio.run(...)` y `@skip_no_db`. **A2** le añade la equivalencia de DDL, que reutiliza esos helpers, levanta una **segunda** base y ejecuta `CREATE EXTENSION IF NOT EXISTS pg_trgm` → `import app.db_init` → `Base.metadata.create_all` (D-B). Reutilizar el andamiaje es la razón de que A2 no pague otra vez su coste | A1 + A2 |
| `test_plans_repository.py` | PostgreSQL real sobre la fixture `session` (`conftest.py:87-110`, aislamiento por SAVEPOINT con `join_transaction_mode="create_savepoint"`). El caso que motiva R3 se siembra explícito: **dos** proyectos, **dos** boards con columnas distintas, dos tareas `primary` de la misma actividad. Instancia `PlansRepository(session)` directamente. Aquí vive también el conteo de sentencias de `test_list_activity_tasks_is_a_single_query` (H4) | C |
| `test_plans_service.py` | **Fakes, sin base** (`solercia-persistence.md:44`): un doble del repositorio que devuelve tuplas de roll-up preparadas. Aquí viven `null ≠ 0`, `activity_key`, vocabularios y `resolution='manual'`. Sin `@skip_no_db` en las unidades puras | D |
| `test_plans_endpoints.py` | API real in-process vía `httpx.AsyncClient`, patrón de `test_intake_classifier_endpoints.py` y `test_project_hierarchy_endpoints.py`: helpers `_auth`, `_seed_plan`, `_link_task`. La siembra usa **la costura de escritura del repositorio** (D10/D-M), nunca `INSERT` crudo — es el error que el 43 corrigió con su D-G | E, F |

### Comando y línea base

```
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  .venv/bin/python -m pytest -q \
  tests/test_migration_institutional_plans.py \
  tests/test_plans_repository.py \
  tests/test_plans_service.py \
  tests/test_plans_endpoints.py \
  tests/test_migrations_baseline.py
```

**Línea base a no regresar: la vigente en el tracker al iniciar cada rebanada**, re-medida en la
Fase 0 de cada una. No se congela una cifra: el 48-puerto-llm y el 44 agregan pruebas en paralelo
(lección del 43, tarea 0.6). La línea base **solo vale con `TEST_DATABASE_URL` puesta**; sin ella,
`skip_no_db` salta cientos de pruebas y la corrida no sirve de referencia.

---

## Threat Matrix

La matriz estándar (`references/threat-matrix.md`) cubre enrutamiento de archivos, shell,
subprocesos, automatización de VCS/PR y clasificación de ejecutables. Este cambio no toca ninguna
de esas fronteras:

| Frontera | Aplicabilidad |
|---|---|
| Rutas tipo documentación · clasificación de ejecutables | **N/A** — el cambio no clasifica ni ejecuta archivos; los importadores de DOCX/XLSX son del 45b (escenario 31 lo prueba) |
| Selección de repositorio git (`git -C`, rutas relativas/absolutas) | **N/A** — sin automatización de VCS |
| Estado de commit (staged, `commit -a`, índice vacío) | **N/A** — sin automatización de VCS |
| Estado de push (rama de seguimiento, primer push, refspec) | **N/A** — sin automatización de VCS |
| Comandos de PR (`--head`, prefijo de entorno, comandos compuestos) | **N/A** — sin automatización de PR |
| Shell / subprocesos | **N/A** — el único proceso externo es `alembic` dentro de las pruebas, ya existente |

Las fronteras reales de este cambio son **aislamiento entre organizaciones**, **veracidad del dato
de avance** y **autoridad de la afirmación institucional**, y sí son aplicables:

| Caso adversario | Comportamiento seguro | Prueba en rojo |
|---|---|---|
| **Fuga entre tenants por un `JOIN plans` olvidado** en cualquiera de las **once** consultas de lectura del repositorio. `plan_activities` no tiene `organization_id`, así que un `select(PlanActivity)` suelto devuelve el mundo entero | D-D: un único `_activity_scope(organization_id)` que **todas** componen; `_require_activity` devuelve `None` para inexistente y para ajena, y el servicio traduce ambas al mismo 404 (no distingue, para no filtrar existencia) | 16, y sobre todo **17 paramétrica sobre los 5 endpoints de lectura** — no una sola aserción global |
| **Fuga por el lado de la tarea**: enlazar o leer tareas de otra organización a través de una actividad propia | El roll-up comprueba el tenant **dos veces**: por `plans.organization_id` (lado actividad) y por `projects.organization_id` (lado tarea), D-G | 18 `test_cross_tenant_task_link_is_rejected` |
| **`null` colapsado a `0`**: una actividad sin evidencia mostrada como «0 % de avance» es una afirmación falsa ante el SIG y ante Control Interno (R7) | D-F: una sola regla, `primary_task_count == 0 ⇒ None`, que cubre también el caso «tiene enlaces pero ninguno contable» y elimina la división por cero | 12, en **dos** capas: repositorio (valor) y endpoint (`null` literal en el JSON) |
| **Avance inventado por periodo**: devolver el último periodo con reporte cuando el cliente no pidió ninguno equivale a presentar el dato del cuatrimestre I como el del II | D-F: sin `?period=`, `reported_progress` y `reported_period` son `None`. El sistema no elige por el usuario | 15 |
| **N+1 al pintar la vista**: 62 actividades reales × una consulta de avance cada una (R8) | D-G: una consulta agregada por lote con `FILTER`; tres consultas fijas por listado, independientes de N | 13 y 14 sobre lote; el listado de E se prueba con lote representativo |
| **Autorreferencia** de una actividad, que produciría un ciclo de avance sobre sí misma | Defensa en dos capas: `ck_plan_activity_links_no_self` en el motor **y** `plan_activity_self_link` 422 en el servicio, que responde sin llegar a la base | 7, en las dos capas |
| **Escritura sin RBAC**: cualquier miembro registrando un avance cuatrimestral. Un reporte del Decreto 612 es una afirmación institucional (P3) | `require_role(MemberRole.admin, MemberRole.manager)` como singleton de módulo en los 5 endpoints de escritura; lectura abierta a todo miembro | 26 paramétrica con `member` **y** `viewer`, 27 |
| **Secuestro de la resolución**: un cliente marca `resolution='exact'` en un enlace que ningún documento respalda (D14) | El campo **no existe** en `ActivityLinkCreate`: Pydantic lo ignora estructuralmente y el servicio fija `manual` por construcción. No es una defensa, es una ausencia | 24 |
| **Segunda y tercera línea de defensa del PAI** guardadas en Command «porque están en la misma hoja» — columnas `AA`, `AB`, `AC` (R9, ADR 0009) | D-N: el esquema de escritura declara exactamente cinco campos y la tabla exactamente cinco columnas de negocio. La frontera está en el modelo, no en la prosa | 30 |
| **Autoría paralela de un plan**: un formulario creando planes que divergen del documento fuente (D10) | No hay ruta HTTP de creación; la única escritura es la costura de repositorio que el importador del 45b consume | 29 `test_no_registered_route_creates_a_plan_or_an_activity` |
| **Divergencia modelo↔migración** que hace que las pruebas validen una regla distinta de la de producción (R4) | D-B: equivalencia de DDL comparada entre las dos rutas de construcción del esquema; `alembic check` solo como existencia por nombre | 4 |
| **Ancla retenida tras desenlazar**: con soft delete, el único conservaría el par y el re-enlace legítimo daría 500 | D-C: las tres tablas hijas no llevan `SoftDeleteMixin`; desenlazar borra la fila, igual que `TaskLabel` | 25 (re-enlace tras `DELETE`) |
| **Fuga por el destino de un enlace actividad↔actividad** (H11): las dos FK de `plan_activity_links` apuntan a la misma tabla y el `CHECK` solo prohíbe la autorreferencia; nada en el esquema impide enlazar hacia una actividad de otra organización | D-K: `to_activity_id` pasa por el mismo `_require_activity(organization_id, ...)` que el origen (D-D) y responde `plan_activity_not_found` 404 sin crear fila | 24, aserción añadida |
| **Carrera en el `POST` de enlaces** (H10): dos peticiones concurrentes del mismo par pasan las dos la consulta previa; la perdedora recibiría un `IntegrityError` sin capturar y saldría **500** ante una petición válida | D-K: el servicio envuelve la escritura y traduce `IntegrityError` al **mismo** 409 de dominio (`plan_task_link_duplicate` / `plan_activity_link_duplicate`), con `rollback` previo. La consulta previa se conserva como camino normal | `test_concurrent_duplicate_link_surfaces_409_not_500` (apoyo) |
| **Borrado físico de enlaces sin rastro de autor** (H16): `DELETE` de `task_plan_activities` y `plan_activity_links` elimina la fila (D-C) y con ella `updated_by`; queda registrado **quién creó** el enlace, nunca **quién lo quitó** | **Riesgo aceptado, no mitigado.** `task_history` es del agregado `tasks` y no cubre estas tablas; el registro de aplicación conserva la petición pero no es evidencia consultable desde el producto. Se acepta porque desenlazar una tarea de una actividad no es una afirmación institucional —lo es el reporte del periodo, que **sí** conserva `updated_by` (D-C/H9)— y porque el soft delete introduciría el fallo del único retenido. **Alternativa futura, si el negocio lo exige**: una tabla de bitácora propia del módulo (`plan_link_events`) escrita en el mismo caso de uso, **no** `SoftDeleteMixin` | N/A — riesgo aceptado y escrito (R15); ninguna prueba en rojo lo cubre porque no hay comportamiento que probar |
| **Criterio de exclusión divergente**: el 44 cambia el denominador de `projects` y el de `plans` queda midiendo otra cosa en silencio (R6) | D-E: `progress_denominator()` es el único punto, y devuelve también los `JOIN` que el criterio nuevo necesitará | `test_progress_denominator_matches_the_current_criterion` (apoyo) |
| **Colisión o hueco de numeración de migración** con el 43, el 44 o el 40 (R2, ya materializada **dos** veces) | Compuerta de Fase 0 con `alembic heads` en vivo + inventario de `alembic/versions/` + conteo de cuántas revisiones **reclama cada cambio que efectivamente entra en la ola**, ejecutada inmediatamente antes de escribir el archivo. No se reserva número para un cambio que no se aplica | `op.create_table` sobre una tabla existente falla de forma **ruidosa**; y un `down_revision` hacia una revisión inexistente rompe `alembic upgrade` en **despliegue** —la prueba de migración lo detecta antes, pero solo si el hueco ya existe en disco al correrla— |

---

## Rebanadas y carga de revisión

Estrategia `auto-chain` con **feature branch chain** sobre el tracker `feat/45a-planes-modelo-api`:
A1 apunta al tracker y cada rebanada siguiente a la rama de la anterior. Presupuesto = estimación
× 1,2 + ≈50 líneas de marcas de `tasks.md`, truncado a la centena.

**Siete rebanadas** (H2). La antigua **A** se parte en dos porque mezclaba dos entregables con
verificación distinta —la migración, que se prueba con `alembic upgrade`/`downgrade` sobre una base
desechable, y los cinco modelos, que se prueban comparando el DDL contra `create_all`— y porque
esa mezcla ocultaba una subestimación: el archivo de migración por sí solo mide ≈264 líneas
(el bloque de código de este diseño) y el calco de `test_migration_project_kind.py` mide **244
líneas en disco**. La antigua A declaraba ≈390 para migración **más** modelos **más** ambas pruebas.

| # | Rama → destino | Contenido | ≈ líneas | Presupuesto | Escenarios | Reversa |
|---|---|---|---:|---:|---|---|
| **A1** | `feat/45a-a1-migracion` → tracker | `0028_add_institutional_plans.py` (5 tablas, 10 FKs, 5 únicos, **9** índices, 1 `CHECK`) · `test_migration_institutional_plans.py` con el andamiaje completo, siembra por SQL crudo y `upgrade`/`downgrade` en base desechable | ~515 | **600** | 3, 7 (motor), 10 (motor) | `alembic downgrade -1` + revert. **Cero tablas preexistentes tocadas, cero filas afectadas** |
| **A2** | `feat/45a-a2-modelos-ddl` → rama de A1 | Los 5 modelos con `__table_args__` espejados literalmente (D-C, D-H) · import de los cinco en `db_init.py` con `# noqa: F401` · la prueba de equivalencia de DDL, que reutiliza el andamiaje de A1 y exige el orden `pg_trgm` → `import app.db_init` → `create_all` (D-B) | ~420 | **500** | 4 | Revert; las tablas quedan sin mapeo ORM y la migración permanece |
| **B** | `feat/45a-b-vocabularios-esquemas` → rama de A2 | `vocabularies.py` (D-J) · `progress.py` (D-E) · `schemas.py` completo, incluidos `PlanDetailRead`/`PlanActivityGroupCount` (H13), `ActivityTaskRead` (H4) e `is_confirmed` (H3) · `include_router` en `main.py` con el router aún vacío. **Sin modelos**: se entregaron en A2 | ~440 | **500** | 30, 31, 32 | Revert; el mapeo ORM permanece |
| **C** | `feat/45a-c-repositorio` → rama de B | `_activity_scope`, `_require_activity`, roll-up cruzado por lote, `list_activity_tasks` en **una** consulta (H4), `count_activities_by_group` (H13), `list_reports_for_period`, 5 `upsert_*` (D10), `delete_*`, `SORTABLE_FIELDS` · `test_plans_repository.py` | ~460 | **600** | 2, 5, 6, 8 (repo), 9, 12 (repo), 13, 14, 28 | Revert; el modelo permanece |
| **D** | `feat/45a-d-servicio` → rama de C | `PlansService`: `activity_key`, doble avance con `null ≠ 0` y sin adivinar periodo (D-F), `is_confirmed` (H3), vocabularios (D12), `resolution='manual'` (D14), códigos de error, transacción · `test_plans_service.py` con fakes | ~355 | **400** | 7 (servicio), 8 (`is_confirmed`), 11, 15 | Revert; el repositorio permanece |
| **E** | `feat/45a-e-api-lectura` → rama de D | Los 5 `GET` en el orden de D-L · paginación opt-in · `test_plans_endpoints.py` (parte de lectura) e **aislamiento de tenant por endpoint** | ~420 | **500** | 1, 12 (API), 16, 17, 19, 20, 21, 29 | Revert; **el 45b sigue desbloqueado**: consume repositorio y servicio, no HTTP |
| **F** | `feat/45a-f-api-escritura` → rama de E | `PUT` del reporte · `POST`/`DELETE` de los dos tipos de enlace · captura de `IntegrityError` → 409 (H10) · destino del enlace por `_require_activity` (H11) · `require_role` singleton · pruebas de RBAC, idempotencia y 404/409/422 | ~410 | **500** | 10 (API), 18, 22, 23, 24, 25, 26, 27 | Revert; la lectura permanece y el 45c puede empezar por la vista de solo lectura |

**Descomposición de A1 y A2**, que es lo que sostiene las dos cifras:

| Rebanada | Pieza | ≈ líneas | Evidencia |
|---|---|---:|---|
| A1 | `0028_add_institutional_plans.py` | 264 | Bloque de código de la sección «Migración `0028`» de este diseño: 43 de docstring + 220 de cuerpo |
| A1 | `test_migration_institutional_plans.py` (andamiaje + siembra + `upgrade`/`downgrade`) | ~250 | Calco de `backend/tests/test_migration_project_kind.py`, **244 líneas medidas en disco**; la siembra del 45a es mayor (organización + usuario + proyecto + tarea) y las aserciones cubren 5 tablas, 5 únicos, el `CHECK` y 9 índices |
| A2 | `plans/models.py` (5 modelos con espejo literal) | ~290 | `PlanActivityLink` completo mide ~55 en este diseño; `PlanActivity` tiene 16 columnas de negocio más los mixins |
| A2 | `plans/__init__.py` + import en `db_init.py` | ~10 | Un import por modelo con `# noqa: F401` |
| A2 | Equivalencia de DDL en el archivo que creó A1 | ~120 | Segunda base desechable + `pg_trgm` + `create_all` + comparación de 9 `pg_get_indexdef` y 6 `pg_get_constraintdef`; reutiliza los helpers de A1 |

> **Divergencia declarada frente a la cifra indicativa del orquestador.** La decisión H2 sugería
> ≈300 líneas y presupuesto 400 para cada una de A1 y A2. La decisión H5, en la misma pasada, ordena
> re-estimar **con la evidencia del validador**, y esa evidencia (migración ≈264 + prueba ≈244) ya
> supera por sí sola las ≈300 de A1. Este diseño escribe la estimación que la evidencia sostiene
> —A1 ≈515 / 600 y A2 ≈420 / 500— porque dejar ≈300 reproduciría exactamente el hallazgo H5 que la
> pasada debía cerrar. Si el orquestador prefiere conservar ≈300 / 400, son **dos literales por
> rebanada** en esta tabla y en `state.yaml`; ninguna decisión de diseño cambia.

Total estimado **≈3 020 líneas** (`additions + deletions`), de las cuales ≈1 200 son pruebas.
La cifra anterior, ≈2 230, era el resultado de la subestimación de A que H5 detectó.
`400-line budget risk: **High**` · `Chained PRs recommended: **Yes**`. El pronóstico formal lo
emite `sdd-tasks`.

**Contingencia prevista** (patrón de la rebanada C del 43): si **F** desborda su presupuesto se
parte en **F1** (reporte del periodo + enlace tarea↔actividad — la escritura que el 45c necesita) y
**F2** (enlaces actividad↔actividad manuales, cuyo productor real es el importador del 45b). F2
puede posponerse sin bloquear ni al 45b ni al 45c. Segunda contingencia: **A1 es la rebanada que
no se puede partir más** —la migración y su prueba de `upgrade`/`downgrade` son un solo hecho
verificable— así que su presupuesto de 600 se acepta como excepción explícita en vez de fingir un
corte que no existe. Tercera contingencia: si el orquestador rechaza D13 y reincorpora el menú
«Planes», entra en F con `order=7` y suma ≈35 líneas al presupuesto.

### Fase 0 de cada rebanada — la compuerta de numeración es obligatoria en A1

Antes de escribir **el archivo de migración** (no antes de planificar):

| # | Acción | Criterio de salida |
|---|---|---|
| 0.1 | `cd backend && .venv/bin/python -m alembic heads` | Una sola cabeza, sin bifurcación. Si hay dos, se detiene y se reporta |
| 0.2 | Inventario de `backend/alembic/versions/` | Número real en disco del último consecutivo |
| 0.3 | Revisión de **cuántas** revisiones reclama cada cambio que **efectivamente entra en esta ola** (43, 44, 48) en sus `tasks.md`/`design.md`. El 40 queda **fuera**: no se le reserva número | Lista de números reclamados, no supuestos, y **sin huecos**. El 44 ya pasó de reclamar una a reclamar dos, y la reserva del 40 tuvo que retirarse: contar y descartar reservas muertas es el gate completo, no solo leer `alembic heads` |
| 0.4 | Re-anclaje de `revision` y `down_revision` | Los dos valores escritos en el archivo coinciden con 0.1–0.3. **El diseño no se renegocia**: solo cambian dos literales y el docstring |
| 0.5 | Re-medición de la línea base de pruebas con `TEST_DATABASE_URL` | Cifra de la rebanada, no una congelada del 43 |

Las rebanadas A2 y B–F ejecutan solo 0.5.

---

## Migración / despliegue

Un solo paso: `alembic upgrade head`. Sin retrollenado, sin transformación de datos, sin bandera de
funcionalidad, sin ventana de mantenimiento.

- **Precondiciones de contrato: ninguna.** El 45a no depende del 43, del 40 ni del 44 para
  planificar ni para implementar: no toca `tasks` fuera de la FK, no necesita `external_key` ni
  `context_group` y su modelo es autónomo.
- **Precondición de secuencia, sí, y es la única**: `down_revision="0027"` exige que `0025` (43) y
  `0026`/`0027` (44) existan en disco cuando la rebanada **A1** se aplique. Si el 45a llegara antes, la
  compuerta de Fase 0 re-ancla los dos literales al head real y el diseño sigue intacto (R2). El
  **40 queda fuera de la cadena**: se le retiró la reserva de `0026` porque no entra en esta ola, y
  reservar un número para un cambio que no se aplica deja un hueco que rompe `alembic upgrade` en
  despliegue.
- **Reversa completa**: `alembic downgrade -1`. Las cinco tablas son nuevas y ninguna tabla
  preexistente las referencia, así que bajar no pierde un solo dato de otro agregado.
- **Arranque**: `db_init.py` importa los cinco modelos y nada más. `_ensure_menus` no cambia, así
  que **ninguna organización ve una entrada «Planes» apuntando a una ruta que no existe** (D13).
- **Frontend**: sin cambios. Ni un archivo, ni un tipo, ni una ruta.
- **Desbloqueo**: al terminar la rebanada **D**, el 45b ya tiene modelo, vocabularios y costura de
  escritura idempotente, y puede arrancar sin esperar a E ni a F. El 45c necesita E (lectura) y,
  para la vista completa, F.
- **Coordinación con el 44** (R6): quien aplique segundo edita **un** punto —`progress_denominator()`
  si es el 44, el CTE de `projects/repository.py` si es el 45a—. Es coordinación, no bloqueo.

---

## Riesgos abiertos

| Riesgo | Mitigación en este diseño |
|---|---|
| **R2** · La numeración `0028` es una reclamación, no una promesa, y **ya se desplazó dos veces**: `0028 → 0029` cuando el 44 pasó a reclamar dos revisiones, y `0029 → 0028` al eliminarse la reserva de `0026` para el 40 | Compuerta de Fase 0 con `alembic heads` en vivo, inventario de disco y **conteo de revisiones reclamadas por cada cambio pendiente que efectivamente entra en esta ola**, ejecutada inmediatamente antes de escribir el archivo. Re-anclar cuesta dos literales y un docstring. **Regla derivada**: no se reserva número para un cambio que no se aplica en la ola — un hueco en la cadena rompe `alembic upgrade` en despliegue, no en la prueba |
| **R3** · El roll-up no se reutiliza: `rollup_progress` está atado al subárbol de un proyecto | D-G escribe SQL nuevo unido por `board.project_id = task.project_id` y lo prueba contra PostgreSQL real con el caso que lo motiva: dos proyectos con boards de columnas distintas |
| **R4** · `alembic check` 1.14.0 no compara `CheckConstraint` ni `postgresql_where`: falso negativo silencioso | D-B: equivalencia de `pg_get_indexdef`/`pg_get_constraintdef` entre las dos rutas de construcción del esquema. El gate se conserva con su alcance escrito |
| **R5** · Un `JOIN plans` olvidado filtra datos entre organizaciones | D-D centraliza el alcance en una función; la prueba de aislamiento **por endpoint** (17) se conserva igual, porque centralizar reduce la probabilidad, no autoriza a dejar de comprobar |
| **R6** · El criterio de exclusión del avance está en movimiento por el 44 | D-E lo aísla en `progress_denominator()`, que devuelve predicado **y** `JOIN`. Un solo punto, una sola prueba que cambia con él |
| **R7** · `null` colapsado a `0` | D-F: una sola regla, probada en repositorio, servicio y JSON de respuesta |
| **R8** · N+1 al calcular el avance de un listado | D-G: tres consultas fijas por listado, independientes de N |
| **R9** · Tentación de guardar segunda y tercera línea de defensa del PAI | D-N: la frontera está en el esquema y en la tabla, con guardia de unidad pura (30) |
| **R10** · Cinco tablas en una sola migración | Transacción de Alembic en PostgreSQL: entran las cinco o ninguna. El `downgrade` se ejercita en la propia prueba (3) |
| **R11** · Identificadores sin `naming_convention` en `Base` | Toda restricción nombrada explícitamente; el más largo mide 41 caracteres frente al límite de 63 |
| **R12 (nuevo)** · `paginate(...)` **agrega** cláusulas de orden en vez de reemplazarlas | El repositorio construye el `Select` sin `order_by` y decide después según el camino (D-L). Si se olvida, el orden natural y el paginado se encadenan y producen un `ORDER BY` contradictorio, no un error |
| **R13 (nuevo)** · El rango `0–100` del avance reportado **no lo defiende el motor**: no hay `CHECK` de rango | Deliberado (D-J): el alcance ratificado fija un solo `CHECK`. La defensa es `validate_reported_progress` en el servicio, y el 45b —único otro escritor— debe llamarla antes de usar la costura. Queda anotado como mejora barata para ese cambio |
| **R14 (nuevo, H12)** · El `period` de un reporte **no se contrasta** con `scheduled_periods` de la actividad ni con el `plan_type` de su plan: se puede registrar un reporte del cuatrimestre III en una actividad cuya fuente solo programaba I y II | **Riesgo aceptado y escrito.** Ningún requisito de la spec lo exige: el requisito de escritura (`:148`) solo acota el periodo al vocabulario `{I, II, III, ANUAL}`. `scheduled_periods` es un dato **descriptivo de la fuente**, no una restricción de negocio, y el importador del 45b no puede garantizar que esté completo en los tres documentos. Convertirlo en validación bloquearía reportes legítimos por un dato de calidad desconocida. Si el negocio lo pidiera, es una comprobación de servicio en `upsert_report` —cero migraciones (D12)— y un requisito nuevo con su propio escenario |
| **R15 (nuevo, H16)** · El `DELETE` de enlaces es físico (D-C) y **no deja `deleted_by`**: queda quién creó el enlace, nunca quién lo quitó | **Riesgo aceptado.** `task_history` pertenece al agregado `tasks` y no cubre estas tablas; el registro de aplicación no es evidencia consultable desde el producto. Se acepta porque desenlazar no es una afirmación institucional —lo es el reporte del periodo, que sí conserva `updated_by`— y porque el soft delete traería el fallo del único retenido (D-C). Alternativa futura si el negocio lo exige: bitácora propia del módulo (`plan_link_events`) escrita en el mismo caso de uso, **nunca** `SoftDeleteMixin` |

## Preguntas abiertas

- [ ] **Ninguna que bloquee la implementación.** Las siete de la exploración (P1–P7) quedaron
      resueltas o asignadas a su cambio propietario, y las catorce decisiones de este diseño
      (`D-A … D-N`) son de nivel técnico y quedan cerradas aquí.
- [ ] **Los cinco supuestos de la ronda de preguntas de `proposal.md:216-227` siguen vigentes y
      ninguno bloquea.** Se listan por trazabilidad, con el efecto concreto que tendría una
      respuesta distinta sobre **este** diseño:

| # | Supuesto vigente | Qué cambiaría en el diseño si la respuesta fuera otra |
|---|---|---|
| 1 | El reporte es **borrador de trabajo**: último valor por periodo, con `created_by`/`updated_by`, sin versionado | Si fuera el valor oficial, `plan_activity_reports` necesitaría historial —una sexta tabla o un `JSONB` de versiones— y `PUT` dejaría de ser un `upsert` plano (D11) |
| 2 | Calculado y reportado **se muestran los dos**, sin alerta ni umbral de discrepancia | Una regla de discrepancia sería un requisito nuevo con su propia pregunta («¿qué diferencia es tolerable?») y un campo derivado más en `PlanActivityRead` |
| 3 | Una tarea **puede** ser `primary` de más de una actividad | Restringirlo exigiría un único parcial `(task_id) WHERE role='primary'` **en la migración**: es la única de las cinco que tendría que resolverse **antes** de la rebanada A1 |
| 4 | Se guardan **todas** las actividades del plan importado, con `is_mine` para distinguir | Guardar solo las propias abarataría el 45b pero rompería el enlace PTR → PSPI cuando la actividad destino no sea propia. El 45a ya está preparado para ambas: `is_mine` es un filtro, no una condición de existencia |
| 5 | Vocabulario de periodo común: `I`/`II`/`III` + `ANUAL` | Un ritmo distinto por tipo de plan cambiaría `REPORT_PERIODS` (una línea en `vocabularies.py`, cero migraciones — que es justamente el punto de D12) |

- [ ] **D13 sigue siendo la única divergencia declarada frente al alcance dictado** y ya fue
      ratificada por el orquestador el 2026-08-26. Si se revirtiera, la entrada de menú entra en la
      rebanada F con `order=7` y ≈35 líneas más de presupuesto.

## Referencias

- `openspec/changes/45a-planes-modelo-api/{exploration.md,proposal.md,state.yaml}` ·
  `specs/institutional-plans/spec.md` (14 requisitos / 32 escenarios).
- `agents/rules/solercia-persistence.md:41-46` — repositorios sin commit (`:41`); **`organization_id`
  «or an equivalent tenant scope»** en lecturas, actualizaciones y borrados (`:42` — el `JOIN plans`
  **es** ese alcance equivalente, la regla no exige la columna, H15); servicios probados con fakes y
  adaptadores contra PostgreSQL real (`:44`); JSONB y SQL textual confinados al adaptador (`:45`).
- `docs/adr/0009-solercia-command-connect-data-conventions.md:78-80,238-240` — frontera Command /
  Security (D5, D-N).
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` — **§6 «Convención de persistencia»,
  punto 5 (`:108`)**: tenant en toda lectura, actualización y eliminación; **§7 «Convención de
  nombres y datos» (`:116`, tabla en `:118-125`)**: columnas semánticas en `lower_snake_case`.
  *(Corrección de cita: el documento **no tiene** un §6.5 numerado; la referencia anterior lo
  suponía.)*
- `openspec/config.yaml:20-30` — `rules.design` (decisiones con justificación, `router → service →
  repository`) y `rules.apply.tdd: true`.
- `openspec/specs/{api-conventions,multi-tenancy,tasks,project-hierarchy}/spec.md` — línea base que
  el 45a **cumple** y no modifica; `project-hierarchy/spec.md:111-137` es el roll-up de
  `GET /projects/{id}/progress` que este cambio **generaliza en SQL nuevo**, no reutiliza;
  `multi-tenancy/spec.md:24` es la nota as-built que respalda el tenant por `JOIN`
  («Task, Sprint y User NO llevan `organization_id`; su scope se deriva por join»), D-D/H15.
- `openspec/specs/labels/spec.md:12` — **discrepancia con el código, documentada y no corregida
  aquí** (H8): la spec describe `TaskLabel` como «Pk + Timestamp + SoftDelete», pero
  `labels/models.py:43` declara `class TaskLabel(PkMixin, TimestampMixin, Base)`. El precedente que
  D-C invoca es el código. Corregir esa spec es un cambio aparte: el 45a no modifica la capacidad
  `labels`.
- `openspec/changes/43-tareas-origen-externo/design.md` — precedentes D-B (equivalencia de DDL),
  D-D (el repositorio es el puerto del agregado), D-F (campos extra se ignoran, no se rechazan),
  D-G (la costura de escritura se implementa donde nace el modelo) y D-I (una fila con borrado
  suave y un único parcial deben cubrir el mismo conjunto).
- `openspec/changes/44-importar-checklist-xlsx/specs/project-hierarchy/spec.md` —
  `board_columns.excluded_from_progress` y `context_group` como criterio de exclusión futuro (R6,
  D-E).
- Código verificado: `backend/app/modules/projects/repository.py:290-350` (CTE `rollup_progress`),
  `projects/models.py:32-53,69` (`uq_project_code_per_org`, `code`),
  `tasks/schemas.py:126-127` + `tasks/service.py:965-968` (`task_key` transitorio),
  `labels/models.py:43-55` (asociación sin `SoftDeleteMixin`),
  `task_links/models.py:23-35` (asociación **con** `SoftDeleteMixin`, por contraste),
  `boards/models.py:46-70` (`status_key`, `column_order`),
  `shared/base_model.py:10-83` (los cinco mixins),
  `shared/pagination.py:24-27,73-135` (paginación opt-in),
  `shared/exceptions.py:14-26` (`AppException`),
  `search/schemas.py:15` (`ENTITY_TYPES: frozenset[str]`, vocabulario cerrado vigente, D-J/H7),
  `activity/recorder.py:23-24` (`ACTOR_TYPE_USER`/`ACTOR_TYPE_SYSTEM` en un archivo fuera del
  quinteto, D-J/H7),
  `dependencies.py:189-203` (`require_role` completo: fábrica, `_checker` y el `AppException`
  `forbidden` 403),
  `intake/router.py:30-34` (comentario de `ruff B008` + los tres singletons de módulo),
  `main.py:14-53,158-192` (cableado; el `include_router` del 45a va **después** de
  `assistant_router` en `:192`, que HEAD ya trae del 48),
  `db_init.py:41-96` (import de modelos),
  `database.py:32-33` (`Base` sin `naming_convention`),
  `alembic/versions/0019_add_intake.py:43-134,293-320` (patrón `create_table` + JSONB + downgrade),
  `alembic/versions/0024_add_work_calendar.py:1-41` (docstring de cabecera y compuerta de head),
  `tests/conftest.py:63-84` (fixture `engine`: `import app.db_init` → `pg_trgm` → `create_all`) y
  `tests/conftest.py:87-110` (fixture `session`, aislamiento por SAVEPOINT con
  `join_transaction_mode="create_savepoint"`),
  `tests/test_migration_project_kind.py` (**244 líneas**, calco del andamiaje de A1).
