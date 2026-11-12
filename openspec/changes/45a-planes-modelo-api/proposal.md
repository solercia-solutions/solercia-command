# Proposal: 45a · Planes institucionales (Decreto 612) — modelo y API

## Intent

**Problema de negocio.** El trabajo de la entidad ya está comprometido con tres planes formales del Decreto 612 —PSPI 2026 (25 actividades), PTR 2026 (26 acciones de tratamiento) y PAI 2026 (11 actividades propias de las políticas 11 y 12)— pero **Command no tiene dónde registrar ese compromiso**. Hoy la relación tarea ↔ actividad de plan vive fuera del sistema: en el criterio del responsable, en un archivo de cruce y en la memoria de quien reporta. El resultado operativo es concreto:

| Hoy | Costo |
|---|---|
| El avance de una actividad de plan se arma a mano cada cuatrimestre | El reporte al SIG/PAI se rehace desde cero tres veces al año |
| No hay contraste entre lo que dicen las tareas y lo que se reportó | Nadie puede sustentar un porcentaje ante Planeación o Control Interno con el trabajo que lo respalda |
| Una tarea que aporta a varias actividades no puede decirlo | Los propios documentos exigen la relación N:N (R34 → PSPI 2.5 y 5.3; R39 → PSPI 1.1, 1.2 y 1.3) |
| El avance de una actividad cruza proyectos distintos | El roll-up existente (`projects/repository.py:290-350`) está modelado sobre el subárbol de **un** proyecto y no sirve |

**Urgencia.** Dos cambios dependen de que este modelo exista y ninguno puede avanzar sin él: **45b** (importadores de las tres fuentes + enlazador) y **45c** (vista «Planes»). Además, el ritual de reporte del PAI es la misma actividad 4.1 del PSPI: cada cuatrimestre que pasa sin el modelo es un reporte más construido a mano y no reproducible.

**Éxito.** Una actividad de plan es un objeto consultable con identificador legible (`PSPI-2026/1.1`), sabe qué tareas la sustentan y expone **dos avances que nunca se mezclan**: el **calculado** desde el estado real de sus tareas `primary` y el **reportado** por el responsable en el periodo. Cuando una actividad no tiene tareas enlazadas, su avance calculado es `null` —«no hay evidencia»—, **nunca `0`** —«se hizo nada»—, porque ante un ente de control esas dos afirmaciones no son intercambiables. El 45b encuentra una costura de escritura idempotente ya construida en lugar de inventar la suya, y el 45c encuentra la API completa sin necesidad de tocar backend.

## Scope

### In Scope

- **Migración `0028_add_institutional_plans`** (`down_revision="0027"`, sujeta a la compuerta en vivo de la Fase 0): cinco tablas nuevas —`plans`, `plan_activities`, `plan_activity_reports`, `plan_activity_links`, `task_plan_activities`— con sus FKs `ON DELETE CASCADE`, índices, únicos de alcance y el `CHECK ck_plan_activity_links_no_self`.
- **Espejado literal** de todo objeto de esquema en `__table_args__` de cada modelo: el harness construye el esquema con `Base.metadata.create_all` (`tests/conftest.py`), no con Alembic. El gate real es una **prueba de equivalencia de DDL** (`pg_get_indexdef` / `pg_get_constraintdef` entre `create_all` y `upgrade head`), no `alembic check` (lección verificada del 43, D-B).
- **Módulo `backend/app/modules/plans/`** con la estructura fija del repositorio: `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`.
- **Repositorio**: lecturas con alcance de tenant obligatorio vía `JOIN plans` (`plan_activities` **no** denormaliza `organization_id`), **roll-up cruzado** —la última columna activa del board de *cada* tarea, no de un proyecto—, CRUD de reportes y de enlaces, y **costura de escritura idempotente** de planes y actividades por `code`, que es la que consumirá el importador del 45b.
- **Servicio**: `activity_key` derivado y transitorio (`f"{plan.code}/{activity.code}"`, patrón `task_key` de `tasks/service.py:967`), doble avance con `null ≠ 0`, vocabularios cerrados validados en la capa de servicio y `resolution='manual'` impuesto a todo enlace creado por API.
- **Router `/api/v1/plans`** con 5 endpoints de lectura y 5 de escritura (tabla en «Approach»), envelope `{data, message, meta}`, paginación opt-in y errores `AppException(code=...)`.
- **RBAC**: lectura para cualquier miembro autenticado; escritura con `require_role(MemberRole.admin, MemberRole.manager)` declarado como singleton de módulo (esquiva `ruff B008`, patrón `intake/router.py:32-34`).
- **Cableado**: `app/main.py` (`include_router`) y `app/db_init.py:43-96` (import de modelos con `# noqa: F401` para que las `relationship()` por cadena resuelvan).
- **Pruebas** con TDD estricto: migración sobre base desechable con `downgrade`, repositorio contra PostgreSQL real, servicio con fakes, endpoints por API real in-process.

### Out of Scope

- **Importadores DOCX/XLSX, enlazador, mapa semilla y CLI** → **45b**. Su autoridad es el documento fuente; consumen la costura de escritura que entrega el 45a.
- **Vista «Planes», entidad de frontend, rutas, i18n e ícono** → **45c**.
- **Entrada del menú «Planes» en `_MENU_SEED` / `_ROLE_MENU_SEED`** → recomendada para el **45c** (ver **D13**; es la única divergencia frente al alcance dictado y requiere ratificación del orquestador).
- **Creación de planes y actividades por HTTP** — no existe `POST /plans`: la autoridad de un plan del Decreto 612 es su documento, no un formulario (ver **D10**).
- **PTEP-2026** — `plan_type` admite `ptep`, pero no hay fuente extraída (P1).
- **Monitoreo cualitativo, evaluación independiente y observaciones-recomendaciones del PAI** (columnas `AA`, `AB`, `AC`) — frontera ADR 0009: Security es la única autoridad sobre cumplimiento y cierre de evidencia (**D5**).
- **Cambios en `tasks` más allá de la relación N:N** — ni columnas nuevas, ni `TaskRead.plan_activities`, ni `task_history` de los enlaces (ver **D9**).
- **Cambio del criterio de exclusión del avance** — el literal `status != 'cancelled'` lo sustituye el **44** por `board_columns.excluded_from_progress`; el 45a consume el criterio vigente al momento de su apply, no lo redefine.

## Capabilities

### New Capabilities

- `institutional-plans`: planes institucionales como dimensión transversal de compromiso — plan, actividad con identificador legible derivado, reporte de autoevaluación por periodo, enlace actividad ↔ actividad con su resolución trazable, enlace N:N tarea ↔ actividad con rol, y doble avance (calculado desde las tareas vs. reportado por el responsable) con alcance de tenant transitivo.

### Modified Capabilities

**Ninguna.** Las dos candidatas se examinaron y se descartan con razón explícita:

| Candidata | Veredicto | Razón |
|---|---|---|
| `tasks` | **No se modifica** | La exposición del lado de la tarea se sirve desde el módulo `plans` (`GET /plans/activities?task_id=`), no desde `TaskRead` (**D9**) |
| `project-hierarchy` | **No se modifica** | Su requisito de roll-up (`spec.md:111-137`) describe `GET /projects/{id}/progress` sobre un subárbol. El 45a escribe **SQL nuevo** en el módulo `plans` sobre un conjunto de tareas de proyectos distintos: no altera ni un requisito de esa capacidad. Quien sí lo modificará es el **44**, al reemplazar el literal `cancelled` por la bandera de columna |

`rbac-catalog`, `multi-tenancy`, `api-conventions` y `boards` se **cumplen**, no se modifican: el 45a no cambia un solo requisito suyo.

## Approach

### Piezas

| # | Pieza | Decisión |
|---|---|---|
| 1 | **Migración `0028`** | Patrón aditivo canónico de `0024_add_work_calendar.py`: `op.create_table` sin `batch_alter_table` (PostgreSQL exclusivo, cero apariciones en 24 migraciones), `downgrade()` en orden inverso, docstring que cita el cambio SDD y la verificación en vivo del head |
| 2 | **Cinco tablas** | `plans` (`TenantMixin`) · `plan_activities` · `plan_activity_reports` · `plan_activity_links` · `task_plan_activities`. Alcance de tenant **transitivo** por `plan_id → plans.organization_id`; denormalizar `organization_id` está prohibido por `agents/rules/solercia-persistence.md` y por el precedente de `tasks` (**P7**) |
| 3 | **JSONB** | `iso_controls`, `external_codes` (plural: PSPI 2.4 lleva `OM-05` **y** `OM-08`), `scheduled_periods`, `evidence_refs`. Precedente sólido: `intake/models.py:21,71,108`, `connectors/models.py:54,73`; sin extensión ni migración especial |
| 4 | **`activity_key`** | Campo transitorio de Pydantic calculado en el servicio, jamás columna. Sobrevive a un cambio de `id` porque se reconstruye de dos columnas con unicidad garantizada (`uq_plans_org_code` + `uq_plan_activities_plan_code`) |
| 5 | **Roll-up cruzado** | CTE `DISTINCT ON (board.project_id) … ORDER BY column_order DESC, created_at DESC` **unido por `board.project_id = task.project_id`** en lugar de filtrado a un proyecto, conservando `Board.is_active` y `BoardColumn.is_active`. Es SQL nuevo, no una reutilización de `rollup_progress` |
| 6 | **Doble avance** | `calculated_progress` = tareas `primary` en la última columna ÷ tareas `primary` no excluidas. `reported_progress` = el valor del periodo consultado. Los enlaces `contributes` **no entran en la razón**: se exponen aparte como `contributing_task_count` |
| 7 | **Conflictos persistidos** | `plan_activity_links.resolution` (`exact`/`by_external_code`/`conflict`/`manual`) + `source_reference` con el texto literal de la fuente. Un enlace `conflict` es consultable y nunca se cuenta como confirmado (**D6**) |
| 8 | **Router** | `require_role` singleton de módulo; **el `GET /plans/activities` estático debe declararse antes que `/plans/{plan_id}`**, o FastAPI intentará convertir `"activities"` en UUID y devolverá 422 en lugar de la lista |

### Superficie de API

| # | Método y ruta | Rol | Qué entrega |
|---|---|---|---|
| 1 | `GET /api/v1/plans` | miembro | Planes de la organización · `?plan_type=&period_year=&status=` · paginación opt-in |
| 2 | `GET /api/v1/plans/{plan_id}` | miembro | Detalle del plan y conteo de actividades por grupo |
| 3 | `GET /api/v1/plans/activities` | miembro | Actividades de todos los planes · `?plan_id=&plan_type=&is_mine=&group_code=&task_id=&period=` · cada fila con `activity_key`, `calculated_progress`, `reported_progress` del periodo, `primary_task_count`, `contributing_task_count` |
| 4 | `GET /api/v1/plans/activities/{activity_id}` | miembro | Actividad + sus reportes por periodo + enlaces entrantes y salientes con `resolution` y `source_reference` |
| 5 | `GET /api/v1/plans/activities/{activity_id}/tasks` | miembro | Tareas enlazadas · `?role=` · con `task_key`, título, estado, proyecto y si cuentan al avance |
| 6 | `PUT /api/v1/plans/activities/{activity_id}/reports/{period}` | admin·manager | Crea **o actualiza** el reporte del periodo (upsert idempotente sobre `uq_plan_activity_reports_activity_period`) |
| 7 | `POST /api/v1/plans/activities/{activity_id}/tasks` | admin·manager | Enlace tarea ↔ actividad (`task_id`, `role`, `note`) |
| 8 | `DELETE /api/v1/plans/activities/{activity_id}/tasks/{task_id}` | admin·manager | Elimina ese enlace |
| 9 | `POST /api/v1/plans/activities/{activity_id}/links` | admin·manager | Enlace actividad ↔ actividad (`to_activity_id`, `link_type`); el servicio fija `resolution='manual'` |
| 10 | `DELETE /api/v1/plans/activities/{activity_id}/links/{link_id}` | admin·manager | Elimina ese enlace |

Toda lectura cruza `JOIN plans` con filtro por `organization_id`; una actividad de otra organización responde **404**, igual que el resto de detalles del repositorio.

### Frontera con Solercia Security (ADR 0009)

Command guarda **solo el autorreporte de primera línea**: `% de avance cuatrimestral`, `avance cualitativo`, `evidencia`, `se cumplió la actividad` y `se cumplió en la fecha`. **No modela** monitoreo cualitativo, evaluación independiente ni observaciones-recomendaciones: son segunda y tercera línea de defensa, y `docs/adr/0009-…:78-80,238-240` reserva a Security la autoridad sobre cumplimiento, validación y cierre de evidencia. Es una **frontera declarada**, no una omisión; debe quedar escrita en el `design.md`.

## Decisiones tomadas

### Adoptadas de la exploración (ratificadas por el orquestador el 2026-08-26)

| # | Decisión | Justificación breve |
|---|---|---|
| D1 | `code` + `activity_key` derivado, **sin `public_id`** | `public_id` tiene cero apariciones en `backend/`; la forma canónica del repositorio es columna `code` con unicidad de alcance más clave compuesta expuesta solo en la respuesta (`projects.code`, `tasks.task_number` → `task_key`) |
| D2 | Modelo de cinco tablas | `external_codes` en plural (la fuente tiene una actividad con dos códigos), sin `reported_progress` redundante en la actividad, `resolution`/`source_reference` en los enlaces, `CHECK` anti-autorreferencia y sin denormalizar `organization_id` |
| D3 | Doble avance, `null ≠ 0` | Cero enlaces `primary` significa «sin evidencia», no «cero por ciento»: colapsarlos produciría un dato falso ante un ente de control |
| D4 | DOCX por `zipfile` + `xml.etree` | Aplica al **45b**; se registra aquí porque fija que el 45a **no** agrega dependencias a `requirements.txt` |
| D5 | Frontera ADR 0009 | Command guarda primera línea; Security es autoridad de cumplimiento |
| D6 | Conflictos registrados, nunca resueltos en silencio | El 45a entrega el **soporte de datos** (`resolution` + `source_reference`); la política la ejerce el 45b |
| D7 | Formato de `plan_links` para el CSV del 44 | `PSPI-2026/1.1:primary;PAI-2026/12.4:contributes` — la clave es exactamente `activity_key`, lo que obliga a que D1 exista antes que el 44 lo emita |
| D8 | Migración `0028` | Cadena sin reservas: 43→`0025`; 44→`0026` (`board_columns`) **y** `0027` (`tasks`); el 45a toma `0028` con `down_revision="0027"`, confirmada por compuerta en vivo en la Fase 0 (ver **R2**). El cambio 40 **no tiene número apartado**: tomará el siguiente consecutivo libre en el momento de su propio `apply` |
| P1 | Cuatro `plan_type`, tres importables | `ptep` existe en el vocabulario desde el día uno para no exigir una migración cuando aparezca la fuente |
| P3 | `require_role(admin, manager)` para escribir; lectura para cualquier miembro | Un reporte cuatrimestral es una afirmación institucional; leerlo no lo es |
| P5 | Tabla semilla de enlaces PAI, con `T-63` | Alcance del **45b** |
| P7 | `plan_activities` **sin** `organization_id` | Ratificado con prueba de aislamiento de tenant por endpoint |
| P2 · P4 · P6 | Resueltas fuera del 45a | P2 (seguimiento 2025/2026 del PAI) y P6 (R26/R32) son del 45b; P4 quedó cerrada en D8 |

### Nuevas de esta fase

| # | Decisión | Justificación |
|---|---|---|
| **D9** | La exposición del lado de la tarea **no entra en `TaskRead`**: se sirve con `GET /plans/activities?task_id=` | Embeber una relación en `TaskRead` obligaría a carga anticipada en **todos** los caminos de lectura de tareas —listado, detalle y `GET /dashboard/executive`, que comparten `TaskRead.model_validate` con `from_attributes`—, porque un acceso perezoso a una relación en SQLAlchemy async falla en ejecución. Es un cambio de rendimiento y de acoplamiento (`tasks` → `plans`) desproporcionado para el 45a, y dejaría `tasks` como capacidad modificada por un campo que en ese momento nadie consume. Si el 45c demuestra que la insignia en el modal la necesita embebida, **ese** cambio será el dueño del delta de `tasks` |
| **D10** | La escritura de planes y actividades vive en el **repositorio** (upsert idempotente por `code`), **sin superficie HTTP** | Dos razones independientes. De negocio: la autoridad de un plan del Decreto 612 es su documento fuente; un formulario crearía una segunda ruta de autoría que divergiría del documento y chocaría con la idempotencia por `(plan.code, activity.code)` del importador. Técnica: entregar la costura en el 45a evita que las pruebas siembren por un camino que la aplicación no usa —el error que el 43 corrigió con D-G— y le da al 45b un único punto de escritura en vez de inventarse el suyo |
| **D11** | El reporte del periodo se escribe con `PUT …/reports/{period}` idempotente, no con `POST` + `PATCH` | El único `(plan_activity_id, period)` hace que «crear» y «actualizar» sean el mismo hecho de negocio: el responsable ajusta su reporte varias veces antes del corte. Un `POST` devolvería 409 en el segundo intento legítimo |
| **D12** | Vocabularios cerrados como `String(n)` validado en el servicio, **nunca `SAEnum`** | Aplica a `plan_type`, `status`, `period`, `role`, `link_type` y `resolution`. Un enum de PostgreSQL obligaría a una migración por cada valor nuevo. Precedentes: `connectors.provider` («deliberately NOT a PG enum»), `tasks.status`, y D3 del 43 |
| **D13** | El menú «Planes» se **difiere al 45c** (divergencia declarada frente al alcance dictado) | `_ensure_menus` (`db_init.py:431-456`) siembra menús **globales** en cada arranque y solo INSERTA los faltantes: nunca actualiza `order`, `icon` ni `path` de una fila existente. Sembrar «Planes» con `path=/plans` en el 45a pondría, en todas las organizaciones, un enlace de barra lateral hacia una ruta que no existe hasta el 45c → comodín/404 para todo usuario. Además, como el sembrado no necesita migración de datos, diferirlo no cuesta nada: la entrada aparece en el siguiente arranque tras el 45c. Consecuencia práctica: la entrada debe tomar un `order` libre (7, tras «Conexiones») porque renumerar la semilla no afecta a una base ya sembrada |
| **D14** | La API nunca acepta `resolution` del cliente | Todo enlace creado por HTTP es `manual` por construcción; los valores `exact`, `by_external_code` y `conflict` son afirmaciones sobre la **lectura de una fuente** y solo el importador del 45b puede emitirlos. Aceptarlo por API permitiría marcar como «exacto» un enlace que ningún documento respalda |

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `backend/alembic/versions/0028_add_institutional_plans.py` | New | 5 tablas, FKs `ON DELETE CASCADE`, índices, 5 únicos y 1 `CHECK` |
| `backend/app/modules/plans/__init__.py` | New | Módulo |
| `backend/app/modules/plans/models.py` | New | 5 modelos con espejo literal en `__table_args__` |
| `backend/app/modules/plans/schemas.py` | New | Lectura, escritura y `activity_key` transitorio |
| `backend/app/modules/plans/repository.py` | New | Lecturas con tenant por `JOIN`, roll-up cruzado, upsert idempotente, CRUD de reportes y enlaces |
| `backend/app/modules/plans/service.py` | New | `activity_key`, doble avance, vocabularios, `resolution='manual'` |
| `backend/app/modules/plans/router.py` | New | 10 endpoints + `require_role` singleton |
| `backend/app/main.py:18-46,158-188` | Modified | Import + `include_router(..., prefix=API_PREFIX)` |
| `backend/app/db_init.py:43-96` | Modified | Import de los 5 modelos con `# noqa: F401` |
| `backend/tests/test_migration_institutional_plans.py` | New | Base desechable + `downgrade` + equivalencia de DDL |
| `backend/tests/test_plans_repository.py` | New | Roll-up cruzado y aislamiento de tenant contra PostgreSQL real |
| `backend/tests/test_plans_api.py` | New | Los 10 endpoints, RBAC y `null ≠ 0` |
| `openspec/specs/institutional-plans/spec.md` | New (vía `sdd-archive`) | Capacidad nueva |

**No se toca**: `tasks`, `boards`, `projects`, `dashboard`, `sprints`, `intake`, `connectors`, `db_init._MENU_SEED` (D13) ni `frontend/`.

## Rollback Plan

| Escenario | Reversa |
|---|---|
| La rebanada A falla o el modelo resulta equivocado | `alembic downgrade -1` + revert de los commits. **Cero filas afectadas y cero tablas preexistentes tocadas**: las cinco tablas son nuevas y ningún módulo vigente las referencia |
| Falla B, C, D, E o F | Revert de los commits de la rebanada. Las tablas quedan vacías y sin lector: no hay estado observable que reparar ni datos que migrar |
| La prueba de equivalencia de DDL reporta diferencia tras el merge | Señala qué objeto difiere entre `Base.metadata.create_all` y `alembic upgrade head`; se corrige **el modelo**, nunca la migración |
| El roll-up cruzado resulta incorrecto en producción | El avance calculado es una **lectura derivada**: no hay dato persistido que corregir. Se corrige la consulta y el valor se recalcula en la siguiente petición |
| Otro cambio toma `0028` antes que el 45a | La compuerta de la Fase 0 relee `alembic heads` en vivo y re-ancla número y `down_revision` antes de escribir la migración (R2) |

## Risks

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| R1 | **Tamaño**: ≈ 2 260 líneas (×1,2) para el 45a solo | Alta | Seis rebanadas encadenadas con presupuesto explícito; `400-line budget risk: High` declarado desde la propuesta |
| R2 | **La numeración `0028` presupone el orden de aplicación 43 → 44 → 45a y el conteo exacto de migraciones ajenas.** El 45a no depende de ninguno para *planificar*, así que su apply podría llegar antes y dejar `down_revision="0027"` apuntando a una revisión inexistente. Ya se movió dos veces: primero porque el 44 pasó de reclamar una migración a reclamar dos, y después al eliminarse la **reserva** que apartaba `0026` al cambio 40 —una reserva que habría encadenado el 44 a una revisión que nadie escribiría en esta ola, rompiendo `alembic upgrade head` en despliegue | **Alta** (materializada dos veces) | El número es una **reclamación, no una promesa**, y **ningún número se reserva a un cambio que no aplica**: compuerta de Fase 0 con `alembic heads` en vivo + inventario de `alembic/versions/` + revisión de **cuántas** migraciones reclama cada cambio pendiente, ejecutada inmediatamente antes de escribir la migración. La compuerta exige `alembic heads == 0027` (44 aplicado) antes de escribir `0028`. El número y el `down_revision` se re-anclan sin renegociar el diseño |
| R3 | **El roll-up no se reutiliza**: `rollup_progress` está atado al subárbol de un proyecto y una actividad agrupa tareas de proyectos distintos, cada uno con su board y su última columna | Alta | SQL nuevo probado contra PostgreSQL real con el caso que lo motiva: dos tareas `primary` de la misma actividad en dos proyectos con boards de columnas distintas |
| R4 | **Espejado migración ↔ modelo**: `alembic check` 1.14.0 no compara `CheckConstraint` ni `postgresql_where`; el `CHECK` anti-autorreferencia podría faltar en `__table_args__` y las pruebas validarían una regla distinta de la de producción (falso negativo silencioso) | Media/Alta | Prueba de equivalencia de DDL (`pg_get_indexdef` / `pg_get_constraintdef`) entre las dos rutas de construcción del esquema, exactamente como la entregó el 43 (D-B). `alembic check` se conserva solo como guardia de existencia por nombre |
| R5 | **`plan_activities` sin `organization_id`**: un olvido del `JOIN plans` en cualquier lectura filtra datos entre organizaciones | Media | Prueba de aislamiento de tenant **por endpoint**, no una sola global; ratifica P7 |
| R6 | **Criterio de exclusión del avance en movimiento**: el 44 sustituye el literal `status != 'cancelled'` por `board_columns.excluded_from_progress`. Si el 44 aplica primero, el roll-up del 45a nace con el criterio viejo; si aplica después, debe actualizar también el SQL del 45a | Media | El 45a usa el criterio **vigente al momento de su apply** y lo fija en una prueba nombrada; se deja nota de coordinación cruzada en ambos cambios para que quien aplique segundo actualice al otro. Ninguno de los dos bloquea al otro |
| R7 | **`null` colapsado a `0`**: una actividad sin tareas enlazadas mostrada como «0 % de avance» es una afirmación falsa ante el SIG | Media | Escenario de spec explícito y aserción dedicada en las pruebas de servicio y de API |
| R8 | **N+1 al calcular el avance de un listado**: 62 actividades reales (25 + 26 + 11) con una consulta por actividad | Media | El roll-up se resuelve en **una sola consulta agregada por lote** de actividades; prueba con conteo de consultas o con lote representativo |
| R9 | **Frontera ADR 0009**: la tentación de guardar en Command el monitoreo y la evaluación independiente del PAI porque «están en la misma hoja» | Media | D5 escrita como frontera en propuesta, spec y diseño; las columnas `AA`/`AB`/`AC` no existen en el modelo |
| R10 | **Cinco tablas de una sola vez** en una migración | Baja | Alembic corre la migración dentro de una transacción en PostgreSQL: o entran las cinco o no entra ninguna. El `downgrade` se ejercita en la propia prueba |
| R11 | **Nombres de identificadores**: el más largo es `uq_plan_activity_reports_activity_period` (40 caracteres) | Baja | Muy por debajo del límite de 63 de PostgreSQL; `Base` no declara `naming_convention`, así que **toda** restricción se nombra explícitamente |

Los riesgos 3, 4, 6, 7, 8, 10, 11, 12 y 13 de la exploración pertenecen al **45b** (fuentes, importadores, confidencialidad de los documentos) o al **45c** (ausencia de runner de pruebas de frontend) y no se arrastran aquí.

## Dependencies

- **Ninguna para planificar ni para implementar.** El 45a no consume nada del 43, del 44 ni del 40: no toca `tasks` fuera de la FK, no necesita `external_key` ni `context_group`, y su modelo es autónomo.
- **Dependencia de secuencia, no de contrato**: la migración toma el número libre en el momento de su apply (R2).
- **Coordinación con el 44** sobre el criterio de exclusión del avance (R6). Es coordinación, no bloqueo.
- **El 45a bloquea al 45b** (que consume la costura de escritura y el modelo) **y al 45c** (que consume la API completa).

## Success Criteria

- [ ] TDD estricto: prueba en rojo antes del código en las seis rebanadas (`openspec/config.yaml` → `rules.apply.tdd: true`).
- [ ] `test_migration_institutional_plans.py` en verde: base desechable → `upgrade` al head anterior → siembra por SQL crudo con asyncpg → `upgrade 0028` → aserciones sobre `information_schema` (5 tablas, 5 únicos, el `CHECK`, los índices) → `downgrade` → las cinco tablas ausentes y las filas sembradas intactas.
- [ ] **Equivalencia de DDL** en verde: `pg_get_indexdef` y `pg_get_constraintdef` idénticos entre una base construida con `alembic upgrade head` y otra con `CREATE EXTENSION pg_trgm` → `import app.db_init` → `Base.metadata.create_all`.
- [ ] **Roll-up cruzado** contra PostgreSQL real: una actividad con dos tareas `primary` en **dos proyectos distintos con boards de columnas distintas** reporta el avance correcto usando la última columna del board de *cada* tarea; los enlaces `contributes` no alteran la razón.
- [ ] **`null ≠ 0`**: una actividad sin enlaces `primary` responde `calculated_progress: null`; una con enlaces y ninguna tarea terminada responde `0`.
- [ ] **Aislamiento de tenant en toda lectura**: para cada uno de los 5 endpoints de lectura, un usuario de la organización B recibe 404 sobre un plan o una actividad de A, y ningún listado incluye filas de A.
- [ ] **RBAC**: los 5 endpoints de escritura responden 403 a `member` y `viewer`, y 200/204 a `admin` y `manager`.
- [ ] **Idempotencia**: dos `PUT` consecutivos del mismo `(activity, period)` dejan una sola fila; dos `POST` del mismo `(task, activity)` no crean duplicado; un enlace hacia la misma actividad rechaza por el `CHECK`.
- [ ] **Sin regresión** frente a la línea base **re-medida al iniciar cada rebanada** (no una cifra congelada: el 48 y el 44 agregan pruebas en paralelo), con `TEST_DATABASE_URL` configurada. Sin esa variable, `skip_no_db` salta cientos de pruebas y la corrida no sirve de referencia.
- [ ] `cd backend && TEST_DATABASE_URL=… .venv/bin/python -m pytest -q tests/test_migration_institutional_plans.py tests/test_plans_repository.py tests/test_plans_api.py tests/test_migrations_baseline.py`

## Carga de revisión

Estimado **≈ 2 200–2 300 líneas** (`additions + deletions`), de las cuales ≈ 900 son pruebas. Muy por encima del umbral por defecto de 400.

`400-line budget risk: **High**` · `Chained PRs recommended: **Yes**`

Estrategia `auto-chain` con **feature branch chain** sobre el tracker `feat/45a-planes-modelo-api`: A apunta al tracker y cada rebanada siguiente a la rama de la anterior. Presupuesto = estimación × 1,2 + ≈50 líneas de marcas de `tasks.md`, truncado a la centena.

| # | Rama | Contenido | ≈ líneas | Presupuesto | Reversa |
|---|---|---|---:|---:|---|
| **A** | `feat/45a-a-migracion` | Migración `0028` (5 tablas, índices, únicos, `CHECK`) + espejo en `__table_args__` + prueba de migración con `downgrade` y equivalencia de DDL | ~390 | **500** | `alembic downgrade -1` + revert; cero tablas preexistentes tocadas |
| **B** | `feat/45a-b-modelos` | 5 modelos + `schemas.py` + import en `db_init` + `include_router` vacío en `main.py` | ~330 | **400** | revert; las tablas quedan sin mapeo ORM |
| **C** | `feat/45a-c-repositorio` | Repositorio: lecturas con tenant por `JOIN`, roll-up cruzado, upsert idempotente de planes/actividades (D10), CRUD de reportes y enlaces + pruebas contra PostgreSQL real | ~410 | **500** | revert; el modelo permanece |
| **D** | `feat/45a-d-servicio` | Servicio + `activity_key` derivado + doble avance con `null ≠ 0` + vocabularios (D12) + `resolution='manual'` (D14) + pruebas con fakes | ~330 | **400** | revert; el repositorio permanece |
| **E** | `feat/45a-e-api-lectura` | Los 5 `GET` + orden de declaración de rutas + paginación + pruebas de endpoints y de aislamiento de tenant | ~390 | **500** | revert; 45b sigue desbloqueado (consume repositorio y servicio, no HTTP) |
| **F** | `feat/45a-f-api-escritura` | `PUT` de reporte + `POST`/`DELETE` de los dos tipos de enlace + `require_role` singleton + pruebas de RBAC e idempotencia | ~380 | **500** | revert; la lectura permanece y el 45c puede empezar por la vista de solo lectura |

**Contingencia prevista** (patrón de la rebanada C del 43): si F desborda, se parte en **F1** (reporte del periodo + enlace tarea ↔ actividad, que es la escritura que el 45c necesita) y **F2** (enlaces actividad ↔ actividad manuales, cuyo productor real es el importador del 45b). F2 puede posponerse sin bloquear a 45b ni a 45c.

El pronóstico formal (`Decision needed before apply`, `Chained PRs recommended`, `400-line budget risk`) lo emite `sdd-tasks`.

## Proposal question round

Esta fase no pudo abrir una ronda de preguntas interactiva con el usuario. Las siguientes cinco preguntas **de producto** mejorarían el PRD; ninguna bloquea `sdd-spec` ni `sdd-design`, porque cada una lleva el supuesto con el que el 45a avanza si no se responde.

| # | Pregunta | Supuesto vigente si no hay respuesta |
|---|---|---|
| 1 | ¿El reporte cuatrimestral que guarda Command es el **borrador de trabajo** del responsable o el **valor oficial** que se copia al formato del SIG/PAI? | Borrador de trabajo: se guarda el último valor por periodo, con `created_by`/`updated_by` de `AuditMixin`, **sin** versionado ni firma. Si fuera el valor oficial, haría falta historial del reporte |
| 2 | Cuando el avance **calculado** y el **reportado** difieren, ¿cuál manda en la conversación con Planeación o Control Interno, y debe Command **señalar** la discrepancia? | Ninguno manda: se muestran los dos, sin alerta ni umbral. Una regla de discrepancia sería un requisito nuevo (¿qué diferencia es tolerable?) |
| 3 | ¿Una misma tarea puede ser `primary` de **más de una actividad**? | Sí: el modelo lo permite (el único es `(task_id, plan_activity_id)`) y los documentos lo exigen para `contributes`. Si el negocio dice que dos actividades no pueden apoyarse en la misma tarea como evidencia principal, hay que restringirlo **antes** de la migración |
| 4 | ¿Command debe guardar también las actividades **ajenas** (≈ 99 del PAI de otras dependencias, acciones del PTR de otras áreas) o solo las propias? | Se guardan todas las de los planes importados, con `is_mine` para distinguirlas; la vista filtra por `is_mine=true` por defecto. Guardar solo las propias abarataría el 45b pero rompería el enlace PTR → PSPI cuando la actividad destino no sea propia |
| 5 | ¿PSPI y PTR se reportan con el **mismo ritmo cuatrimestral** del PAI, o tienen su propio corte (mensual, anual, por fecha fin)? | Mismo vocabulario `I`/`II`/`III` más `ANUAL` para los planes que solo cierran una vez. Un ritmo distinto por tipo de plan cambiaría el vocabulario de `period` y la forma de la vista |

## Preguntas abiertas

**Ninguna que bloquee.** Las siete de la exploración (P1–P7) quedaron resueltas o asignadas a su cambio propietario. Se registra un único punto que **requiere ratificación del orquestador antes de `sdd-spec`**:

- **D13 — el menú «Planes»**: la propuesta lo difiere al 45c en lugar de sembrarlo en el 45a, porque `_ensure_menus` siembra globalmente en cada arranque y el enlace apuntaría a una ruta inexistente hasta el 45c. Es la única divergencia frente al alcance dictado. Si el orquestador prefiere sembrarlo en el 45a, la entrada entra en la rebanada F con `order=7` y suma ≈35 líneas a su presupuesto.

## Referencias

- `openspec/changes/45a-planes-modelo-api/exploration.md` — exploración compartida del 45, con las decisiones del orquestador del 2026-08-26.
- `agents/rules/solercia-persistence.md:41-45` — repositorios sin commit, `organization_id` obligatorio en toda lectura y escritura, JSONB y SQL textual confinados al adaptador.
- `docs/adr/0009-solercia-command-connect-data-conventions.md:78-80,238-240` — frontera Command / Security (D5).
- `docs/decisions/2026-08-23-solercia-platform-decisions.md` — §6.5 (tenant en toda lectura y escritura), §7 (columnas semánticas en `lower_snake_case`).
- `openspec/specs/project-hierarchy/spec.md:111-137` — requisito de roll-up que el 45a **no** modifica.
- `openspec/specs/{tasks,multi-tenancy,api-conventions,boards,rbac-catalog}/spec.md` — línea base que el 45a cumple.
- `openspec/changes/43-tareas-origen-externo/` — precedentes D-B (equivalencia de DDL), D-D (el repositorio es el puerto del agregado), D-G (la costura de escritura se implementa donde nace el modelo).
- `openspec/changes/44-importar-checklist-xlsx/exploration.md:166,220` — `board_columns.excluded_from_progress` y las **dos** migraciones que el 44 reclama, `0026` (`board_columns`) y `0027` (`tasks`) (R2, R6).
- `backend/app/modules/projects/repository.py:290-347` — roll-up vigente que el 45a **generaliza**, no reutiliza.
- `backend/app/db_init.py:129-163,431-482` — semilla de menús que solo inserta lo faltante (D13).
