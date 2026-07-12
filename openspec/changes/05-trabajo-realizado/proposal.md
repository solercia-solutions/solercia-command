# Proposal: 05 · Trabajo realizado (TimeLog + ActivityLog + cruce asignado vs realizado)

## Intent

El cruce "trabajo asignado vs realizado" es una capacidad diferenciadora del producto (CLAUDE.md): el jefe ve la discrepancia entre lo que asignó y lo que la gente de verdad hizo. Hoy no existe base de datos que lo alimente: no hay registro de tiempo por tarea/usuario ni changelog automático de mutaciones. La vista ejecutiva mide carga solo por conteo de tareas activas y no puede responder "quién tiene asignado pero no registra actividad". Este cambio construye las dos fuentes de datos (tiempo y historial) y extiende el dashboard con la vista de discrepancia.

## Scope

### In Scope
- **TaskTimeLog**: entradas de tiempo por tarea/usuario (`date`, `hours` Decimal, `note?`). CRUD; el colaborador registra su propio tiempo, admin/manager consultan el de todos. Agregación diaria/semanal por usuario.
- **ActivityLog / TaskHistory**: changelog automático de mutaciones de tarea (cambio de estado, reasignación, estimación, movimiento de sprint, movimiento de columna) con quién, cuándo, campo, valor anterior→nuevo. Lectura por tarea (historial) y por usuario/día (actividad).
- **Cruce en dashboard**: extender ejecutiva/desempeño con horas registradas vs estimación, tareas asignadas vs tareas con actividad, y colaboradores con tareas asignadas y CERO actividad en N días.

### Out of Scope (non-goals)
- Cronómetro en vivo / capturas de pantalla / monitoreo de escritorio.
- Integraciones externas de time-tracking (Toggl, Harvest, Jira Tempo).
- Facturación o cálculo de costo a partir de horas.
- Canal email/WebSocket para estas señales (corresponde a 08 y 09).
- Modelo de capacidad por persona (el `workload` sigue por conteo; solo se suma la discrepancia).
- Cualquier cambio en `frontend/` (constraint `frontend-frozen`).

## Capabilities

### New Capabilities
- `time-logs`: registro de tiempo por tarea/usuario, permisos propio-vs-todos, agregación diaria/semanal.
- `activity-history`: captura automática del changelog de mutaciones de tarea (incluidas las generadas por el sistema) y lectura por tarea y por usuario/día.

### Modified Capabilities
- `dashboard-executive`: nuevos campos de cruce asignado vs realizado sobre `executive`/`performance`.

## Approach

Dos módulos backend nuevos (`time_logs`, `activity`) con patrón router→service→repository y scope de tenant vía join a Project, reutilizando la resolución de auth-user y los campos de auditoría de `02-contrato-api`. La captura de historial se centraliza en la capa de servicio de tareas para cubrir mutaciones de usuario y del sistema (cierre de sprint, motor de alertas). El dashboard suma agregaciones sobre las dos tablas nuevas sin romper su contrato actual. TDD estricto: prueba en rojo antes del código.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/time_logs/` | New | Modelo, router, service, repository de TaskTimeLog |
| `backend/app/modules/activity/` | New | ActivityLog/TaskHistory + endpoints de lectura |
| `backend/app/modules/tasks/service.py` | Modified | Punto de captura del historial en mutaciones |
| `backend/app/modules/sprints/`, `alerts/` | Modified | Emitir historial en cambios generados por el sistema |
| `backend/app/modules/dashboard/` | Modified | Campos de cruce asignado vs realizado |
| `backend/alembic/` | New | Migración de las dos tablas nuevas |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Mecanismo de captura de historial (servicio explícito vs event listener SQLAlchemy) y cobertura de cambios del sistema | High | Decidir en design; recomendación inicial: captura explícita en servicio para controlar actor y contexto |
| Historial incompleto si el motor de alertas / cierre de sprint mueve tareas sin pasar por el punto de captura | Med | Test que verifique historial tras cierre de sprint y tras acción del motor de alertas |
| Doble sistema de roles (MemberRole vs RBAC) al aplicar permisos propio-vs-todos | Med | Alinear con el criterio de `02-contrato-api`; documentar el rol usado |
| Costo de agregación en dashboard con muchos time logs | Low | Agregar en repository con índices por (user, date) |

## Rollback Plan

Cambio aditivo. Revertir el merge de código y bajar (downgrade) la migración Alembic que crea `task_time_logs` y `task_history`/`activity_log`; los endpoints nuevos y los campos añadidos al dashboard desaparecen sin afectar datos existentes.

## Dependencies

- `depends_on: 02-contrato-api` — auditoría `created_by`/`updated_by`, resolución de auth-user y contrato de paginación para las nuevas listas.

## Success Criteria

- [ ] Endpoints de TaskTimeLog (CRUD + agregación diaria/semanal) con tests happy path, error y permisos (propio vs todos).
- [ ] Toda mutación listada (estado, reasignación, estimación, sprint, columna) deja registro de historial, incluidas las generadas por el sistema (cierre de sprint, alertas).
- [ ] Lectura de historial por tarea y de actividad por usuario/día.
- [ ] Dashboard expone: horas registradas vs estimación, tareas asignadas vs con actividad, y colaboradores con asignación y CERO actividad en N días.
- [ ] Todo el código nace con prueba en rojo (TDD estricto); listas nuevas paginadas.
