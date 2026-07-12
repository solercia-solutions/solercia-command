# Proposal: 10 · Búsqueda global + filtros avanzados

## Intent

La Fase 4 del CLAUDE.md pide "filtros avanzados y búsqueda global". Hoy no existe forma de encontrar una tarea, proyecto o comentario sin conocer su ubicación exacta: la única búsqueda es `GET /tasks/by-key/{key}` (clave exacta). La lista de tareas solo filtra por `sprint_id/status/assignee_id` y no combina prioridad, etiquetas ni texto. Con el backend ya maduro (labels en 04, historial en 05), el jefe y el colaborador necesitan una caja de búsqueda transversal y filtros combinables para operar sin fricción.

## Scope

### In Scope
- **Búsqueda global** `GET /api/v1/search?q=&types=&page=&size=`: resultados multi-entidad sobre **tasks** (título, descripción, clave `SDM-7`), **projects** (nombre, código, descripción) y **comments** (cuerpo). Respuesta envuelta `{data, message, meta}` con `entity_type`, id, snippet y contexto de proyecto.
- **Filtros avanzados** en `GET /projects/{id}/tasks`: combinables `status`, `priority`, `assignee_id`, `label_id` (multi), `sprint_id`, `due_from/due_to`, `q` (texto), adoptando la paginación estándar `?page&size&sort&order` de 02.
- **Extensión `pg_trgm` + índices GIN** sobre los campos de texto buscables (migración Alembic 0008 con downgrade).

### Out of Scope (non-goals)
- Búsqueda sobre assets/licencias (07 pendiente), reminders (06), adjuntos, notificaciones o time-logs.
- Ranking semántico / FTS con `tsvector` y stemming en español (hardening futuro; ver Approach).
- Búsquedas guardadas, historial de búsqueda, autocompletado o facetas.
- Cualquier cambio en `frontend/` (constraint `frontend-frozen`).

## Capabilities

### New Capabilities
- `global-search`: endpoint transversal con scope estricto por organización, paginación y agrupación por tipo de entidad.

### Modified Capabilities
- `tasks`: la lista por proyecto amplía sus filtros combinables (prioridad, etiquetas, rango de fechas, texto) y adopta paginación estándar.

## Approach

Módulo nuevo `search` (router→service→repository) que consulta cada entidad con su scope de tenant: projects/comments por `organization_id` directo (TenantMixin), tasks vía join a `Project.organization_id` (Task no lleva `organization_id`). Coincidencia por **`ILIKE '%q%'` acelerado con `pg_trgm`**: mantiene la semántica de subcadena que espera una caja de búsqueda, tolera errores de tipeo vía `similarity()` para el orden, y solo exige habilitar una extensión + índices GIN (limpiamente reversible). Se descarta `tsvector` para el MVP por su complejidad (columnas generadas, config de idioma, parseo de `tsquery`) y peor ajuste a búsqueda por subcadena parcial. Los filtros avanzados reutilizan el constructor de query del repository de tareas.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/search/` | New | Router, service, repository de búsqueda multi-entidad |
| `backend/app/modules/tasks/repository.py` | Modified | Filtros combinables + paginación en la lista |
| `backend/app/modules/tasks/{router,schemas}.py` | Modified | Query params de filtros avanzados |
| `backend/alembic/versions/0008_*.py` | New | `CREATE EXTENSION pg_trgm` + índices GIN (con downgrade) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `CREATE EXTENSION pg_trgm` requiere privilegios; podría fallar en entornos restringidos | Med | `IF NOT EXISTS`; el postgres de docker corre como superusuario; documentar prerrequisito |
| Fuga de datos entre tenants en la consulta multi-entidad | High | Scope obligatorio en cada rama (join a Project para tasks); test de aislamiento por entidad |
| Rendimiento de `ILIKE` sin índice en tablas grandes | Med | Índices GIN `gin_trgm_ops`; paginación obligatoria |
| Downgrade que deje la extensión huérfana o rompa por dependencias | Med | Downgrade borra índices y luego la extensión en orden inverso |

## Rollback Plan

Cambio aditivo. Revertir el merge de código y ejecutar `alembic downgrade` de la migración 0008 (elimina índices GIN y la extensión `pg_trgm`). El endpoint `/search` desaparece y `GET /projects/{id}/tasks` vuelve a sus filtros previos; ningún dato de dominio se altera.

## Dependencies

- `depends_on: 02-contrato-api` — paginación estándar reutilizada por los filtros y la búsqueda.
- `depends_on: 04-labels-checklists-dependencias` — el filtro `label_id` requiere Label/TaskLabel.
- `depends_on: 05-trabajo-realizado` — cadena del roadmap (backend maduro previo a la búsqueda transversal).

## Success Criteria

- [ ] `GET /search?q=` devuelve tasks, projects y comments de la organización activa, con snippet y contexto, envuelto `{data, message, meta}` y paginado.
- [ ] Ningún resultado cruza la frontera de organización (test de aislamiento por cada tipo de entidad).
- [ ] `GET /projects/{id}/tasks` combina `status+priority+label_id+assignee_id+sprint+fechas+q` con paginación estándar.
- [ ] Migración 0008 crea `pg_trgm` + índices GIN y su `downgrade` los revierte sin pérdida de datos.
- [ ] Todo el código nace con prueba en rojo (TDD estricto); happy path + error + permisos/aislamiento por endpoint.
