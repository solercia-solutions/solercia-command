# Planes institucionales y reestructuración de organizaciones — ODD

## Objetivo
Separar tenants (SDMujer, IDARTES, Solercia personal), dejar el SGSI como proyecto y construir los planes institucionales transversales (Decreto 612 / MIPG): un plan agrupa actividades y cada actividad se sustenta en tareas de cualquier proyecto de la organización (M:N).

## Por qué
Una tarea vive en un solo proyecto. Si los planes fueran proyectos, una tarea del SGSI no podría aportar al Plan de Seguridad, al Plan de Tratamiento de Riesgos y al PETI a la vez. Los jefes necesitan ver el avance por plan.

## Alcance autorizado (2026-09-30)
- Implementar el cambio `openspec/changes/45a-planes-modelo-api` (backend: migración, modelos, repositorio, servicio, API). Sin UI ni menú (así lo fija 45a).
- Reestructurar datos reales: crear organizaciones SDMujer e IDARTES, proyecto SGSI, mover proyectos, conectores e intake a su tenant.

## Restricciones
- Migración de planes = `0027` (`down_revision="0026"`): el cambio 44 no reclamó `0027`.
- Pruebas SOLO contra un PostgreSQL desechable propio. Nunca contra el PG original (127.0.0.1:5434, `gestion_proyectos-postgres-1`) ni los volúmenes de recuperación.
- Sin commits: el índice tiene cambios ajenos preparados que se preservan.
- Respaldo lógico antes de cualquier escritura en la base real.
- TDD: desactivado (sin configuración de proyecto); pruebas funcionales por fase con pytest.

## Tareas
- [x] P1 Planes 45a fases 0–2: migración `0027` + 5 modelos con DDL equivalente.
- [x] P2 Planes 45a fases 3–5: vocabularios, esquemas, repositorio (roll-up cruzado entre proyectos), servicio.
- [x] P3 Planes 45a fases restantes: API `/plans` con permisos y pruebas.
- [x] O1 Respaldo lógico de la base original (post-0026): `pre-restructure-20260930171831.dump` en el directorio privado de respaldos, 46 tablas con datos en `pg_restore --list`, SHA-256 en `SHA256SUMS.pre-restructure`.
- [x] O2 Crear organizaciones SDMujer (`sdmujer`) e IDARTES (`idartes`) vía `OrganizationService.create_bootstrap` (Generales con 7 columnas, membresía admin).
- [x] O3 Decisión del usuario: SEGURIDAD → SGSI (conserva 7 estados), PANDORA al mismo nivel, SDMUJER desactivado (borrado lógico). Solercia Connect + cuenta SDMujer + 82 intake + 8 corridas + intake_settings → SDMujer; Jira + cuenta IDARTES → IDARTES; credenciales siguen a su cuenta. Roles RBAC (3), 20 menús por rol y rol ADMIN copiados a cada organización nueva. Invariantes anti-cruce dentro de la transacción.
- [x] O4 0027 aplicada en la original (2026-09-30). Verificación independiente previa: 63 passed en PG desechable nuevo (`127.0.0.1:55444`, eliminado). Clon: upgrade → downgrade → upgrade; original: upgrade. En ambos, la huella solo agrega 5 tablas vacías (`plans`, `plan_activities`, `plan_activity_reports`, `plan_activity_links`, `task_plan_activities`) y cambia `alembic_version`.
- [x] N1 45b: importadores PSPI/PTR (DOCX, stdlib) y PAI (XLSX, openpyxl) + enlaces actividad↔actividad (D6) + CLI `python -m scripts.import_plans` (simulación por defecto, `--apply` en una transacción). Enlazador tarea↔actividad fuera de alcance (0 tareas); `upsert_task_link` queda como costura. Pendiente: `--apply` en la base real (decisión del usuario).
- [x] N2 45c: vista «Planes» (solo lectura) en el frontend + menú «Planes» (orden 7; ADMIN `*`, MANAGER, MEMBER) + CLI `scripts.sync_menu_catalog` (simulación por defecto, `--apply` solo inserta). Pendiente: correr la CLI contra la base real (orquestador).
- [x] N3 Escritura en «Planes»: reporte de avance por actividad y periodo (`PUT .../reports/{period}`) y vincular/desvincular tareas de cualquier proyecto con rol principal/aporta (`POST/DELETE .../tasks`), solo para admin/manager de la organización activa (misma regla que `require_plans_write_role`). Selector de tareas sobre `GET /search?types=task` (ya es multiproyecto y por tenant; sin endpoint nuevo para candidatos). Único endpoint nuevo: `GET /plans/activities/conflict-counts` (lectura) para la insignia de conflictos en la lista. Vínculos actividad↔actividad siguen de solo lectura.
- [x] O5 El bootstrap de organizaciones crea, en la misma transacción, los roles ADMIN/MANAGER/MEMBER, sus menús (catálogo único `app/modules/roles/seed_catalog.py`, reexportado por `db_init`) y el rol ADMIN del creador.
- [x] J1 Alimentación Jira → `idartes` (herramienta + ensayo en clon; aplicación en la real pendiente del orquestador). `backend/app/modules/jira_import/{client,snapshot,adf,mapper,repository,apply,report}.py` + CLI `python -m scripts.import_jira` (`--fetch` a snapshot; simulación por defecto en transacción READ ONLY; `--apply` en una transacción). Decisiones de mapeo:
  - Alcance: todo proyecto con al menos un issue creado o actualizado desde 2026-01-01 (JQL por proyecto). Los padres fuera de la ventana se importan como contexto para no romper la jerarquía. Jira no tiene categorías de proyecto: no se crean áreas.
  - Metodología: `scrum` si el proyecto tiene tablero `scrum` o algún issue de la ventana referencia un sprint (los tableros `simple` de proyectos gestionados por el equipo también usan sprints); si no, `kanban`.
  - Columnas: las del tablero Jira (solo las que tienen estados), más los estados que usan los issues y el tablero no muestra, y las columnas de categoría «done» al final (Command toma la última columna como finalizada). Sin tablero: estados del proyecto ordenados por categoría. `status_key` = nombre de la columna.
  - Issues → tareas: `source='jira'`, `external_key`=clave, `task_number`=número Jira (la clave Command coincide con la de Jira), tipo (Epic/Historia/Tarea/Subtarea/Error → epic/story/task/subtask/bug), prioridad (Highest→critical), descripción ADF→Markdown, título >200 recortado con el título completo al inicio de la descripción, responsable, informador como `created_by`, fechas reales (creación, actualización, vencimiento y fecha de inicio a medianoche de Bogotá), `completed_at` = fecha de resolución solo en la última columna, puntos (Story Points / Story point estimate, redondeo hacia arriba; se descartan en kanban), sprint = último sprint del issue, padre.
  - Sprints: los referenciados por issues de la ventana y los del tablero activos, futuros o terminados desde 2026; future→draft, active→active, closed→closed con `closed_at` y puntos completados. Idempotencia por (proyecto, nombre).
  - Usuarios: solo cuentas `atlassian` (activas e inactivas; las `app` se omiten). Jira oculta el correo: marcador `jira-<accountId>@idartes.jira.example.org` (dominio reservado por IANA, sin buzón; `.invalid` rompe `EmailStr` de `UserRead`), sin contraseña (el inicio de sesión local se rechaza), `is_active` = estado en Jira, vínculo por `federated_identities` (provider `jira`, issuer `https://<sitio>`, subject `accountId`). La cuenta conectada del conector Jira (`jira-<accountId>`) se resuelve al usuario existente, que conserva su rol admin. Nuevos: membresía `member` + rol RBAC `MEMBER`. No se envían correos ni invitaciones.

## Evidencia
- Ensayo en copia desechable (`solercia-pg-mig0026-20260930125402`): scripts de pasos A (Python, bootstrap oficial) y B (SQL, una transacción) → resultado esperado; segunda corrida sin cambios de conteos (idempotente).
- Original (2026-09-30): mismo resultado; conteos por tabla idénticos al ensayo. Estado: `idartes` = GENERALES + jira (1 cuenta); `sdmujer` = GENERALES, PAN, SGSI, SDM (inactivo) + solercia_connect (1 cuenta, 82 intake); `solercia` = google, microsoft365, sin proyectos.
- Scripts en el scratchpad de la sesión: `create_orgs.py`, `restructure.sql`.
- P1–P3 (2026-09-30), observado contra un PostgreSQL desechable propio (`solercia-plans-testpg`, `127.0.0.1:55433`, tmpfs); nunca contra `5434`:
  - `alembic heads` (lectura de archivos): una sola cabeza `0026` antes del cambio; `0027_add_institutional_plans.py` (`down_revision="0026"`) queda como cabeza única.
  - P1: `test_migration_institutional_plans.py` + `test_migrations_baseline.py` → 9 passed (upgrade, downgrade sin perder filas, CHECK de autoenlace, único tarea↔actividad, equivalencia de DDL `create_all` ≡ `upgrade head`).
  - P2/P3: `test_plans_repository.py` 12 passed; `test_plans_service.py` 12 passed; `test_plans_endpoints.py` 27 passed (las cinco rutas de escritura responden 403 a `member` y `viewer`). Conjunto del cambio: 60 passed.
  - Otras pruebas de migración: `test_migration_project_is_system.py::test_single_revision_head` fijaba la cabeza en `0026` y se ajustó a «una sola cabeza». `test_migration_task_external_origin.py::test_anchor_objects_exist_by_name_in_both_schemas` falla igual sin `0027` (preexistente).
  - `ruff check`/`ruff format --check` limpios sobre el módulo y sus pruebas; `mypy app/modules/plans` sin errores.
  - No medida la línea base de la suite completa (fuera de alcance por restricción). Sin commits ni cambios al índice.

- N1/O5 (2026-09-30), PG desechable propio `solercia-45b-testpg` (`127.0.0.1:55466`, tmpfs); nunca `5434`:
  - Fuentes copiadas a `scratchpad/plan-sources/` con SHA-256 idéntico al original (`SHA256SUMS`). PAI autoritativo: «… Consolidado dependencias - CORREGIDO.xlsx» (docs/plans); candidatos comparados en `reports/pai-candidatos-comparacion.md`.
  - Simulación contra org sintética `sdmujer`: PSPI 25, PTR 26, PAI 11 actividades; 15 enlaces PTR→PSPI (12 `exact`, 3 `conflict` R17/R19/R20), 2 a revisión sin enlace (R26, R32); advertencias R31, R40, R43, 28≠29 y seguimiento PAI diligenciado (P2, no importado). La base quedó con 0 planes.
  - Pruebas: `test_plans_importers.py` 15, `test_plans_import_apply.py` 3, `test_organization_bootstrap_rbac.py` 2, `test_organization_bootstrap.py` 15; conjunto con planes/organizaciones/RBAC/menús: 119 passed. `ruff` limpio en archivos nuevos; `mypy` sin errores nuevos.

- Carga real (2026-10-01): verificación independiente previa 124 passed (PG desechable `127.0.0.1:55477`, eliminado); respaldo `pre-plans-import-*.dump` (51 tablas con datos). Tras un reinicio de Docker se recopiaron las fuentes y su SHA-256 coincidió con el registrado. Simulación contra la base real → 62 actividades nuevas; `--apply` → PSPI-2026 25, PTR-2026 26, PAI-2026 11 en `sdmujer`, 15 enlaces (3 `conflict`); segunda corrida `--apply` → 0 nuevas (idempotente). Ninguna otra organización tiene planes.

- N2 (2026-10-01), PG desechable propio `solercia-45c-testpg` (`127.0.0.1:55488`, tmpfs, eliminado al terminar); nunca `5434`:
  - `npx ng build` OK (chunk perezoso `plans-component` 30 kB); advertencia de presupuesto del bundle inicial (1,06 MB > 1 MB), no atribuible a este cambio (solo agrega una ruta y un alias de ícono al bundle inicial). `eslint` limpio en archivos nuevos.
  - Sin runner de pruebas de frontend en el proyecto: las funciones puras de `pages/plans/plans-view.ts` se verificaron con un script de aserciones en Node (`--experimental-strip-types`, scratchpad): periodo actual, `null` ≠ 0, promedios, agrupación, filtros.
  - Backend: menú/RBAC/sync + `test_plans_*` → 98 passed. `test_sync_menu_catalog.py` 5 passed (idempotencia, nunca actualiza ni borra, rol faltante se informa, simulación no escribe, `--database-url` obligatorio). Guardia 45a «sin menú ni ruta /plans» reemplazada por `test_menu_seed_plans.py`. `ruff` limpio.

- N2 en vivo (2026-10-01): verificación independiente 67 passed (PG desechable `127.0.0.1:55499`, eliminado). `sync_menu_catalog` contra la real: simulación → 1 menú «Planes» + 9 permisos (3 roles × 3 organizaciones); `--apply` → insertados; segunda corrida → «Sin cambios». Backend en host (uvicorn 127.0.0.1:8081, `STARTUP_PROFILE=local_restricted`, `WS_ENABLED=false`) + `ng serve` 4242. Playwright: IDARTES muestra el estado vacío; SDMujer muestra PAI 11 / PSPI 25 / PTR 26 con «Sin tareas vinculadas» y «Sin reporte» (III preseleccionado); el cajón de PTR-2026/R17 marca «Referencia en conflicto en la fuente» con el texto «4.5 (OM-03)»; la vista se adapta a 390 px. Corrección del orquestador: el encabezado de grupo duplicaba el número («11. 11. …») y mostraba «ALTO. Riesgos Altos»; ahora solo antepone códigos numéricos que el nombre no trae (`plans.component.ts` `groupTitle`).

- N3 (2026-10-01), PG desechable propio `solercia-A-testpg` (`127.0.0.1:55510`, tmpfs, eliminado al terminar); nunca `5434`:
  - Backend: `test_plans_*.py` → 71 passed (incluye `test_plans_conflict_counts.py` 3: ambos extremos, ruta literal antes de `{activity_id}`, aislamiento entre organizaciones). `ruff check`/`ruff format --check` limpios; `mypy app/modules/plans` sin errores.
  - Frontend: `npx ng build` OK (chunk `plans-component` 54,7 kB; advertencia previa del presupuesto inicial 1,06 MB, no atribuible). `eslint src/pages/plans src/entities/plan` limpio. Funciones puras nuevas (`previousPeriod`, `checkProgress`, `parseProgress`, `parseEvidence`, tri-estado, `defaultLinkRole`, `conflictIndex`) verificadas con aserciones en Node (scratchpad).
  - Sin prueba en vivo de escrituras (la base real no se toca); verificación visual pendiente.

- J1 (2026-10-01), PG desechables propios `solercia-C-clonepg` (`127.0.0.1:55530`, clon de `pre-sdm-idartes-feed-20261001065001.dump`) y `solercia-C-testpg` (`127.0.0.1:55531`); nunca `5434`:
  - Jira (solo GET): 34 proyectos visibles, 21 con actividad en 2026 (1746 issues + 10 padres de contexto), 172 cuentas (97 humanas: 43 activas, 54 inactivas; 75 de aplicación), 1 correo visible. Snapshot crudo en el scratchpad de la sesión (`jira-feed/raw`, archivos 0600).
  - Ensayo: simulación → 0 cambios en la base; `--apply` → 96 usuarios, 97 identidades, 96 membresías y roles MEMBER, 21 proyectos, 81 columnas, 100 sprints, 1756 tareas, 1431 padres; segundo `--apply` → 0 creados, 0 actualizados, conteos idénticos. Comprobaciones SQL: toda tarea en una columna de su tablero, `completed_at` solo en la última columna, clave = código-número, contador ≥ máximo. Humo de API en proceso (proyectos, tareas, tablero, sprints, miembros, `/admin/users`, ejecutivo, búsqueda) → 200; kanban responde 422 «no admite sprints» (esperado).
  - Pruebas: `test_jira_import_mapper.py` 14, `test_jira_import_client.py` 5, `test_jira_import_apply.py` 1 (PG) → 20 passed; `-k jira` → 100 passed, 5 skipped. `ruff` limpio.

- Aplicación real del orquestador (2026-10-01):
  - N3 (UI reportar/vincular): backend local reiniciado; `GET /plans/activities/conflict-counts` registrado; formulario de reporte visible en PTR-2026/R17 (sin escrituras de prueba en la base real).
  - B (SDMujer): verificación independiente 59 passed (PG desechable 55541). Respaldo `pre-sdm-idartes-feed-*.dump`. `import_sdm_tasks` con `--assignee-email/--actor-email admin@solercia.com` → 199 creadas (SGSI 102, GENERALES 63, PAN 34); reaplicación 199 sin cambios. `feed_plan_followup` → 4 reportes PAI (periodo II) + 49 enlaces (25 primary, 24 contributes; PSPI 42, PTR 7); reaplicación 0 escrituras. PSPI muestra 12 % calculado (25/25 actividades con tareas).
  - C (IDARTES Jira): verificación 20 passed (PG desechable 55551). Respaldo `pre-jira-*.dump`. `import_jira --from-snapshot` → 96 usuarios nuevos (+1 existente), 21 proyectos, 100 sprints, 1756 tareas; reaplicación 0 nuevos/0 actualizados.
  - Aislamiento: idartes 22 proyectos/1756 tareas/97 miembros/100 sprints; sdmujer 3/199/1/0 con 49 enlaces de plan; solercia vacía; 0 enlaces tarea↔actividad cruzando organización; solo 1 usuario con contraseña.

## Siguiente
- Revisar listas: 71 notas de tareas SDMujer (58 categorías sin regla → GENERALES), 26 de seguimiento, 3 conflictos PTR→PSPI, 2 referencias PTR sin enlace.
- Correos de relleno `@idartes.jira.example.org` de 96 usuarios Jira: el outbox debe omitir ese dominio antes de activar `EMAIL_ENABLED`.
- Confirmar con el usuario si PUAECD (proyecto del Jira de IDARTES) pertenece a IDARTES.
- La organización activa vuelve a IDARTES tras reiniciar el backend (revisar `ActiveOrgStore`/validación).
- PETI sin fuente localizada. Commits propuestos por los escritores sin ejecutar (índice con cambios ajenos).
