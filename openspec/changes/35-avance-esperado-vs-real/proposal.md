# Proposal: 35 · Avance esperado vs. real (semáforo, tendencia y refuerzo)

## Intent

Hoy la vista de jefe (`dashboard-executive`) solo muestra `percent_done` = completadas/total por conteo simple (`app/modules/dashboard/service.py:_build_projects_progress`): sin **cuánto DEBERÍA ir a la fecha**, sin ponderar por horas, sin rollup por área, sin tendencia ni alerta accionable. El jefe no distingue "va al día" de "va retrasado" ni sabe cuánto reforzar. Este cambio (OLA 4, fase 4.3) calcula el **% esperado** (distribución por due dates sobre los días laborales del calendario del 28; lineal sobre el rango de tareas si faltan fechas — `Project` no tiene fechas propias), el **% real** (completadas, ponderado por `estimation_hours` si existen; conteo si no), la **desviación** con semáforo configurable y la **tendencia de 4 semanas**, y emite una alerta de refuerzo por el motor de alertas existente.

## Scope

### In Scope
- Módulo nuevo `app/modules/progress/`: `ProgressService` que reúsa `WorkCalendarResolver` (28), el árbol/`project_kind` de `ProjectRepository` (27) y `TaskRepository`.
- Fórmulas: esperado (due dates → días laborales; lineal por rango de tareas si faltan), real (ponderado por horas o conteo), desviación = esperado − real, tendencia 4 semanas.
- Umbrales por empresa: verde ≤5%, amarillo ≤15%, rojo >15% (default), configurables en `organizations`.
- Snapshots semanales `project_progress_snapshot` (job en el scheduler existente) como fuente de la tendencia; tarjeta "hoy" on-demand.
- Endpoints: tarjeta por proyecto, rollup por subárbol/área, corte mensual por área.
- Alerta de refuerzo: nueva `AlertStrategy project_reinforcement` + AlertRule sembrada, evaluada por el scheduler horario existente.
- UI: tarjetas con semáforo y tendencia en la vista ejecutiva (`frontend/src/pages/executive`).

### Out of Scope
- Burndown por sprint (cambio 42), festivos/husos (futuro del 28), canales email/WebSocket nuevos (reúsa los actuales).
- Reconstruir el % ESPERADO histórico previo a los snapshots (revisionista; solo el real es reconstruible por `completed_at`).

## Capabilities

### New Capabilities
- `project-progress`: esperado/real/desviación/tendencia, umbrales por empresa, snapshots, endpoints tarjeta/rollup/corte mensual.

### Modified Capabilities
- `alert-engine`: nueva estrategia `project_reinforcement` (refuerzo accionable).
- `dashboard-executive`: tarjetas por proyecto enriquecidas con esperado/real/semáforo.

## Approach

`ProgressService` calcula on-demand la tarjeta "hoy"; un job semanal del scheduler persiste `project_progress_snapshot` (esperado, real, desviación) que alimenta la tendencia de 4 semanas — evita reconstruir el esperado histórico (no fiable: tareas, fechas y calendario mutan). Umbrales: dos columnas `Numeric` en `organizations` (patrón aditivo de `theme`/calendario), default 5/15. El refuerzo es una Strategy nueva en el registro de alertas (mismo contrato `evaluate → AlertCandidate`), deduplicada por `project_reinforcement:{project_id}:{iso_week}:{user}` para disparar una vez por semana, proyecto y destinatario.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/progress/*` | New | Service, repository, schemas, router, modelo snapshot |
| `backend/app/modules/organizations/{models,schemas,router}.py` | Modified | Columnas de umbral + endpoint de config |
| `backend/app/alerts/strategies/project_reinforcement.py`, `registry.py` | New/Modified | Estrategia de refuerzo registrada |
| `backend/app/alerts/scheduler.py` | Modified | Job semanal de snapshots |
| `backend/app/modules/dashboard/*` | Modified | Componer/enriquecer tarjetas (o front consume progress) |
| `frontend/src/pages/executive/*`, `entities/executive/*` | Modified | Tarjetas con semáforo y tendencia |
| `backend/alembic/versions/` | New | Umbrales en organizations + tabla snapshot |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Tendencia vacía las primeras 4 semanas | Alta | Backfill del real por `completed_at`; esperado "sin dato" hasta acumular |
| Esperado erróneo si faltan due dates | Media | Fallback lineal sobre el rango de tareas; documentar el supuesto |
| Cálculo pesado en árboles grandes | Media | Rollup por CTE de subárbol; snapshots evitan recomputar la tendencia |
| Semáforo depende del calendario del 28 | Media | Reusar `WorkCalendarResolver`; default 8h/L-V si falla |
| Alerta de refuerzo ruidosa | Media | Dedup semanal por proyecto/usuario; umbral configurable |

## Rollback Plan

Migración aditiva y reversible: el downgrade elimina las columnas de umbral y la tabla `project_progress_snapshot`; se retira el router `progress`, la estrategia `project_reinforcement` del registro y el job semanal. Sin borrado de datos preexistentes; la vista ejecutiva vuelve al `percent_done` actual.

## Dependencies

- `28-calendario-laboral`: `ResolvedCalendar` (días laborales) para distribuir el esperado.
- `27-plantillas-idempotentes`: `project_kind`/árbol para el rollup por subárbol/área.
- `25-multiempresa-scoping`: todo scoped por `organization_id`.

## Success Criteria

- [ ] Tarjeta por proyecto: esperado, real, desviación y semáforo (umbrales 5/15 configurables por empresa).
- [ ] Tendencia de 4 semanas desde snapshots; rollup por subárbol/área.
- [ ] Corte mensual por área (qué llega / necesita refuerzo / va adelantado).
- [ ] Alerta `project_reinforcement` con horas de refuerzo, emitida por el scheduler y deduplicada.
- [ ] Migración aditiva/reversible; suite backend en verde; scoping multi-tenant intacto.

## Proposal question round

Supuestos a validar con el usuario: (1) módulo nuevo `progress` (no extender `dashboard`) por ser capacidad acotada con snapshots + alerta; (2) tendencia desde snapshots semanales, sin reconstrucción retroactiva del esperado (que sería revisionista); (3) umbrales como dos columnas `Numeric` en `organizations` (5/15 default), no JSONB; (4) real ponderado por `estimation_hours` cuando existen, conteo simple si no; (5) refuerzo como `AlertStrategy` evaluada por el scheduler horario, dedup semanal por proyecto/usuario; (6) fallback lineal sobre el rango de tareas porque `Project` no tiene start/end propios. Segunda ronda disponible si se quiere revisar los destinatarios de la alerta o la política de ponderación.
