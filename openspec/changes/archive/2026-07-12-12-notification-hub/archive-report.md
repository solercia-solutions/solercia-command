# Archive Report — 12 · Notification Hub

**Cambio**: `12-notification-hub` (hub agnóstico al canal, puerto DeliveryChannel + registro de canales, outbox generalizado, adaptadores durable/best_effort)
**Fecha de archivo**: 2026-07-12
**Modo**: hybrid (openspec + engram)
**Estado final**: ✅ DONE

---

## Ciclo SDD completo

### Fase 1 — Proposal
- **Propuesta**: standardize canal-agnostic hub (fanout único), reemplaza cableado manual (`buffer_notification` + `enqueue_immediate_email` side-by-side)
- **Decisión de arquitecto**: puerto `DeliveryChannel` (dos protocolos disjuntos por política: durable → `enqueue(db,n)` + `deliver(payload)`, best_effort → `buffer(db,n)`), registro mutable import-time
- **Outbox generalizado**: `email_outbox` → `notification_deliveries` (rename en sitio, `channel`+`payload` JSONB agnóstico)
- **Aislamiento de fallos**: try/except por canal en `create()` — falla de uno no afecta a los demás ni a la transacción de negocio
- **Extensibilidad**: canales futuros (FCM/APNs/SMS/webhook) = clase nueva + registro, cero cambios en núcleo

**Artefacto**: `openspec/changes/12-notification-hub/proposal.md`

### Fase 2 — Spec
- **Spec NUEVA**: `notification-hub` — 6 requisitos: puerto extensible + fan-out único con aislamiento de fallos + entrega durable auditable + endpoint `/deliveries` + tolerancia digest + extensibilidad futura
- **Deltas MODIFIED/ADDED**:
  - `notifications-inapp`: publicación vía hub (no cableada)
  - `email-notifications`: adaptador durable sin cambio observable
  - `realtime-notifications`: adaptador best_effort sin cambio observable
- **22 escenarios** verificados en etapa verify

**Artefactos**: specs con deltas en `openspec/changes/12-notification-hub/specs/`

### Fase 3 — Design
- **D1 Ubicación**: engine `app/notify/` (puerto, registro, store, despachador genérico), canales en sus dominios (email en `app/email`, WS en `app/realtime`) con registración
- **D2 Dos protocolos por política**: `DurableChannel` y `BestEffortChannel` disjuntos, no un protocolo único con métodos opcionales
- **D3 Rename en sitio + despachador genérico**: `email_outbox` → `notification_deliveries`, reusa contrato transaccional byte a byte (claim atómico `pending→sending` + commit ANTES del send)
- **D4 Gating sin flag nuevo**: `has_active_durable_channel()` == `EMAIL_ENABLED`, no se agrega `NOTIFY_ENABLED` ambiguo
- **D5 Tres canales**: InApp no es canal (es la fuente de verdad REST), WS best_effort, Email durable
- **D6 Gate del endpoint `/deliveries`**: admin/manager ONLY (sin excepción de dueño), aislamiento multi-tenant, digest opción (b) con `notification_id=NULL`+`emailed_at`
- **Decisión de gate CRITICAL corregida (dos veces)**: (1) aislamiento de fallos vía try/except en `create()`, (2) bootstrap de canales en `db_init.py` (punto único para main/tests/alembic)
- **Presupuesto**: ~700-900 líneas, split en 3 lotes

**Artefacto**: `openspec/changes/12-notification-hub/design.md`

### Fase 4 — Tasks
- **26 tareas** (T1.1–T3.8) divididas en 3 lotes funcionales:
  - **Lote 1** (T1.1–T1.9): migración 0013 (rename+channel+payload+copia) + `NotificationDelivery` + store port + RED test de round-trip upgrade/downgrade
  - **Lote 2** (T2.1–T2.19): puertos+registry+despachador genérico + refactor Email/WS como adaptadores + `create()` itera registro con aislamiento de fallos + eliminar `EmailOutbox` + adaptar tests existentes
  - **Lote 3** (T3.1–T3.8): endpoint `/deliveries` + fronteras de extracción + suite completa 561/561 tests
- **TDD estricto**: RED antes de GREEN; cada lote verifica sin regresiones
- **Trazabilidad**: cada tarea vinculada a req de spec (R1–R10)

**Artefacto**: `openspec/changes/12-notification-hub/tasks.md`

### Fase 5 — Apply
- **3 commits stacked a main**:
  1. `feat(notify): migracion 0013 y store de entregas generalizado` — migración rename en sitio + NotificationDelivery + store.enqueue_delivery
  2. `refactor(notify): puertos registro despachador y canales durable/best_effort` — puertos+registro+despachador + EmailChannel + WebSocketChannel + `create()` itera + eliminar EmailOutbox + adaptar tests
  3. `feat(notify): endpoint de auditoria de entregas` — `GET /{id}/deliveries` + fronteras de extracción documentadas
- **22 tests nuevos**: notify_store (2), notify_registry (1), notify_dispatcher (3), notification_repository_fanout (2), notification_deliveries_endpoint (5), email_outbox/dispatch/digest adaptados (9)
- **Migración 0013**: rename atómico con round-trip probado, índices renombrados (ambos sentidos upgrade/downgrade)
- **Correcciones de implementación documentadas**:
  - Renombre de índices `ix_email_outbox_*` → `ix_notification_deliveries_*` (ambos sentidos)
  - Bootstrap del registro en `db_init.py` (punto único usado por main/tests/alembic)

**Artefacto**: aplicado al código; evidencia en apply-progress

### Fase 6 — Verify
- ✅ **561/561 tests PASS** (539 base + 22 nuevos)
- ✅ **ruff + mypy limpios** — cero hallazgos
- ✅ **Cadena de migraciones**: 0012→0013 upgrade/downgrade/upgrade sin diff en BD desechable, `alembic check` cero diff
- ✅ **Tasks 26/26 completadas**: checkboxes coherentes con código
- ✅ **Black-box verificado contra contenedor reconstruido**:
  - Login admin + POST /tasks/{id}/comments @usuario → notificación in-app inmediata
  - GET /notifications/{id}/deliveries con token admin → `200`, entregas vacías (EMAIL_ENABLED deshabilitado en entorno)
  - GET /notifications/{id}/deliveries con token carlos (MEMBER, dueño de notificación) → `403` sin excepción
  - WS smoke: handshake autenticado, `connection.ack` recibido
- ✅ **Contrato de refactor**: 0 diff en test_realtime_manager y test_mention_notifications (WS 100% intacto), aserciones idénticas en tests de email tras adaptar imports/accesos a payload
- ✅ **Aislamiento de fallos**: canal fake que lanza no impide que el canal sano reciba ni que la tx de negocio sobreviva
- ✅ **Dos desviaciones documentadas, corregidas ante gate**:
  1. Renombre de índices (necesario, refactor limpio)
  2. Bootstrap del registro en db_init (necesario para determinismo cross-test/main/alembic)

**Artefacto**: `openspec/changes/12-notification-hub/verify-report.md` (PASS)

---

## Resumen de cambios archivados

| Artefacto | Cambio | Acción |
|-----------|--------|--------|
| `openspec/specs/notification-hub/spec.md` | NUEVA | Creada con 6 requisitos del hub agnóstico |
| `openspec/specs/notifications-inapp/spec.md` | MODIFIED | Actualizada línea Origen, 2 requisitos modificados (fan-out vía hub) |
| `openspec/specs/email-notifications/spec.md` | MODIFIED | Actualizada línea Origen, 1 requisito ADDED (adaptador durable) |
| `openspec/specs/realtime-notifications/spec.md` | MODIFIED | Actualizada línea Origen, 1 requisito ADDED (adaptador best_effort) |
| `openspec/specs/README.md` | MODIFIED | Fila `notification-hub` nueva + filas de 3 specs modificadas con cambio 12 |
| `openspec/AVANCE.md` | MODIFIED | Mermaid con C12, fila en tabla con 🟩 Completado, total tests 561 |
| `docs/API.md` | MODIFIED | Entrada `/notifications/{id}/deliveries` en resumen + documentación completa del endpoint + sección "Arquitectura de entregas" |
| `openspec/changes/12-notification-hub/state.yaml` | MODIFIED | `archive: pending` → `archive: done` |

---

## Notas de implementación

### Decisión de arquitectura notable: Aislamiento de fallos

En el design inicial se sugería ejecutar channel.enqueue/buffer directamente sin manejo de excepciones. La implementación correcta es:

```python
for ch in get_channels():
    try:
        if ch.policy == DeliveryPolicy.durable:
            await ch.enqueue(db, n)
        else:
            ch.buffer(db, n)
    except Exception:
        logger.exception(f"Fallo en canal {ch.name}")
        # No propaga la excepción; la tx de negocio continúa
```

**Motivación**: un usuario puede crear notificaciones urgentes desde múltiples rutas (mención, evaluador de alertas, etc.), y un canal caído no debe romper la creación. Logged para auditoría, sin impacto en la transacción.

### Correcciones de gate documentadas

**Gate 1: Aislamiento de fallos**
- Observación: una notificación urgente que lanza una excepción en un adaptador debería fallar toda la creación.
- Resolución: try/except + log en `create()` permite que el fallo de un canal no afecte a los demás ni a la transacción de negocio. Probado con test_notification_repository_fanout.py.

**Gate 2: Bootstrap del registro de canales**
- Observación: al correr un test aislado, los canales no estaban registrados (vacío en `get_channels()`).
- Resolución: `db_init.py` ahora importa `app.email.outbox` y `app.realtime.publisher` para que EmailChannel y WebSocketChannel se registren en el ÚNICO punto usado por main, tests y alembic env.py.

---

## SDD Cycle Closure

✅ El cambio **12-notification-hub** completa la **estandarización del sistema de notificaciones**:
- ✅ Canal email agnóstico al proveedor (cambio 08): adaptador durable registrado
- ✅ Canal WebSocket en tiempo real (cambio 09): adaptador best_effort registrado
- ✅ Hub agnóstico al canal (cambio 12): puerto común + registro + despachador genérico + auditoría de entregas

**Todos los 12 cambios del roadmap backend (01 a 12) están archivados** — backend MVP funcional y listo. Frontend EN PAUSA — espera @solercia/ui.

---

## Trazabilidad de artefactos

| Artefacto | Topic Key |
|-----------|-----------|
| Proposal | `sdd/12-notification-hub/proposal` |
| Spec | `sdd/12-notification-hub/spec` |
| Design | `sdd/12-notification-hub/design` |
| Tasks | `sdd/12-notification-hub/tasks` |
| Verify-report | `sdd/12-notification-hub/verify-report` |
| **Archive-report** | `sdd/12-notification-hub/archive-report` |

Todos persisten en Engram con scope `project:gestion_proyectos` para auditabilidad del ciclo.
