# Delta para alert-engine: estrategia blocked_task

## ADDED Requirements

### Requirement: Estrategia blocked_task registrada en el registry

El registry de estrategias de alerta DEBE incluir `blocked_task` (`rule_type=blocked_task`), evaluando las tareas con al menos un enlace `is_blocked_by` activo hacia una tarea no completada durante más de `threshold_params.days` días, y notificando al assignee de la tarea bloqueada.

#### Scenario: Notificación por bloqueo prolongado

- DADO una tarea bloqueada por otra tarea activa desde hace más de `threshold_params.days=3` días, con la regla blocked_task habilitada
- CUANDO corre el evaluador
- ENTONCES el assignee de la tarea bloqueada recibe una notificación in-app

#### Scenario: Sin notificación por bloqueo reciente

- DADO una tarea bloqueada desde hace 1 día, con `threshold_params.days=3`
- CUANDO corre el evaluador
- ENTONCES no se genera ninguna notificación de blocked_task para esa tarea

### Requirement: Deduplicación de la notificación blocked_task

El evaluador DEBE aplicar la deduplicación estándar (`exists_active(org, dedup_key)`) a los candidatos de blocked_task, de modo que corridas repetidas del scheduler no generen notificaciones duplicadas mientras el bloqueo siga activo.

#### Scenario: Corridas repetidas sin duplicar

- DADO una tarea bloqueada que ya generó una notificación blocked_task activa
- CUANDO el evaluador corre nuevamente sin que cambie la condición de bloqueo
- ENTONCES no se crea una segunda notificación para el mismo dedup_key

### Requirement: Seed idempotente de la regla blocked_task por defecto

El seed de reglas por defecto (`db_init.py`) DEBE crear, para cada organización, la quinta regla `blocked_task` (junto con las 4 existentes) de forma idempotente: ejecutar el seed más de una vez NO DEBE crear reglas duplicadas del mismo `rule_type`.

#### Scenario: Seed inicial

- DADO una organización sin reglas de alerta
- CUANDO corre el seed de reglas por defecto
- ENTONCES la organización queda con 5 reglas activas, incluida blocked_task

#### Scenario: Re-seed sin duplicar

- DADO una organización que ya tiene sus 5 reglas por defecto, incluida blocked_task
- CUANDO el seed se ejecuta nuevamente
- ENTONCES la organización sigue teniendo exactamente una regla activa por cada `rule_type`, sin duplicados
