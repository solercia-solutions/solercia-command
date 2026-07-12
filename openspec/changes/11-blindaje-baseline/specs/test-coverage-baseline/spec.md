# test-coverage-baseline Specification

## Purpose

Contrato transversal de cobertura de pruebas para blindar la línea base as-built (cambio 11). No define comportamiento de producto nuevo: define qué suites DEBEN existir sobre los escenarios de `openspec/specs/*/spec.md`, más dos requisitos sin cobertura hoy: matriz de permisos vigente por endpoint y aislamiento entre tenants.

## Requirements

### Requirement: Cobertura por capacidad derivada de los escenarios as-built

Por cada una de las 10 capacidades objetivo, el backend DEBE tener al menos un test automatizado por cada escenario Dado/Cuando/Entonces de su spec as-built, escrito primero en rojo (TDD estricto) y luego llevado a verde sin alterar el comportamiento documentado.

| Capacidad | Spec fuente | Requisitos a cubrir |
|---|---|---|
| auth | `specs/auth` | R1–R5 |
| users-admin | `specs/users-admin` | R1–R4 |
| rbac-catalog | `specs/rbac-catalog` | R1–R4 |
| multi-tenancy | `specs/multi-tenancy` | R1–R4 |
| projects | `specs/projects` | R1–R4 |
| tasks | `specs/tasks` | R1–R6 |
| methodology-strategies | `specs/methodology-strategies` | R1–R4 |
| alert-engine | `specs/alert-engine` | R1–R4 (ver requisito dedicado; R5–R7 —`blocked_task`— ya cubiertos por `test_blocked_task_alert.py` del cambio 04, NO se duplican) |
| notifications-inapp | `specs/notifications-inapp` | R1–R4 |
| dashboard-executive | `specs/dashboard-executive` | R1–R4 + work_gap |

#### Scenario: Suite verde derivada del spec as-built

- GIVEN el spec as-built de una capacidad objetivo
- WHEN se ejecuta su suite de tests
- THEN cada escenario documentado tiene al menos un test y la suite pasa en verde

#### Scenario: Test nace en rojo

- GIVEN un escenario del spec as-built sin test previo
- WHEN se escribe el test antes de tocar producción
- THEN falla (rojo) en su primera ejecución, confirmando que ejercita comportamiento real

### Requirement: Matriz de permisos por endpoint (comportamiento vigente)

Conviven dos mecanismos de rol: `MemberRole` (admin/manager/member/viewer; definido en `dependencies.py` pero NO aplicado como `require_role()` en ningún router hoy) y el catálogo RBAC (`require_admin`, exige `Role.code == 'ADMIN'`). La suite DEBE verificar, por endpoint, el gate REALMENTE implementado, no un modelo ideal.

| Gate efectivo vigente | Endpoints |
|---|---|
| `require_admin` (RBAC ADMIN) | users-admin (todos), rbac-catalog (todos), `PATCH /alert-rules/{id}`, `POST /alerts/evaluate` |
| Dueño del recurso (`user_id` propio) | `PATCH`/`DELETE /time-logs/{id}` |
| `MemberRole` admin\|manager (inline) | `GET /users/{id}/time-logs` de otro usuario |
| Solo autenticación + membresía | projects, tasks, methodology (lectura), `GET /alert-rules`, notifications-inapp, dashboard-executive |

#### Scenario: Endpoint admin-only rechaza roles no-ADMIN

- GIVEN usuarios con y sin rol RBAC ADMIN en la misma organización
- WHEN cada uno llama un endpoint gateado por `require_admin`
- THEN solo el usuario ADMIN recibe 2xx; el resto recibe 403

#### Scenario: Endpoint sin gate de rol acepta cualquier miembro

- GIVEN usuarios con `MemberRole` admin, manager, member y viewer
- WHEN cada uno llama un endpoint sin gate de rol (ej. projects, dashboard-executive)
- THEN los cuatro reciben 2xx, documentando el comportamiento vigente

### Requirement: Aislamiento entre tenants con fixture de dos organizaciones

Toda suite de un endpoint tenant-scoped (todas las capacidades objetivo salvo el catálogo global de menús) DEBE usar un fixture con DOS organizaciones, cada una con datos propios (proyecto, tarea, regla de alerta y notificación). Los tests DEBEN afirmar que un miembro de A nunca lista, lee, edita ni borra un recurso cuyo `organization_id` (propio o de su ancestro, ej. Task→Project) pertenezca a B.

#### Scenario: Listado no cruza organizaciones

- GIVEN dos organizaciones A y B con proyectos y tareas propios
- WHEN un miembro de A lista `/projects` o `/tasks`
- THEN la respuesta solo contiene registros de A

#### Scenario: Acceso directo a recurso ajeno rechazado

- GIVEN un recurso de la organización B
- WHEN un miembro de A intenta `GET`/`PATCH`/`DELETE` ese recurso por su id
- THEN la API responde 403 o 404 y el recurso de B no cambia ni se expone

### Requirement: Cobertura del motor de alertas (4 estrategias + evaluator + scheduler + dedup)

La suite DEBE cubrir, sin depender del reloj real: las 4 estrategias de `rule_type` sin test previo (`task_overdue`, `task_at_risk`, `sprint_at_risk`, `workload_imbalance`; la quinta, `blocked_task`, ya está cubierta por `test_blocked_task_alert.py` y se excluye), la iteración de reglas `enabled` por organización, el gate de deduplicación (`exists_active`) y el disparo del scheduler — probando idempotencia por repetición de entrada, no por temporización real.

#### Scenario: Evaluación repetida no duplica notificación

- GIVEN una regla cuya condición sigue vigente
- WHEN el evaluador corre dos veces seguidas sin cambios en los datos
- THEN solo existe una notificación activa con ese `dedup_key`

#### Scenario: Cada estrategia produce su alerta esperada

- GIVEN datos que satisfacen la condición de cada una de las 4 estrategias
- WHEN el evaluador procesa las reglas `enabled` de la organización
- THEN cada estrategia genera la notificación correspondiente a su `rule_type`
