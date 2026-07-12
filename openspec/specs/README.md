# Índice de specs — trazabilidad capacidad → cambio de origen

**Convención**: cada carpeta de `openspec/specs/` es la **verdad viva por capacidad** (documenta el comportamiento vigente del sistema). Los cambios archivados en [`../changes/archive/`](../changes/archive/) son **deltas históricos**: registran qué aportó cada ciclo SDD, pero la spec viva ya los tiene fusionados. Cada `spec.md` lleva, justo después del título, una línea `> **Origen**` con esta misma trazabilidad.

La **línea base as-built** (2026-07-11) documenta las 14 capacidades que existían antes de adoptar SDD (pre-SDD, sin ciclo de cambio propio). Ver la tabla "Lo construido" en [`../AVANCE.md`](../AVANCE.md).

## Tabla de trazabilidad

| Capacidad | Spec | Cambio(s) de origen |
|-----------|------|---------------------|
| Historial de actividad | [activity-history](activity-history/spec.md) | [05-trabajo-realizado](../changes/archive/2026-07-11-05-trabajo-realizado/) |
| Motor de alertas | [alert-engine](alert-engine/spec.md) | baseline + [04-labels-checklists-dependencias](../changes/archive/2026-07-11-04-labels-checklists-dependencias/) |
| Convenciones de API | [api-conventions](api-conventions/spec.md) | baseline + [01-fundacion-tdd](../changes/archive/2026-07-11-01-fundacion-tdd/) + [02-contrato-api](../changes/archive/2026-07-11-02-contrato-api/) |
| Archivos adjuntos | [attachments](attachments/spec.md) | baseline |
| Autenticación | [auth](auth/spec.md) | baseline |
| Tableros persistentes | [boards](boards/spec.md) | [03-boards-persistentes](../changes/archive/2026-07-11-03-boards-persistentes/) |
| Checklists de tarea | [checklists](checklists/spec.md) | [04-labels-checklists-dependencias](../changes/archive/2026-07-11-04-labels-checklists-dependencias/) |
| Comentarios y menciones | [comments-mentions](comments-mentions/spec.md) | baseline |
| Vista ejecutiva | [dashboard-executive](dashboard-executive/spec.md) | baseline + [05-trabajo-realizado](../changes/archive/2026-07-11-05-trabajo-realizado/) |
| Herramientas de desarrollo | [dev-tooling](dev-tooling/spec.md) | [01-fundacion-tdd](../changes/archive/2026-07-11-01-fundacion-tdd/) |
| Búsqueda global | [global-search](global-search/spec.md) | [10-busqueda-global](../changes/archive/2026-07-12-10-busqueda-global/) |
| Labels (etiquetas de tarea) | [labels](labels/spec.md) | [04-labels-checklists-dependencias](../changes/archive/2026-07-11-04-labels-checklists-dependencias/) |
| Estrategias de metodología | [methodology-strategies](methodology-strategies/spec.md) | baseline + [03-boards-persistentes](../changes/archive/2026-07-11-03-boards-persistentes/) |
| Multi-tenancy | [multi-tenancy](multi-tenancy/spec.md) | baseline |
| Notificaciones en tiempo real | [realtime-notifications](realtime-notifications/spec.md) | [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) |
| Notificaciones in-app | [notifications-inapp](notifications-inapp/spec.md) | baseline + [06-reminders](../changes/archive/2026-07-12-06-reminders/) + [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) |
| Recordatorios (manuales y por regla) | [reminders](reminders/spec.md) | [06-reminders](../changes/archive/2026-07-12-06-reminders/) |
| Proyectos | [projects](projects/spec.md) | baseline |
| Catálogo RBAC | [rbac-catalog](rbac-catalog/spec.md) | baseline |
| Sprints | [sprints](sprints/spec.md) | baseline |
| Dependencias tarea-tarea | [task-dependencies](task-dependencies/spec.md) | [04-labels-checklists-dependencias](../changes/archive/2026-07-11-04-labels-checklists-dependencias/) |
| Tareas | [tasks](tasks/spec.md) | baseline + [03-boards-persistentes](../changes/archive/2026-07-11-03-boards-persistentes/) + [10-busqueda-global](../changes/archive/2026-07-12-10-busqueda-global/) |
| Registro de tiempo | [time-logs](time-logs/spec.md) | [05-trabajo-realizado](../changes/archive/2026-07-11-05-trabajo-realizado/) |
| Administración de usuarios | [users-admin](users-admin/spec.md) | baseline |
| Cobertura de línea base | [test-coverage-baseline](test-coverage-baseline/spec.md) | [11-blindaje-baseline](../changes/archive/2026-07-12-11-blindaje-baseline/) |

**Leyenda**: `baseline` = línea base as-built (2026-07-11). Cuando aparece `baseline + NN`, la capacidad nació en la línea base y el/los cambio(s) archivados le fusionaron requisitos nuevos o modificados.

## Cambios en curso (sin archivar)

- **cycle2-design-system** — ON-HOLD (frontend). No aporta deltas de specs backend (su carpeta no tiene `specs/`).

## Detalle del mapeo por cambio archivado

| Cambio | Deltas de specs | Capacidad viva afectada |
|--------|-----------------|-------------------------|
| [01-fundacion-tdd](../changes/archive/2026-07-11-01-fundacion-tdd/) | `dev-tooling.md` (nueva), `api-conventions.md` (MODIFIED) | `dev-tooling` (creada), `api-conventions` (modificada: inicialización de esquema vía Alembic) |
| [02-contrato-api](../changes/archive/2026-07-11-02-contrato-api/) | `api-pagination.md`, `audit-fields.md` (ambos deltas de api-conventions) | `api-conventions` (modificada: paginación estándar + auditoría `created_by`/`updated_by`) |
| [03-boards-persistentes](../changes/archive/2026-07-11-03-boards-persistentes/) | `boards.md` (nueva), `methodology-strategies.md` (MODIFIED), `tasks.md` (MODIFIED) | `boards` (creada), `methodology-strategies` y `tasks` (modificadas) |
| [04-labels-checklists-dependencias](../changes/archive/2026-07-11-04-labels-checklists-dependencias/) | `labels.md`, `checklists.md`, `task-dependencies.md` (nuevas), `alert-blocked-task.md` (delta de alert-engine) | `labels`, `checklists`, `task-dependencies` (creadas), `alert-engine` (modificada: estrategia `blocked_task`) |
| [05-trabajo-realizado](../changes/archive/2026-07-11-05-trabajo-realizado/) | `time-logs/spec.md`, `activity-history/spec.md` (nuevas), `dashboard-executive/spec.md` (ADDED) | `time-logs`, `activity-history` (creadas), `dashboard-executive` (modificada: bloque `work_gap`) |
| [10-busqueda-global](../changes/archive/2026-07-12-10-busqueda-global/) | `global-search/spec.md` (nueva), `tasks/spec.md` (MODIFIED + ADDED) | `global-search` (creada: endpoint GET /search con scope estricto multi-tenant), `tasks` (modificada: filtros avanzados combinables en GET /projects/{id}/tasks) |
| [11-blindaje-baseline](../changes/archive/2026-07-12-11-blindaje-baseline/) | `test-coverage-baseline/spec.md` (nueva) | `test-coverage-baseline` (creada: contrato de cobertura de tests as-built) |
| [06-reminders](../changes/archive/2026-07-12-06-reminders/) | `reminders/spec.md` (nueva), `notifications-inapp/spec.md` (ADDED) | `reminders` (creada: recordatorios manuales y por regla), `notifications-inapp` (modificada: origen `rule_type="reminder"`) |
| [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) | `realtime-notifications/spec.md` (nueva), `notifications-inapp/spec.md` (ADDED) | `realtime-notifications` (creada: canal WS push en tiempo real), `notifications-inapp` (modificada: publicación best-effort al conectar) |

## Inconsistencias detectadas

1. **Formato de deltas heterogéneo entre archives**: los cambios 01–04 guardan sus deltas como archivos planos `specs/<nombre>.md`, mientras que el 05 usa el formato de carpeta `specs/<capacidad>/spec.md`. No afecta la trazabilidad, pero conviene unificar hacia el formato de carpeta en cambios futuros.
2. **Nombres de delta que no coinciden con la carpeta de capacidad**: `api-pagination.md` y `audit-fields.md` (cambio 02) son en realidad deltas de `api-conventions`, y `alert-blocked-task.md` (cambio 04) es un delta de `alert-engine`. Se verificó que su contenido SÍ está fusionado en las specs vivas correspondientes (no hay deltas huérfanos), pero el nombre del archivo no delata a qué capacidad pertenece.
3. **Idioma y estilo de títulos mixtos en las specs vivas**: `activity-history` y `time-logs` usan encabezados en inglés (`Specification` / `Purpose`); `checklists`, `labels` y `task-dependencies` usan el prefijo `Especificación:`; el resto usa `Spec —`. Es solo cosmético, pero delata tres generaciones de plantilla distintas.
