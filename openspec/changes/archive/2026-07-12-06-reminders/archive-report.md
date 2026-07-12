# Archive Report: 06 · Reminders (recordatorios manuales y automáticos)

**Fecha de archivo**: 2026-07-12  
**Estado**: ✅ COMPLETADO  
**Ciclo SDD**: proposal → spec → design → tasks → apply → verify → archive

---

## Resumen ejecutivo

El cambio 06-reminders ha sido completado, verificado y archivado. Se entregó la capacidad de **recordatorios personales manuales y automáticos por regla**, ambos integrados al motor de scheduler existente y materializados como notificaciones in-app. El sistema garantiza disparo idempotente, aislamiento multi-tenant/personal (ni un admin ve recordatorios ajenos), y soporte para cancelación concurrente sin doble disparo. Suite de tests: **439/439 verdes** (25 nuevos en 06, crecimiento 414→439).

---

## Trazabilidad de artefactos

| Fase | Artefacto | Ubicación | Observación |
|------|-----------|-----------|-------------|
| **Proposal** | proposal.md | `openspec/changes/06-reminders/proposal.md` | Scope, approach, risks, success criteria (6 requisitos, 3 estrategias de riesgo) |
| **Spec** | reminders/spec.md | `openspec/changes/06-reminders/specs/reminders/spec.md` | Spec delta nueva (capacidad NEW): Reminder + ReminderRule, 9 requirements, 21 escenarios |
| **Spec** | notifications-inapp/spec.md | `openspec/changes/06-reminders/specs/notifications-inapp/spec.md` | Delta ADDED: origen `rule_type="reminder"` en bandeja compartida |
| **Design** | design.md | `openspec/changes/06-reminders/design.md` | Decisiones arquitectónicas: claim atómico, dedup, gate anti-carrera (4 decisiones clave) |
| **Tasks** | tasks.md | `openspec/changes/06-reminders/tasks.md` | 22/22 tareas completadas; Fase A (CRUD+migración) + Fase B (motor+scheduler+admin); split stacked-to-main |
| **Apply** | (commits en main) | `backend/` | Dos commits: `5d3ba38` (Fase A: migración 0009 + CRUD) + `c4b1157` (Fase B: dispatcher+job) |
| **Verify** | verify-report.md | `openspec/changes/06-reminders/verify-report.md` | PASS; 439/439 tests, ruff/mypy limpios, 21/21 escenarios spec + 2/2 delta; contrato black-box contra contenedor |

---

## Fusión de deltas a specs vivas

### 1. Spec NUEVA: `openspec/specs/reminders/spec.md`

**Acción**: Creada (capacidad nueva)  
**Contenido**: Copia integra del delta `openspec/changes/06-reminders/specs/reminders/spec.md` + línea de origen.  
**Línea de origen**: `> **Origen**: cambio [06-reminders](../../changes/archive/2026-07-12-06-reminders/)`  
**Requisitos fusionados**: 9 requirements con 21 escenarios (creación manual, listado propio, edición/cancelación scheduled-only, aislamiento multi-tenant, ReminderRule config, disparo idempotente manual, disparo admin-only, omisión por tarea completada, disparo task_due_soon).

### 2. Spec MODIFICADA: `openspec/specs/notifications-inapp/spec.md`

**Acción**: ADDED requirement integrado  
**Línea de origen actualizada**: `> **Origen**: línea base as-built (2026-07-11) + [06-reminders](../../changes/archive/2026-07-12-06-reminders/)`  
**Delta fusionado**:
```
### Requirement: Origen "reminder" integrado a la bandeja compartida

El sistema MUST aceptar `rule_type="reminder"` como origen válido de `Notification`, 
generado por el disparo de un `Reminder` manual o por la evaluación de una `ReminderRule` 
(`task_due_soon`). Estas notificaciones MUST cumplir el mismo contrato ya vigente de la 
bandeja: privacidad por `recipient_user_id`, deduplicación por `dedup_key`, conteo de no 
leídas y ciclo de vida por `status`.

#### Scenario: Recordatorio manual aparece en la bandeja
#### Scenario: Deduplicación aplica igual que a mención y alertas
```

**Preservado**: Todo el contenido preexistente (R1–R4, campos, limitaciones). No hay requisitos modificados ni removidos — solo ADDED.

### 3. `openspec/specs/README.md`

**Cambios**:
- Fila **nueva** para reminders:  
  ```
  | Recordatorios (manuales y por regla) | [reminders](reminders/spec.md) | [06-reminders](../changes/archive/2026-07-12-06-reminders/) |
  ```
- Fila **actualizada** para notifications-inapp:  
  ```
  | Notificaciones in-app | [notifications-inapp](notifications-inapp/spec.md) | baseline + [06-reminders](../changes/archive/2026-07-12-06-reminders/) |
  ```
- Tabla de detalle de cambios archivados — fila **nueva** para 06-reminders:  
  ```
  | [06-reminders](../changes/archive/2026-07-12-06-reminders/) | `reminders/spec.md` (nueva), `notifications-inapp/spec.md` (ADDED) | `reminders` (creada: recordatorios manuales y por regla), `notifications-inapp` (modificada: origen `rule_type="reminder"`) |
  ```

---

## Actualización de documentación transversal

### `openspec/AVANCE.md`

**Cambios**:

1. **Línea "Última actualización"**:  
   - Antes: `...10-busqueda-global archivado... 11-blindaje-baseline archivado... 4 cambios backend pendientes`  
   - Después: `...06-reminders archivado — recordatorios manuales y automáticos por regla; \`Reminder\` + \`ReminderRule\` con disparo idempotente vía scheduler; origen \`rule_type="reminder"\` integrado a la bandeja compartida; 21 escenarios verificados, 439/439 tests verdes, ruff/mypy limpios... 3 cambios backend pendientes`

2. **Mermaid classDef**:  
   - Antes: `class C06,C07,C08,C09 pending`  
   - Después: `class C06 done` + `class C07,C08,C09 pending`

3. **Tabla de roadmap (fila 06)**:  
   - Estado: `⬜ Pendiente` → `🟩 Completado`  
   - Specs: `—` → `[reminders](specs/reminders/spec.md) (nueva) · [notifications-inapp](specs/notifications-inapp/spec.md) (modificada)`

4. **Sección "Lo construido"**:  
   - Antes: `Total tras cambio 10: **414 tests en 25 archivos**`  
   - Después: `Total tras cambio 06: **439 tests en 26 archivos** (43 en baseline + 296 en cambios 01-05 + 25 en cambio 06 + 32 en cambio 10 + 43 en cambio 11 = 439)`

### `docs/API.md`

**Agregados en tabla "Resumen de endpoints"** (sugerencia del verify-report resuelta):

8 nuevas filas de reminders/reminder-rules + 1 POST dispatch:
```
GET    /api/v1/reminders                    Sí   📄 Lista recordatorios personales
POST   /api/v1/reminders                    Sí      Crear recordatorio (futuro; 422 si ≤ ahora)
GET    /api/v1/reminders/{id}               Sí      Obtener recordatorio propio (404 si ajeno)
PATCH  /api/v1/reminders/{id}               Sí      Editar scheduled-only (422 en otro status)
DELETE /api/v1/reminders/{id}               Sí      Cancelar recordatorio
GET    /api/v1/reminder-rules               Sí   📄 Listar reglas del usuario
POST   /api/v1/reminder-rules               Sí      Crear regla (task_due_soon + lead_days)
PATCH  /api/v1/reminder-rules/{id}          Sí      Editar lead_days/enabled/params
POST   /api/v1/reminders/dispatch           Admin   Disparo admin-only (conteo creado)
```

**Actualización de contexto**:
- "20 routers" → "21 routers"  
- "17 endpoints paginables" → "19 endpoints paginables"

---

## Verificación de completitud

### Compuerta de tareas (Task Completion Gate) ✅ PASS

- `openspec/changes/06-reminders/tasks.md`: **22/22 tasks marcadas `[x]`**
- Fase A (T01–T09): CRUD + migración + 12 tests RED→GREEN
- Fase B (T10–T22): Motor + scheduler + 13 tests RED→GREEN
- Ambos commits existen en `main` y son verificables (`5d3ba38`, `c4b1157`)
- **Conclusión**: Cero tareas pendientes ni parciales. Estado de implementación confirmado.

### Compuerta de verificación ✅ PASS

- `openspec/changes/06-reminders/verify-report.md`: **PASS, 439/439 tests, 0 fallos**
- Migración 0009 aplicada (`alembic current` = 0009)
- No hay CRITICAL ni WARNING en el verify
- 21/21 escenarios de spec + 2/2 de delta con evidencia de test verde
- Contrato black-box (admin + member sin ADMIN):
  - POST /reminders (futuro): 201 ✓ | POST /reminders (pasado): 422 ✓
  - GET /reminders: 200 ✓ | POST /reminders/dispatch (admin): 200 ✓ | POST /reminders/dispatch (member): 403 ✓
- ruff y mypy: cero hallazgos
- **Conclusión**: Listo para archivar.

### Sugerencias del verify (no bloqueantes) 📋

**SUGGESTION 1** — `docs/API.md` no fue actualizado (RESUELTO en archive).  
✅ Se completó la documentación de los 9 endpoints + 1 dispatch en la tabla "Resumen de endpoints" y se actualizó el contexto (routers + paginables).

**SUGGESTION 2** — FK `reminders.user_id → users.id` con `ondelete="SET NULL"` sobre columna `nullable=False`.  
📝 **Documentada como deuda preexistente** (patrón igual en `0007_add_time_logs_and_task_history.py` para `TaskTimeLog.user_id`). No introducida por 06, no bloqueante, no resuelta en este cambio (corresponde a futuro hardening de modelo de datos).

---

## Desviaciones de diseño (validadas, correctas)

**Documentada en tasks.md, verificada en verify-report.md**:

- **"TaskDueSoonStrategy no filtra status='done'/'cancelled' literal"**: El modelo `Task` de este código no tiene estado global "cancelled" — `status` es string libre validado por metodología. El precedente real (`task_at_risk.py`) filtra solo `is_active` e `completed_at IS NULL`. Implementación coincide exactamente con el patrón. **Cubre 3 escenarios de R8** (completada/cancelada/borrada) con los 2 estados reales que el sistema modela.

---

## Contenido del archivo del cambio

**Ruta archivada**: `openspec/changes/archive/2026-07-12-06-reminders/` (git mv realizado por el orquestador)

**Contenido preservado**:
- `proposal.md` — Scope, approach, rollback plan
- `specs/reminders/spec.md` — Spec nueva (9 req, 21 esc)
- `specs/notifications-inapp/spec.md` — Delta ADDED
- `design.md` — 4 decisiones arquitectónicas
- `tasks.md` — 22/22 tareas + Fase A/B + trazabilidad
- `verify-report.md` — PASS, matriz de cumplimiento, hallazgos
- `state.yaml` — Cierre de todas las fases (archive: done)

---

## Impacto en la suite de tests

| Métrica | Antes (cambio 05) | Cambio 06 | Después |
|---------|------------------|-----------|---------|
| Tests totales | 414 | +25 | **439** |
| Archivos de test | 25 | +1 | 26 |
| Archivos backend/tests | `test_*.py` | `test_reminders.py`, `test_reminder_dispatch.py` | Nuevas suites |
| Ruff | 0 issues | 0 issues | 0 issues |
| Mypy | 0 issues | 0 issues | 0 issues |

---

## Cierre del ciclo SDD

✅ **Proposal**: Requerimientos y approach validados  
✅ **Spec**: 11 escenarios (9 reminders + 2 notifications-inapp delta) definidos y clavados  
✅ **Design**: 4 decisiones arquitectónicas documentadas  
✅ **Tasks**: 22/22 checkeadas, aplicadas, verificadas  
✅ **Apply**: 2 commits en main con cobertura TDD estricta  
✅ **Verify**: 439/439 tests verdes, contrato black-box confirmado  
✅ **Archive**: Deltas fusionados a specs vivas, documentación transversal actualizada, archivo movido

**Estado final**: 🟩 **COMPLETADO** — Listo para el próximo cambio (07-assets-sdmujer).
