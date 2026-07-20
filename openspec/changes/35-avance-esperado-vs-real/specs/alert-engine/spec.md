# Delta for alert-engine

## ADDED Requirements

### Requirement: Estrategia de refuerzo `project_reinforcement`

El registro de estrategias DEBE incluir `project_reinforcement`, evaluada por el scheduler horario existente. Un proyecto genera un candidato cuando su semáforo (capability `project-progress`) es `amarillo` o `rojo` y su `real_pct < 100`. El mensaje DEBE ser accionable: "Para cumplir el {fecha}, esta semana el equipo debe completar {N} horas", donde `{fecha}` es el máximo `due_date` del alcance y `{N} = techo(horas_pendientes_del_alcance / semanas_laborales_restantes_hasta_{fecha})` (mínimo 1 semana). El `dedup_key` DEBE ser `project_reinforcement:{project_id}:{iso_week}:{recipient_user_id}`, para disparar como máximo una vez por semana, proyecto y destinatario. Los destinatarios DEBEN ser los miembros con rol `admin` o `manager` de la organización del proyecto.

#### Scenario: Refuerzo con cálculo de horas concreto

- GIVEN un proyecto con semáforo `rojo`, 40 horas pendientes y `due_date` máximo a 2 semanas laborales de hoy
- WHEN corre el evaluador
- THEN genera un candidato con cuerpo que incluye "20 horas" (40/2) para cada admin/manager de la organización

#### Scenario: Última semana antes del vencimiento

- GIVEN un proyecto con 15 horas pendientes y su `due_date` máximo dentro de la semana ISO en curso
- WHEN corre el evaluador
- THEN el candidato pide las 15 horas completas esta semana (1 semana laboral restante, mínimo)

#### Scenario: Sin refuerzo cuando el semáforo es verde

- GIVEN un proyecto con semáforo `verde`
- WHEN corre el evaluador
- THEN no se genera ningún candidato `project_reinforcement` para ese proyecto

#### Scenario: Dedup semanal por proyecto y destinatario

- GIVEN un candidato `project_reinforcement` ya notificado a un admin en la semana ISO actual
- WHEN el evaluador corre de nuevo esa misma semana sin cambios
- THEN no se crea una segunda notificación para ese mismo `dedup_key`

## MODIFIED Requirements

### Requirement: Seed idempotente de reglas de alerta por defecto (incluye refuerzo de proyecto)

Dado una organización sin reglas de alerta, cuando corre el seed de reglas por defecto, la organización DEBE quedar con 8 reglas activas (task_overdue, task_at_risk, sprint_at_risk, workload_imbalance, blocked_task, license_expiring, license_expired, project_reinforcement). Si el seed se ejecuta nuevamente, DEBE seguir habiendo exactamente una regla activa por cada `rule_type`, sin duplicados.
(Previously: el seed creaba 7 reglas activas, sin `project_reinforcement`.)

#### Scenario: Seed inicial con 8 reglas

- GIVEN una organización recién creada
- WHEN corre el seed de reglas por defecto
- THEN queda con exactamente 8 reglas activas, una por cada `rule_type` conocido

#### Scenario: Seed re-ejecutado no duplica

- GIVEN una organización que ya tiene las 8 reglas
- WHEN el seed corre de nuevo
- THEN sigue habiendo exactamente una regla activa por `rule_type`, sin duplicados

## Referencias

- `openspec/specs/alert-engine/spec.md` (línea base)
- `openspec/changes/35-avance-esperado-vs-real/proposal.md`
- `openspec/changes/35-avance-esperado-vs-real/specs/project-progress/spec.md`
