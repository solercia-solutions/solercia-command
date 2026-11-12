# Delta for dashboard-executive

> Base: `openspec/specs/dashboard-executive/spec.md`. Este delta MODIFICA
> **R1** (`:22` de la línea base) y **R3** (`:24`) para excluir las tareas de
> contexto (`context_group IS NOT NULL`, ADDED en la capacidad `tasks` de este
> mismo cambio) de los tres bloques que miden **volumen de trabajo por
> persona**: `by_assignee`, `workload` y el conteo `totals.tasks`. Los bloques
> de **riesgo** no se tocan: `at_risk` sigue mostrando toda tarea vencida o
> marcada con `risk_flag`, sea o no de contexto, y los contadores
> `totals.overdue` y `totals.at_risk` siguen espejando esa lista, porque un
> riesgo real sigue siendo un riesgo real aunque no cuente como carga de
> nadie. `projects_progress` NO cambia en este delta: conserva su cálculo
> existente. Es la cuarta capacidad modificada del cambio 44: la decisión de
> excluir contexto del dashboard cambia el comportamiento observable de
> `GET /dashboard/executive`, cuyos requisitos ya están publicados, así que el
> ajuste exige un delta MODIFIED y nunca ADDED.

## MODIFIED Requirements

### Requirement: R1 — La agrupación por persona excluye tareas de contexto

`GET /api/v1/dashboard/executive` DEBE agrupar en `by_assignee` las tareas en curso de cada responsable EXCLUYENDO toda tarea con `context_group IS NOT NULL`, con exactamente el mismo criterio que `workload`. Los dos bloques cuentan trabajo asignado, así que NO DEBEN discrepar: una tarea que no cuenta como carga en `workload` tampoco DEBE aparecer como trabajo en curso en `by_assignee`, ni sumar en su conteo de tareas activas.
(Previously: "`executive` DEBE agrupar las tareas en curso por assignee (`by_assignee`) para responder «¿en qué anda cada persona?»." — sin ninguna exclusión de tareas de contexto; el dashboard no conocía `context_group` porque la columna no existía.)

#### Scenario: Tarea de contexto no aparece en la agrupación por persona

- DADO un colaborador con 3 tareas en curso asignadas y 1 tarea adicional con `context_group` no nulo, también en curso y asignada a él
- CUANDO el jefe consulta `GET /dashboard/executive`
- ENTONCES `by_assignee` reporta para ese colaborador sus 3 tareas en curso y un conteo de activas de 3, sin la de contexto

#### Scenario: Colaborador cuyas tareas activas son todas de contexto no aparece en by_assignee

- DADO un colaborador cuyas únicas tareas activas asignadas tienen `context_group` no nulo
- CUANDO se consulta `GET /dashboard/executive`
- ENTONCES ese colaborador NO aparece en `by_assignee`, igual que cualquier colaborador con cero tareas activas

### Requirement: R3 — Carga por persona y totales excluyen tareas de contexto

`GET /api/v1/dashboard/executive` DEBE reportar la carga por persona (`workload`) y el conteo de tareas de los totales agregados (`totals.tasks`) EXCLUYENDO toda tarea con `context_group IS NOT NULL`. `projects_progress` NO cambia en este requisito: conserva su cálculo existente, sin exclusión de contexto. El bloque `at_risk` tampoco cambia: NO DEBE aplicar ninguna exclusión de contexto; una tarea de contexto vencida o marcada con `risk_flag` DEBE seguir apareciendo en `at_risk`. Los contadores de riesgo de los totales (`totals.overdue` y `totals.at_risk`) DEBEN seguir el MISMO criterio que la lista `at_risk` y NO DEBEN excluir contexto: `totals.at_risk` DEBE ser siempre igual a la cantidad de elementos de `at_risk`.
(Previously: "`executive` DEBE reportar la carga por persona (`workload`) y el progreso por proyecto (`projects_progress`) con totales." — sin ninguna exclusión de tareas de contexto; el dashboard no conocía `context_group` porque la columna no existía.)

#### Scenario: Tarea de contexto no cuenta en la carga por persona

- DADO un colaborador con 3 tareas activas asignadas y 1 tarea adicional con `context_group` no nulo también asignada a él
- CUANDO el jefe consulta `GET /dashboard/executive`
- ENTONCES `workload` reporta 3 tareas para ese colaborador, sin incluir la de contexto

#### Scenario: Tarea de contexto no cuenta en los totales

- DADO una organización con 10 tareas totales, 2 de ellas con `context_group` no nulo
- CUANDO se consulta `totals`
- ENTONCES `totals.tasks` reporta 8: excluye las 2 tareas de contexto

#### Scenario: Tarea de contexto vencida sigue apareciendo en at_risk

- DADO una tarea con `context_group` no nulo cuyo `due_date` ya pasó sin completarse
- CUANDO se consulta `at_risk`
- ENTONCES esa tarea aparece en `at_risk`, a pesar de estar excluida de `by_assignee`, de `workload` y de `totals.tasks`, y `totals.at_risk` la cuenta: coincide con la cantidad de elementos de `at_risk`

## Referencias

- `openspec/specs/dashboard-executive/spec.md` (línea base, R1 en `:22` y R3 en `:24`)
- `backend/app/modules/dashboard/service.py` — `_build_by_assignee` (`:184-220`), `_build_workload` (`:234-259`), `_build_at_risk` (`:222-232`) y `_build_totals` (`:297-316`)
- `openspec/changes/44-importar-checklist-xlsx/specs/tasks/spec.md` (columna `context_group`, ADDED en este mismo cambio)
- `openspec/changes/44-importar-checklist-xlsx/{proposal,exploration}.md` (decisión D3 del orquestador)
