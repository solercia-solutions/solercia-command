# Resincronización SDMujer, filtro por año y páginas con la interfaz de PANDORA — ODD

## Objetivo

Que Command refleje el estado real del checklist de SDMujer, que las tareas de IDARTES se puedan
separar por año y que las páginas internas usen la misma interfaz de `pandora_front` que el shell.

## Problema y motivo

- La base tiene 199 tareas de SDMujer (respaldo del 1-oct 07:20); la carpeta va en T-205 y tiene
  24 tareas con diferencias de descripción, prioridad o estado.
- IDARTES se importó con `created >= 2026 OR updated >= 2026`: conviven issues de años anteriores y
  ni la API ni la UI filtran por año.
- El shell ya está alineado con PANDORA (`odd/tasks/ui-shell-pandora.md`), pero las páginas
  internas conservan el estilo anterior.

## Alcance autorizado

Autorizado por el usuario el 2026-10-04: «Sí, continuemos y por favor renueva también la UI con la
misma interfaz de pandora-front». Orden acordado: resincronización y filtro por año primero; el
clasificador/conciliación de correo después (fuera de este documento).

## Restricciones

- Rama `feat/ui-shell-pandora`. Commits por unidad de trabajo, sin atribución a herramientas, sin push.
- Escritura en la base real solo con confirmación explícita del comando exacto.
- Solo se enciende el contenedor `postgres` del compose (el backend tiene scheduler de correo saliente).
- Persistencia: leer `agents/rules/solercia-persistence.md` antes de tocar repositorios.
- Textos de interfaz en español colombiano con tuteo. Lista de UX antes de cerrar cada pantalla.

## Modo de pruebas

- Backend: TDD estricto (`openspec/config.yaml`, `rules.apply.tdd`). Runner:
  `cd backend && pytest tests/<archivo> -v`, solo las pruebas del cambio, contra base de pruebas.
- Frontend: sin runner; `npm run build`, `npm run lint` y navegador.

## Entrega

Estrategia `ask-on-risk`. Pronóstico > 400 líneas por las páginas; cada página es una rebanada.

## Tareas

- [x] S01 Resincronizar SDMujer: simulación (6 nuevas, 24 con diferencias, 175 sin cambios) y
      aplicación con `--apply --update-existing`, confirmada por el usuario el 2026-10-04.
- [x] S02 Backend: filtro `year` (año de `created_at`) en `GET /projects/{id}/tasks` (TDD).
      Más `GET /projects/{id}/tasks/years`. Commit `fc915ab`.
- [x] S03 Frontend: `year` en `TaskQuery` y `sol-select` «Año» en el workspace del proyecto,
      con periodos reales (patrón «Periodo» de la telemetría de PANDORA). Commit `8f7b954`.
- [x] S04 `/projects/:id` (workspace): barra de filtros y grid a `sol-data-table` paginada (L).
      Commit `064204b`.
- [x] S05 `/projects`: encabezado `h1.sol-display`, filtros en `sol-card` (M). Backend `d320782`,
      `353c760`, `0d2a1f5`; frontend `31fac20`.
- [ ] S06 `/task/:key` y `sol-task-detail-panel`: patrón de perfil de PANDORA (M).
- [ ] S07 `/plans`: `sol-drawer` + `sol-form-field`, menos Tailwind (L).
- [ ] S08 `/admin/*`: acciones al inicio, paginación, toolbar, `sol-drawer` (5 × S).
- [ ] S09 `/teams`, `/performance`, `/executive`, `/connections`, `/tasks/import`, `/hierarchy`.

Referencia de patrones PANDORA (solo lectura, `IDARTES/pandora_proxy/pandora_front`):
listado `pages/administrador/usuarios/gestion-usuarios/ui/gestion-usuarios-page.component.ts`;
periodo `pages/administrador/telemetria/ui/telemetria-uso-page.component.ts`;
formulario `.../gestion-usuarios/ui/usuario-form-modal.component.ts`; detalle
`pages/perfil/ui/perfil-page.component.ts`.

## Progreso y evidencia

- 2026-10-04 S01 simulación: `scripts.import_sdm_tasks` en modo solo lectura sobre
  `127.0.0.1:5434/solercia`. 205 planificadas; diferencias por campo: descripción 14, prioridad 11,
  estado 5. Nuevas: T-200..T-205.
- 2026-10-04 S01 aplicación: `{"created": 6, "updated": 24, "unchanged": 175}` en una transacción.
  Verificación: nueva simulación `{"unchanged": 205}`; SELECT da 205 tareas `checklist_xlsx` en
  sdmujer. Dato lateral: `intake_items` 82 `pending`, 8 corridas, última 2026-09-05.

- 2026-10-04 S02: zona `America/Bogota` (ya usada por el resumen de correo y la importación del
  checklist); rango semiabierto [1-ene, 1-ene+1) sobre `created_at`; `year` validado 2000–2100
  con `Query(ge, le)` (422 fuera). `/tasks/years` incluye subtareas (el workspace lista con
  `include_subtasks`). Pruebas en `backend/tests/test_task_year_filter.py` contra PostgreSQL
  desechable (`docker run --rm postgres:16-alpine` en :55432), nunca contra :5434.
  RED: 8 fallidas, 1 pasada (aislamiento daba 404 por ruta inexistente). GREEN: 9/9 más
  `test_task_filters.py` 11/11 y `test_task_hierarchy.py` 7/7; `ruff check` limpio.
- 2026-10-04 S03: `TaskQuery.year`, `WorkspaceService.taskYears()`, `sol-select` «Año» con
  «Todos los años»; llaves nuevas `workspace.year.*` en `es-CO.json`. Estados: cargando,
  sin tareas en el año (con botón «Ver todos los años»), error de tareas y aviso si falla la
  consulta de años. `npm run build` exit 0 (aviso de presupuesto del bundle inicial, 1,09 MB),
  `npm run lint` exit 0. Pendiente: verificación en navegador (backend del compose apagado).

- 2026-10-04 S03 navegador (backend en el host con `STARTUP_PROFILE=local_restricted`,
  `EMAIL_ENABLED=false`, sin scheduler; front `ng serve` :4242): en IDARTES › MUNDOS DIGITALES
  el selector «Año» carga 2026 y pide `?include_subtasks=true&year=2026`. Por año en BD: 2026 933,
  2025 5, 2024 6. El tablero parece vacío porque las 944 tareas están en «Listo» (quinta columna,
  fuera de la vista); los estados vienen así de Jira. Hallazgos para S04: el selector queda
  apilado sobre «Nueva tarea» y desalineado del título; el tablero no indica columnas fuera de
  la vista ni conteos totales.

- 2026-10-04 S04: encabezado `h1.sol-display` + badge de metodología + conteo, «Nueva tarea» en
  la misma fila. Barra de filtros extraída a `workspace-filters.component.ts` (`sol-card`): Año,
  Estado (columnas del tablero), Responsable (miembros del proyecto), Prioridad y Buscar (`q`,
  350 ms). Todos viajan al backend y aplican a todas las pestañas, como el año. «Limpiar filtros»
  e indicador «N filtros activos» solo con filtros distintos del año preseleccionado. Cuadrícula
  en `sol-data-table` (paginada, acciones al inicio, `collapseWidth` 760, `trackByKey` id, badges);
  sin buscador propio para no duplicar `q`. La librería no expone clic de fila: el detalle se abre
  desde el ícono «ver», el código o el título. Tablero: resumen de conteos por columna que lleva a
  cada una (`scrollIntoView`, respeta `prefers-reduced-motion`); arrastrar y soltar sin cambios.
  Estados: spinner con `role=status`, error con «Reintentar» (tablero oculto para no mostrar
  ceros), sin coincidencias con «Limpiar filtros», sin tareas en el año y vacío legítimo.
- 2026-10-04 S04 verificación: `npm run build` exit 0 (aviso de presupuesto igual, 1,09 MB) y
  `npm run lint` exit 0. Navegador 1440×900 y 390×844, claro y oscuro: PANDORA-IDARTES pide
  `status=EN CURSO&…&q=zzzxq` y muestra «Ninguna tarea coincide»; responsable + prioridad da
  «1 tarea» y «2 filtros activos»; limpiar vuelve a 14. En MUNDOS DIGITALES el chip «Listo 14»
  desplaza el tablero a esa columna. Error simulado (500 en la ruta) → alerta y reintento OK. A
  390 px la tabla colapsa a tarjetas y no hay desplazamiento horizontal de página.
- Veredicto UX: viene a ver y encontrar tareas del proyecto. Fricciones abiertas: (1) a 390 px la
  barra de filtros ocupa ~400 px antes del tablero → revelación progresiva (botón «Filtros (n)»);
  (2) `sol-select` y `sol-input` de la librería no asocian la etiqueta al control (nombre accesible
  = valor/placeholder); (3) el vacío legítimo no se pudo ver con datos reales (solo lectura).

- 2026-10-04 S05 backend: `GET /projects?year=` (2000–2100, 422 fuera) deja solo proyectos con
  tareas activas creadas ese año en Bogotá (subtareas incluidas, como `/tasks/years`; EXISTS).
  Cada proyecto trae `task_count` y `open_task_count` en UNA consulta agregada para la página
  (la prueba de N+1 pasa de 3 a 4 SELECT constantes). Conteos sobre tareas raíz, la misma unidad
  del encabezado del workspace (en navegador una tarjeta decía 16 y el workspace 5; corregido).
  Abierta = no `cancelled` y no cerrada; cerrada = `completed_at` o estado igual a la última
  columna del tablero (regla de `TaskService._resolve_completed_at` y `rollup_progress`): las
  tareas de SDMujer en «Completada»/«Done» no tienen `completed_at`. `GET /projects/years`
  declarado antes de `/{project_id}`. Helper compartido `task_year_bounds`.
  RED: 9 fallidas, 1 pasada (401); luego 1 RED por conteo de subtareas y 1 por última columna.
  GREEN: `test_project_year_filter.py` 12/12 más vecinos (`test_task_year_filter`,
  `test_projects`, `test_project_kind_filter`, `test_board_aware_call_sites`,
  `test_project_update`, `test_project_hierarchy_endpoints`) 70/70 en PostgreSQL desechable
  :55432; `ruff check` limpio en los archivos tocados.
- 2026-10-04 S05 frontend: `h1.sol-display` + conteo («20 proyectos con tareas en 2026», «1 de 22
  proyectos» con filtros locales) y «Crear proyecto» en la misma fila. `projects-filters.component.ts`
  (`sol-card`): Año (años reales + «Todos los años», preselecciona el actual o el más reciente),
  Metodología (solo las presentes) y Buscar (nombre o código, sin tildes). Año al backend,
  metodología y búsqueda en el cliente. Tarjetas: «N tareas en 2026 · M abiertas», sin «Sin
  descripción», código del proyecto. `?year=` (o `all`) en la URL, en el enlace a cada proyecto y
  en «Volver a proyectos»; el workspace lo preselecciona. «Limpiar filtros» vuelve al año natural
  (un año llegado por URL distinto cuenta como filtro activo). Proyecto nuevo con año elegido →
  se abre su workspace (sin tareas no saldría en la lista). Selector «Proyecto padre» carga la
  lista completa sin año. Estados: spinner `role=status`, error con «Reintentar», sin
  coincidencias con «Limpiar filtros», sin proyectos en el año con «Ver todos los años», vacío
  legítimo con «Crear proyecto», aviso en línea si falla `/projects/years` (lista todos).
  Vista tabla (`sol-view-toggle` + `sol-data-table`) no se hizo: anotada como mejora.
- 2026-10-04 S05 verificación: `npm run build` exit 0 (bundle inicial 1,09 MB, igual) y
  `npm run lint` exit 0. Navegador 1440×900 y 390×844, claro y oscuro, sin desplazamiento
  horizontal: IDARTES 2026 = 20 de 22 (oculta «Pandora Contratacion» y «Generales», sin tareas
  2026); 2025 = 8; PANDORA-IDARTES 2025 «5 tareas» igual al workspace con `?year=2025`; todos
  los años 29 = 29. SDMujer 2026: Generales 67/52, PANDORA 34/27, SGSI 104/91 abiertas. Búsqueda
  `zzzxq` → «Ningún proyecto coincide» y limpiar; 500 simulado en `/projects` → alerta y
  «Reintentar» OK; 500 en `/projects/years` → aviso y todos los proyectos. Solo lectura.
- Veredicto UX S05: viene a encontrar el proyecto en el que trabaja este año. Bien: año
  preseleccionado con datos reales, opciones conocidas en vez de texto libre, conteos que
  coinciden con el workspace, el año no se pierde al entrar y volver. Fricciones: (1) «Removida»
  y «Diferida» cuentan como abiertas (las columnas no tienen categoría) → categoría de columna
  (abierta/cerrada/descartada); (2) a 390 px la barra ocupa ~250 px → filtros plegables, igual
  que S04; (3) etiquetas de `sol-select`/`sol-input` sin asociación accesible (librería).

## Siguiente paso

S06. Pendientes: categoría de columna para «abierta», filtros plegables en móvil, etiquetas
accesibles en `@solercia/ui`, vista tabla opcional en `/projects`.
