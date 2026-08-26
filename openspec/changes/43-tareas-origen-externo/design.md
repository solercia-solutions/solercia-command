# Design: 43 · Ancla de procedencia externa en `tasks` (`source` + `external_key`)

> Fase `sdd-design`. Store híbrido: espejo de Engram `sdd/43-tareas-origen-externo/design`.
> Entradas: `proposal.md`, `specs/tasks/spec.md` (11 requisitos / 26 escenarios ADDED),
> `exploration.md`, `state.yaml`.
> Decisiones cerradas que este diseño **implementa sin reabrir**: D1 (unicidad org-wide en el
> servicio), D2 (`CHECK` de «clave exige origen»), D3 (`String(50)`/`String(255)`), D4 (tarea manual
> = ambas `NULL`), D5 (endpoint dedicado diferido), D6 (insignia diferida al 44), D7 (repartición de
> requisitos con el 40), D8 (reanclaje del 40 dentro del 43), D9 (sin `task_history`) y D-INM
> (inmutabilidad por API).
> Referencias de código verificadas en disco el 2026-08-26.
>
> **Pasada correctiva (2026-08-26)**: tras la verificación independiente del diseño se resolvieron
> catorce hallazgos. Los tres de fondo quedan registrados como decisiones: **D-I** (una tarea con
> borrado suave libera su ancla), la **adopción del orden `(source, external_key, project_id)` con
> eliminación del índice de apoyo** (D-A) y la **implementación de D-G dentro del 43**
> (`create_task(..., external_origin=...)`), que deja de ser nota de contrato y pasa a ser código
> con prueba.

## Enfoque técnico

Cambio estrictamente aditivo sobre un agregado existente. No hay módulos nuevos de dominio, no hay
endpoints nuevos, no hay estado nuevo: dos columnas nulables, **dos** objetos de esquema (un índice
único parcial y un `CHECK`), dos filtros sobre una cadena ya construida, **una costura de lectura**
(`TaskRepository.get_by_external_key`) y **un único camino de escritura del ancla**
(`TaskService.create_task(..., external_origin=...)`, de palabra clave e invisible al esquema HTTP).
Esa pareja lectura/escritura es el contrato real que consumen los cambios 44 y 47.

El idioma es el del propio módulo `tasks`: migración aditiva al estilo de
`0022_add_project_kind.py`, índice parcial espejado en `__table_args__` al estilo de
`users/models.py:28-39`, filtro por la cadena de tres saltos `router → service → repository`
(`router.py:44-121` → `service.py:67-156` → `repository.py:42-125`) y lectura puntual con `JOIN
Project` + `Project.organization_id` como toda otra lectura del repositorio (`repository.py:1-5`:
«every read joins `Task` to `Project` and filters by `organization_id`»).

La regla irrenunciable que atraviesa el diseño: **`tasks` no tiene `organization_id` y no lo va a
tener**. El tenant es transitivo por `project_id`. De ahí sale toda la arquitectura de la garantía:
lo que PostgreSQL puede expresar con las columnas que la tabla ya tiene (unicidad **por proyecto**)
lo da el motor; lo que exigiría un `JOIN` dentro de un `UNIQUE` (unicidad **por organización**) lo
da el servicio consultando la costura antes de insertar.

---

## Decisiones de arquitectura

### D-A · Forma exacta de la garantía: **dos** objetos — índice único parcial + `CHECK` de «clave exige origen»

**Elección**: `uq_tasks_source_external_key_project (source, external_key, project_id) WHERE source
IS NOT NULL AND external_key IS NOT NULL AND is_active`, acompañado de
`ck_tasks_external_key_requires_source CHECK (external_key IS NULL OR source IS NOT NULL)`. **No hay
índice de apoyo**: son dos objetos de esquema, no tres.

El orden de columnas es deliberado. `(source, external_key, project_id)` da **exactamente la misma
unicidad por proyecto** que `(project_id, source, external_key)` — un índice único no distingue orden
para la restricción — pero además sirve como **prefijo** a la búsqueda org-wide de
`get_by_external_key`, que filtra por `(source, external_key)` sin conocer el proyecto. Con el orden
inverso, `project_id` sería la columna líder, el índice no serviría a esa consulta y haría falta un
segundo índice.

| Alternativa | Por qué se rechaza |
|---|---|
| `(project_id, source, external_key)` **más** índice de apoyo `(source, external_key)` (forma anterior de este diseño) | Dos índices donde uno basta: el único con `(source, external_key)` como prefijo cubre la unicidad por proyecto **y** la lectura org-wide. Un índice de más es escritura de más en cada `INSERT`/`UPDATE` de `tasks`, mantenimiento de más y un objeto más que espejar y que probar |
| `UniqueConstraint` plana sobre las tres columnas | Indexa el 100 % de las filas (la inmensa mayoría manuales, con ambas `NULL`) y **no cierra nada**: en PostgreSQL cada `NULL` es distinto, así que N tareas manuales conviven pero también conviven N filas `(P, NULL, 'T-05')` duplicadas |
| Índice parcial `WHERE external_key IS NOT NULL` **sin** `CHECK` (lo que fijaba el 40, `40/tasks.md:64`) | Deja abierto exactamente ese agujero: `(P, NULL, 'T-05')` entra dos veces sin colisión |
| `CHECK` de par estricto `(source IS NULL) = (external_key IS NULL)` | Prohibiría registrar procedencia sin clave estable, un caso legítimo que el 47 puede necesitar (un correo sin `internetMessageId` utilizable) |
| Un solo índice único org-wide vía `EXCLUDE` o trigger | PostgreSQL no admite subconsultas en `EXCLUDE`; un trigger esconde lógica de negocio en el motor y es invisible para `create_all` |

**Justificación**: el `CHECK` es lo que vuelve *sana* la semántica del índice parcial. Sin él, el
predicado `source IS NOT NULL AND external_key IS NOT NULL` no protege el espacio de claves, sólo lo
recorta. Con él, toda fila con clave tiene origen, así que toda fila con clave está dentro del
predicado y por tanto sujeta a la unicidad. El tercer conjunto del predicado (`AND is_active`) es
D-I, abajo.

**Precedentes en el repositorio**: `0017` (`uq_users_numero_documento` con `postgresql_where`),
`0018:88-101` (dos parciales complementarios sobre `org_role_templates`) y `0023:415-421`.
`CheckConstraint` / `op.create_check_constraint`, en cambio, **no tienen precedente**: la búsqueda
sobre `backend/` devuelve cero apariciones. Este cambio introduce el primero, con nombre explícito
(`Base` no declara `naming_convention`, `database.py:32-33`), como ya se hace con
`uq_project_code_per_org` (`projects/models.py:38`).

### D-B · El gate `alembic check` **no** cubre el `CHECK` ni el `postgresql_where` — la prueba sí

**Hecho verificado** sobre el `alembic==1.14.0` instalado (`requirements.txt:5`):

| Objeto | ¿`alembic check` lo compara? | Evidencia |
|---|---|---|
| Existencia del índice por **nombre**, sus columnas y su carácter único | **Sí** | `alembic/autogenerate/compare.py`, `_compare_indexes_and_uniques` |
| `postgresql_where` del índice (predicado parcial) | **No** | `alembic/ddl/postgresql.py:322-380` — `compare_indexes` compara sólo unicidad, expresiones y `_dialect_options`, que a su vez sólo mira `postgresql_nulls_not_distinct` (`:313-320`) |
| `CheckConstraint` | **No, en absoluto** | `compare.py` no contiene ni una aparición de `CheckConstraint`: no existe comparador |

**Consecuencia de diseño**: el riesgo real **no** es un falso positivo del gate, es un **falso
negativo silencioso**. Si el modelo declarara `postgresql_where=text("external_key IS NOT NULL")` y
la migración `text("source IS NOT NULL AND external_key IS NOT NULL")`, `alembic check` seguiría en
verde y la suite (que construye el esquema con `Base.metadata.create_all`, `conftest.py:74-80`)
estaría probando contra una regla distinta de la que corre en producción. Lo mismo si el `CHECK`
apareciera sólo en la migración: las pruebas nunca lo verían.

**Elección**: el espejado se enforza con una prueba de equivalencia de DDL, no con el gate.
`test_create_all_and_migration_declare_the_same_anchor_ddl` levanta **dos** bases desechables — una
con `alembic upgrade 0025`, otra con `Base.metadata.create_all` — y compara, normalizadas, las
cadenas que devuelven `pg_get_indexdef(indexrelid)` para el índice único parcial y
`pg_get_constraintdef(oid)` para el `CHECK`. PostgreSQL normaliza el predicado al almacenarlo, así
que la comparación es entre dos formas ya canónicas y no entre dos literales de Python. Esa prueba
es **el gate real del espejado**; `alembic check` sólo se conserva como capa adicional de existencia
por nombre.

| Alternativa | Por qué se rechaza |
|---|---|
| Confiar en `alembic check` (lo que asumían `proposal.md` R2/R3 y `state.yaml.risks`) | Verificado falso: el gate no ve el predicado ni el `CHECK`. Es condición **necesaria** (detecta un índice ausente por nombre) pero no suficiente |
| Compartir una constante de texto entre `models.py` y la migración | Cero migraciones importan `app.*` (verificado sobre las 24). Una migración es una fotografía inmutable del esquema en un punto del tiempo; acoplarla al modelo vivo rompe `alembic downgrade` en cuanto el modelo cambie |
| Sólo revisión humana del diff | Es precisamente el fallo que R3 describe: la divergencia no rompe nada hasta que rompe todo, meses después |

**Justificación**: `alembic check` se conserva como gate (detecta que el índice exista por nombre en
ambos lados) y se documenta con precisión qué cubre; la prueba de equivalencia cubre el resto.

### D-C · Vocabulario de `source`: constante + validador puro en `app/modules/tasks/sources.py`

**Elección**: un módulo nuevo y minúsculo, `backend/app/modules/tasks/sources.py`, con
`KNOWN_TASK_SOURCES: Final[frozenset[str]]` y `validate_task_source(value: str) -> str`. Sin enum de
PostgreSQL, sin `SAEnum`, sin tabla de catálogo.

| Alternativa | Por qué se rechaza |
|---|---|
| Leer las claves de `app.integrations.registry._ADAPTERS` | Ese dict se puebla **en tiempo de importación** por cada adaptador (`registry.py:1-7`): la validez de un `source` dependería de qué adaptadores se hayan importado en ese proceso. Además crearía la dependencia `tasks → integrations`, que el módulo evita deliberadamente incluso para `labels`/`boards` (importaciones diferidas, `repository.py:99-102`). Y `checklist_xlsx` **no es** un conector: nunca estaría en el registro |
| Constante dentro de `tasks/service.py` | 44 y 47 viven en otros módulos y tendrían que importar un archivo de ~970 líneas para leer un `frozenset` |
| `SAEnum` / enum nativo de PostgreSQL | Una migración por cada proveedor nuevo. Prohibido por D3 y contradice el comentario normativo de `connectors/models.py:50-52` («deliberately NOT a PG enum») |
| `app/shared/enums.py` | Ese archivo aloja enumerados; esto no es un enumerado y `shared/enums.py` no tiene hoy ningún vocabulario de proveedor |

**Contenido y extensión**: `checklist_xlsx` (no es conector; lo escribe el 44) más los **siete**
`provider` realmente registrados — `microsoft365`, `google`, `jira`, `glpi`, `mcp`, `fake` y
`solercia_connect`. Ocho valores en total.

`solercia_connect` es un adaptador de pleno derecho, no un caso de borde: declara
`PROVIDER = "solercia_connect"` (`adapters/solercia_connect/adapter.py:53`, reexportado en
`adapter.py:253` como `provider = PROVIDER`), se registra al importarse
(`adapters/solercia_connect/__init__.py:14`) y `app/db_init.py:36` lo importa junto a los otros
seis. Y `intake/service.py:295` escribe `source_provider=connector.provider` **sin filtrar por
proveedor**, así que un `IntakeItem` con `source_provider="solercia_connect"` ya es posible hoy; en
cuanto el 47 ancle desde ahí, `validate_task_source` lo rechazaría si faltara del vocabulario. Su
ausencia era un rechazo silencioso esperando una fecha.

`planner` **no está**, y un comentario dice por qué (se lee vía `microsoft365` +
`Capability.external_tasks`; la distinción por capacidad vive en `intake_items.item_type`). Extender
el vocabulario es **una línea aquí y cero migraciones**; ese es el punto entero de D3.

**Guardia contra deriva** (escenario 10): la enumeración manual del vocabulario es sostenible
sólo si algo avisa cuando el catálogo de adaptadores crece. La prueba hace
`import app.db_init` (que registra los siete) y afirma
`{a.provider for a in _ADAPTERS.values()} <= KNOWN_TASK_SOURCES`. Es un **subconjunto**, no una
igualdad: `checklist_xlsx` está en el vocabulario y nunca estará en el registro. La prueba importa
`integrations`; el módulo `tasks` **sigue sin importarlo**, que es lo que esta decisión protege.

**Precedente de estructura**: `activity/recorder.py` demuestra que un módulo puede tener archivos
fuera del cuarteto `models/schemas/repository/service/router`.

*Nota de contrato para 44 y 47*: `validate_task_source` es el único punto de validación; el `CHECK`
del motor sólo exige que haya origen, no que el origen sea conocido. Un vocabulario en la base
habría exigido migración; esta repartición es deliberada.

### D-D · El repositorio **es** el puerto de lectura: sin envoltorio `find_by_external_key`

**Elección**: la **lectura** por ancla entra por `TaskRepository.get_by_external_key(...)` y nada
más. No se agrega `TaskService.find_by_external_key`. (La **escritura** sí tiene caso de uso en el
servicio: es D-G, y su único llamador interno es `create_task`.)

| Alternativa | Por qué se rechaza |
|---|---|
| Envoltorio de lectura `TaskService.find_by_external_key` en el 43 | Nacería sin un solo llamador — `create_task` consume el repositorio directamente, como ya hace con el resto del agregado — y sería un método de paso cuya única prueba posible es una tautología. Ningún requisito de la spec lo pide |
| Un servicio de reconciliación genérico en el 43 | Es el comportamiento del importador (leer-o-actualizar), explícitamente fuera de alcance (queda en el 40, D7). El 43 entrega leer y crear, no reconciliar |

**Justificación**: `agents/rules/solercia-persistence.md` pide «Protocols de cara a la aplicación» y
«métodos semánticos por agregado», y prohíbe `get(id)` sin tenant a nivel de servicio.
`get_by_external_key(organization_id, source, external_key)` **es** ese método semántico con tenant
obligatorio: es el puerto de lectura del agregado `Task`. Lo consumen dos actores: `create_task`
(dentro del propio módulo, para la comprobación org-wide de D-G) y el **caso de uso del importador**
de 44 y 47, cuando necesitan decidir entre crear y reconciliar.

El patrón de consumo cruzado ya existe en el repositorio: `TaskService._require_sprint` instancia
`SprintRepository(self.repo.db)` (`service.py:931`) — un servicio del módulo A usando el repositorio
del módulo B dentro de su propia transacción. 44 y 47 harán exactamente eso:
`TaskRepository(self.db).get_by_external_key(...)` para decidir, y `create_task(..., external_origin=
(source, external_key))` para escribir.

**Desviación observada y respetada**: la regla dice «los repositorios nunca hacen commit», pero
`TaskRepository.create`/`save` (`repository.py:229-242`) sí comitean. Es una desviación
**preexistente** de todo el módulo; el 43 no la corrige (no es su cambio) y no la propaga:
`get_by_external_key` es una lectura pura, sin `commit`, sin `flush`, sin mutación.

### D-E · La costura devuelve el ancla **más antigua** de forma determinista, no `scalar_one_or_none`

**Elección**: `.order_by(Task.created_at.asc(), Task.id.asc()).limit(1)` + `.scalars().first()`.

**Alternativa rechazada**: `.scalar_one_or_none()`, que es lo que usan `get`
(`repository.py:187`) y `get_by_project_and_number` (`:207`).

**Justificación — con precisión**: `scalar_one_or_none()` **no** es inseguro por sí mismo bajo un
`LIMIT 1`; con una sola fila devuelta no puede lanzar `MultipleResultsFound`. La razón real de
`.first()` sobre un `limit(1)` explícito es otra: **tolerar de forma determinista varias filas
legítimas**. Es la consecuencia directa de D1 — el motor garantiza unicidad por proyecto, y dos
proyectos de la misma organización **pueden** contener legítimamente el mismo ancla (escenario
«Misma clave en proyectos distintos no colisiona en el motor», que la spec exige que funcione). Sin
`limit(1)`, `scalar_one_or_none()` lanzaría `MultipleResultsFound` → 500 exactamente en la situación
que la costura existe para detectar. Un 500 no es una detección, es una caída. `limit(1)` +
`.first()` expresa esa intención en una sola línea, sin depender de que un lector futuro entienda
que el `LIMIT` es lo que vuelve seguro al `scalar_one_or_none`.

El desempate es **`(created_at asc, id asc)`**, no sólo `created_at`: `created_at` puede empatar al
milisegundo entre dos filas creadas en la misma transacción, y un empate sin desempate devuelve
filas distintas entre llamadas. Con el desempate por `id`, dos llamadas consecutivas devuelven
siempre la misma fila y una reimportación reconcilia siempre contra el registro original, nunca
contra un duplicado posterior. La limitación queda documentada en el docstring del método y en la
spec, y el índice único parcial, con `(source, external_key)` como prefijo (D-A), es lo que hace
barata esta consulta.

### D-F · Inmutabilidad: campos extra se **ignoran**, no se rechazan

**Hecho verificado**: ni `TaskCreate` (`schemas.py:13-59`), ni `TaskUpdate` (`:62-92`), ni `TaskRead`
(`:95-153`) declaran `extra="forbid"`; `TaskRead` sólo declara `ConfigDict(from_attributes=True)`
(`:98`). El comportamiento por defecto de Pydantic v2 es `extra="ignore"`.

**Elección**: no se toca ninguno de los dos esquemas de escritura. Un `POST`/`PATCH` que incluya
`source` o `external_key` recibe 201/200 y el ancla no cambia. **No** se agrega `extra="forbid"`.

**Justificación**: rechazar con 422 sería un cambio de contrato para *todo* el resto de campos
desconocidos del endpoint, no sólo para estos dos — una regresión potencial para cualquier cliente
que hoy envíe un campo de más. `service.py:422` usa `model_dump(exclude_unset=True)`: un campo que el
esquema no declara jamás llega al `dict`, así que la protección es estructural, no defensiva.
Además, `update_task` no captura `IntegrityError` (`service.py:396-508`): si `TaskUpdate` aceptara el
ancla, una violación del único se convertiría en un 500 en lugar de un error de dominio (D-INM,
razón 2).

### D-G · Camino de escritura del ancla: **implementado en el 43**, keyword-only en `create_task`

**Elección**: `TaskService.create_task` gana un parámetro de palabra clave
`external_origin: tuple[str, str] | None = None`. `TaskCreate` y `router.py` **no cambian**: el
parámetro es invisible al esquema HTTP y por tanto inalcanzable desde la API (D-INM intacto).

```python
async def create_task(
    self,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    data: TaskCreate,
    *,
    actor_id: uuid.UUID | None = None,
    external_origin: tuple[str, str] | None = None,   # (source, external_key)
) -> TaskRead: ...
```

**Por qué se implementa aquí y no se difiere** (corrige la versión anterior, que lo dejaba como nota
de contrato):

1. `validate_task_source` **nacía sin un solo llamador**. Un validador que nadie invoca es una
   promesa, no una garantía: el requisito de spec «Vocabulario de `source`» exige una capa de
   escritura que rechace `planner`, y sin camino de escritura esa capa no existe en ninguna parte.
2. Las pruebas de exposición y de la costura necesitaban anclar filas con `UPDATE` crudo — es decir,
   probaban contra un camino que la aplicación no usa. Con `create_task(..., external_origin=...)`
   prueban contra el camino real.
3. Cierra **R9** en vez de mitigarlo: 44 y 47 ya no *deberían* usar la misma forma, la usan porque
   es la única que existe.

**Comportamiento**: cuando `external_origin` viene informado, `create_task` (a) valida el
vocabulario con `validate_task_source(source)`; (b) comprueba la unicidad org-wide llamando a
`self.repo.get_by_external_key(organization_id, source, external_key)`; (c) si ya hay una tarea
activa con ese ancla en la organización, lanza `AppException` con código estable
`task_external_anchor_conflict` y `status_code=409`, **sin insertar**; (d) si no, asigna
`source`/`external_key` al objeto `Task` **antes** de `self.repo.create(task)`, de modo que el ancla
entra en el mismo `INSERT` que el resto de la fila.

*Nota de convención*: el código es `task_external_anchor_conflict` en `lower_snake_case`, no
`TASK_EXTERNAL_ANCHOR_CONFLICT`. Los 25 códigos vigentes de `tasks/service.py` (`task_not_found`,
`invalid_task_type`, `sprint_closed`…) son todos `lower_snake_case`, igual que el valor por defecto
`app_error` de `AppException` (`shared/exceptions.py:20`). El ejemplo en mayúsculas de `CLAUDE.md`
no coincide con el código real; manda el código.

| Alternativa | Por qué se rechaza |
|---|---|
| `UPDATE` posterior a la creación | Abre una ventana en la que la fila existe **sin** ancla y un barrido concurrente la duplica. Además necesitaría capturar `IntegrityError`, que `update_task` no hace hoy |
| Agregar el ancla a `TaskCreate` | Rompe D-INM: la vuelve alcanzable por HTTP y reabre el secuestro de fila que la Threat Matrix cierra |
| Un método aparte `create_imported_task` | Duplicaría las ~80 líneas de validación de metodología, jerarquía, estimación, `assignee` y `sprint` de `create_task`. La procedencia no cambia ninguna de esas reglas |
| Confiar sólo en el índice único | El índice garantiza **por proyecto**; el conflicto entre proyectos de la misma organización sólo lo ve la aplicación (D1). Y un `UniqueViolation` sin capturar es un 500, no un error de dominio |

**Regla de transacción**: `create_task` no abre ni cierra transacción propia; el `commit` sigue
ocurriendo dentro de `TaskRepository.create` (`repository.py:229-235`). Es la desviación
**preexistente** que D-D documenta y que el 43 no corrige ni empeora: el ancla viaja en el mismo
`INSERT`, así que no hay estado intermedio observable.

### D-I · Una tarea con borrado suave **libera** su ancla

**Elección**: el predicado del índice único parcial incluye `AND is_active`, es decir
`WHERE source IS NOT NULL AND external_key IS NOT NULL AND is_active`.

**Secuencia de fallo que motivó el cambio** (con el predicado anterior, sin `is_active`):

```
importar ('jira','PROJ-1') en P  ──▶  fila viva, ancla ocupada
borrado suave de esa tarea       ──▶  is_active=false, PERO el índice sigue reteniendo el ancla
reimportar ('jira','PROJ-1') en P
        │
        ├─ get_by_external_key(...)  ──▶  None   (la costura excluye is_active=false)
        │                                  «no existe, hay que crearla»
        └─ INSERT                    ──▶  UniqueViolation  ──▶  500
```

La costura y el índice discrepaban sobre qué significa «ocupado». La costura ya excluye
`is_active=false` — como el 100 % de las lecturas de `TaskRepository` — así que reportaba el ancla
como libre mientras el motor la seguía reservando. El resultado no era una detección de duplicado
sino un 500 sin salida: la única forma de reimportar sería borrar físicamente la fila, y el proyecto
**prohíbe el delete físico** (`CLAUDE.md`, «Soft delete: NUNCA delete físico»).

| Alternativa | Por qué se rechaza |
|---|---|
| Dejar el ancla retenida y hacer que `get_by_external_key` incluya las borradas suavemente | Rompe la convención del repositorio entero (toda lectura filtra `is_active.is_(True)`) y obligaría a cada importador a distinguir «viva» de «borrada» antes de decidir. Además resucitaría tareas que el usuario borró a propósito |
| Dejarlo retenido y capturar `UniqueViolation` en el importador | Convierte un caso normal (reimportar algo que se borró) en un error que el importador debe entender y traducir. La restricción estaría prohibiendo un caso legítimo |
| Añadir `deleted_at` al índice en lugar de `is_active` | `is_active` es la columna que filtra el 100 % de las lecturas; `deleted_at` es informativa. Espejar el predicado sobre la columna que nadie consulta invitaría a que ambos se separen |

**Justificación**: la unicidad debe cubrir el mismo conjunto de filas que la costura considera
existentes. Con `AND is_active`, «ocupado por el motor» y «encontrado por la costura» pasan a ser la
misma cosa, y borrar suavemente una tarea libera su ancla para una reimportación futura, que es el
comportamiento que un usuario espera de un borrado.

**Salvedad — ruta de restauración**: hoy **no existe** ninguna ruta que reactive una tarea. La
búsqueda sobre `backend/app/` sólo devuelve `task.is_active = False` (`tasks/service.py:645`); las
reactivaciones existentes son de otros agregados (`task_links/service.py:117`,
`connectors/repository.py:136`, `glpi_sync/repository.py:74`) y ninguna toca `tasks`. Por eso D-I es
seguro hoy. Pero si alguna vez se agrega un «restaurar tarea», esa ruta **debe comprobar el ancla
antes de reactivar** (llamar a `get_by_external_key` y rechazar si el ancla ya está ocupada por una
tarea activa); de lo contrario el `UPDATE ... SET is_active=true` reingresa la fila al predicado del
índice y produce un `UniqueViolation` en la reactivación. Queda registrado como riesgo abierto (R10)
para el cambio que la introduzca, no como trabajo del 43.

### D-H · Frontend: sólo el tipo, verificado por la compilación existente

**Elección**: dos campos opcionales en la interfaz `Task` de
`frontend/src/entities/workspace/workspace.model.ts:9-38`. `TaskDetail extends Task`
(`entities/task/task-detail.model.ts:4-9`) los hereda sin editar ese archivo. Sin insignia (D6).

**Verificación**: `cd frontend && npm run build`. **No** se agrega una prueba de tipos, y la razón es
concreta, no comodidad:

1. `frontend/package.json:5-11` no define ningún script de pruebas ni hay runner configurado
   (`ng`, `start`, `build`, `lint`, `watch`).
2. `tsconfig.app.json:7-10` declara `"files": ["src/main.ts"]` y `"include": ["src/**/*.d.ts"]`: el
   compilador sólo recorre lo alcanzable desde `main.ts`. Un archivo suelto de aserciones de tipo
   **nunca se compilaría** y daría una falsa sensación de cobertura.
3. Agregar dos propiedades opcionales a una interfaz es aditivo puro: no puede romper la
   compilación. `npm run build` es, honestamente, un gate de **no regresión**, no de existencia.

Quien prueba la *existencia* del contrato es el backend (escenarios «Tarea importada expone ambas
claves» y «Listado y tablero exponen los campos nuevos»), más la lectura de un diff de dos líneas.
El primer punto de uso real del tipo llega con la insignia del 44.

---

## Estructura de módulos

| Archivo | Contenido |
|---|---|
| `backend/alembic/versions/0025_add_task_external_origin.py` | Crear · 2 columnas + `CHECK` + único parcial (2 objetos) |
| `backend/app/modules/tasks/models.py` | Modificar · 2 columnas + 2 objetos en `__table_args__` |
| `backend/app/modules/tasks/sources.py` | Crear · `KNOWN_TASK_SOURCES` (8 valores) + `validate_task_source` |
| `backend/app/modules/tasks/schemas.py` | Modificar · 2 campos en `TaskRead` |
| `backend/app/modules/tasks/repository.py` | Modificar · 2 filtros + `get_by_external_key` |
| `backend/app/modules/tasks/service.py` | Modificar · reenvío de 2 kwargs en `list_tasks` + `external_origin` en `create_task` (D-G) |
| `backend/app/modules/tasks/router.py` | Modificar · 2 `Query` |
| `frontend/src/entities/workspace/workspace.model.ts` | Modificar · 2 campos opcionales |

### Migración `0025_add_task_external_origin.py`

```python
"""add_task_external_origin

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-26 00:00:00.000000

Change 43-tareas-origen-externo (design.md "Migración 0025"). Head verified
live (``alembic heads`` -> single ``0024``, no fork) immediately before
authoring this file.

Purely additive, NO backfill: both columns are NULLABLE, so every existing
row keeps its values and simply gains two NULLs. Same additive pattern as
``0022_add_project_kind.py``, WITHOUT the ``server_default``/``alter_column``
pair — that pair exists only to backfill a ``NOT NULL`` column, and neither of
these is ``NOT NULL``.

``downgrade()`` reverses in strict creation order (unique index -> check ->
external_key -> source): additive metadata never referenced by a foreign key,
so dropping it loses no task business data.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kept BYTE-IDENTICAL to app/modules/tasks/models.py `__table_args__`
# (design.md D-B). `alembic check` does NOT compare these predicates, so the
# equality is enforced by test_migration_task_external_origin.py.
#
# `AND is_active` (design.md D-I): a soft-deleted task RELEASES its anchor, so
# the index covers exactly the same rows `get_by_external_key` considers to
# exist. Column order is `(source, external_key, project_id)` (design.md D-A):
# same per-project uniqueness, and its leading `(source, external_key)` prefix
# also serves the org-wide lookup, which is why there is no second index.
_ANCHOR_UNIQUE_WHERE = (
    "source IS NOT NULL AND external_key IS NOT NULL AND is_active"
)
_ANCHOR_CHECK = "external_key IS NULL OR source IS NOT NULL"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("source", sa.String(length=50), nullable=True))
    op.add_column(
        "tasks", sa.Column("external_key", sa.String(length=255), nullable=True)
    )
    op.create_check_constraint(
        "ck_tasks_external_key_requires_source", "tasks", _ANCHOR_CHECK
    )
    op.create_index(
        "uq_tasks_source_external_key_project",
        "tasks",
        ["source", "external_key", "project_id"],
        unique=True,
        postgresql_where=sa.text(_ANCHOR_UNIQUE_WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_tasks_source_external_key_project", table_name="tasks")
    op.drop_constraint(
        "ck_tasks_external_key_requires_source", "tasks", type_="check"
    )
    op.drop_column("tasks", "external_key")
    op.drop_column("tasks", "source")
```

*Gotcha*: sin `batch_alter_table` — no aparece en ninguna de las 24 migraciones; el proyecto es
PostgreSQL exclusivo. Sin `server_default` — 0022/0024 lo usan sólo para retrollenar columnas `NOT
NULL`, y aquí ninguna lo es.

### Espejo en `Task.__table_args__`

`tasks/models.py` hoy declara **sólo** los dos GIN trigram (`:43-58`) y cero restricciones únicas.
Se agregan **dos** entradas y dos importaciones (`CheckConstraint`, `text`):

```python
__table_args__ = (
    Index("ix_tasks_title_trgm", ...),          # sin cambios
    Index("ix_tasks_description_trgm", ...),    # sin cambios
    # External-origin anchor (change 43-tareas-origen-externo). Declared HERE
    # and not only in migration 0025 because the test harness builds the
    # schema with `Base.metadata.create_all` (tests/conftest.py:74-80), same
    # rule as `uq_users_numero_documento` (users/models.py:28-39).
    # The predicates below are BYTE-IDENTICAL to 0025: `alembic check` does
    # NOT compare partial-index WHERE clauses nor CHECK constraints
    # (alembic 1.14.0, ddl/postgresql.py:322-380), so the equivalence is
    # asserted by test_migration_task_external_origin.py, not by the gate.
    CheckConstraint(
        "external_key IS NULL OR source IS NOT NULL",
        name="ck_tasks_external_key_requires_source",
    ),
    # `(source, external_key, project_id)`: same per-project uniqueness as the
    # reverse order, but the leading `(source, external_key)` prefix ALSO
    # serves `get_by_external_key`'s org-wide lookup — which is why this is
    # the only index the anchor needs (design.md D-A).
    # `AND is_active`: a soft-deleted task RELEASES its anchor, so the index
    # covers exactly the rows the seam considers to exist (design.md D-I).
    Index(
        "uq_tasks_source_external_key_project",
        "source",
        "external_key",
        "project_id",
        unique=True,
        postgresql_where=text(
            "source IS NOT NULL AND external_key IS NOT NULL AND is_active"
        ),
    ),
)

# Origin system of an imported task (change 43). Free-form string validated at
# the write layer against `app.modules.tasks.sources.KNOWN_TASK_SOURCES`,
# deliberately NOT a PG enum (same reason as `connectors.provider`). NULL on
# every manually created task — there is no `manual` sentinel (D4).
source: Mapped[str | None] = mapped_column(String(50), nullable=True)
# Opaque key of the task in `source` (e.g. "T-05", "PROJ-123", an Outlook
# internetMessageId). Length aligned with `intake_items.external_id`, the
# value change 47 copies verbatim.
external_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

Ninguna de las dos columnas lleva `index=True`: el único parcial ya cubre el patrón de consulta con
su prefijo `(source, external_key)`, y un índice sobre `source` solo no tiene caso de uso.

### `sources.py`

```python
"""Vocabulary of ``tasks.source`` (change 43-tareas-origen-externo).

``tasks.source`` is a free-form ``String(50)``, deliberately NOT a PG enum:
adding a provider must be ONE line here and ZERO migrations (design.md D-C,
same rationale as ``connectors.provider``, connectors/models.py:50-52).

This module deliberately does NOT read ``app.integrations.registry``: that dict
is populated at IMPORT time by each adapter's own module, so its contents would
depend on which adapters happen to be imported; it would create a
``tasks -> integrations`` dependency the module avoids even for ``labels``; and
``checklist_xlsx`` is not a connector at all. A TEST guards the drift instead
(``test_every_registered_adapter_provider_is_a_known_task_source``).

Writing the anchor goes through exactly ONE entry point:
``TaskService.create_task(..., external_origin=(source, external_key))``
(design.md D-G). It is keyword-only and absent from ``TaskCreate``, so it is
unreachable over HTTP; changes 44 and 47 MUST use it instead of inventing
their own write path.
"""

from typing import Final

from app.shared.exceptions import AppException

KNOWN_TASK_SOURCES: Final[frozenset[str]] = frozenset(
    {
        # Not a connector: the CHECKLIST_TAREAS.xlsx importer (change 44).
        "checklist_xlsx",
        # The SEVEN registered connector providers. MUST stay byte-identical
        # to `Connector.provider` / `IntakeItem.source_provider` — never a
        # synthetic or renamed value. Kept in sync with
        # `app/integrations/adapters/` by the drift guard test above.
        # `planner` is NOT here on purpose: Planner is read THROUGH
        # `microsoft365` + `Capability.external_tasks`; the per-capability
        # distinction already lives in `intake_items.item_type`.
        "microsoft365",
        "google",
        "jira",
        "glpi",
        "mcp",
        "fake",
        "solercia_connect",
    }
)


def validate_task_source(value: str) -> str:
    """Return ``value`` when it belongs to the vocabulary, else raise 422.

    Called by ``TaskService.create_task`` BEFORE writing `tasks.source`, which
    is the only path that writes it. The database CHECK only enforces "a key
    requires an origin"; it does not know the vocabulary.
    """

    if value not in KNOWN_TASK_SOURCES:
        raise AppException(
            "El sistema de origen indicado no es válido para una tarea.",
            code="invalid_task_source",
            status_code=422,
        )
    return value
```

El mensaje **no interpola el valor recibido**, siguiendo la convención de mensajes de error del
repositorio (español colombiano formal, sin eco de la entrada).

### Costura `TaskRepository.get_by_external_key`

```python
async def get_by_external_key(
    self,
    organization_id: uuid.UUID,
    source: str,
    external_key: str,
) -> Task | None:
    """Return the active task anchored to ``(source, external_key)`` inside
    the organization, or ``None``.

    THE read seam of the anchor. `TaskService.create_task` calls it before
    inserting an `external_origin`, and the import flows (changes 44 and 47)
    call it to decide between creating and reconciling: the engine only
    guarantees uniqueness WITHIN a project
    (`uq_tasks_source_external_key_project`) — `tasks` has no
    `organization_id` and Postgres cannot express UNIQUE across a JOIN
    (design.md D1/D-E).

    Deliberately `limit(1)` + `.first()` instead of `scalar_one_or_none()`:
    two projects of the same organization MAY legally hold the same anchor, so
    an unbounded `scalar_one_or_none()` would raise `MultipleResultsFound` (a
    500) exactly where a duplicate must be DETECTED, turning a diagnosis into
    a crash. The tie-break is `(created_at asc, id asc)` — `created_at` alone
    can tie for rows created in the same transaction — so two consecutive
    calls always return the SAME row and a re-import reconciles against the
    original task, never against a later duplicate.

    Returns `None` (never raises) when there is no match. Excludes
    soft-deleted tasks AND tasks under soft-deleted projects, same as
    `list_for_org` (repository.py:157-171). Does NOT commit.
    """

    result = await self.db.execute(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.source == source,
            Task.external_key == external_key,
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
            Task.is_active.is_(True),
        )
        .order_by(Task.created_at.asc(), Task.id.asc())
        .limit(1)
    )
    return result.scalars().first()
```

### Escritura del ancla en `TaskService.create_task` (D-G)

El resto de `create_task` (`service.py:252-335`) **no cambia**: jerarquía, strategy, estimación,
`assignee`, `sprint` y `task_number` siguen exactamente igual. Se agrega el parámetro y un bloque de
guarda antes de construir el `Task`, más dos asignaciones dentro del constructor:

```python
    # -- External-origin anchor (change 43, design.md D-G) ------------------
    # Keyword-only and absent from TaskCreate: unreachable over HTTP (D-INM).
    # Only an importer (changes 44/47) or a maintenance operation passes it.
    anchor_source: str | None = None
    anchor_key: str | None = None
    if external_origin is not None:
        anchor_source, anchor_key = external_origin
        # The DB CHECK only enforces "a key requires an origin"; the closed
        # vocabulary lives here (raises 422 `invalid_task_source`).
        validate_task_source(anchor_source)
        # Org-wide uniqueness is the SERVICE's job (D1): the partial unique
        # index only covers one project, and `tasks` has no organization_id.
        existing = await self.repo.get_by_external_key(
            organization_id, anchor_source, anchor_key
        )
        if existing is not None:
            raise AppException(
                "Ya existe una tarea activa con esa procedencia externa en "
                "esta organización.",
                code="task_external_anchor_conflict",
                status_code=409,
            )

    task = Task(
        ...,                       # sin cambios
        source=anchor_source,      # NULL on every manually created task (D4)
        external_key=anchor_key,
    )
    task = await self.repo.create(task)   # el ancla viaja en el MISMO INSERT
```

Tres propiedades que importan: el ancla entra en el `INSERT` inicial y no en un `UPDATE` posterior
(sin ventana de duplicación); el conflicto sale como error de dominio 409 y no como `IntegrityError`
→ 500; y una creación **sin** `external_origin` recorre exactamente el mismo camino que hoy, con
ambas columnas en `NULL`.

### Filtros — la cadena de tres saltos, sin novedad estructural

| Salto | Edición |
|---|---|
| `router.py:44-121` | `source: str \| None = Query(default=None, description="Filtra por sistema de origen exacto (ej. 'checklist_xlsx', 'jira').")` y `external_key: str \| None = Query(default=None, description="Filtra por clave exacta en el sistema de origen (ej. 'T-05').")`, reenviados en la llamada a `service.list_tasks` (`:105-120`) |
| `service.py:67-156` | Dos kwargs más en la firma y en el reenvío a `repo.list_for_project` (`:111-130`). Cero lógica |
| `repository.py:42-125` | `if source is not None: stmt = stmt.where(Task.source == source)` y su gemelo, junto a los `if` existentes (`:84-97`) |

**No** se agregan a `SORTABLE_FIELDS` (`repository.py:26-33`): ordenar un tablero por sistema de
origen no es un caso de uso y ampliar la whitelist amplía la superficie de `?sort=` sin razón.

### `TaskRead` y frontend

```python
# TaskRead (schemas.py, tras `task_key`)
# External-origin anchor (change 43). Read-only: never accepted by TaskCreate
# or TaskUpdate (D-INM). NULL on manually created tasks.
source: str | None = None
external_key: str | None = None
```

```ts
// workspace.model.ts, interfaz Task
/** Origin system of an imported task (change 43). Absent/null on manual
 * tasks. Read-only: never sent on create/update. */
source?: string | null;
/** Key of the task in that origin system (e.g. "T-05", "PROJ-123"). */
external_key?: string | null;
```

---

## Flujo de datos

**Ancla — el camino completo que el 43 entrega (lectura + escritura):**

```
Importador (44 / 47)         tasks/service.py           tasks/repository.py        PostgreSQL
      │                            │                            │                      │
      │ get_by_external_key(org, s, k)  ── decide crear o reconciliar ──▶ SELECT tasks
      ├─────────────────────────────────────────────────────────▶│  JOIN projects
      │                            │                            │  WHERE project.org = :o
      │                            │                            │    AND project.is_active
      │                            │                            │    AND source = :s      usa el
      │                            │                            │    AND external_key = :k prefijo
      │                            │                            │    AND task.is_active   (source,
      │                            │                            │  ORDER BY created_at,   external_
      │◀────────────────────────────────────────────────────────┤  id  LIMIT 1            key) del
      │  Task | None               │                            │                      único parcial
 ┌────┴─────┐                      │                            │
 │ None?    │                      │                            │
 │          │── no ─▶ reconciliar la fila existente (comportamiento del importador, 40/44/47)
 │          │                      │                            │
 │          └── sí ─▶ create_task(org, proj, TaskCreate(...), external_origin=(s, k))
 └──────────┘                      │                            │
                                   │ validate_task_source(s) ── 422 si no está en el vocabulario
                                   │ get_by_external_key(...) ── 409 task_external_anchor_conflict
                                   │                            │
                                   ├───────────────────────────▶│ INSERT (ancla incluida)
                                   │                            │   ── uq_tasks_source_external_key_
                                   │                            │        project  (por proyecto, y
                                   │                            │        sólo sobre filas activas)
                                   │                            │   ── ck_tasks_external_key_
                                   │                            │        requires_source
```

**Lectura por HTTP — el camino que sí entrega el 43:**

```
GET /projects/{id}/tasks?status=in_progress&source=checklist_xlsx&external_key=T-05
        │
        ▼
router.list_tasks ──▶ service.list_tasks ──▶ repository.list_for_project
   (2 Query nuevas)      (2 kwargs)             (2 .where() nuevos)
                                                       │
                              TaskRead.model_validate(task)  ◀── from_attributes
                                                       │
                        {"data": [...], "meta": {...}}  ── source/external_key incluidos
                        en listado, detalle y GET /dashboard/executive SIN tocar
                        TaskService._to_read (:954-969) ni DashboardService._to_read (:468-473)
```

---

## Cambios de archivos

| Archivo | Acción | Descripción |
|---|---|---|
| `backend/alembic/versions/0025_add_task_external_origin.py` | Crear | 2 columnas nulables + `CHECK` + único parcial (2 objetos); `down_revision="0024"` |
| `backend/app/modules/tasks/models.py` | Modificar | 2 columnas + 2 entradas en `__table_args__`; importar `CheckConstraint` y `text` |
| `backend/app/modules/tasks/sources.py` | Crear | `KNOWN_TASK_SOURCES` (8 valores) + `validate_task_source` |
| `backend/app/modules/tasks/schemas.py` | Modificar | 2 campos en `TaskRead`. `TaskCreate`/`TaskUpdate` intactos |
| `backend/app/modules/tasks/repository.py` | Modificar | 2 filtros en `list_for_project` + `get_by_external_key` |
| `backend/app/modules/tasks/service.py` | Modificar | 2 kwargs de paso en `list_tasks` + `external_origin` en `create_task` (validación de vocabulario, guarda org-wide 409 y 2 asignaciones) |
| `backend/app/modules/tasks/router.py` | Modificar | 2 `Query` con `description` en `list_tasks`. **`create_task` no cambia**: `external_origin` es de palabra clave y el router no lo pasa |
| `frontend/src/entities/workspace/workspace.model.ts` | Modificar | 2 campos opcionales en `Task` |
| `backend/tests/test_migration_task_external_origin.py` | Crear | Patrón `test_migration_project_kind.py:73-244` + equivalencia de DDL (D-B) |
| `backend/tests/test_tasks_external_origin.py` | Crear | Patrón `test_task_filters.py:1-64` + unidades puras del vocabulario |
| `openspec/changes/40-jira-import-usuario/{design.md,tasks.md,specs/tasks/spec.md,state.yaml}` | Modificar | Reanclaje (D8) — artefactos, sin código |

**No se toca**: `boards`, `sprints`, `methodology`, `labels`, `checklists`, `task_links`,
`activity`, `dashboard`, `intake`, `backend/tests/test_migrations_baseline.py` (es el gate, no cambia
ni una línea), `frontend/src/entities/task/task-detail.model.ts` (hereda por `extends`).

---

## Estrategia de pruebas (TDD estricto: rojo antes que código)

`openspec/config.yaml:26-30` fija `tdd: true`. Cada escenario de la spec tiene una prueba nombrada.

### Cobertura escenario → prueba (26 / 26)

Columna **Tipo**: `RED` = debe fallar antes del código y pasar después; `guardia` = verde desde el
primer momento, existe para que **siga** siéndolo (H10 — un `guardia` que arranca rojo delataría
que el supuesto que protege ya está roto).

| # | Requisito · Escenario | Prueba | Tipo | Archivo · rebanada |
|---|---|---|---|---|
| 1 | Ancla · Duplicado exacto en el mismo proyecto es rechazado | `test_duplicate_anchor_in_the_same_project_raises_unique_violation` (`asyncpg.exceptions.UniqueViolation`) | RED | migración · A |
| 2 | Ancla · Múltiples tareas manuales sin ancla conviven | `test_many_unanchored_tasks_coexist_in_the_same_project` (3 filas `(NULL, NULL, P)`) | RED | migración · A |
| 3 | Ancla · Misma clave en proyectos distintos no colisiona | `test_the_same_anchor_in_two_projects_does_not_collide` | RED | migración · A |
| 4 | Ancla · Clave externa sin origen viola la integridad | `test_external_key_without_source_raises_check_violation` (`asyncpg.exceptions.CheckViolation`) | RED | migración · A |
| 5 | Ancla · **Una tarea con borrado suave libera su ancla** (D-I) | `test_a_soft_deleted_task_releases_its_anchor` (ancla → `UPDATE is_active=false` → segunda fila activa con el mismo par **aceptada**). La mitad de costura del escenario («devuelve solo la activa») la asegura la prueba 22 | RED | migración · A |
| 6 | Migración · Agrega columnas nulables sin afectar filas existentes | `test_upgrade_adds_nullable_columns_without_touching_existing_rows` (`information_schema.columns`: presentes, `is_nullable='YES'`; la fila sembrada intacta con ambas `NULL`) | RED | migración · A |
| 7 | Migración · Downgrade limpio conserva las filas | `test_downgrade_removes_the_columns_without_losing_rows` | RED | migración · A |
| 8 | Espejo ORM · Esquema de `create_all` coincide con el de la migración | `test_create_all_and_migration_declare_the_same_anchor_ddl`, **aserción de índice**: `pg_get_indexdef` de `uq_tasks_source_external_key_project` idéntico en las dos bases desechables | RED | migración · A |
| 9 | Espejo ORM · **La equivalencia de DDL se comprueba por definición, no por `alembic check`** | `test_create_all_and_migration_declare_the_same_anchor_ddl`, **aserción de restricción**: `pg_get_constraintdef` de `ck_tasks_external_key_requires_source` idéntico en ambas. Pruebas de **apoyo, sin escenario propio**: `test_migrations_baseline.py::test_alembic_check_reports_no_diff_after_upgrade` (`:192-214`, archivo sin cambios, **guardia**) y `test_anchor_objects_exist_by_name_in_both_schemas` (lo único que el gate sí cubre, D-B) | RED | migración · A |
| 10 | Vocabulario · Origen de conector coincide exactamente con el identificador | `test_every_registered_adapter_provider_is_a_known_task_source`: tras `import app.db_init`, afirma `{a.provider for a in _ADAPTERS.values()} <= KNOWN_TASK_SOURCES` (subconjunto: `checklist_xlsx` nunca estará en el registro), más `validate_task_source("microsoft365") == "microsoft365"`. Guardia **contra deriva** una vez verde; arranca en rojo sólo porque `sources.py` aún no existe | RED → guardia | API · B |
| 11 | Vocabulario · `planner` no es un valor válido de `source` | `test_planner_is_rejected_as_a_task_source` (`AppException`, `code == "invalid_task_source"`, `status_code == 422`, el valor **no** aparece en `detail`) | RED | API · B |
| 12 | Conviven · Tarea importada expone ambas claves | `test_task_detail_exposes_task_key_and_external_key_side_by_side` — ancla vía `create_task(..., external_origin=("jira", "PROJ-123"))` y consulta `GET /tasks/{id}` | RED | API · B |
| 13 | Conviven · Listado y tablero exponen los campos sin cambios de servicio | `test_listing_and_executive_dashboard_expose_source_and_external_key`: **al menos una fila anclada** vía `create_task(..., external_origin=...)`, de modo que `GET /projects/{id}/tasks` y `GET /dashboard/executive` devuelven valores **no nulos** (no sólo la presencia de la clave), sin editar los dos `_to_read` | RED | API · B |
| 14 | Filtros · `source` y `external_key` componen con otros filtros | `test_source_and_external_key_filters_compose_with_status` | RED | API · C |
| 15 | Filtros · Sin coincidencias devuelve colección vacía, no error | `test_a_filter_without_matches_returns_an_empty_collection_with_200`. **El proyecto debe tener al menos una tarea sin ancla**: sobre un proyecto vacío la respuesta sería vacía incluso sin el filtro implementado y la prueba nacería verde | RED | API · C |
| 16 | Inmutabilidad · `POST` con `external_key` no lo persiste | `test_post_with_external_key_in_the_body_is_ignored_without_a_validation_error` (201 y `external_key is None`) | RED | API · B |
| 17 | Inmutabilidad · `PATCH` con `source` no altera un ancla existente | `test_patch_with_source_never_alters_an_existing_anchor` — ancla vía `create_task(..., external_origin=...)`; el `status` sí cambia, el ancla no | RED | API · B |
| 18 | **Escritura reservada** · `create_task` con `external_origin` válido persiste y expone el ancla | `test_create_task_with_external_origin_persists_and_exposes_the_anchor` (el `TaskRead` devuelto trae ambos valores; la fila releída también) | RED | API · B |
| 19 | **Escritura reservada** · Ancla ya activa en la organización aborta la creación | `test_create_task_rejects_an_anchor_already_active_in_the_organization` (**otro** proyecto de la misma organización; `AppException` `code == "task_external_anchor_conflict"`, `status_code == 409`, y el conteo de tareas del segundo proyecto no cambia) | RED | API · B |
| 20 | Costura · Encuentra un ancla existente en la organización | `test_get_by_external_key_finds_an_anchor_inside_the_organization` | RED | API · B |
| 21 | Costura · Nunca cruza organizaciones | `test_get_by_external_key_never_crosses_organizations` (segunda organización, mismo ancla ⇒ `None`) | RED | API · B |
| 22 | Costura · Excluye tareas **y proyectos** con borrado suave | `test_get_by_external_key_excludes_soft_deleted_tasks_and_projects` (dos casos: `Task.is_active=false` y `Project.is_active=false`, ambos ⇒ `None`) | RED | API · B |
| 23 | Sin historial · `PATCH` sin diff de procedencia | `test_patch_records_no_history_entry_for_source_or_external_key` (`_HISTORY_TRACKED_FIELDS`, `service.py:387-394`, no los contiene) | **guardia** | API · B |
| 24 | Sin historial · `is_context` y `merge_into` fuera del modelo | `test_is_context_and_merge_into_are_not_persisted_columns` (unidad pura sobre `Task.__table__.columns`) | **guardia** | API · B |
| 25 | Frontend · El tipo `Task` incluye los campos opcionales | `cd frontend && npm run build` + revisión del diff (D-H: no hay runner y `tsconfig.app.json:7` sólo compila lo alcanzable desde `main.ts`) | RED | build · B |
| 26 | Frontend · `TaskDetail` hereda los campos | Mismo comando; `TaskDetail extends Task` no requiere edición (`task-detail.model.ts:4-9`) | RED | build · B |

Escenarios sin prueba automatizada: **ninguno de backend**. Los dos de frontend (25, 26) se cierran
con la compilación existente, con la justificación de D-H escrita.

**Guardias** (verdes desde el primer momento; **no** siguen el ciclo RED/GREEN): 23, 24 y la prueba
de apoyo `test_alembic_check_reports_no_diff_after_upgrade`. Declararlas como RED sería un error de
planificación: si alguna arrancara en rojo, el supuesto que protegen ya estaría roto y eso sería un
hallazgo, no un paso del TDD. La 10 es un caso mixto y queda marcado como tal: nace roja porque el
módulo no existe y **queda** como guardia permanente contra la deriva del catálogo de adaptadores.

### Estructura de los dos archivos nuevos

| Archivo | Andamiaje |
|---|---|
| `test_migration_task_external_origin.py` (rebanada A) | Calco literal de `test_migration_project_kind.py:73-244`: `_sync_dsn` / `_admin_dsn` / `_recreate_*_database` / `_drop_*_database` / `_alembic_config` / `_run_against`, base desechable `solercia_test_task_external_origin_migration`, `command.upgrade(cfg, "0024")` → siembra por SQL crudo con `asyncpg` (organización + 2 proyectos + 1 tarea) → `command.upgrade(cfg, "0025")` → aserciones → `command.downgrade(cfg, "0024")`. **Todas** las pruebas de este archivo son síncronas con `asyncio.run(...)` y `@skip_no_db`: ya no aloja pruebas de API (las de exposición pasaron a la rebanada B, porque anclan con `create_task(..., external_origin=...)` y ese camino nace en B). La equivalencia de DDL (filas 8 y 9) levanta una **segunda** base desechable y, sobre ella, ejecuta en este orden: `CREATE EXTENSION IF NOT EXISTS pg_trgm` (obligatorio, `conftest.py:74-80`) → **`import app.db_init`** → `Base.metadata.create_all`. El `import app.db_init` **no es opcional**: es lo que puebla `Base.metadata` con todos los modelos ORM (`conftest.py:66-69` lo hace por la misma razón); sin él, `create_all` construiría un esquema incompleto y la comparación de DDL sería vacua |
| `test_tasks_external_origin.py` (rebanadas B y C) | Calco de `test_task_filters.py:1-64`: helpers `_auth`, `_create_project`, `_create_task`, `_list_tasks`; API real in-process vía `httpx`; `@skip_no_db` + `@pytest.mark.asyncio(loop_scope="session")`. Toda fila anclada se crea con `TaskService(...).create_task(..., external_origin=(source, external_key))` sobre la fixture `session` — **nunca** con `UPDATE` crudo: el ancla ya tiene camino de escritura legítimo (D-G) y probar contra un `UPDATE` sería probar contra un camino que la aplicación no usa. Las pruebas de la costura instancian `TaskRepository(session)` directamente. Las pruebas 10, 11 y 24 son unidades puras **sin** `@skip_no_db` |

### Comandos y línea base

```
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test \
  .venv/bin/python -m pytest -q \
  tests/test_migration_task_external_origin.py \
  tests/test_tasks_external_origin.py \
  tests/test_migrations_baseline.py
cd frontend && npm run build
```

**Línea base a no regresar**: **1411 pasadas / 3 fallidas preexistentes**, todas en
`tests/test_adapter_microsoft365.py`, dependientes del reloj y ajenas a este cambio: se heredan, no
se arreglan aquí. La línea base **sólo** vale con `TEST_DATABASE_URL` puesta; sin ella `skip_no_db`
salta 898 pruebas y la corrida no sirve de referencia.

---

## Threat Matrix

La matriz estándar (`references/threat-matrix.md`) cubre enrutamiento, shell, subprocesos,
automatización de VCS/PR y clasificación de ejecutables. Este cambio no toca ninguna de esas
fronteras:

| Frontera | Aplicabilidad |
|---|---|
| Rutas tipo documentación / clasificación de ejecutables | N/A — el cambio no clasifica ni ejecuta archivos |
| Selección de repositorio git · estado de commit · estado de push · comandos de PR | N/A — sin automatización de VCS/PR |
| Shell / subprocesos | N/A — el único proceso externo es `alembic` dentro de las pruebas, ya existente |

Las fronteras reales de este cambio son **integridad del espacio de claves** y **aislamiento entre
organizaciones**, y sí son aplicables:

| Caso adversario | Comportamiento seguro | Prueba en rojo |
|---|---|---|
| Un cliente pre-crea `('checklist_xlsx', 'T-05')` por API y **secuestra** la fila que el importador espera escribir | Inmutabilidad por API: los campos no existen en `TaskCreate`/`TaskUpdate`, así que `model_dump(exclude_unset=True)` nunca los ve. El único camino de escritura es `create_task(..., external_origin=...)`, de palabra clave y no expuesto por el router | 16 `test_post_with_external_key_in_the_body_is_ignored_without_a_validation_error`, 17 `test_patch_with_source_never_alters_an_existing_anchor` |
| **Fuga entre organizaciones** por la costura: leer o reconciliar contra el ancla de otro tenant | `JOIN Project` + `Project.organization_id == organization_id` obligatorio en la firma; no existe sobrecarga sin tenant | 21 `test_get_by_external_key_never_crosses_organizations` |
| Resucitar una tarea borrada suavemente al reimportar | `Task.is_active.is_(True)` y `Project.is_active.is_(True)` en la costura, igual que `list_for_org` | 22 `test_get_by_external_key_excludes_soft_deleted_tasks_and_projects` |
| **Ancla retenida por una fila muerta**: una tarea borrada suavemente bloquea para siempre la reimportación de su propio origen y produce un 500 sin salida (el proyecto prohíbe el delete físico) | D-I: `AND is_active` en el predicado del único, de modo que el motor y la costura cubren el mismo conjunto de filas | 5 `test_a_soft_deleted_task_releases_its_anchor` |
| **Duplicación entre proyectos de la misma organización**, que el motor no puede impedir | Guarda org-wide en `create_task` antes del `INSERT` (D-G): error de dominio 409 `task_external_anchor_conflict`, no `IntegrityError` → 500 | 19 `test_create_task_rejects_an_anchor_already_active_in_the_organization` |
| **Agujero silencioso de unicidad**: `(NULL, 'T-05', P)` duplicado no colisiona porque el `NULL` vuelve distintas las filas | `ck_tasks_external_key_requires_source` hace imposible la clave sin origen, así que toda fila con clave cae dentro del predicado del único | 4 `test_external_key_without_source_raises_check_violation` + 1 `..._raises_unique_violation` |
| **Divergencia modelo↔migración** que hace que las pruebas validen una regla distinta de la de producción | Equivalencia de DDL comparada entre las dos rutas de construcción del esquema; el gate `alembic check` como capa adicional para la existencia por nombre (D-B: no cubre predicado ni `CHECK`) | 8 y 9 `test_create_all_and_migration_declare_the_same_anchor_ddl`, más `test_anchor_objects_exist_by_name_in_both_schemas` |
| **Colisión de migraciones con el 40**: doble `op.add_column` sobre `tasks.source` y fallo duro | Reanclaje del 40 como unidad de trabajo explícita y verificable dentro del 43 (D8) | Verificación del reanclaje en la unidad de artefactos; además `op.add_column` sobre columna existente falla de forma **ruidosa**, nunca en silencio |
| Un `source` inventado o renombrado rompe la correspondencia con el catálogo de conectores | `validate_task_source` con vocabulario cerrado y **un único llamador real** (`create_task`); el mensaje de error no hace eco del valor recibido | 10 y 11 |
| **Deriva del catálogo**: se agrega un adaptador nuevo y nadie actualiza `KNOWN_TASK_SOURCES`, así que su primera importación falla con un 422 incomprensible | Guardia de subconjunto sobre `_ADAPTERS` tras `import app.db_init` (D-C). Fue exactamente el fallo latente de `solercia_connect`, ausente del vocabulario original | 10 `test_every_registered_adapter_provider_is_a_known_task_source` |
| **Truncado de `external_key`** a 255 caracteres frente a un `internetMessageId` largo | Longitud alineada con `intake_items.external_id`, que ya almacena ese mismo valor en producción; ampliarla sería una migración aditiva trivial. La verificación con datos reales es tarea del **47** | Fuera del alcance del 43 (declarado, R4) |

---

## Rebanadas y carga de revisión

Estrategia `auto-chain` con **feature branch chain**. Tracker `feat/43-tareas-origen-externo`; A
apunta al tracker, B a la rama de A y C a la rama de B.

| # | Rama | Contenido | ≈ líneas | Presupuesto (×1,2) | Verificación propia | Reversa |
|---|---|---|---|---|---|---|
| **A** | `feat/43-a-migracion` → tracker | `0025_add_task_external_origin.py` · espejo en `Task.__table_args__` (2 columnas + `CheckConstraint` + 1 `Index`) · `test_migration_task_external_origin.py` | 294–344 | **400** | Escenarios 1–9 + gate `alembic check` | `alembic downgrade -1` + revert; **cero filas afectadas** (columnas nulables y 0 tareas tras el 42) |
| **B** | `feat/43-b-escritura` → rama de A | `sources.py` · `get_by_external_key` · **`create_task(..., external_origin=...)`** (D-G) · `TaskRead.source`/`external_key` · 2 campos en `workspace.model.ts` · `test_tasks_external_origin.py` | 327–427 | **500** | Escenarios 10–13, 16–26 | Revert de los commits de B; las columnas y las dos restricciones **permanecen** |
| **C** | `feat/43-c-filtros` → rama de B | Filtros `?source=`/`?external_key=` en los tres saltos `router → service → repository` · sus dos pruebas | ~150 | **200** | Escenarios 14, 15 | Revert de los commits de C; **44 y 47 siguen desbloqueados**, porque lo que consumen es la costura y el camino de escritura, no los filtros |

Total estimado **≈770–920 líneas** (`additions + deletions`), de las cuales ≈480–570 son pruebas.
Muy por encima del umbral de 400 ⇒ cadena obligatoria. El pronóstico formal
(`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`) lo emite
`sdd-tasks`.

**Por qué hay una rebanada C y antes no la había.** Implementar D-G (antes diferido) suma ~25 líneas
de servicio y ~50 de prueba, y las dos pruebas de exposición (12 y 13) migran de A a B porque anclan
con `create_task(..., external_origin=...)`, que nace en B. Sin recortar, B quedaría en 477–577
líneas y su presupuesto en **700** — por encima del techo de ~600 que esta cadena se fijó. Se aplica
entonces la contingencia que el diseño ya tenía prevista: los dos filtros salen a una rebanada C
propia. El criterio de corte no cambió: **la costura, el vocabulario y el camino de escritura son lo
que desbloquea a 44 y 47; los filtros no.** C puede incluso posponerse sin bloquear nada.

### Unidad de artefactos: «Reanclaje del 40» (D8)

Edición de artefactos OpenSpec: **no cuenta contra el presupuesto de revisión**, pero es una unidad
de trabajo explícita y verificable, porque es la mitigación de R1. Debe completarse **antes** de que
el 40 llegue a `apply` y **antes** de cualquier `sdd-archive` de 40 o 43.

| Ubicación | Edición exacta |
|---|---|
| `40/tasks.md:47` (fila U1) | Reducir el objetivo y el mensaje de commit a `projects`+`sprints`; restar ≈40–60 líneas de la estimación de la unidad |
| `40/tasks.md:59` (0.4) | El head real ya no es `0021_unique_org_member`: en disco es `0024`, y tras el 43 será `0025` |
| `40/tasks.md:60` (0.5) | El próximo consecutivo libre no es `0022`: es **el siguiente consecutivo libre en el momento del `apply` del 40**, verificado entonces con `alembic heads` y con los cambios pendientes (hoy sería `0029` si el 44 y el 45a aterrizan antes). **No se reserva ningún número por adelantado**: un `down_revision` hacia una revisión que nadie ha escrito rompe `alembic upgrade head` en despliegue |
| `40/tasks.md:64` (1.1) | Renombrar a `00NN_add_external_anchor_projects_sprints.py`, con `00NN` resuelto por la compuerta en el `apply` del 40; **eliminar** `tasks` de la lista de tablas y el índice `uq_tasks_project_source_external_key` de la de índices (el 43 lo entrega con otro nombre y otro orden de columnas: `uq_tasks_source_external_key_project`); alinear `source` de `VARCHAR(20)` a `String(50)` (D3) |
| `40/tasks.md:65` (1.2) | Quitar `backend/app/modules/tasks/models.py` de la lista de modelos a editar |
| `40/tasks.md:66` (1.3) | `test_external_anchor_migration.py` pierde las aserciones sobre `tasks` (las cubre `test_migration_task_external_origin.py` del 43) |
| `40/tasks.md:68-69` (1.5, 1.6) | `TaskRead` ya expone ambos campos: pasan de RED/GREEN a **verificación** de que siguen expuestos |
| `40/tasks.md:72` (Commit 1) | Mensaje → `feat(anchors): agrega source/external_key con únicos parciales a projects/sprints` |
| `40/design.md:26-31` (D2) | Marcar la fila de `tasks` como **entregada por el 43**; conservar la decisión para `projects`/`sprints` |
| `40/design.md:75` | `app/modules/{projects,sprints}/models.py` — sin `tasks` |
| `40/design.md:76` | `alembic/versions/00NN_add_external_anchor_projects_sprints.py`, con `00NN` resuelto por la compuerta en el `apply` del 40 |
| `40/design.md:116-121` | `down_revision` real (la cabeza en vivo en el momento del `apply` del 40, verificada con `alembic heads`; nunca un literal fijado hoy) y alcance de **dos** tablas, no tres |
| `40/specs/tasks/spec.md:3-6` (preámbulo) | **Reescribir**: hoy dice que el delta «AGREGA el ancla de procedencia externa». Tras el traslado el delta ya no agrega el ancla — la **consume**. Debe decir que el ancla la entrega el cambio 43 y que este delta agrega sólo la reconciliación idempotente del importador. Sin esta edición el preámbulo contradice el cuerpo del propio archivo |
| `40/specs/tasks/spec.md:10-22` | **Eliminar** el requisito «Ancla de procedencia externa (source + external_key)» y sus 2 escenarios: reescrito y trasladado al 43 (D7) |
| `40/specs/tasks/spec.md:33-40` | **Eliminar** «Clave local y clave externa conviven como referencias distintas» y su escenario: trasladado al 43 |
| `40/specs/tasks/spec.md:24-31` | **Conservar** «Reconciliación idempotente por procedencia externa»: es comportamiento del importador, no del modelo de datos |
| `40/specs/tasks/spec.md:45` (referencias) | Ajustar «precedente de ancla de procedencia **+ idempotencia**» → sólo idempotencia; y agregar `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` como origen del ancla que este delta presupone |
| `40/state.yaml:76` (`spec_notes`) | **Reescribir** la nota «Delta MODIFIED tasks: ancla de procedencia externa (source + external_key)…»: el ancla ya no la entrega el 40. Debe decir que el 40 conserva sólo la reconciliación idempotente y que `source`/`external_key` llegan del 43 |
| `40/state.yaml` | Registrar el traslado en `spec_notes` y actualizar `last_updated` (`:72`, hoy `2026-07-20`) |

**Verificación de la unidad**: tras las ediciones,
`rg -n "Ancla de procedencia" openspec/changes/40-jira-import-usuario/` no debe devolver ningún
**requisito** (sólo referencias al 43 como proveedor), y
`rg -n "0022|VARCHAR\(20\)|uq_tasks_project_source_external_key" openspec/changes/40-jira-import-usuario/`
debe quedar sin coincidencias.

---

## Migración / despliegue

Un solo paso: `alembic upgrade head`. Sin retrollenado, sin transformación de datos, sin bandera de
funcionalidad, sin ventana de mantenimiento.

- **Precondición dura**: el cambio **42** debe estar archivado antes del `apply` del 43
  (`42/state.yaml:55` excluye explícitamente `tasks.source`/`external_key` y declara que bloquea a
  este cambio). Tras el 42 la base queda con 1 organización, 1 usuario, `SDMUJER > SEGURIDAD +
  PANDORA` y **0 tareas**: no hay una sola fila que retrollenar ni una sola colisión histórica que
  resolver. Es la razón por la que este es el momento exacto para agregar la restricción.
- **Reversa completa**: `alembic downgrade -1`. Ambas columnas son nulables, así que ninguna fila
  existente cambia al subir ni al bajar.
- **Cabeza de Alembic**: `0024` en disco hoy; el 43 toma `0025`. **Ningún número queda reservado al
  40**: tras el reanclaje toma el siguiente consecutivo libre en el momento de su propio `apply`
  (hoy sería `0029` si el 44 —`0026` y `0027`— y el 45a —`0028`— aterrizan antes). El gate `0.4` del
  40 (`40/tasks.md:59`) debe verificar el head en vivo y los cambios pendientes antes de fijarlo.
- **Frontend**: dos propiedades opcionales de una interfaz. Sin build especial, sin migración de
  datos en cliente, sin cambio visible para el usuario.
- **Desbloqueo**: al terminar el 43 — en rigor, al terminar la rebanada **B**; la C es opcional — el
  44 y el 47 tienen columnas, restricciones, vocabulario, costura de lectura y **camino de
  escritura**. Ninguno de los dos necesita tocar `tasks/models.py`, escribir su propia migración ni
  inventar cómo persistir el ancla.

---

## Riesgos abiertos

| Riesgo | Mitigación en este diseño |
|---|---|
| El gate `alembic check` da una falsa sensación de cobertura sobre el espejado (**verificado**: no compara `postgresql_where` ni `CheckConstraint`) | D-B: la equivalencia se prueba comparando el DDL real de las dos rutas de construcción del esquema. El gate se conserva y su alcance real queda escrito, para que nadie vuelva a asumir de más |
| Primer `CheckConstraint` del repositorio: cero precedentes de `op.create_check_constraint` y de su `drop_constraint(..., type_="check")` | La prueba de migración ejercita el `downgrade` completo (escenario 6), así que un `type_` mal puesto se cae en rojo antes del merge, no en producción |
| La unicidad org-wide es de **aplicación**, no de motor: un importador que escriba el ancla sin pasar por `create_task` puede duplicar entre proyectos | Documentado como limitación explícita en la spec y en el docstring de la costura; D-G reduce la superficie a **un solo** camino de escritura, que ya trae la guarda 409 incorporada; D-E hace la lectura determinista y barata (prefijo del único parcial) |
| ~~44 y 47 podrían inventar cada uno su propio camino de escritura del ancla~~ **(R9 cerrado)** | Ya no es un riesgo por documentar sino código entregado: `create_task(..., external_origin=...)` existe, valida el vocabulario, comprueba la unicidad org-wide y tiene dos escenarios de spec propios (18, 19) |
| **R10 (nuevo)** · Una futura «restauración de tarea» (`is_active=false → true`) puede chocar contra el ancla que D-I liberó, produciendo `UniqueViolation` en la reactivación | Hoy **no existe** ninguna ruta de restauración de tareas (verificado: `tasks/service.py:645` sólo pone `is_active = False`), así que el riesgo es futuro, no presente. El cambio que la introduzca debe llamar a `get_by_external_key` antes de reactivar y rechazar si el ancla ya está ocupada. Queda escrito en D-I para que no se descubra por un 500 |
| El 44 necesita `is_context` y `merge_into` como columnas reales y podría asumirlas entregadas | Declaradas fuera de alcance por escrito, con un escenario de spec (24) que **prueba** que siguen sin persistirse |
| Colisión de migraciones con el 40 | Unidad de artefactos «Reanclaje del 40» con lista exacta de ediciones y comandos de verificación |
| `external_key` de 255 podría truncar un `internetMessageId` de Outlook | Alineado con `intake_items.external_id`, que ya almacena ese valor. Ampliar sería una migración aditiva trivial. Verificación con datos reales: tarea del **47** |

## Preguntas abiertas

- [ ] **Ninguna que bloquee la implementación ni que requiera al usuario.** Las nueve preguntas de la
      exploración quedaron resueltas como D1–D9 y no se reabren. Las **nueve** decisiones de este
      diseño (D-A … D-I) son de nivel técnico y quedan cerradas aquí.
- [ ] Dos puntos anotados que **no bloquean** el 43 y se resuelven en su cambio propietario: el
      etiquetado visible de la procedencia (**44**) y la longitud efectiva de `external_key` frente a
      datos reales (**47**).

## Referencias

- `agents/rules/solercia-persistence.md` — repositorios sin commit, tenant obligatorio en toda
  lectura, métodos semánticos por agregado, sin controladores genéricos sobre recursos de tenant.
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` §5.4 (identificadores de proveedor
  opacos calificados por fuente), §5.5 (idempotencia obligatoria en ingestión), §6.5 (tenant en toda
  lectura/escritura), §7 (columnas semánticas en `lower_snake_case`).
- `openspec/config.yaml:20-30` — `rules.design` (decisiones con justificación, `router → service →
  repository`) y `rules.apply.tdd: true`.
- `openspec/changes/43-tareas-origen-externo/{exploration,proposal}.md` · `specs/tasks/spec.md`.
- `openspec/specs/tasks/spec.md` (línea base) · `openspec/specs/intake-items/spec.md` (precedente de
  ancla de procedencia).
- `openspec/changes/40-jira-import-usuario/{design.md,tasks.md,specs/tasks/spec.md,state.yaml}` —
  reanclaje.
- `openspec/changes/42-purga-datos-demo/state.yaml:55` — exclusión explícita de
  `tasks.source`/`external_key` y dependencia declarada.
