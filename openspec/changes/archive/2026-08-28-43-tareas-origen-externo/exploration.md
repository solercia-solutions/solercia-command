# Exploración — 43-tareas-origen-externo

> Fase `explore` (SDD). Artefacto canónico persistido en Engram (`sdd/43-tareas-origen-externo/explore`, #3719) y volcado a disco por el orquestador el 2026-08-26. Referencias a código con `ruta:línea` verificadas sobre el commit `c1b9799`.

## 1. Estado actual

### 1.1 Modelo `Task` — `backend/app/modules/tasks/models.py`
- Mixins: `PkMixin` (UUID app-side), `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin` (:39).
- `__table_args__` (:43-58): SOLO dos índices GIN trigram (`ix_tasks_title_trgm`, `ix_tasks_description_trgm`). CERO restricciones únicas hoy.
- `organization_id` NO existe: tenant transitivo por `project_id` (join a `Project`), documentado en el docstring del módulo (:1-8) y del repositorio (:1-5).
- `project_id` FK CASCADE NOT NULL indexada (:60-65). `parent_task_id` FK autorreferencial SET NULL nullable, sin índice (:72-76).
- `status`: `String(60)` NOT NULL, SIN enum, validado en servicio contra `allowed_statuses()` de la strategy (:96-98). `task_type`: `String(40)` libre (:92-95). `priority`: `SAEnum(Priority, native_enum=False, length=20)` (:99-103).
- Soft delete: `is_active` + `deleted_at` (`shared/base_model.py:36-47`). Auditoría: `created_by`/`updated_by` FK nullable SET NULL (`base_model.py:61-83`).
- `task_number`: Integer nullable indexado, asignado por `UPDATE ... RETURNING projects.task_counter` (:140-143).
- `is_context` NO es columna: campo transitorio de `TaskRead` (schemas.py:153) calculado en `_to_read`. El 44 lo necesitaría como columna real.

### 1.2 Esquemas — `backend/app/modules/tasks/schemas.py`
- `TaskCreate` (:13-59) y `TaskUpdate` (:62-92) sin `source`/`external_key`. `model_dump(exclude_unset=True)` en service.py:422 distingue ausente de `None` explícito.
- `TaskRead` (:95-153) con `ConfigDict(from_attributes=True)`. CLAVE: `TaskService._to_read` (service.py:954-969) usa `TaskRead.model_validate(task)` sin mapeo manual, igual que `DashboardService._to_read` (dashboard/service.py:469-473). Agregar campos al esquema los expone en TODOS los consumidores con cero cambios de servicio.
- No existe clase `TaskFilters`: los filtros son `Query` sueltos en el router.

### 1.3 Listado y filtros
Cadena de 3 saltos por filtro: `router.py:44-121` (`Query(default=None, description=...)`) → `service.py:67-156` (reenvía kwargs) → `repository.py:42-125` (`stmt = stmt.where(...)`).
Filtros vigentes: `sprint_id`, `status`, `assignee_id`, `parent_task_id`, `task_type`, `label_ids` (OR + distinct), `priority`, `due_from`/`due_to` (`func.date`), `q` (ILIKE), `subtasks_only`, `top_level_only`.
Paginación: `shared/pagination.py`; `PaginationParams.requested` True solo con `page` o `sort` (:39-48); sin eso, orden `Task.order asc, created_at asc` (repository.py:122). `SORTABLE_FIELDS` (repository.py:26-33): order, title, status, priority, due_date, created_at.
Lecturas puntuales: `get`, `get_by_ids`, `get_by_project_and_number`, `list_for_org`. NO existe búsqueda por clave externa.

### 1.4 Creación/actualización y precedente `intake`
- `create_task` (service.py:252-335): valida jerarquía, resuelve status+columna desde strategy, valida estimación, verifica assignee/sprint, asigna `task_number` atómico, persiste. NO existe upsert; toda creación es INSERT nuevo.
- `update_task` (service.py:396-508): snapshot pre-mutación de `_HISTORY_TRACKED_FIELDS` (status, assignee_id, estimation_points, estimation_hours, sprint_id, priority — :387-394) → diff → `record_task_history` ANTES de `repo.save()`, misma transacción.
- `TaskUpdate` NO acepta `project_id` y el servicio nunca lo reasigna: HOY UNA TAREA NO PUEDE MOVERSE ENTRE PROYECTOS POR LA API. `PATCH /projects/{id}/parent` (projects/router.py:128) reparenta PROYECTOS, no tareas.
- Precedente `intake` (`intake/models.py:39-71`): `IntakeItem.source_provider: String(50)` indexado, `external_id: String(255)` indexado, `UNIQUE(organization_id, connector_id, external_id)`. Al convertir a tarea (`intake/service.py:560-580`) NO ancla nada: solo `item.created_task_id = task.id` y la línea de texto `f"Origen: {item.source_provider} — {item.origin_actor}"` (:177-185). Trazabilidad hoy = texto libre + FK inversa.

### 1.5 Convenciones Alembic
- `backend/alembic/versions/`, 24 archivos, `00NN_verbo_sustantivo.py`; docstring repite el nombre. `revision`/`down_revision` string; sin `branch_labels`/`depends_on`.
- CABEZA REAL EN DISCO: `0024` (`0024_add_work_calendar.py:38-39`, `down_revision="0023"`). Siguiente libre: **0025**.
- Patrón aditivo canónico: `0022_add_project_kind.py` (docstring que cita el cambio, `op.add_column`, `server_default` solo si NOT NULL y luego `alter_column(server_default=None)`).
- NO hay `batch_alter_table` en ningún archivo: PostgreSQL exclusivo.
- Índices únicos parciales ya establecidos: `0017:58-63` (`uq_users_numero_documento ... postgresql_where`), `0018:89-101` (dos parciales complementarios), `0023:416-421`.
- REGLA DURA: el índice parcial debe declararse TAMBIÉN en el modelo ORM (`users/models.py:30-38`, `org_role_templates/models.py:36-51` lo dicen explícitamente) porque el harness construye el esquema con `Base.metadata.create_all` (`tests/conftest.py:43-84`), no con Alembic.
- GATE AUTOMÁTICO: `tests/test_migrations_baseline.py:192-214` (`test_alembic_check_reports_no_diff_after_upgrade`) corre `alembic check` y falla ante cualquier diff modelo↔migración. Los parciales de 0017/0018 ya lo pasan.
- Pruebas de migración aisladas: patrón literal `test_migration_project_kind.py:73-244` (base desechable, upgrade a head-1, siembra por SQL crudo con asyncpg, upgrade, aserciones sobre information_schema, downgrade, aserción de no pérdida de filas).

### 1.6 Vocabulario de proveedores
`Connector.provider` = `String(50)` indexado con comentario normativo «deliberately NOT a PG enum» (`connectors/models.py:50-53`). Valores reales: `microsoft365` (microsoft365/adapter.py:35), `google` (:33), `jira` (jira/adapter.py:208), `glpi` (:305), `mcp` (:20), `fake` (fake.py:115). `shared/enums.py` NO tiene enum de proveedor. Planner NO es proveedor: se lee vía `microsoft365` + `Capability.external_tasks`.

### 1.7 Frontend
- `frontend/src/entities/workspace/workspace.model.ts:9-38` — interfaz `Task`, casi todo opcional (`task_key?`, `is_context?`). Punto de extensión.
- `frontend/src/entities/task/task-detail.model.ts:4-9` — `TaskDetail extends Task`, hereda gratis.
- `frontend/src/widgets/task-modal/task-modal.component.ts` — único modal. No existe `entities/task/task.model.ts`.

### 1.8 Pruebas
`test_tasks_crud.py`, `test_tasks_pagination.py`, `test_task_filters.py`, `test_task_key.py`, `test_task_hierarchy.py`, `test_task_detail_enrichment.py`, `test_task_links.py`, `test_task_reorder.py`, `test_task_sprint_closed_guard.py`. Estilo (`test_task_filters.py:1-59`): helpers `_auth`, `_create_project`, `_create_task`; API real vía httpx in-process; `@skip_no_db` + `@pytest.mark.asyncio(loop_scope="session")`. Fixtures conftest: `engine` (create_all + CREATE EXTENSION pg_trgm), `session` (SAVEPOINT, resiste commits), `client`, `tenant`, `user`. Línea base: 1411 passed / 3 failed preexistentes (`test_adapter_microsoft365.py`, reloj).

## 2. Áreas afectadas
- CREAR `backend/alembic/versions/0025_add_task_external_origin.py`
- `backend/app/modules/tasks/models.py` — 2 columnas + Index + CheckConstraint en `__table_args__` (obligatorio para create_all y alembic check)
- `backend/app/modules/tasks/schemas.py` — `TaskRead.source`, `TaskRead.external_key`. NO tocar TaskCreate/TaskUpdate
- `backend/app/modules/tasks/repository.py` — filtros + `get_by_external_key(organization_id, source, external_key)`
- `backend/app/modules/tasks/service.py` — paso de filtros + seam
- `backend/app/modules/tasks/router.py` — 2 Query
- `frontend/src/entities/workspace/workspace.model.ts` — 2 campos opcionales
- CREAR `backend/tests/test_migration_task_external_origin.py`, `backend/tests/test_tasks_external_origin.py`
- CREAR delta `openspec/changes/43-tareas-origen-externo/specs/tasks/spec.md`
- REANCLAR `openspec/changes/40-jira-import-usuario/{design,tasks}.md` y `specs/tasks/spec.md`
Sin impacto: boards, sprints, methodology, labels, checklists, task_links, activity, dashboard.

## 3. Unicidad — análisis

### 3.1 NULL en PostgreSQL
UNIQUE plana no impide duplicados manuales (cada NULL es distinto) pero paga índice sobre el 100 % de las filas. Peor: deja agujero silencioso — `(P, NULL, 'T-05')` duplicado NO colisiona porque el NULL en `source` vuelve distintas las filas.

### 3.2 Opciones
A. UniqueConstraint plana — indexa todo, no cierra el agujero, incoherente con 0017/0018. Bajo.
B. Índice parcial `WHERE external_key IS NOT NULL` (lo que fijó el 40) — deja abierto `(P, NULL, 'T-05')`. Bajo.
C. RECOMENDADA: índice parcial `WHERE source IS NOT NULL AND external_key IS NOT NULL` + `CHECK (external_key IS NULL OR source IS NOT NULL)` — cierra el agujero, permite procedencia sin ancla. Bajo.
D. CHECK de par estricto `(source IS NULL) = (external_key IS NULL)` — prohíbe procedencia sin clave estable. Bajo.
=> **C**.

### 3.3 ¿Por proyecto o por organización?
Hechos: (1) tasks sin organization_id; (2) denormalizar está PROHIBIDO por ADR/42 y por D2 del 40 (40/design.md:26-31); (3) PostgreSQL no puede expresar UNIQUE a través de un JOIN; (4) hoy una tarea NO puede moverse entre proyectos por la API (verificado: `TaskUpdate` sin project_id, 29 apariciones de project_id en service.py, ninguna es escritura).
Opciones: A solo por proyecto | B denormalizar (prohibido) | C tabla puente `task_external_anchors` (desproporcionado) | D trigger/EXCLUDE (PostgreSQL no admite subconsultas; lógica escondida en el motor) | **E RECOMENDADA**: garantía dura por proyecto en BD + búsqueda org-wide en el repositorio antes de insertar.
Entrega de E: `uq_tasks_project_source_external_key (project_id, source, external_key)` parcial + `TaskRepository.get_by_external_key(organization_id, source, external_key)` (JOIN Project + filtro organization_id) — ES EL SEAM QUE 44 Y 47 NECESITAN — + índice de apoyo NO único `ix_tasks_source_external_key (source, external_key) WHERE external_key IS NOT NULL` (el único tiene project_id como columna líder y NO sirve a la búsqueda org-wide).
Limitación conocida a documentar: el motor garantiza unicidad por proyecto; la org-wide la garantiza el servicio.

## 4. Vocabulario de `source`
TIPO RECOMENDADO: `String(50)` libre validado en servicio contra whitelist, NUNCA SAEnum. Precedentes: `connectors.provider` String(50) «deliberately NOT a PG enum», `intake_items.source_provider` String(50), `tasks.status` String(60) validado por strategy, `tasks.task_type` String(40) libre. Un SAEnum obligaría a migración por proveedor.
DISCREPANCIA: `40/tasks.md:64` fija `VARCHAR(20)`. Recomiendo String(50) y realinear el 40.
`external_key`: `String(255)` = `intake_items.external_id` (el 47 copia ese valor literal).
VALORES: `checklist_xlsx` (44), `microsoft365` (47, cubre correo/calendario/Planner), `google`, `jira` (40), `glpi`, `mcp`, `fake`.
REGLA: cuando el origen es conector, `tasks.source` DEBE ser exactamente `connector.provider` (= `intake_items.source_provider`).
`planner`: NO agregarlo (crearía vocabulario paralelo; la distinción por capacidad ya vive en `intake_items.item_type`).
`manual`: NO usar centinela; tarea manual deja ambas en NULL (evita retrollenado, respeta la semántica del índice parcial, no mete valor falso en el espacio de claves).

## 5. Exposición
5.1 Lectura: `TaskRead.source`/`external_key` como `str | None = None`. Gratis por `model_validate` + `from_attributes`.
5.2 Filtros `?source=&external_key=` de igualdad exacta, componibles. 3 puntos de edición, ~30 líneas. NO agregarlos a `SORTABLE_FIELDS`.
5.3 Endpoint dedicado: RECOMENDADO DIFERIR. 44 y 47 son importadores de backend que llaman al repositorio, no a HTTP. Si `propose` lo incluye: `GET /tasks/by-external-key?source=&external_key=` con QUERY params (nunca path: el `internetMessageId` de Outlook tiene forma `<...@...>` y admite `/`), declarado ANTES de `/tasks/{task_id}` (misma nota que router.py:147-149).
5.4 INMUTABILIDAD: `source`/`external_key` NO entran en TaskCreate ni TaskUpdate. (a) Seguridad: un cliente podría pre-crear `T-05` y secuestrar la fila del importador; (b) un PATCH que viole el único daría IntegrityError → 500 (update_task no lo captura); (c) la regla de persistencia prohíbe controladores genéricos para recursos de tenant. Los importadores escriben el ancla en su propio servicio, como `intake` escribe `created_task_id`. Corrección posterior = operación de mantenimiento (`backend/app/maintenance/` del 42).
5.5 Auditoría: NO agregar a `_HISTORY_TRACKED_FIELDS` (campos inmutables → diff siempre vacío).

## 6. Reanclaje del 40 (planificado, sin aplicar)
Sin reanclar habría DOBLE migración de `tasks.source`/`external_key` y fallo duro en `op.add_column`.
- `40/tasks.md:59` (0.4): head ya no es 0021 sino 0024; tras el 43 será 0025.
- `40/tasks.md:60` (0.5): próximo libre no es 0022 sino el siguiente consecutivo libre en el momento del apply del 40, verificado entonces con `alembic heads` y con los cambios pendientes (hoy sería 0029 si el 44 y el 45a aterrizan antes). SIN NÚMERO RESERVADO.
- `40/tasks.md:64` (1.1): renombrar a `00NN_add_external_anchor_projects_sprints.py` (`00NN` = consecutivo libre resuelto en el apply del 40); ELIMINAR `tasks` y `uq_tasks_project_source_external_key`; alinear `source` a String(50).
- `40/tasks.md:65` (1.2): quitar `tasks/models.py` de la lista.
- `40/tasks.md:66` (1.3): `test_external_anchor_migration.py` pierde las aserciones sobre tasks.
- `40/tasks.md:68-69` (1.5, 1.6): TaskRead ya expone los campos → pasan de RED/GREEN a verificación.
- `40/tasks.md:47` (fila U1) y `:72` (Commit 1): reducir alcance/mensaje a projects+sprints; restar ~40-60 líneas.
- `40/design.md:26-31` (D2): marcar la fila de `tasks` como entregada por el 43.
- `40/design.md:75-76`: `app/modules/{projects,sprints}/models.py`; migración `00NN_...` (consecutivo libre resuelto en el apply del 40).
- `40/design.md:116-121`: down_revision real y alcance de dos tablas.
- `40/specs/tasks/spec.md:10-22`: MOVER al 43 «Ancla de procedencia externa». Sin esto `sdd-archive` fusionaría el requisito dos veces.
- `40/specs/tasks/spec.md:33-40`: «Clave local y externa conviven» → también al 43 (es exposición).
- `40/specs/tasks/spec.md:24-31`: «Reconciliación idempotente» SE QUEDA en el 40 (comportamiento del importador).
- BRECHA: el texto de spec del 40 promete unicidad org-wide mientras su D2 implementa por proyecto. El 43 debe explicitar qué garantiza el motor y qué el servicio.

## 7. Frontend
RECOMENDADO: en el 43, SOLO el tipo (`source?: string | null`, `external_key?: string | null` en workspace.model.ts). Insignia DIFERIDA al 44: (1) tras el 43 no hay una sola tarea anclada (el 42 dejó 0 tareas) → interfaz muerta imposible de verificar; (2) el 44 sabe cómo etiquetarla («Checklist T-05» vs «checklist_xlsx / T-05»); (3) tocar task-modal obliga a la pasada de `ux-psicologia` sobre un componente que no gana información. Si se incluye igual: insignia de solo lectura junto al `task_key`, visible solo si `external_key` no es nulo, con aria-label del sistema de origen.

## 8. Pruebas propuestas
- `test_migration_task_external_origin.py` (patrón `test_migration_project_kind.py:73-244`): base desechable, upgrade 0024, siembra SQL cruda, upgrade 0025, aserciones information_schema (columnas presentes, is_nullable='YES', fila intacta con ambas NULL), downgrade 0024, columnas ausentes y fila viva. Misma base: unicidad — dos `(P,'checklist_xlsx','T-05')` → UniqueViolation; N `(P,NULL,NULL)` sin conflicto; misma clave en proyectos distintos sin conflicto; `(P,NULL,'T-05')` → violación del CHECK.
- `test_tasks_external_origin.py` (patrón `test_task_filters.py:1-59`): POST expone ambos null; TaskCreate con external_key no lo persiste; PATCH tampoco; filtros `?source=`/`?external_key=` componen con `?status=`; `get_by_external_key` no cruza organizaciones.
- `test_migrations_baseline.py` sin cambios pero ES EL GATE (`alembic check`).
Comando: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@127.0.0.1:5434/solercia_test .venv/bin/python -m pytest -q tests/test_migration_task_external_origin.py tests/test_tasks_external_origin.py tests/test_migrations_baseline.py`

## 9. Estimación
0025 migración 70-85 | models.py 25-35 | schemas.py 8-12 | repository.py 40-55 | service.py 25-35 | router.py 12-18 | frontend 6-8 | test migración 190-230 | test API 230-280 | delta spec 70-90. TOTAL ≈ 680-850.
400-line budget risk: **High**. 2 rebanadas encadenadas:
- A (~330-380): migración + `__table_args__` + TaskRead + test de migración. Rollback: `alembic downgrade -1` + revert; cero filas afectadas.
- B (~350-450): `get_by_external_key` + filtros + tipo frontend + test API. Rollback: revert; las columnas siguen para 44/47.
El reanclaje del 40 es edición OpenSpec: no cuenta contra el presupuesto pero DEBE ser unidad de trabajo explícita.

## 10. Riesgos
R1 colisión de migraciones con el 40 → §6 como unidad de trabajo verificable.
R2 `alembic check` falla si modelo y migración divergen → declarar el índice en `__table_args__` con el mismo `postgresql_where` (patrón users/models.py:30-38).
R3 el harness usa create_all, no Alembic → misma mitigación que R2.
R4 `external_key` 255 puede truncar un internetMessageId largo → alinear con intake_items.external_id; verificación real es tarea del 47.
R5 la unicidad org-wide es de aplicación, no de motor → documentar como limitación y obligar a 44/47 a pasar por `get_by_external_key`.
R6 duplicación de requisitos al archivar 40 y 43 → repartición explícita antes de sdd-archive.
R7 el 44 necesita `is_context` y `merge_into` como datos reales; hoy `is_context` es transitorio → FUERA del 43, pero `propose` debe declararlo para que el 44 no lo asuma entregado.

## 11. Preguntas abiertas (con recomendación)
Q1 ¿unicidad org-wide en motor o en servicio? → SERVICIO (§3.3 opción E).
Q2 ¿CHECK de par estricto o «clave exige origen»? → «clave exige origen».
Q3 ¿String(50) o VARCHAR(20)? → String(50); realinear el 40.
Q4 ¿centinela 'manual' o NULL? → NULL.
Q5 ¿endpoint by-external-key en el 43? → diferir; si se incluye, query params.
Q6 ¿insignia en el frontend? → diferir al 44; el 43 aporta solo el tipo.
Q7 ¿el 43 asume el requisito de spec del 40? → sí, junto con «clave local y externa conviven»; el 40 conserva «reconciliación idempotente».
Q8 ¿el reanclaje del 40 dentro del 43 o aparte? → dentro del 43, como unidad de artefactos.
Q9 ¿source/external_key en task_history? → no.
Bloqueantes de diseño si se resuelven en contra: Q1, Q2, Q7.

### Decisiones del orquestador (2026-08-26, autonomía delegada por el usuario)
Se adoptan las nueve recomendaciones tal cual: Q1 servicio (opción E), Q2 «clave exige origen» (opción C), Q3 `String(50)`, Q4 NULL sin centinela, Q5 endpoint dedicado diferido (solo filtros), Q6 insignia diferida al 44 (solo tipo), Q7 el 43 asume «Ancla de procedencia externa» y «Clave local y externa conviven» (el 40 conserva «Reconciliación idempotente»), Q8 reanclaje del 40 dentro del 43 como unidad de artefactos, Q9 sin `task_history`.

## 12. Recomendación
Cambio estrictamente aditivo de dos rebanadas:
1. `0025_add_task_external_origin` (down_revision "0024"): `tasks.source VARCHAR(50) NULL`, `tasks.external_key VARCHAR(255) NULL`, CHECK `ck_tasks_external_key_requires_source`, único parcial `uq_tasks_project_source_external_key (project_id, source, external_key) WHERE source IS NOT NULL AND external_key IS NOT NULL`, apoyo `ix_tasks_source_external_key (source, external_key) WHERE external_key IS NOT NULL`; todo espejado en `Task.__table_args__`.
2. Exposición de solo lectura + filtros `?source=`/`?external_key=` + seam `get_by_external_key` (el contrato real que consumen 44 y 47).
3. Inmutabilidad por API.
4. Vocabulario `source` = `connector.provider` + `checklist_xlsx`; `manual` no es valor, es NULL.
5. Reanclaje documentado del 40.
Listo para `propose`: SÍ, con las 9 preguntas resueltas por el orquestador.

## Referencias
`agents/rules/solercia-persistence.md` (repositorios sin commit, tenant obligatorio, sin controladores genéricos, SQL en adaptadores) · `docs/decisions/2026-08-23-solercia-platform-decisions.md` §5.5 (idempotencia obligatoria en ingestión), §5.4 (identificadores de proveedor opacos calificados por fuente), §6.5 (tenant en toda lectura/escritura), §7 (columnas semánticas lower_snake_case) · `openspec/specs/tasks/spec.md` · `openspec/specs/intake-items/spec.md` · `openspec/changes/40-jira-import-usuario/{design,tasks}.md` · `openspec/changes/42-purga-datos-demo/state.yaml:55,88` (el 42 excluye tasks.source/external_key y declara que bloquea al 43).
