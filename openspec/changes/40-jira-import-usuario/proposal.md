# Proposal: 40 · Importación Jira por usuario (elegir → previsualizar → importar)

## Intent

El módulo `jira_import` (cambio 18) hoy solo extrae y normaliza issues a partir de un JQL y devuelve un snapshot: NUNCA persiste, no deja elegir proyecto, no previsualiza y no convierte la estimación original. Un usuario con su conector Jira no puede traer un proyecto completo (épicas/historias/subtareas/sprints) a la plataforma. La OLA 4 (fase 4.4) pide convertir el conector "conectado" (panel del 39) en una importación real y segura: elegir proyecto → previsualizar → importar, preservando la clave Jira como referencia y sin duplicar al reimportar.

## Scope

### In Scope
- `GET /connectors/{id}/jira/projects`: proyectos Jira accesibles con el conector del usuario (`/project/search`).
- `POST /connectors/{id}/jira/preview`: conteos por tipo (épicas/historias/subtareas/bugs) + sprints + mapeo propuesto de estados/tipos/estimaciones. NO persiste.
- `POST /connectors/{id}/jira/import-project`: importación idempotente (transaccional o por lotes) que crea Project/Sprint/Task locales y devuelve resumen (creados/actualizados/omitidos + no homologados).
- Jerarquía epic→story→subtask vía `parent_task_id` (dos pasadas: crear y luego enlazar por clave padre).
- `task_key` local atómico (`projects.task_counter`); clave Jira original preservada como ancla de reimportación.
- `timeoriginalestimate` (segundos) → horas con `seconds_to_hours` (cambio 34); story points → `estimation_points`.
- Estado Jira → estados de la metodología destino (scrum) leído DESDE la strategy; reusa el reporte de no homologados del 18.
- Asignados: match por email si el usuario existe en la org; si no → sin asignar con nota.
- Frontend: asistente de 3 pasos desde la tarjeta del conector (punto de entrada del 39).
- TDD con fixtures de respuestas Jira mockeadas (`httpx.MockTransport`, patrón del 18).

### Out of Scope
- Modo administrador multi-proyecto por lotes con progreso reanudable (cambio 41).
- Escritura hacia Jira (Jira permanece solo-lectura).
- Reparación OAuth / import Planner/Google (cambios 38/posteriores).
- Sincronización programada/scheduler.

## Capabilities

### New Capabilities
- `jira-import-wizard`: asistente frontend de 3 pasos (elegir → previsualizar → importar) lanzado desde la tarjeta del conector.

### Modified Capabilities
- `jira-import`: de extracción solo-lectura a flujo de importación — listar proyectos, previsualizar y persistir idempotente con mapeo a la metodología destino y conversión de estimación.
- `tasks`: las entidades importadas (task/sprint/project) ganan un ancla de procedencia externa (source + clave externa) que preserva la clave Jira y habilita la reimportación idempotente.

## Approach

Extender `JiraClient` con `/project/search` y agregar `original_estimate_seconds` a los campos de búsqueda, al `NormalizedJiraIssue` y al normalizer. Un builder de preview arma conteos + mapeo propuesto sin persistir. Un servicio de escritura crea Project/Sprint/Task en transacción/lotes: asigna `task_key` atómico, enlaza jerarquía por clave padre (dos pasadas), mapea estado→metodología destino vía strategy, convierte estimación con `seconds_to_hours` (34) y homologa asignado por email contra los miembros de la org. Idempotencia anclada en `(org, source='jira', external_key)`: reimportar reconcilia (actualiza), nunca duplica; conflicto ambiguo → rechazo con mensaje claro. Frontend: asistente de 3 pasos desde el panel del 39.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/jira_import/{router,service,schemas}.py` | Modified | Endpoints projects/preview/import-project + servicio de escritura |
| `backend/app/integrations/adapters/jira/{client,dtos,normalizer,adapter}.py` | Modified | `/project/search`, `original_estimate_seconds`, campo estimación |
| `backend/app/modules/tasks/models.py` (+ sprints/projects) | Modified | Ancla de procedencia externa (source + external_key) |
| `backend/alembic/versions/*` | New | Columnas + índice/único de procedencia externa |
| `frontend/src/pages|widgets` (asistente) + `entities/*` | New/Modified | Asistente de 3 pasos + tipos/servicios |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Asignado sin email (normalizer prioriza `accountId`) | Alta | Preservar `emailAddress`; sin match → sin asignar + nota |
| Import grande excede transacción/timeout | Media | Lotes por sprint/tipo + resumen; sin duplicar por lote |
| Subtarea con padre fuera del set | Media | Dos pasadas; huérfana → sin padre + nota en resumen |
| Estado/sprint Jira no homologado (workflow custom) | Media | Fallback por bucket/estrategia + reporte de no homologados (18) |
| Cambio grande supera presupuesto de 400 líneas | Alta | PRs encadenados (backend flujo → persistencia/migración → front) |

## Rollback Plan

Revertir los commits (adapter/servicio/endpoints/front) y aplicar `alembic downgrade` para quitar las columnas de procedencia externa. Las filas importadas son identificables por `external_key` para limpieza puntual; ningún dato preexistente se altera de forma destructiva.

## Dependencies

- `39-conector-capacidades`: tarjeta/panel de acciones = punto de entrada del asistente.
- `34-estimacion-normalizada`: `seconds_to_hours` en `work_calendar/estimation.py`.
- Existentes: `18-adapter-jira` (cliente/normalizer/mappings), `14` connectors (credenciales Fernet), `methodology-strategies` (estados destino).

## Success Criteria

- [ ] Lista los proyectos Jira accesibles con el conector del usuario.
- [ ] Preview devuelve conteos + mapeo propuesto (estados/tipos/estimaciones) sin persistir.
- [ ] Import crea Project/Sprint/Task con jerarquía correcta, `task_key` atómico, estimación en horas + story points y clave Jira preservada.
- [ ] Reimportar el mismo proyecto NO duplica (reconciliación idempotente).
- [ ] Asignado homologado por email o sin asignar con nota.
- [ ] Asistente de 3 pasos operativo; suite backend en verde; textos de UI en español colombiano formal (tuteo).

## Proposal question round

Supuestos a validar (el sub-agente no pregunta en vivo): (1) el ancla de idempotencia es una columna de procedencia externa `(source, external_key)` en task/sprint/project con único por scope, siguiendo el precedente de `IntakeItem`, en vez de un JSONB `metadata` — implica migración Alembic (a diferencia de 34/36/39); (2) reimportar reconcilia (actualiza título/estado/estimación/sprint del ítem anclado), nunca duplica; conflicto ambiguo → rechazo con mensaje; (3) el destino por defecto es un proyecto `scrum` nuevo por proyecto Jira, con `code` derivado de la clave Jira; (4) el asignado se homologa por email exacto contra miembros de la org (requiere preservar `emailAddress`, hoy el normalizer prioriza `accountId`); (5) el import es por proyecto único (multi-proyecto/lotes = cambio 41). Segunda ronda disponible para revisar el destino (proyecto nuevo vs. proyecto existente elegible), el gesto de reconciliación (actualizar vs. solo-nuevos) y el mapeo de estado de sprint Jira (`future`/`active`/`closed` → `active`/`closed`).
