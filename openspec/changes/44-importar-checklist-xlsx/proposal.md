# Proposal: 44 · Importador idempotente de `CHECKLIST_TAREAS.xlsx`

## Intent

**Problema de negocio.** La lista real de trabajo del responsable de seguridad de la información vive fuera del sistema: **135 filas** (`T-01`…`T-135`) en una hoja de cálculo que se edita a diario. Solercia Command no ve ni una sola de ellas. La vista ejecutiva no puede responder «¿en qué anda cada persona?», el motor de alertas no dispara sobre vencimientos que ya ocurrieron (cinco actividades del Plan de Seguridad están vencidas, dos **desde marzo de 2026**), y el roll-up de avance reporta sobre una base vacía. Todo el seguimiento se hace hoy releyendo la hoja a mano.

**Por qué ahora.** Tres condiciones coinciden y no se repiten:

| Condición | Estado |
|---|---|
| Base sin datos que reconciliar | El cambio 42 dejó **0 tareas**, 1 organización, `SDMUJER > SEGURIDAD + PANDORA` |
| Ancla de procedencia disponible | El cambio 43 entrega `external_origin`, `get_by_external_key` y `checklist_xlsx` en `KNOWN_TASK_SOURCES` |
| Deuda asignada explícitamente a este cambio | `openspec/specs/data-maintenance/spec.md:142`: «Entre este cambio y el **cambio 44**, `Removida` y `Gestionada aparte` cuentan como pendientes en el denominador» |

**La consolidación no puede aplicarse a ciegas.** El análisis de consolidación previo se verificó fila por fila contra el archivo: de 14 propuestas, **7 confirmadas, 5 corregidas y 2 rechazadas**. La corrección más costosa: tratar el bloque PSPI (`T-82`…`T-106`) como «espejos» habría **borrado trabajo que no existe en ningún otro sitio** —cinco filas dicen literalmente «Sin tarea operativa previa»— y habría escondido cinco vencidas. Por eso la consolidación se propone en un **CSV que el usuario revisa antes de escribir nada**, y no se decide dentro del importador.

**Idempotencia.** §5.5 de las decisiones de plataforma la exige en toda ingestión. Sin ella, el segundo `--execute` duplica 135 tareas y ensucia el tablero que este cambio existe para poblar. El criterio de aceptación es literal: **una segunda corrida con el mismo XLSX y el mismo CSV reporta `0 creadas, 0 actualizadas, 0 cambios`**.

**Éxito.** El usuario abre `http://localhost:4242`, ve su checklist real distribuido entre SEGURIDAD y PANDORA con estados, prioridades, vencimientos, responsables y etiquetas navegables; el avance consolidado deja de contar como pendiente lo que fue removido; las tareas de contexto no inflan la carga por persona pero sí siguen apareciendo en riesgo si están vencidas; y volver a correr el importador no cambia nada.

## Scope

### In Scope

- **Migración `0026`** — `board_columns.excluded_from_progress BOOLEAN NOT NULL DEFAULT false`, espejada en `__table_args__`.
- **Denominador de avance por bandera de columna** — la CTE de `rollup_progress` (`projects/repository.py:290-350`) deja de excluir el literal `cancelled` y pasa a excluir las columnas marcadas. Se marcan `Removida` y `Gestionada aparte`.
- **Tablero de PANDORA ampliado a 7 columnas** vía `ensure_board_columns`, en este orden exacto: `Backlog, Doing, Diferida, Recurrente, Gestionada aparte, Removida, Done`. Invariante nueva que congela columnas y orden (`_i4` solo protege a SEGURIDAD).
- **Migración `0027`** — `tasks.context_group VARCHAR(80) NULL` y `tasks.merge_into_task_id UUID NULL` (auto-FK `ondelete="SET NULL"`), espejadas en `__table_args__`; expuestas en `TaskRead`.
- **Exclusión de contexto en la vista ejecutiva** — `_build_workload` y `_build_totals` excluyen `context_group IS NOT NULL`; `_build_at_risk` **no**.
- **Insignia de procedencia en el frontend** (diferida por el 43, D6): insignia de solo lectura junto al `task_key`, visible solo con `external_key` no nulo, con `aria-label` del sistema de origen. Revisión `ux-psicologia` obligatoria.
- **`completed_at_override`** — tercer parámetro de palabra clave en `TaskService.create_task`, ausente de `TaskCreate`/`TaskUpdate` y del router; se aplica **solo** cuando el estado resuelto es el de cierre.
- **Paquete `backend/app/importers/checklist/`** — `parser.py` (XLSX, sin BD), `mapping.py` (funciones puras fila → intención), `consolidation.py` (CSV), `importer.py` (caso de uso dueño de la transacción) y `report.py`.
- **CLI `backend/scripts/import_checklist.py`** — `--file`, `--dry-run` (por defecto), `--csv-out`, `--execute --csv-in <ruta>`, `--update-existing`, `--database-url`, códigos de salida 0/1/2/3/4.
- **Usuarios sin acceso** — `User(hashed_password=None, is_active=True)` + `OrganizationMember(role=viewer)`.
- **Etiquetas en dos niveles** — `area:<primer segmento normalizado>` (27 valores), `apoyo-ia:{total,parcial,no}`, `recurrente` y `pspi:x.y`.

### Out of Scope

- **Tablas de vínculos de plan del cambio 45** — el enlace al PSPI viaja como etiqueta `pspi:x.y`; el 45 hará una migración trivial de etiqueta a relación.
- **Microsoft Planner** — las ocho filas `T-74`…`T-81` se importan como texto ya presente en la hoja; no se consulta Planner.
- **Ingesta de correo (cambio 47)**.
- **El `is_context` transitorio de `TaskRead`** — se queda **intacto** con su significado actual (padre ajeno devuelto como contexto bajo el filtro `assignee_id`). El 44 **no** lo convierte en columna: introduce `context_group`, que es otra cosa.
- **`TaskCreate` y `TaskUpdate`** — no cambian. Ni el ancla, ni `context_group`, ni `merge_into_task_id`, ni `completed_at` se vuelven escribibles por API.
- **Cambiar la metodología de PANDORA** — sigue siendo `kanban`; `_i3_hierarchy_shape` sigue verde.
- **Castellanizar los rótulos de PANDORA** (`Backlog → Sin iniciar`) — posible con `rename_column` sin tocar `status_key`, pero es UX opcional y no bloqueante.
- **Conteos esperados de filas** en código o pruebas — la hoja es un documento vivo.

## Capabilities

### New Capabilities

- `checklist-import`: importación idempotente de un checklist en XLSX hacia proyectos, tableros, etiquetas y usuarios de una organización, con fase de consolidación revisable por CSV y ejecución en dos modos (`--dry-run` / `--execute`).

### Modified Capabilities

- `project-hierarchy` (`openspec/specs/project-hierarchy/spec.md:113`): **MODIFIED** del requisito «Avance consolidado por conteo de tareas (roll-up)». El denominador deja de definirse como «todas las tareas del proyecto, EXCLUYENDO las de estado `cancelled`» y pasa a «EXCLUYENDO las tareas asignadas a columnas marcadas `excluded_from_progress`». El escenario «Tareas cancelled excluidas del denominador» se reescribe sobre la bandera. Nunca ADDED: el requisito ya existe publicado.
- `boards`: **ADDED** de la bandera `excluded_from_progress` como propiedad configurable de columna, y **ADDED** del sembrado idempotente de las 7 columnas de PANDORA con orden congelado por invariante. El requisito «Configuración runtime de columnas» (`:85`) no cambia.
- `tasks`: **ADDED** de `context_group`, `merge_into_task_id` y `completed_at_override` (escritura reservada al caso de uso, como el ancla del 43), más la exposición de solo lectura y la insignia de procedencia. `TaskCreate`/`TaskUpdate` intactos.
- `dashboard-executive`: **MODIFIED** del requisito **R3** (`spec.md:24`). Excluir las tareas de contexto de `workload` y `totals` —y no de `at_risk`— es un cambio observable del endpoint `GET /dashboard/executive`. **Añadida a la lista de tres capacidades que trajo el encargo**: la decisión D3 la implica y omitirla dejaría un cambio de comportamiento sin requisito que lo respalde. Ver «Preguntas abiertas».

## Approach

Siete piezas encadenadas. **A, B y C son costuras de esquema** y no dependen del XLSX: pueden entregarse y verificarse contra la base real antes de que exista una sola línea de parser.

| Pieza | Qué entrega | Decisión de fondo |
|---|---|---|
| **A** | `excluded_from_progress` + CTE del roll-up + 7 columnas de PANDORA + invariante | La bandera por columna es agnóstica de metodología y de tenant; meter `Removida`/`Gestionada aparte` como literales en el SQL genérico del roll-up empeoraría el problema que tiene hoy (`cancelled` no excluye nada porque ninguna metodología de esta organización lo produce) |
| **B** | `context_group` + `merge_into_task_id` + `TaskRead` + exclusión en el dashboard + insignia de UI | `context_group VARCHAR(80)` expresa dos cosas con una columna: `NOT NULL` significa «es contexto» y el valor es el nombre del grupo. Excluir por etiqueta exigiría un `JOIN` extra a `task_labels` dentro de una CTE ya cara |
| **C** | `completed_at_override` keyword-only | Hoy `completed_at` **no es escribible por ningún camino**: se deriva en `_resolve_completed_at` y `create_task` lo invoca con `current=None`, así que una tarea creada en la columna de cierre recibe `now()`. Sin esta costura, «CERRADA el 2026-08-16» no es representable |
| **D** | `parser.py` + `mapping.py` | Todo puro y sin BD: estados, prioridades, las tres formas de `Fecha Límite`, ruteo a SEGURIDAD/PANDORA, normalización de categorías, extracción de `completed_at` desde `Observaciones` |
| **E** | `consolidation.py` | Escritura, lectura y validación del CSV: toda fila decidida, toda referencia `merge_into:`/`subtask_of:` apunta a un `ID` presente en el XLSX, y sin ciclos en el grafo de subtareas |
| **F** | `importer.py` | Caso de uso dueño de la única transacción, al estilo de `maintenance/runner.py`: usuarios `viewer`, `ensure_label`, creación por ancla, dos pasadas para subtareas, fusiones, contexto e informe |
| **G** | `scripts/import_checklist.py` | CLI calcada de `purge_demo_data.py` + prueba extremo a extremo de idempotencia |

### La fila fusionada se crea, no se omite

Omitirla sería un fallo de idempotencia: si `T-81` no se crea, la siguiente corrida ve `get_by_external_key('checklist_xlsx','T-81') → None` y querrá crearla, y la decisión viviría solo en el CSV. Se crea con su ancla, en la columna `Removida` del proyecto destino, con `merge_into_task_id` apuntando a la superviviente y descripción «Consolidada en `SEG-N` (T-05)». Queda fuera del avance por el mismo mecanismo que cualquier otra `Removida`, sin regla nueva. `task_dependencies` queda descartada: es una arista `blocks`, otra semántica.

### Semántica de la reejecución

`--execute` **exige** `--csv-in`: sin el CSV no hay decisiones y el importador no debe adivinarlas. Por defecto **solo crea lo que falta**. La actualización de tareas ya importadas se habilita con `--update-existing` y se limita a una lista blanca (`status`, `priority`, `due_date`, `completed_at`, etiquetas). Motivo: una vez importadas, esas tareas se editan en la aplicación; un `--execute` que sobrescriba en silencio destruiría el trabajo del usuario, que es exactamente el fallo del que este cambio protege.

## Decisiones tomadas

### Del orquestador (2026-08-26)

| # | Decisión | Justificación |
|---|---|---|
| D1 | **Un solo cambio con siete rebanadas A→G**, no dos cambios | El ciclo verify/archive se hace una vez y las costuras A/B/C se verifican contra la base real dentro de la misma cadena; el usuario ve su checklist al cerrar el 44 |
| D2 | `Diferida` y `Recurrente` **permanecen en el denominador**; solo `Removida` y `Gestionada aparte` se marcan `excluded_from_progress` | Es literalmente lo que el 42 comprometió (`data-maintenance/spec.md:142`). La bandera deja la puerta abierta a cambiar de opinión sin migración |
| D3 | El dashboard **excluye `context_group`** en `_build_workload` y `_build_totals`; **no** en `_build_at_risk` | Una tarea de contexto vencida sigue siendo un riesgo real que el jefe debe ver; en cambio no debe contar como carga de nadie |
| D4 | Opción **B** para PANDORA: 7 columnas vía `ensure_board_columns`, `Done` última | Sin migración ni cambio de metodología. `_i3` sigue verde, `status_key` verbatim igual que SEGURIDAD, `BoardAwareStrategy.allowed_statuses()` las toma de la BD y `allowed_statuses()[-1]` sigue siendo el estado de cierre |
| D5 | `context_group` + `merge_into_task_id` como columnas, con la fila fusionada creada | Ver «Approach». `merge_into_task_id` y no `merge_into`, por convención con `parent_task_id` |
| D6 | Bandera `excluded_from_progress` en `board_columns`, no literales en SQL | Ver «Approach» |
| D7 | Usuarios sin login: `hashed_password=None` + `viewer` | Cero esquema nuevo. `auth/service.py:27` ya rechaza `hashed_password is None` con el mismo resultado genérico que una contraseña errónea. `is_active=False` está descartado: los desaparecería de `list_org_members` y de la vista ejecutiva, que es justo donde deben verse como responsables |
| D8 | `completed_at_override` keyword-only, solo en el estado de cierre | Réplica exacta del patrón que el 43 estableció para el ancla. Descartados: `UPDATE` posterior (abre una ventana con la fila ya visible con `completed_at = now()`) y añadirlo a `TaskUpdate` (rompería D-INM del 43 y lo expondría por API) |
| D9 | Paquete propio `backend/app/importers/checklist/` | Screaming Architecture: `maintenance` significa hoy «purga y bootstrap de la instalación» y su spec está **archivada**. El paquete nuevo tiene capacidad OpenSpec propia y puede importar `ensure_board_columns` sin heredar el alcance de la purga |

### Técnicas, adoptadas de la exploración

| # | Decisión | Justificación |
|---|---|---|
| D-CSV | `--execute` exige `--csv-in`; por defecto solo crea faltantes; `--update-existing` con lista blanca | Ver «Semántica de la reejecución» |
| D-LBL | `area:<primer segmento normalizado>` (27 valores) + `apoyo-ia:*` + `recurrente` + `pspi:x.y`. La categoría completa va a la descripción como línea `**Categoría:** …`, no a una etiqueta | Una etiqueta por `Categoría` da **72** nombres que, al ser `uq_labels_project_name`, se duplican en SEGURIDAD y PANDORA: ~150 filas de `labels` para 135 tareas y un desplegable inservible. La fuente además trae inconsistencias de caja y variantes que exigen normalizar |
| D-PSPI | Etiqueta `pspi:x.y` sobre las 25 filas del plan y sobre las operativas que el CSV declare vinculadas | Es lo único con numeración explotable en la fuente. **No existe numeración de PAI**: `pai:12.1` no es derivable de este archivo. El control ISO ya viaja en el `Detalle` y no se convierte en etiqueta |
| D-REC | La etiqueta `recurrente` se deriva de una **regla explícita**, no del cruce ingenuo estado×fecha | `T-25` es `DIFERIDA` con fecha `Recurrente` y `T-39` es `RECURRENTE` con fecha ISO: los dos conjuntos **no coinciden** |
| D-CNT | Ningún conteo esperado de filas en código ni en pruebas | La hoja es un documento vivo: hoy 135 filas, y el análisis previo del orquestador correspondía a una versión con 131 que ni siquiera incluía `T-132`…`T-135`, dos de ellas CRÍTICAS |
| D-DESC | Descripción > 4000 caracteres: **fallo en esa fila con su `ID`**, nunca truncar en silencio | `TaskCreate.description` tiene `max_length=4000` y la descripción es compuesta (Solicitante + Fecha límite + Detalle + Observaciones) |
| D-MIG | `0026` (rebanada A, `down_revision="0025"`) y `0027` (rebanada B, `down_revision="0026"`). El `0025` es del 43 y **no hay número reservado** para el 40 | Sin reservas: `0026` es la primera libre tras el 43, y el 40 tomará el siguiente consecutivo libre en el momento de su propio `apply`. Se usan **dos** migraciones y no una porque A y B son PR encadenados con reversa independiente: una sola migración compartida rompería `alembic downgrade -1` como reversa de A |
| D-DDL | Los tres objetos espejados en `__table_args__`, con prueba de **equivalencia de DDL** entre `create_all` y `upgrade head` | El harness construye el esquema con `Base.metadata.create_all` (`tests/conftest.py:74-80`). El 43 verificó que `alembic check` 1.14.0 **no** compara `postgresql_where` ni `CheckConstraint`: el riesgo real es un falso negativo silencioso |
| D-BADGE | La insignia de procedencia se entrega en B, con `ux-psicologia` obligatorio antes de cerrar la rebanada | El 43 la difirió (D6) porque tras él no existía ni una sola tarea anclada. En B ya existen columnas y contrato; la insignia por fin es verificable |
| D-CSV-DEF | Los valores por defecto del CSV son los **veredictos verificados**, no las propuestas originales | Fusiones confirmadas como `merge_into:`; `T-23` como `subtask_of:T-77`; `T-76→T-35` como `import` con nota «la fuente lo deja abierto»; `T-78` independiente con nota; el bloque PSPI como tareas reales (`T-94` y `T-99` marcadas consolidaciones, `T-82`/`T-92` con nota de cobertura parcial); grupos de contexto corregidos (con `T-07`, `T-107`, `T-122`, `T-71`, `T-54`; sin `T-74`); `T-95` en el conteo; contradicciones como notas |

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `backend/alembic/versions/0026_*.py` | New | `board_columns.excluded_from_progress` (rebanada A) |
| `backend/alembic/versions/0027_*.py` | New | `tasks.context_group`, `tasks.merge_into_task_id` (rebanada B) |
| `backend/app/modules/boards/models.py` | Modified | Columna nueva + espejo |
| `backend/app/modules/tasks/models.py:43-58,72-76` | Modified | Dos columnas nuevas + espejo de la auto-FK |
| `backend/app/modules/tasks/schemas.py:95-153` | Modified | `context_group`, `merge_into_task_id` en `TaskRead`. **`TaskCreate`/`TaskUpdate` no se tocan** |
| `backend/app/modules/tasks/service.py:252-335,854-864` | Modified | `completed_at_override` keyword-only |
| `backend/app/modules/projects/repository.py:290-350` | Modified | CTE de `rollup_progress` con la bandera en lugar del literal `cancelled` |
| `backend/app/modules/dashboard/service.py:85-91` | Modified | `_build_workload` y `_build_totals` excluyen contexto; `_build_at_risk` no |
| `backend/app/maintenance/bootstrap.py`, `invariants.py` | Modified | 7 columnas de PANDORA + banderas + invariante de orden |
| `backend/app/importers/checklist/` | New | `parser.py`, `mapping.py`, `consolidation.py`, `importer.py`, `report.py` |
| `backend/scripts/import_checklist.py` | New | CLI |
| `frontend/src/entities/workspace/workspace.model.ts` | Modified | Dos campos opcionales + insignia de procedencia |
| `openspec/changes/44-*/specs/checklist-import/spec.md` | New | Capacidad nueva |
| `openspec/changes/44-*/specs/{project-hierarchy,boards,tasks,dashboard-executive}/spec.md` | New | Deltas |

**No se toca**: `sprints`, `checklists`, `comments`, `attachments`, `alerts`, `intake`, `connectors`, `task_links`, `backend/app/ai/`, `openspec/changes/48-puerto-llm/`.

## Risks

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | El 43 está en `apply: pending`; sin él no existen `external_origin` ni `get_by_external_key` | Alta | Dependencia dura: el 44 no arranca hasta el archivado del 43 |
| R2 | Colisión de nombre con el `is_context` existente, que significa **otra cosa** (padre ajeno devuelto como contexto bajo `assignee_id`, calculado en `_to_read`) | Alta | Columna nueva `context_group`; el `is_context` transitorio queda intacto, igual que el tipo del frontend que lo consume |
| R3 | Importar 135 tareas —muchas vencidas desde marzo/abril/junio— distorsiona la vista ejecutiva de golpe | Alta | D3 acota la exclusión a `workload` y `totals`; se prueba con el conjunto real en la fase operativa **antes** de `--execute` |
| R4 | Marcar el bloque PSPI como contexto ocultaría cinco vencidas, dos desde marzo | Alta | Solo `T-94` y `T-99` son consolidaciones reales; el resto entra al conteo como tarea propia. Fijado en los valores por defecto del CSV (D-CSV-DEF) |
| R5 | `BoardService.add_column` **slugifica** (`diferida`) y `ensure_board_columns` escribe **verbatim** (`Diferida`): mezclarlos dejaría los dos valores en el mismo despliegue | Media | Usar **solo** `ensure_board_columns` para PANDORA; invariante que verifica los `status_key` verbatim |
| R6 | El orden de columnas determina `allowed_statuses()[-1]`: si `Done` deja de ser la última, `_resolve_completed_at` y el término `done` del roll-up se rompen **en silencio** | Media | Invariante explícita de orden; `ensure_board_columns` ya corrige `order` derivado |
| R7 | La descripción compuesta puede pasar de 4000 caracteres | Media | Medir por fila y fallar en esa fila con su `ID` (D-DESC) |
| R8 | Sin el CSV, `--execute` recrearía las filas fusionadas | Media | `--execute` exige `--csv-in`, y la fila fusionada **se crea** con su ancla |
| R9 | Modificar requisitos ya publicados de `project-hierarchy` y `dashboard-executive` puede duplicarlos al archivar | Media | Deltas **MODIFIED** explícitos sobre los requisitos existentes, nunca ADDED; el delta debe contener el bloque completo, escenarios incluidos |
| R10 | SSO podría vincular las cuentas sin credenciales si algún día se habilita Keycloak (`auth/sso_service.py:159-173` autoaprovisiona por correo verificado con `SSO_AUTO_PROVISION`) | Baja/futuro | Documentado; no se mitiga en este cambio |
| R11 | `data_only=True` puede devolver `datetime` en unas celdas y `str` en otras de la misma columna | Baja | El parser acepta ambos tipos; prueba pura dedicada |

## Rollback Plan

| Escenario | Reversa |
|---|---|
| Falla A | `alembic downgrade -1` (elimina `excluded_from_progress`) + revert de los commits. La CTE vuelve al literal `cancelled`, que hoy no excluye nada: **cero efecto observable**. Las columnas de PANDORA son idempotentes y aditivas; si estorban, se eliminan con la API de columnas indicando destino de reasignación |
| Falla B | `alembic downgrade -1` + revert. A permanece. Se pierde el contexto, la fusión y la insignia; el importador aún no existe |
| Falla C | Revert de los commits. Sin `completed_at_override` las tareas cerradas nacen con `completed_at = now()`: dato inexacto, no corrupción |
| Falla D, E, F o G | Revert de los commits. **Ninguna toca el esquema**: A, B y C quedan entregados y verificados por sí solos |
| El `--execute` importa mal | La transacción es única y solo comitea si todas las validaciones pasan (patrón `maintenance/runner.py:19-61`); en cualquier otro camino, `rollback()`. Si el fallo se detecta después, todas las filas llevan `source='checklist_xlsx'`: son identificables y removibles por ancla, sin tocar nada creado a mano |

## Dependencies

- **Cambio 43 archivado antes del `apply` del 44.** Entrega `create_task(..., external_origin=...)`, `TaskRepository.get_by_external_key`, `KNOWN_TASK_SOURCES` con `checklist_xlsx` y el único parcial `uq_tasks_source_external_key_project`. Sin él, el 44 no tiene por dónde escribir ni leer el ancla.
- **Cambio 42 archivado** (ya lo está): deja `SDMUJER > SEGURIDAD + PANDORA`, `ensure_board_columns` y el runner transaccional.
- **Numeración de Alembic**: cabeza en disco `0024`; `0025` es del 43 y el 44 toma `0026` y `0027`. **Sin reservas**: el 40 reanclado tomará el siguiente consecutivo libre en el momento de su propio `apply`, no un número apartado por adelantado. Compuerta de la Fase 0: `alembic heads` en vivo debe ser `0025` (43 aplicado) antes de escribir `0026`.
- `openpyxl==3.1.5` ya está en `backend/requirements.txt:17` y en los overrides de `mypy`.
- El **cambio 45** consumirá las etiquetas `pspi:x.y` como punto de partida de sus tablas de vínculos.

## Success Criteria

- [ ] TDD estricto (`openspec/config.yaml` `rules.apply.tdd: true`): prueba en rojo antes del código en las siete rebanadas.
- [ ] **Pruebas puras, sin BD y sin `@skip_no_db`**, para `parser.py` y `mapping.py`: los 7 estados, las 4 prioridades, las 3 formas de `Fecha Límite`, el ruteo SEGURIDAD/PANDORA, la normalización de categorías, la extracción de `completed_at` y el caso en que `openpyxl` devuelve `datetime` en vez de `str`.
- [ ] **Pruebas de integración con XLSX generado en `tmp_path`** (6-10 filas que cubran los 7 estados, una fusión, una subtarea, un grupo de contexto y una `Observaciones` con «CERRADA el YYYY-MM-DD»). **Nunca el archivo real**: 135 filas de datos institucionales no entran al repositorio.
- [ ] **Pruebas de migración** para `0026` y `0027` con el patrón `test_migration_project_kind.py:73-244` (base desechable, `upgrade`, aserciones sobre `information_schema`, `downgrade` sin pérdida de filas) **más equivalencia de DDL** entre `Base.metadata.create_all` y `alembic upgrade head`, como en el 43.
- [ ] **Idempotencia extremo a extremo**: `--execute --csv-in` dos veces sobre el mismo XLSX reporta `0 creadas, 0 actualizadas, 0 cambios` en la segunda corrida.
- [ ] El CSV se rechaza **antes de escribir nada** ante: fila sin decidir, referencia a un `ID` inexistente y ciclo en el grafo de subtareas.
- [ ] `--execute` sin `--csv-in` termina con error y código de salida distinto de 0.
- [ ] Una fila cuya descripción compuesta supere 4000 caracteres falla nombrando su `ID`; ninguna descripción se trunca.
- [ ] `ensure_label` es idempotente (`create_label` **no** es get-or-create: lanza 422 `duplicate_label_name`) y `assign_label` no duplica.
- [ ] Invariante nueva en verde: PANDORA tiene sus 7 columnas, en orden, con `status_key` verbatim y `Done` última.
- [ ] Ningún conteo esperado de filas aparece en el código ni en las pruebas.
- [ ] Revisión `ux-psicologia` aprobada antes de cerrar la rebanada B (insignia de procedencia).
- [ ] **Sin regresión** frente a la línea base **re-medida al iniciar cada rebanada** (no una cifra congelada: la suite está en deriva, 1411 → 1415 → 1429, con el cambio 48 escribiendo pruebas en paralelo).
- [ ] `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q` en verde salvo las 3 fallidas preexistentes de `tests/test_adapter_microsoft365.py` (dependientes del reloj).

## Fase operativa manual (después del `apply`, antes del `archive`)

1. `python backend/scripts/import_checklist.py --file <ruta al XLSX real> --dry-run --csv-out checklist_consolidation.csv` — no escribe una sola fila.
2. **El usuario revisa el CSV** y ajusta las decisiones (fusiones, subtareas, grupos de contexto, notas). Es su fuente de verdad; el importador solo propuso.
3. `python backend/scripts/import_checklist.py --file <ruta> --execute --csv-in checklist_consolidation.csv`.
4. Verificación en `http://localhost:4242`: tablero de SEGURIDAD y de PANDORA, avance consolidado, vista ejecutiva y filtros por etiqueta `area:*`.
5. Segunda corrida idéntica → `0 creadas, 0 actualizadas, 0 cambios`.

Esta fase es **operativa, no de diseño**: no bloquea `sdd-spec` ni `sdd-design`.

## Carga de revisión

Estimado **≈2300-2700 líneas** (`additions + deletions`), ~55 % pruebas. Muy por encima del umbral por defecto de 400.

`400-line budget risk: **High**` · `Chained PRs recommended: **Yes**` · `Decision needed before apply: **No**` (estrategia `auto-chain` ya resuelta).

Topología **feature branch chain** sobre el tracker `feat/44-importar-checklist-xlsx`: A apunta al tracker y cada rebanada siguiente a la rama de la anterior.

| Rebanada | Rama | Contenido | Presupuesto |
|---|---|---|---|
| **A** | `feat/44-a-avance` | Migración `0026` + espejo · CTE del roll-up con la bandera · 7 columnas y banderas de PANDORA · invariante nueva · pruebas | **500** |
| **B** | `feat/44-b-contexto` | Migración `0027` + espejo · `TaskRead` · exclusión de contexto en el dashboard · tipo e insignia del frontend · pruebas | **400** |
| **C** | `feat/44-c-completado` | `create_task(..., completed_at_override=...)` · pruebas | **200** |
| **D** | `feat/44-d-parser` | `parser.py` + `mapping.py` · pruebas puras sin BD | **600** |
| **E** | `feat/44-e-consolidacion` | `consolidation.py`: escritura, lectura y validación del CSV · pruebas | **600** |
| **F** | `feat/44-f-importador` | `importer.py`: usuarios `viewer`, `ensure_label`, creación y reconciliación, dos pasadas de subtareas, fusiones, contexto, informe · pruebas de integración | **600** |
| **G** | `feat/44-g-cli` | `scripts/import_checklist.py` + prueba extremo a extremo de idempotencia | **400** |

Presupuestos = estimación de la exploración × 1,2 + ≈50 líneas de marcas en `tasks.md`, redondeado a la centena. Total **3300**.

**Aviso para `sdd-tasks`**: la rebanada B absorbe además la exclusión de contexto en el dashboard (D3), que la exploración no había presupuestado. Si al desglosar excede su presupuesto de 400, aplicar la contingencia que el 43 ya usó: sacar la insignia del frontend a una rebanada propia, que puede posponerse sin bloquear a D-G. El pronóstico formal lo emite `sdd-tasks`, no esta propuesta.

## Preguntas abiertas

**Ninguna bloqueante.** Las tres decisiones de alcance que la exploración dejó al orquestador quedaron resueltas como D1, D2 y D3, y las nueve recomendaciones técnicas de §3 se adoptaron íntegras. La revisión del CSV de consolidación es una **fase operativa** posterior al `apply`, no un vacío de diseño.

Un solo punto requiere confirmación del orquestador **antes de `sdd-spec`**, y no de diseño sino de alcance de artefactos:

- **`dashboard-executive` como cuarta capacidad modificada.** El encargo enumeró tres (`project-hierarchy`, `boards`, `tasks`), pero D3 cambia el comportamiento observable de `GET /dashboard/executive` y el requisito **R3** de esa spec está publicado. O se incluye el delta **MODIFIED** de R3, o D3 se implementa sin requisito que lo respalde. Recomendación: incluirlo.

Dos puntos anotados que **no bloquean** este cambio:

- Castellanizar los rótulos de PANDORA (`Backlog → Sin iniciar`, `Doing → En curso`, `Done → Completada`) es posible con `rename_column` **sin tocar `status_key`**. Es UX opcional y puede decidirse durante la fase operativa.
- La migración de las etiquetas `pspi:x.y` a relaciones de plan pertenece al **cambio 45**.

## Referencias

- `openspec/changes/44-importar-checklist-xlsx/exploration.md` — verificación de la consolidación contra el archivo real, hallazgos H1-H5 y decisiones del orquestador.
- `openspec/changes/43-tareas-origen-externo/{proposal,design}.md` y `specs/tasks/spec.md` — ancla de procedencia, `external_origin`, `get_by_external_key`, `KNOWN_TASK_SOURCES`.
- `openspec/specs/data-maintenance/spec.md:142` — deuda del denominador asignada explícitamente a este cambio.
- `openspec/specs/project-hierarchy/spec.md:113` · `openspec/specs/boards/spec.md:85,145` · `openspec/specs/dashboard-executive/spec.md:24` — requisitos afectados.
- `agents/rules/solercia-persistence.md` — repositorios sin commit, tenant obligatorio en toda lectura y escritura, SQL en adaptadores.
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` — §5.4 (identificadores de proveedor opacos calificados por fuente), §5.5 (**idempotencia obligatoria en la ingestión**), §6.5, §7.
- `backend/app/maintenance/{bootstrap,repository,runner,invariants}.py` y `backend/scripts/purge_demo_data.py` — patrones reutilizados.
