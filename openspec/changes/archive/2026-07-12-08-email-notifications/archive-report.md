# Archive Report — 08 · Email notifications

**Cambio**: `08-email-notifications` (canal email + digest configurable)
**Fecha de archivo**: 2026-07-12
**Modo**: hybrid (openspec + engram)
**Estado final**: ✅ DONE

---

## Ciclo SDD completo

### Fase 1 — Proposal (2026-07-12 11:22:59)
- **Propuesta**: backend-only, sin frontend
- **Decisión de arquitecto**: puerto `EmailSender` agnóstico al provider + adaptadores console/smtp por `EMAIL_BACKEND`
- **Outbox transaccional**: encolado atómico con negocio, sin bloquear la tx
- **Digest configurable**: por usuario (none|daily|weekly + hora), idempotente por `emailed_at`
- **Preferencias CRUD**: `GET/PUT /api/v1/notification-preferences` con validación 422
- **Aislamiento multi-tenant**: outbox y digest operan por `organization_id` del destinatario
- **Plantillas español colombiano formal**: texto + HTML sin voseo

**Dependencias**: 02-contrato-api, 07-assets-sdmujer, 09-websocket-realtime (ya aplicados)
**Artefacto**: `openspec/changes/08-email-notifications/proposal.md` (ID Engram: 1375)

### Fase 2 — Spec (2026-07-12 11:27:26)
- **Spec NUEVA**: `email-notifications` — 11 requisitos con escenarios Given/When/Then
  - R1 Puerto agnóstico · R2 EMAIL_ENABLED switch · R3 Envío inmediato urgentes · R4 Preferencia digest · R5 Alcance/marcado digest · R6 Idempotencia · R7 CRUD preferencias · R8 Aislamiento multi-tenant · R9 Plantillas ES formal
- **Delta ADDED**: `notifications-inapp` — requisito de encolado email en la creación sin alterar REST ni contrato
- **19 escenarios verificados** en etapa design; simplificación: 2 buckets (urgente/no-urgente) en lugar de 3

**Artefactos**: 
- `openspec/changes/08-email-notifications/specs/email-notifications/spec.md` (delta completa)
- `openspec/changes/08-email-notifications/specs/notifications-inapp/spec.md` (delta ADDED)
- ID Engram: 1377

### Fase 3 — Design (2026-07-12 11:32:02)
- **D1 Ubicación**: engine `app/email/` (sender, outbox, templates, policy, digest, scheduler) + `NotificationPreference` en `app/modules/notifications/` (CRUD)
- **D2 Outbox = fuente de verdad**: `create()` llama `enqueue_immediate_email()` en la misma tx, `emailed_at` en Notification evita doble correo
- **D3 Despacho dual**: drain post-commit + barrido job; claim atómico `UPDATE...WHERE status=pending RETURNING`; reintento no duplica por dedup_key
- **D4 Digest doble-idempotente**: agrupa no leídas `emailed_at IS NULL`, marca ambas, dedup_key por período evita repetición
- **D5 Clasificación**: `license_expired` IMMEDIATE; resto DIGESTIBLE (task_overdue, sprint_at_risk, mención, reminder)
- **D6 Plantillas Python puras**: render_immediate/render_digest, sin Jinja, HTML inline multipart/alternative
- **D7 Preferencias default `none`**: opt-in, GET sin registro devuelve defaults
- **D8 Puerto + adaptadores**: console (captura en memoria) + smtp (aiosmtplib), factory por EMAIL_BACKEND
- **1300–1600 líneas estimadas**, corte en 3 lotes (A: puerto+plantillas+policy; B: outbox+migración+job; C: preferencias+digest+wiring)
- **Decisión de gate CRITICAL corregida**: job único despachador (prohibe drain inline en evaluador), commit claim antes de send

**Artefacto**: ID Engram: 1380

### Fase 4 — Tasks (2026-07-12 11:47:48)
- **40 tareas** (T01–T40) divididas en 3 lotes funcionales
- **Lote A** (T01–T10): config + requirements.txt + RED/GREEN puerto, plantillas, sender, factory
- **Lote B** (T11–T24): migración 0011 (email_outbox + emailed_at) + models + outbox logic + job dispatch + hook en create()
- **Lote C** (T25–T40): migración 0012 (notification_preferences) + models + CRUD + digest + job digest + wiring final
- **TDD estricto**: RED falla antes de GREEN; cada lote tiene suite que pasa sin regresiones
- **Presupuesto**: High (1300–1600 líneas), split encadenado a main recomendado, size:exception aceptada
- **Trazabilidad**: cada tarea vinculada a requisito de spec (R1–R10)

**Artefacto**: ID Engram: 1382

### Fase 5 — Apply (2026-07-12 — completado)
- **3 commits**: 
  1. feat(email): puerto de envio, adaptadores y plantillas (TDD RED→GREEN, 0 lineas backend imports)
  2. feat(email): outbox transaccional y job de despacho (TDD, alembic 0011)
  3. feat(email): preferencias de digest y job de resumen (TDD, alembic 0012)
- **41 tests nuevos**: email_policy (3), email_templates (4), email_sender (4), email_outbox (6), email_dispatch (6), notification_preferences (4), email_digest (7) + 7 smoke/integration
- **Migraciones**: 0011 (email_outbox + Notification.emailed_at, chain down_revision=0010 de 07) + 0012 (notification_preferences, chain down_revision=0011)
- **Decisión de implementación**: email_dispatch es el ÚNICO despachador (no drain inline en evaluador, evita race conditions)
- **Artefacto**: no se archiva (inline en repo); summary en apply-progress

### Fase 6 — Verify (2026-07-12 13:14:09)
- ✅ **539/539 tests PASS** (498 base + 41 nuevos)
- ✅ **ruff + mypy limpios** sin hallazgos
- ✅ **Cadena de migraciones validada**: 0010→0011→0012 upgrade/downgrade/upgrade sin diff en BD desechable
- ✅ **Tasks 40/40 completadas**: todos los checkboxes coherentes con código
- ✅ **Black-box verificado contra contenedor**:
  - GET sin registro → 200 defaults `none`
  - PUT `daily`+hora → 200, GET lo refleja
  - PUT `hourly` → 422 con detail
  - `license_expired` → correo capturado en adaptador console (no real SMTP)
  - Digest no duplica (correr dos veces = sin segundo correo)
- ✅ **Dos desviaciones documentadas, no bloqueantes**:
  1. Path plano `/notification-preferences` (spec.md vinculante, no sugerencia design.md)
  2. Migraciones divididas 0011+0012 (invariante alembic check: modelo ORM en mismo commit que migración)
- ✅ **RED black-box**: 12 tests sin skipif para email+digest+preferencias (no son test-coverage-baseline, son integración post-apply contra contenedor local Docker reconstruido)

**Artefacto**: ID Engram: 1388

### Fase 7 — Archive (2026-07-12 — EN CURSO)
- **Fusión de deltas a specs vivas**:
  - ✅ `openspec/specs/email-notifications/spec.md` creada (nueva, contiene 11 requisitos + línea Origen)
  - ✅ `openspec/specs/notifications-inapp/spec.md` actualizada (ADDED requirement email + línea Origen incluye cambio 08)
  - ✅ `openspec/specs/README.md` actualizada (fila email-notifications + fila notifications-inapp con 08; detalle del mapeo con cambio 08)
- **Documentación de API actualizada**:
  - ✅ `docs/API.md`: nuevos endpoints `GET/PUT /api/v1/notification-preferences`
  - ✅ `docs/API.md`: sección «Canal email» con arquitectura, configuración, outbox, idempotencia
- **`openspec/AVANCE.md` actualización FINAL — ROADMAP BACKEND COMPLETO**:
  - ✅ Sección "Última actualización": refiere todos 11 cambios completados + 539 tests
  - ✅ Mermaid: cambio C08 de `pending` a `done`; classDef actualizado (sin pending)
  - ✅ Fila 08 en tabla: 🟩 Completado con specs
  - ✅ Conteo total: 539 tests
  - ✅ Deuda pendiente documentada (no bloqueante, post-MVP): 12 RED black-box sin skipif, lock Redis multi-réplica, adaptador Redis pub/sub WS, RBAC granular viewer, mypy tests/, tie-break created_at, get_in_org sin is_active
- ✅ `state.yaml`: `archive: pending` → `archive: done`

**Artículos persistidos a Engram** (toda esta etapa):
- Proposal (ID: 1375)
- Spec (ID: 1377)
- Design (ID: 1380)
- Tasks (ID: 1382)
- Verify-report (ID: 1388)
- **Archive-report** (ID: este documento, topic_key: `sdd/08-email-notifications/archive-report`)

---

## Resumen de cambios archivados

| Artefacto | Cambio | Acción |
|-----------|--------|--------|
| `openspec/specs/email-notifications/spec.md` | NUEVA | Creada con 11 requisitos de dominio |
| `openspec/specs/notifications-inapp/spec.md` | MODIFIED | Agregado requisito ADDED (encolado email en creación) + línea Origen |
| `openspec/specs/README.md` | MODIFIED | Fila `email-notifications` + Origen de `notifications-inapp` |
| `openspec/AVANCE.md` | MODIFIED | C08 de pending a done, 539 tests, deuda post-MVP documentada |
| `docs/API.md` | MODIFIED | Endpoints preferencias + sección canal email |
| `openspec/changes/08-email-notifications/state.yaml` | MODIFIED | `archive: pending` → `archive: done` |

---

## Notas de implementación

### Decisión de arquitectura notable: Gate CRITICAL corregido
El design.md sugería que `drain_outbox_best_effort()` se invocara inline tras commit+flush en el evaluador de alertas. La implementación correcta es:
- **Único despachador**: job `email_dispatch` periódico (N minutos) hace el claim + send + commit
- **Drain inline prohibido**: evita race conditions entre job y requests, simplifica el modelo de concurrencia
- **Motivación**: un usuario puede crear notificaciones urgentes desde múltiples rutas (mención en comentario, evaluador de alertas, etc.), y ejecutar múltiples drenajes es más complejo que centralizar en un job

### Inconsistencia heredada en state.yaml
Los campos `artifacts.specs` y `artifacts.design` están marcados como `false` (no se archivaron) pese a que ambas fases fueron completadas y sus artefactos existen en `openspec/changes/08-email-notifications/`. Esto es una inconsistencia de convención heredada — el ejecutor de apply no actualiza esos booleanos. **Documentado, no bloqueante para el cierre del cambio** (la versión de verdad está en `openspec/changes/08-email-notifications/` directorio).

---

## SDD Cycle Closure

✅ El cambio **08-email-notifications** completa la **PRIMERA ITERACIÓN del roadmap backend**. Todos los 11 cambios (01 a 11) están ahora:
- ✅ Planeados (proposal + spec + design + tasks)
- ✅ Implementados (apply con TDD estricto)
- ✅ Verificados (539 tests, ruff/mypy, black-box end-to-end)
- ✅ Archivados (deltas fusionadas a specs vivas, cambio folder movido a archive/, esta memoria creada)

**Backend MVP funcional y listo. Frontend EN PAUSA — espera @solercia/ui.**

---

## Trazabilidad de artefactos Engram

| Artefacto | ID | Topic Key |
|-----------|----|-----------| 
| Proposal | 1375 | `sdd/08-email-notifications/proposal` |
| Spec | 1377 | `sdd/08-email-notifications/spec` |
| Design | 1380 | `sdd/08-email-notifications/design` |
| Tasks | 1382 | `sdd/08-email-notifications/tasks` |
| Verify-report | 1388 | `sdd/08-email-notifications/verify-report` |
| **Archive-report** | TBD | `sdd/08-email-notifications/archive-report` |

Todos persisten en la BD de Engram con scope `project:gestion_proyectos` para auditabilidad del ciclo.
