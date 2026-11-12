# Proposal: 43 · Ancla de procedencia externa en `tasks` (`source` + `external_key`)

## Intent

**Problema de negocio.** Hoy una tarea no puede decir de dónde vino. Cuando el sistema crea una tarea a partir de un correo, la trazabilidad queda en **texto libre** dentro de la descripción (`intake/service.py:177-185`: `f"Origen: {item.source_provider} — {item.origin_actor}"`) más una FK inversa (`item.created_task_id`). Eso no es una clave: no se puede consultar, no se puede filtrar y, sobre todo, **no impide duplicar**. Volver a correr un importador crea una segunda tarea idéntica y nadie lo detecta hasta que el tablero está sucio.

**Urgencia.** Dos cambios inmediatos consumen esta columna y ninguno puede avanzar sin ella:

| Cambio | Qué escribe | Sin el ancla |
|---|---|---|
| 44 · importador de `CHECKLIST_TAREAS.xlsx` | `source='checklist_xlsx'`, `external_key='T-01'…'T-131'` | 131 tareas duplicadas en cada reintento del import |
| 47 · ingesta de correo | `source = connector.provider`, `external_key = intake_items.external_id` | cada barrido de buzón vuelve a crear las mismas tareas |

La decisión de plataforma §5.5 exige **idempotencia obligatoria en la ingestión** y §5.4 exige **identificadores de proveedor opacos calificados por su fuente**. Ambas son incumplibles hoy en `tasks`. Además, el cambio 42 dejó la base en cero tareas: **este es el momento exacto** para agregar la restricción, porque no hay una sola fila que retrollenar ni una sola colisión histórica que resolver.

**Éxito.** Una tarea nacida de un sistema externo lleva su procedencia como **dato consultable**, el motor impide dos anclas iguales dentro del mismo proyecto, el servicio impide dos anclas iguales dentro de la organización, y una tarea creada a mano sigue viéndose exactamente igual que hoy: ambas columnas nulas, sin restricción, sin valor centinela y sin un solo cambio en su flujo. Los importadores 44 y 47 encuentran una costura de lectura ya construida (`get_by_external_key`) y un único camino de escritura (`create_task(..., external_origin=...)`) en lugar de inventar cada uno los suyos.

## Scope

### In Scope

- Migración aditiva `0025_add_task_external_origin` (`down_revision="0024"`): `tasks.source VARCHAR(50) NULL`, `tasks.external_key VARCHAR(255) NULL` y **dos** objetos de esquema — `CHECK ck_tasks_external_key_requires_source` y el único parcial `uq_tasks_source_external_key_project (source, external_key, project_id) WHERE source IS NOT NULL AND external_key IS NOT NULL AND is_active`. **Corrección del diseño (D-A)**: con `(source, external_key)` como prefijo, ese índice sirve también a la búsqueda org-wide, así que el índice de apoyo previsto originalmente **se elimina**. **Corrección del diseño (D-I)**: `AND is_active` hace que una tarea con borrado suave libere su ancla.
- Espejado literal de esos dos objetos en `Task.__table_args__` (obligatorio: el harness construye el esquema con `Base.metadata.create_all`). **Corrección del diseño (D-B)**: `alembic check` 1.14.0 no compara `postgresql_where` ni `CheckConstraint`, así que el espejado se protege con una prueba de equivalencia de DDL (`pg_get_indexdef`/`pg_get_constraintdef` entre `create_all` y `upgrade head`), no con `alembic check`.
- Exposición de solo lectura: `TaskRead.source` y `TaskRead.external_key` como `str | None = None`.
- Filtros de igualdad exacta `?source=` y `?external_key=`, componibles con los filtros vigentes.
- Costura de repositorio `TaskRepository.get_by_external_key(organization_id, source, external_key)` — el contrato de **lectura** que consumen 44 y 47.
- Vocabulario cerrado en `backend/app/modules/tasks/sources.py` (`KNOWN_TASK_SOURCES` + `validate_task_source`) y **camino de escritura** `TaskService.create_task(..., *, external_origin=(source, external_key))`. **Corrección del diseño (D-G)**: originalmente diferido a 44/47 como nota de contrato, se implementa dentro del 43 porque sin él el validador de vocabulario nace sin llamador y el requisito de spec «Vocabulario de `source`» no queda satisfecho por nada.
- Tipo del frontend: `source?: string | null` y `external_key?: string | null` en la interfaz `Task`.
- Reanclaje documentado del cambio 40 (migración `00NN`: el siguiente consecutivo libre en el momento del `apply` del 40, sin número reservado por adelantado; alcance reducido a `projects`+`sprints`, repartición de requisitos de spec).

### Out of Scope

- **`is_context` y `merge_into` como columnas reales** — hoy `is_context` es un campo transitorio calculado en `_to_read`. Los declara el **cambio 44**; el 43 no los entrega y el 44 no debe asumirlos entregados.
- **Endpoint dedicado** `GET /tasks/by-external-key` — 44 y 47 son importadores de backend que llaman al repositorio, no a HTTP.
- **Insignia de procedencia en la UI** — diferida al 44 (ver decisión D6).
- **`source`/`external_key` en `TaskCreate` y `TaskUpdate`** — inmutabilidad por API, por seguridad y por integridad (ver decisión D-INM).
- **`task_history`** — campos inmutables producen siempre un diff vacío.
- **Reconciliación idempotente** (leer-o-crear por ancla) — es comportamiento del importador; se queda en el 40 y lo ejercen 44 y 47.
- **Retrollenado de datos** — la base tiene 0 tareas tras el cambio 42.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `tasks` (`openspec/specs/tasks/spec.md`): se agregan los requisitos **«Ancla de procedencia externa»** y **«Clave local y externa conviven como referencias distintas»**, ambos trasladados desde el delta del cambio 40, más **«Escritura del ancla reservada al caso de uso de creación»**, que es nuevo y no proviene del 40: es el registro durable de la forma `external_origin` para 44 y 47. El requisito **«Reconciliación idempotente por procedencia externa»** NO se toca aquí: permanece en el 40.

## Approach

### Piezas

| # | Pieza | Decisión |
|---|---|---|
| 1 | **Migración `0025`** | Patrón aditivo canónico de `0022_add_project_kind.py`: `op.add_column` ×2 sin `server_default` (ambas nulables), luego los dos objetos de esquema. Sin `batch_alter_table` (PostgreSQL exclusivo, cero apariciones en las 24 migraciones existentes) |
| 2 | **`CHECK ck_tasks_external_key_requires_source`** | `external_key IS NULL OR source IS NOT NULL`. Cierra el agujero silencioso: sin él, `(NULL, 'T-05', P)` duplicado **no colisiona**, porque el `NULL` en `source` vuelve distintas las filas para el índice único |
| 3 | **Único parcial** | `uq_tasks_source_external_key_project (source, external_key, project_id) WHERE source IS NOT NULL AND external_key IS NOT NULL AND is_active`. Misma unicidad por proyecto que el orden inverso, pero su prefijo `(source, external_key)` sirve además a la búsqueda org-wide. Precedentes de parcial: `0017:58-63`, `0018:89-101`, `0023:416-421` |
| 4 | ~~**Índice de apoyo**~~ **(eliminado, D-A)** | Existía sólo porque el único llevaba `project_id` como columna líder. Con el orden `(source, external_key, project_id)` deja de hacer falta: un índice menos que escribir en cada `INSERT`, que mantener, que espejar y que probar |
| 5 | **`__table_args__`** | Los dos objetos declarados con el **mismo `postgresql_where`** que la migración, siguiendo la nota explícita de `users/models.py:30-38` y `org_role_templates/models.py:36-51` |
| 6 | **`TaskRead`** | Dos campos nuevos y nada más: `TaskService._to_read` y `DashboardService._to_read` usan `TaskRead.model_validate(task)` con `from_attributes`, así que los campos aparecen en **todos** los consumidores con cero cambios de servicio |
| 7 | **Filtros** | Cadena establecida de tres saltos: `router.py` (`Query(default=None, description=...)`) → `service.py` (reenvío de kwargs) → `repository.py` (`stmt.where(...)`). **No** se agregan a `SORTABLE_FIELDS` |
| 8 | **`get_by_external_key`** | `JOIN Project` + filtro por `organization_id`, como exige `agents/rules/solercia-persistence.md` (tenant obligatorio en toda lectura). `tasks` no tiene `organization_id`: el tenant es transitivo por `project_id`, y denormalizarlo está prohibido |
| 9 | **Frontend** | Dos campos opcionales en `workspace.model.ts`. `TaskDetail extends Task` los hereda gratis |

### Dónde vive cada garantía

| Garantía | La da | Por qué |
|---|---|---|
| Unicidad del ancla **dentro de un proyecto** | El motor (índice único parcial) | Expresable en PostgreSQL con las columnas que `tasks` ya tiene |
| Unicidad del ancla **dentro de la organización** | El servicio (`get_by_external_key` antes de insertar) | `tasks` no tiene `organization_id`; PostgreSQL no puede expresar `UNIQUE` a través de un `JOIN`; denormalizar el tenant está prohibido por el ADR y por el propio diseño del 40 |
| Que una tarea no cambie de proyecto y rompa el invariante | El contrato de API vigente | `TaskUpdate` no acepta `project_id` y el servicio nunca lo reasigna: **hoy una tarea no puede moverse entre proyectos por la API** (verificado sobre las 29 apariciones de `project_id` en `service.py`) |

Esta repartición es una **limitación conocida y documentada**, no un descuido: la spec debe decir explícitamente qué garantiza el motor y qué garantiza el servicio, y 44 y 47 quedan obligados a pasar por `get_by_external_key`.

### Vocabulario de `source`

`String(50)` libre, validado en el servicio, **nunca `SAEnum`** — un enum de PostgreSQL obligaría a una migración por cada proveedor nuevo. Precedentes: `connectors.provider` es `String(50)` con el comentario normativo «deliberately NOT a PG enum», `intake_items.source_provider` es `String(50)`, `tasks.status` es `String(60)` validado por la strategy.

**Regla:** cuando el origen es un conector, `tasks.source` DEBE ser exactamente `connector.provider` (el mismo valor que `intake_items.source_provider`). Los adaptadores realmente registrados son **siete**, no seis: `microsoft365` (47 — cubre correo, calendario y Planner), `google`, `jira` (40), `glpi`, `mcp`, `fake` y **`solercia_connect`** (`adapters/solercia_connect/adapter.py:53`, registrado en `adapters/solercia_connect/__init__.py:14` e importado por `app/db_init.py:36`). Con `checklist_xlsx` (44), el vocabulario tiene **ocho** valores. Como `intake/service.py:295` escribe `source_provider=connector.provider` sin filtrar por proveedor, omitir `solercia_connect` habría convertido su primera importación en un 422 incomprensible; una prueba de guardia afirma que todo `provider` registrado pertenece al vocabulario. **`planner` no se agrega**: crearía vocabulario paralelo, y la distinción por capacidad ya vive en `intake_items.item_type`.

### Inmutabilidad por API

`source` y `external_key` **no entran** en `TaskCreate` ni en `TaskUpdate`. Tres razones independientes:

1. **Seguridad**: un cliente podría pre-crear `('checklist_xlsx', 'T-05')` y secuestrar la fila que el importador espera escribir.
2. **Integridad**: un `PATCH` que viole el único produciría `IntegrityError` → 500, porque `update_task` no lo captura.
3. **Regla de persistencia**: prohíbe controladores genéricos sobre recursos de tenant.

Los importadores escriben el ancla por un **único camino interno**: `TaskService.create_task(..., *, external_origin=(source, external_key))`, de palabra clave y ausente del esquema HTTP, que valida el vocabulario, comprueba la unicidad org-wide y persiste el ancla en el mismo `INSERT` que crea la fila. Corregir un ancla mal puesta es una **operación de mantenimiento** (`backend/app/maintenance/`, entregado por el 42), no un `PATCH`.

## Decisiones tomadas

| # | Decisión | Justificación |
|---|---|---|
| D1 | Unicidad org-wide **en el servicio**, no en el motor | Única opción que no denormaliza el tenant (prohibido), no esconde lógica en un trigger y no introduce una tabla puente desproporcionada. Entrega el seam que 44 y 47 necesitan de todos modos |
| D2 | `CHECK` de **«clave exige origen»**, no de par estricto | `(source IS NULL) = (external_key IS NULL)` prohibiría registrar procedencia sin clave estable; la forma elegida cierra el agujero de unicidad sin cerrar ese caso legítimo |
| D3 | `String(50)` / `String(255)` | Alineados con `connectors.provider` y con `intake_items.external_id` (el 47 copia ese valor literal). El `VARCHAR(20)` que fijaba el 40 se realinea |
| D4 | Tarea manual = **ambas columnas NULL**, sin centinela `manual` | Evita retrollenado, respeta la semántica del índice parcial y no mete un valor falso en el espacio de claves |
| D5 | Endpoint dedicado **diferido**; solo filtros | Los consumidores son importadores de backend. Si alguna vez se agrega, será con *query params* (nunca *path*): un `internetMessageId` de Outlook tiene forma `<...@...>` y admite `/` |
| D6 | Insignia de UI **diferida al 44**; el 43 aporta solo el tipo | Tras el 43 no existe **ni una sola** tarea anclada (el 42 dejó 0 tareas): sería interfaz muerta imposible de verificar. Además el 44 sabe cómo etiquetarla y tocar `task-modal` obligaría a una pasada de UX sobre un componente que no gana información |
| D7 | El 43 **asume** «Ancla de procedencia externa» y «Clave local y externa conviven»; el 40 conserva «Reconciliación idempotente» | Sin esta repartición, `sdd-archive` fusionaría el mismo requisito dos veces hacia `openspec/specs/tasks/spec.md` |
| D8 | El reanclaje del 40 se hace **dentro** del 43, como unidad de trabajo de artefactos | Es la mitigación verificable de R1; al ser edición de OpenSpec no cuenta contra el presupuesto de revisión, pero debe ser una tarea explícita y no un supuesto |
| D9 | **Sin** `task_history` para estos campos | Campos inmutables por API ⇒ el diff de `_HISTORY_TRACKED_FIELDS` sería siempre vacío |

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `backend/alembic/versions/0025_add_task_external_origin.py` | New | 2 columnas + CHECK + único parcial (2 objetos de esquema) |
| `backend/app/modules/tasks/models.py` | Modified | 2 columnas + espejo de los 2 objetos en `__table_args__` (que hoy solo tiene los 2 índices GIN trigram) |
| `backend/app/modules/tasks/sources.py` | New | `KNOWN_TASK_SOURCES` (8 valores) + `validate_task_source` |
| `backend/app/modules/tasks/schemas.py` | Modified | `TaskRead.source`, `TaskRead.external_key`. **`TaskCreate`/`TaskUpdate` no se tocan** |
| `backend/app/modules/tasks/repository.py` | Modified | 2 filtros + `get_by_external_key(organization_id, source, external_key)` |
| `backend/app/modules/tasks/service.py` | Modified | Reenvío de los 2 filtros en `list_tasks` + `external_origin` en `create_task` (validación de vocabulario, guarda org-wide 409 y persistencia del ancla) |
| `backend/app/modules/tasks/router.py` | Modified | 2 `Query` con `description`. La firma HTTP de creación **no cambia** |
| `frontend/src/entities/workspace/workspace.model.ts` | Modified | 2 campos opcionales en la interfaz `Task` |
| `backend/tests/test_migration_task_external_origin.py` | New | Patrón `test_migration_project_kind.py:73-244` |
| `backend/tests/test_tasks_external_origin.py` | New | Patrón `test_task_filters.py:1-64` |
| `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md` | New | Delta de la capacidad `tasks` |
| `openspec/changes/40-jira-import-usuario/{design,tasks}.md` y `specs/tasks/spec.md` | Modified | Reanclaje (ver D8) |

**No se toca**: `boards`, `sprints`, `methodology`, `labels`, `checklists`, `task_links`, `activity`, `dashboard`, `intake`.

## Rollback Plan

| Escenario | Reversa |
|---|---|
| La rebanada A falla o la restricción resulta demasiado estricta | `alembic downgrade -1` + revert de los commits. **Cero filas afectadas**: las columnas son nulables y la base tiene 0 tareas |
| La rebanada B falla (vocabulario, seam, camino de escritura o tipo del frontend) | Revert de los commits de B. Las columnas y los dos objetos de esquema **permanecen**; lo que se pierde es el desbloqueo de 44 y 47, que dependen de B |
| La rebanada C falla (filtros) | Revert de los commits de C. **44 y 47 siguen desbloqueados**: consumen la costura y el camino de escritura, no los filtros |
| La prueba de equivalencia de DDL reporta diferencia tras el merge | Señala exactamente qué objeto o qué predicado difiere entre `Base.metadata.create_all` y `alembic upgrade head`; se corrige el modelo, nunca la migración. **`alembic check` no sirve para esto** (D-B: no compara `postgresql_where` ni `CheckConstraint`) y sólo se conserva para detectar la ausencia del índice por nombre |
| El reanclaje del 40 se hace mal y el 40 vuelve a declarar `tasks` | Se detecta antes del apply del 40: `op.add_column` sobre una columna existente falla de forma dura y ruidosa, no en silencio |

## Risks

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | Colisión de migraciones con el 40: doble `add_column` de `tasks.source`/`external_key` y fallo duro | Alta | Reanclaje del 40 como unidad de trabajo verificable dentro del 43 (D8): migración renombrada a `00NN` —el siguiente consecutivo libre en el momento del `apply` del 40, verificado entonces con `alembic heads` y con los cambios pendientes; sin número reservado—, `tasks` eliminado de su alcance, `String(50)` alineado |
| R2 | El modelo y la migración divergen sin que nadie lo note: `alembic check` 1.14.0 no compara `postgresql_where` ni `CheckConstraint` (falso negativo silencioso; corregido en el diseño, D-B) | Media | Declarar los dos objetos en `__table_args__` con el **mismo** `postgresql_where`, siguiendo `users/models.py:30-38`, y protegerlo con la prueba de equivalencia de DDL (`pg_get_indexdef`/`pg_get_constraintdef`) entre `create_all` y `upgrade head` |
| R3 | El harness de pruebas construye el esquema con `create_all`, no con Alembic: una restricción solo en la migración no existiría en las pruebas | Media | Misma mitigación que R2. Es la razón por la que el espejado es obligatorio, no opcional |
| R4 | `external_key` de 255 caracteres podría truncar un `internetMessageId` largo | Baja | Alineado con `intake_items.external_id`, que ya almacena ese valor en producción. La verificación con datos reales es tarea del 47 |
| R5 | La unicidad org-wide es de aplicación, no de motor: un importador que escriba el ancla sin pasar por el caso de uso puede duplicar entre proyectos | Media/Baja tras D-G | Reducido a un **único** camino de escritura (`create_task(..., external_origin=...)`) que ya trae la guarda org-wide y devuelve `409 task_external_anchor_conflict`. La limitación queda igualmente escrita en la spec. El prefijo `(source, external_key)` del único parcial hace barata esa consulta |
| R6 | Duplicación de requisitos al archivar 40 y 43 sobre `openspec/specs/tasks/spec.md` | Media | Repartición explícita (D7) ejecutada **antes** de cualquier `sdd-archive` |
| R7 | El 44 necesita `is_context` y `merge_into` como datos reales y podría asumirlos entregados por el 43 | Media | Declarados fuera de alcance por escrito; `is_context` sigue siendo transitorio en `_to_read` hasta que el 44 lo convierta en columna |

## Dependencies

- **Cambio 42 (`purga-datos-demo`) archivado antes del `apply` del 43.** Su `state.yaml:55` excluye explícitamente `tasks.source`/`external_key` y declara que bloquea al 43. Además deja la base en 1 organización, 1 usuario, `SDMUJER > SEGURIDAD + PANDORA` y **0 tareas**, que es la precondición que hace trivial esta migración.
- **Cambio 40 reanclado** (D8) antes de que el 40 llegue a `apply`.
- Cabeza de Alembic en disco: `0024` (`0024_add_work_calendar.py`). El 43 toma `0025`. **Al 40 no se le reserva ningún número**: toma el siguiente consecutivo libre en el momento de su propio `apply` (hoy sería `0029` si el 44 —`0026` y `0027`— y el 45a —`0028`— aterrizan antes).
- El 43 **bloquea** al 44 (importador de checklist) y al 47 (ingesta de correo).

## Success Criteria

- [ ] TDD estricto: prueba en rojo antes del código en ambas rebanadas.
- [ ] `test_migration_task_external_origin.py` en verde: base desechable → `upgrade 0024` → siembra por SQL crudo con asyncpg → `upgrade 0025` → aserciones sobre `information_schema` (ambas columnas presentes, `is_nullable='YES'`, fila sembrada intacta con ambas nulas) → `downgrade 0024` → columnas ausentes y **fila viva**.
- [ ] Sobre esa misma base: dos `('checklist_xlsx', 'T-05', P)` producen `UniqueViolation`; N filas `(NULL, NULL, P)` conviven sin conflicto; la misma clave en dos proyectos distintos no colisiona; `(NULL, 'T-05', P)` viola `ck_tasks_external_key_requires_source`; y una tarea anclada con `is_active=false` **libera** su ancla para una segunda fila activa con el mismo par (D-I).
- [ ] `test_tasks_external_origin.py` en verde: un `POST /tasks` expone ambos campos en `null`; un `TaskCreate` que incluya `external_key` **no lo persiste**; un `PATCH` tampoco; `create_task(..., external_origin=...)` sí persiste y expone el ancla, y rechaza con `409 task_external_anchor_conflict` un ancla ya activa en otro proyecto de la organización; todo `provider` registrado pertenece a `KNOWN_TASK_SOURCES`; `?source=` y `?external_key=` componen correctamente con `?status=`; `get_by_external_key` **no cruza organizaciones** y excluye tareas y proyectos con borrado suave.
- [ ] **Gate real del espejado**: `test_create_all_and_migration_declare_the_same_anchor_ddl` en verde (compara `pg_get_indexdef` y `pg_get_constraintdef` entre `create_all` y `upgrade head`). `test_migrations_baseline.py::test_alembic_check_reports_no_diff_after_upgrade` se conserva **sin cambios** como guardia de existencia por nombre, no como gate del predicado ni del `CHECK` (D-B).
- [ ] Sin regresión frente a la línea base **1411 pasadas / 3 fallidas preexistentes** (`tests/test_adapter_microsoft365.py`, dependientes del reloj), con `TEST_DATABASE_URL` configurada. Sin esa variable, `skip_no_db` salta 898 pruebas y la corrida no sirve de referencia.
- [ ] `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_task_external_origin.py tests/test_tasks_external_origin.py tests/test_migrations_baseline.py`
- [ ] `openspec/changes/40-jira-import-usuario/` reanclado: migración `00NN` (consecutivo libre resuelto en el `apply` del 40, sin reserva), `tasks` fuera de su alcance, `String(50)` alineado, y los dos requisitos de spec movidos al 43 sin dejar duplicado.

## Carga de revisión

Estimado **≈770–920 líneas** (`additions + deletions`), de las cuales ≈480–570 son pruebas. Muy por encima del umbral por defecto de 400.

`400-line budget risk: **High**`

Estrategia `auto-chain` con **feature branch chain** sobre el tracker `feat/43-tareas-origen-externo`: A apunta al tracker, B a la rama de A y C a la rama de B.

| Rebanada | Contenido | ≈ líneas | Presupuesto (×1,2) | Reversa |
|---|---|---|---|---|
| **A** | Migración `0025` + espejo en `__table_args__` + `test_migration_task_external_origin.py` | 294–344 | **400** | `alembic downgrade -1` + revert; cero filas afectadas |
| **B** | `sources.py` + `get_by_external_key` + `create_task(..., external_origin=...)` + `TaskRead` + tipo del frontend + `test_tasks_external_origin.py` | 327–427 | **500** | revert; las columnas y los dos objetos permanecen |
| **C** | Filtros `?source=`/`?external_key=` en los tres saltos + sus dos pruebas | ~150 | **200** | revert; 44 y 47 siguen desbloqueados |

La rebanada **C** aparece en esta pasada correctiva: implementar D-G dentro del 43 y mover a B las dos pruebas de exposición (que ahora anclan con `create_task(..., external_origin=...)`) dejaba a B en ~477–577 líneas y su presupuesto en 700, por encima del techo de ~600 de la cadena. Se aplicó la contingencia ya prevista: los filtros salen a una rebanada propia, que puede incluso posponerse sin bloquear a 44 ni a 47.

El **reanclaje del 40** es edición de artefactos OpenSpec: no cuenta contra el presupuesto de revisión, pero es una unidad de trabajo explícita y verificable (D8).

El pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`) lo emite `sdd-tasks`.

## Preguntas abiertas

**Ninguna.** Las nueve preguntas abiertas de la exploración quedaron resueltas y registradas como D1–D9. Ninguna decisión de producto pendiente bloquea `sdd-spec` ni `sdd-design`.

Se dejan anotados dos puntos que **no bloquean** este cambio y que se resolverán en su cambio propietario:

- El etiquetado visible de la procedencia (texto de la insignia, ubicación junto al `task_key`, `aria-label` del sistema de origen) se define en el **cambio 44**, cuando existan tareas ancladas reales que permitan verificarlo.
- La longitud efectiva de `external_key` frente a un `internetMessageId` de Outlook se verifica con datos reales en el **cambio 47**; si 255 resultara corto, ampliarlo es una migración aditiva trivial.

## Referencias

- `agents/rules/solercia-persistence.md` — repositorios sin commit, tenant obligatorio en toda lectura/escritura, sin controladores genéricos, SQL en adaptadores.
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` — §5.4 (identificadores de proveedor opacos calificados por fuente), §5.5 (idempotencia obligatoria en ingestión), §6.5 (tenant en toda lectura/escritura), §7 (columnas semánticas en `lower_snake_case`).
- `openspec/changes/43-tareas-origen-externo/exploration.md` — análisis de estado actual y opciones.
- `openspec/specs/tasks/spec.md` (línea base) · `openspec/specs/intake-items/spec.md` (precedente de ancla de procedencia).
- `openspec/changes/40-jira-import-usuario/{design,tasks}.md` y `specs/tasks/spec.md` — reanclaje.
- `openspec/changes/42-purga-datos-demo/state.yaml:55` — exclusión explícita de `tasks.source`/`external_key`.
