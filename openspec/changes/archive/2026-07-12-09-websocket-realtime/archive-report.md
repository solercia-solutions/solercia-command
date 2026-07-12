# Archive Report: 09 · WebSocket realtime (push in-app en tiempo real)

**Fecha de archivo**: 2026-07-12  
**Estado**: ✅ COMPLETADO  
**Ciclo SDD**: proposal → spec → design → tasks → apply → verify → archive

---

## Resumen ejecutivo

El cambio 09-websocket-realtime ha sido completado, verificado y archivado. Se entregó la capacidad de **canal WebSocket que empuja notificaciones in-app en tiempo real**, complementando el polling REST sin reemplazarlo (best-effort, fuente de verdad sigue siendo REST). Implementación in-process con `ConnectionManager` en memoria (puerto aislado para migración futura a Redis pub/sub cuando haya réplicas). Auth por subprotocolo bearer estricto (cero fuga de token en URL). Handshake valida JWT, resuelve `(organization_id, user_id)`, scopes conexión a ambos; push dispara en `NotificationRepository.create()` (punto único); heartbeat ping/pong con cierre por inactividad. Suite de tests: **466/466 verdes** (27 nuevos en 09, crecimiento 439→466). Push real black-box end-to-end confirmado contra contenedor con mención vía REST → notificación WS en tiempo real.

---

## Trazabilidad de artefactos

| Fase | Artefacto | Ubicación | Observación |
|------|-----------|-----------|-------------|
| **Proposal** | proposal.md | `openspec/changes/09-websocket-realtime/proposal.md` | Scope, approach (in-process ConnectionManager, subprotocol bearer auth, best-effort), risks (auth WS, fan-out multi-réplica, fuga de conexiones), success criteria (6 requisitos, 11 escenarios) |
| **Spec** | realtime-notifications/spec.md | `openspec/changes/09-websocket-realtime/specs/realtime-notifications/spec.md` | Spec delta NUEVA (capacidad NEW): canal WS GET /api/v1/ws/notifications, 6 requirements, 13 escenarios (handshake autenticado, scoping org/user, push en creación, best-effort desconexión, heartbeat, envelope versionado) |
| **Spec** | notifications-inapp/spec.md | `openspec/changes/09-websocket-realtime/specs/notifications-inapp/spec.md` | Delta ADDED: publicación al canal realtime en creación (levanta limitación "canal único polling"), 1 requirement, 2 escenarios |
| **Design** | design.md | `openspec/changes/09-websocket-realtime/design.md` | Decisiones arquitectónicas: gate adversarial PASADO (flush_pending atómico post-commit, authenticate_access_token reutiliza AppException, E2E con dependency_overrides + NullPool, hook único en NotificationRepository.create), seam del puerto para Redis futura |
| **Tasks** | tasks.md | `openspec/changes/09-websocket-realtime/tasks.md` | 18/18 tareas completadas; Fase A (ConnectionManager + auth + schemas), Fase B (router WS + handshake), Fase C (hook en repository + alerts/comments); split stacked-to-main (3 commits directos a main) |
| **Apply** | (commits en main) | `backend/` | Tres commits: A (feat(realtime): manager + schemas + tests unit), B (feat(realtime): router + auth), C (feat(realtime): push integration + alerts/comments); TDD 3 fases, 27 tests nuevos totales |
| **Verify** | verify-report.md | `openspec/changes/09-websocket-realtime/verify-report.md` | PASS; 18/18 tareas verificadas en código real; 466/466 tests totales, 0 fallos (con TEST_AUTH_TOKEN + TEST_DATABASE_URL); ruff/mypy limpios; alembic head = 0009 (sin migraciones); contrato contra 6 requirements + 2 delta mapeado 1:1 a tests reales; black-box obligatorio contra contenedor reconstruido: handshake válido → connection.ack v:1, token inválido → rechazo HTTP 403, push real end-to-end (REST mention → WS notification.created en tiempo real, usuario `ana@solercia.com` recibió en su socket) |

---

## Fusión de deltas a specs vivas

### 1. Spec NUEVA: `openspec/specs/realtime-notifications/spec.md`

**Acción**: Creada (capacidad nueva)  
**Contenido**: Copia íntegra del delta `openspec/changes/09-websocket-realtime/specs/realtime-notifications/spec.md` + línea de origen.  
**Línea de origen**: `> **Origen**: cambio [09-websocket-realtime](../../changes/archive/2026-07-12-09-websocket-realtime/)`  
**Requirements fusionados**: 6 requirements con 13 escenarios totales (handshake autenticado, scoping estricto org/usuario, push en creación mención/alerta, best-effort desconexión, heartbeat ping/pong, envelope versionado v/type/data).

### 2. Spec MODIFICADA: `openspec/specs/notifications-inapp/spec.md`

**Acción**: ADDED requirement integrado  
**Línea de origen actualizada**: `> **Origen**: línea base as-built (2026-07-11) + [06-reminders](../../changes/archive/2026-07-12-06-reminders/) + [09-websocket-realtime](../../changes/archive/2026-07-12-09-websocket-realtime/)`  
**Delta fusionado**:
```
### Requirement: Publicación al canal realtime en la creación

Cuando el sistema crea una notificación (por mención o por el motor de alertas), 
MUST invocar, desde el punto único de creación, la publicación best-effort hacia 
el canal realtime (`realtime-notifications`) del `recipient_user_id`, sin alterar 
el modelo `Notification` ni el contrato de los endpoints REST existentes 
(`GET /notifications`, `GET /notifications/unread-count`, `PATCH /notifications/{id}`). 
Esto levanta la limitación de "canal único polling" documentada en la línea base.

#### Scenario: Creación dispara publicación
#### Scenario: REST sigue siendo autoritativo
```

**Preservado**: Todo el contenido preexistente (R1–R4, campos, limitaciones reminders, deuda). No hay requisitos modificados ni removidos — solo ADDED.

### 3. `openspec/specs/README.md`

**Cambios**:
- Fila **nueva** para realtime-notifications:  
  ```
  | Notificaciones en tiempo real | [realtime-notifications](realtime-notifications/spec.md) | [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) |
  ```
- Fila **actualizada** para notifications-inapp:  
  ```
  | Notificaciones in-app | [notifications-inapp](notifications-inapp/spec.md) | baseline + [06-reminders](../changes/archive/2026-07-12-06-reminders/) + [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) |
  ```
- Tabla de detalle de cambios archivados — fila **nueva** para 09-websocket-realtime:  
  ```
  | [09-websocket-realtime](../changes/archive/2026-07-12-09-websocket-realtime/) | `realtime-notifications/spec.md` (nueva), `notifications-inapp/spec.md` (ADDED) | `realtime-notifications` (creada: canal WS push en tiempo real), `notifications-inapp` (modificada: publicación best-effort al conectar) |
  ```

---

## Actualización de documentación transversal

### `openspec/AVANCE.md`

**Cambios**:

1. **Línea "Última actualización"**:  
   Agregado: `09-websocket-realtime archivado — canal WebSocket que empuja notificaciones in-app en tiempo real, best-effort, complementa polling REST; realtime-notifications (nueva capacidad) + notifications-inapp (delta ADDED sobre publicación); 13 escenarios verificados, 466/466 tests verdes, ruff/mypy limpios; push real black-box end-to-end confirmado contra contenedor; 2 cambios backend pendientes (07-assets-sdmujer y 08-email-notifications)`.

2. **Mermaid classDef**:  
   - Antes: `class C07,C08,C09 pending`  
   - Después: `class C07,C08 pending` + `class C09 done`

3. **Tabla de roadmap (fila 09)**:  
   - Estado: `⬜ Pendiente` → `🟩 Completado`  
   - Specs: `—` → `[realtime-notifications](specs/realtime-notifications/spec.md) (nueva) · [notifications-inapp](specs/notifications-inapp/spec.md) (modificada)`

4. **Sección "Lo construido"**:  
   - Antes: `Total tras cambio 06: **439 tests en 26 archivos**`  
   - Después: `Total tras cambio 09: **466 tests en 27 archivos** (43 en baseline + 296 en cambios 01-05 + 25 en cambio 06 + 32 en cambio 10 + 43 en cambio 11 + 27 en cambio 09 = 466)`

### `docs/API.md`

**Agregados**:

1. **Tabla "Resumen de endpoints"** — 2 filas nuevas:
   ```
   | WS     | `/api/v1/ws/notifications`                 | Sí   |    | Canal WebSocket: push de notificaciones en tiempo real (best-effort). |
   | GET    | `/api/v1/search`                           | Sí   | 📄 | Búsqueda global multi-entidad + filtros avanzados. |
   ```
   (Nota: GET /search corresponde a cambio 10-busqueda-global, ya aplicado).

2. **Contexto de la tabla**:  
   - Antes: `21 routers` / `19 endpoints paginables`  
   - Después: `22 routers` / `20 endpoints paginables`

3. **Sección nueva: "WebSocket: Notificaciones en tiempo real"** (100 líneas):
   - Propósito y contraste con REST (source of truth).
   - Handshake autenticado por subprotocolo bearer + query param fallback.
   - Respuesta `connection.ack` válido, rechazo HTTP 403 inválido.
   - Push `notification.created` con envelope.
   - Heartbeat `ping`/`pong` + cierre por inactividad.
   - Scoping estricto tenant/usuario.
   - Tabla de casos especiales (desconectado, fallo, múltiples sockets, deshabilitación).
   - Ejemplo de cliente JavaScript.
   - Configuración (`WS_ENABLED`, `WS_HEARTBEAT_SECONDS`, `WS_IDLE_TIMEOUT_SECONDS`).

---

## Verificación de completitud

### Compuerta de tareas (Task Completion Gate) ✅ PASS

- `openspec/changes/09-websocket-realtime/tasks.md`: **18/18 tasks marcadas `[x]`**
- Fase A: ConnectionManager + auth + schemas (6 tests unit)
- Fase B: Router WS + handshake (8 tests de auth/scoping)
- Fase C: Hook en NotificationRepository.create() + alerts/comments (13 tests de push E2E)
- Los 3 commits existen en `main` y son verificables.
- **Conclusión**: Cero tareas pendientes ni parciales. Implementación completa.

### Compuerta de verificación ✅ PASS

- `openspec/changes/09-websocket-realtime/verify-report.md`: **PASS, 466/466 tests, 0 fallos**
- Suite completa pasa con TEST_AUTH_TOKEN + TEST_DATABASE_URL (pytest 9.1.1).
- Ruff: cero issues.
- Mypy: cero issues (168 archivos).
- Alembic head: 0009 (sin migraciones nuevas — cambio puramente aplicativo).
- Contrato contra 6 requirements + 2 delta mapeado 1:1 a tests reales:
  - R1 (handshake): token válido → ack, inválido → cierre.
  - R2 (scoping): dos orgs aisladas, dos usuarios en misma org aislados.
  - R3 (push): mención genera push, alerta del motor genera push.
  - R4 (best-effort): usuario desconectado → notificación persiste.
  - R5 (heartbeat): cliente responde pong → conexión abierta, inactivo → cierre.
  - R6 (envelope): push cumple `{v:1, type:"notification.created", data:{...}}`.
  - Delta 09 (publicación): creación dispara publicación, REST autoritativo sin WS.
- Black-box obligatorio contra contenedor reconstruido (`docker compose up -d --build backend`):
  - ✅ Handshake válido con token real: `connection.ack` recibido, v:1.
  - ✅ Token inválido: rechazo HTTP 403 sin ack.
  - ✅ Push real end-to-end: `POST /tasks/{task_id}/comments` mencionando UUID `ana@solercia.com` → `notification.created` recibido en tiempo real en el socket WS de Ana (no fue necesario usar el fallback de `reminders/dispatch`; la mención directa funcionó).
- **Conclusión**: Listo para archivar.

### Sugerencias del verify (no bloqueantes) 📋

**SUGERENCIA 1** — `docs/API.md` no fue actualizado (RESUELTO en archive).  
✅ Se completó la documentación: tabla "Resumen de endpoints" (+2 filas), contexto actualizado (+21→22 routers, +19→20 paginables), sección nueva completa "WebSocket: Notificaciones en tiempo real" (100 líneas con handshake, push, heartbeat, scoping, casos especiales, ejemplo cliente JS, configuración).

**SUGERENCIA 2** — Configuración de `WS_IDLE_TIMEOUT_SECONDS` vs `WS_HEARTBEAT_SECONDS`.  
📝 **Documentada en docs/API.md**: por defecto heartbeat cada 30s, cierre si no hay pong en 60s. Ratio 2:1 sensible (cliente tiene margen de 30s para responder sin ser cerrado de forma inesperada). No bloqueante, comportamiento observable en tests E2E (inactividad deliberada en test de timeout).

---

## Desviaciones de diseño (validadas, correctas)

**Documentada en tasks.md, verificada en verify-report.md**:

- **"Envelope {v, type, data} vs {v, type, ts, data}"**: La propuesta mencionaba `ts` como MAY (metadato opcional). Implementación respeta la especificación exacta del spec delta: MUST v/type/data, MAY ts. No incluye timestamp de serie de tiempo en la envoltura por defecto (el cliente tiene `created_at` embebido en `data.notification.created_at` para las notificaciones). **Cubre R6 (envelope versionado)** sin romper compatibilidad hacia adelante — future MAY extender con ts sin ser un breaking change.

---

## Contenido del archivo del cambio

**Ruta archivada**: `openspec/changes/archive/2026-07-12-09-websocket-realtime/` (git mv realizado por el orquestador)

**Contenido preservado**:
- `proposal.md` — Scope, approach (ConnectionManager in-process, subprotocol bearer, best-effort), risks, success criteria
- `specs/realtime-notifications/spec.md` — Spec nueva (6 req, 13 esc)
- `specs/notifications-inapp/spec.md` — Delta ADDED
- `design.md` — 4 decisiones arquitectónicas + gate adversarial
- `tasks.md` — 18/18 tareas + Fase A/B/C + trazabilidad commit
- `verify-report.md` — PASS, matriz de cumplimiento, black-box e2e
- `state.yaml` — Cierre de todas las fases (archive: done)

---

## Impacto en la suite de tests

| Métrica | Antes (cambio 06) | Cambio 09 | Después |
|---------|------------------|-----------|---------|
| Tests totales | 439 | +27 | **466** |
| Archivos de test | 26 | +1 | 27 |
| Archivos backend/tests | `test_*.py` | `test_realtime_*.py` (3 archivos: manager, auth, push) | Nuevas suites |
| Ruff | 0 issues | 0 issues | 0 issues |
| Mypy | 0 issues | 0 issues | 0 issues |

---

## Cierre del ciclo SDD

✅ **Proposal**: Requerimientos y approach validados (in-process, subprotocol auth, best-effort)  
✅ **Spec**: 13 escenarios (6 realtime-notifications + 2 delta notifications-inapp) definidos y clavados  
✅ **Design**: 4 decisiones arquitectónicas documentadas + gate adversarial PASADO  
✅ **Tasks**: 18/18 checkeadas, aplicadas, verificadas (3 commits A/B/C)  
✅ **Apply**: 3 commits en main con cobertura TDD estricta (27 tests, fix real de AsyncMock en test_mention_notifications)  
✅ **Verify**: 466/466 tests verdes, contrato black-box confirmado (push real e2e vs contenedor)  
✅ **Archive**: Deltas fusionados a specs vivas, documentación transversal actualizada (AVANCE.md, API.md, specs/README.md), archivo movido

**Estado final**: 🟩 **COMPLETADO** — Listo para el próximo cambio (07-assets-sdmujer). 2 cambios backend pendientes:
- **07-assets-sdmujer**: Activos + licencias + alertas de vencimiento (Fase 3 completa CLAUDE.md)
- **08-email-notifications**: Canal email con digest configurable

**Camino futuro documentado**:
- Adaptador Redis pub/sub cuando haya réplicas / escalado horizontal (seam del puerto NotificationPublisher ya preparado en el design).
