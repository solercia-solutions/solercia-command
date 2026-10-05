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
- [ ] S04 `/projects/:id` (workspace): barra de filtros y grid a `sol-data-table` paginada (L).
- [ ] S05 `/projects`: encabezado `h1.sol-display`, filtros en `sol-card` (M).
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

## Siguiente paso

Verificar S03 en navegador con el backend arriba; luego S04.
