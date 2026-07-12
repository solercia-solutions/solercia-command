```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:e2d552da97c39e6771856e21de3478ec0a24a9c0841dc7813537975d11429ef2
verdict: pass
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 22/22
test_command: cd backend && pytest tests/ -q (contenedor backend reconstruido, TEST_AUTH_TOKEN via login admin@solercia.com)
test_exit_code: 0
test_output_hash: sha256:e2d552da97c39e6771856e21de3478ec0a24a9c0841dc7813537975d11429ef2
build_command: cd backend && ruff check . && mypy app
build_exit_code: 0
build_output_hash: sha256:ff6ac0cd6357abef2bd1833eca3c7ada33d882dc835a345d320b0551e3e78a71
```

## Verification Report

**Cambio**: 12-notification-hub
**Versión**: N/A (refactor interno, sin versión de API nueva)
**Modo**: Strict TDD (heredado de apply) — verify estándar con evidencia de ejecución real

### Completitud de tareas
| Métrica | Valor |
|---------|-------|
| Tareas totales | 26 |
| Tareas completas | 26 |
| Tareas incompletas | 0 |

Las 26 tareas de `tasks.md` (Fase 1: 1.1–1.9, Fase 2: 2.1–2.19, Fase 3: 3.1–3.8) están marcadas `[x]`. Coinciden con el estado de código inspeccionado — no hay divergencia entre lo declarado completo y la implementación real.

### Build y ejecución de tests

**Nota de infraestructura**: el contenedor `backend` corría con una imagen construida ANTES de los commits de este cambio (sin volumen montado — código horneado en build). Se ejecutó `docker compose up -d --build backend` (obligatorio según instrucciones) para reconstruir la imagen con el código actual antes de correr cualquier prueba black-box o la suite completa dentro del contenedor. Sin este paso, la suite solo veía 539 tests (código viejo) y los tests black-box fallaban con `httpx.LocalProtocolError` por token vacío.

**Build**: ✅ Passed
```text
$ ruff check .
All checks passed!

$ mypy app
Success: no issues found in 189 source files
```

**Tests**: ✅ 561 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
$ pytest tests/ -q   (TEST_AUTH_TOKEN fresco vía login admin@solercia.com/Admin123*, TEST_DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/solercia_test dentro del contenedor)
561 passed, 1 warning in 139.65s (0:02:19)
```
Coincide exactamente con lo esperado (539 base + 22 nuevos). El único warning es un `SAWarning` preexistente de Alembic sobre ciclos de FK entre `dependencies/organizations/users`, no relacionado con este cambio.

**alembic check / current**:
```text
$ alembic current
0013 (head)

$ alembic check
No new upgrade operations detected.
```
Migración `0012 -> 0013` corrió limpia en el arranque del contenedor reconstruido. `alembic check` reporta cero diff — confirma que la corrección de renombre de índices (`ix_email_outbox_*` → `ix_notification_deliveries_*`, ambos sentidos) quedó bien aplicada tras eliminar el modelo `EmailOutbox`.

**Round-trip 0012↔0013**: `test_notification_delivery_migration.py` (2 tests) verificado en aislado — `test_upgrade_renames_table_and_populates_payload_dropping_typed_columns` y `test_downgrade_restores_typed_columns_with_same_values_no_row_lost` — ambos PASSED, cero pérdida de filas en ningún sentido.

**Coverage**: ➖ No disponible (el proyecto no corre `pytest --cov` en este pipeline; no bloquea el veredicto — no hay `coverage` configurado como gate en tasks.md/design.md).

### Contrato del refactor — cero cambio de comportamiento observable

| Verificación | Resultado |
|---|---|
| (a) `git diff 890a966..HEAD -- backend/tests/test_realtime_manager.py backend/tests/test_mention_notifications.py` | ✅ Vacío — comportamiento WS 100% intacto, ni una línea tocada |
| (b) Aserciones de status/attempts/dedup en `test_email_dispatch.py`/`test_email_outbox.py`/`test_email_digest.py` | ✅ Revisadas línea por línea vía `git diff 890a966..HEAD`; el diff es exclusivamente: imports (`EmailOutbox`→`NotificationDelivery`), llamadas de función renombradas (`dispatch_outbox`→`dispatch_deliveries`, `EmailChannel().enqueue`), acceso a payload (`row.recipient_email`→`row.payload["recipient_email"]`) y nombres de logger. Ninguna aserción de `status`/`attempts`/`sent_at`/`dedup_key`/idempotencia fue debilitada, eliminada ni relajada |
| (c) Fan-out con aislamiento de fallos | ✅ `test_notification_repository_fanout.py::test_create_isolates_a_failing_channel_from_the_healthy_one_and_the_tx` — un canal fake que lanza `RuntimeError` no impide que el canal sano reciba la notificación ni que la transacción de negocio sobreviva (commit + re-lectura confirmatoria) |
| (d) Gate del endpoint `/deliveries` | ✅ `test_notification_deliveries_endpoint.py` — member/viewer (incluido el DUEÑO) → 403 (`test_member_and_viewer_get_403_including_the_owner`, parametrizado); admin/manager → 200 (`test_admin_and_manager_list_immediate_delivery`, parametrizado). Confirmado también black-box (ver sección siguiente) |

### Black-box contra contenedor reconstruido (evidencia en vivo)

1. `docker compose up -d --build backend` → imagen reconstruida, contenedor recreado.
2. Logs de arranque: migración `0012 -> 0013` aplicada; `Seed completed`; jobs registrados: `Alert Engine Evaluation`, `Reminder Dispatch` — **sin** job `delivery_dispatch`/`email_digest`, consistente con `EMAIL_ENABLED` no seteado en `docker-compose.yml` (comportamiento esperado de `has_active_durable_channel()`, D4).
3. `alembic current` = `0013 (head)`.
4. Login admin (`admin@solercia.com`/`Admin123*`) → token válido, `/auth/me` confirma rol ADMIN.
5. `POST /tasks/{id}/comments` con `@810e1b02-c99c-4b55-a698-7f4a4e810526` (carlos@solercia.com, MEMBER) → `201`, `mentioned_user_ids` correcto.
6. Login carlos (`Demo123*`, password seed real de usuarios no-admin) → `GET /api/v1/notifications` → `200`, la notificación `rule_type=mention` con `dedup_key=mention:{comment_id}:{user_id}` aparece de inmediato (in-app intacto, canal REST autoritativo sin cambios).
7. `GET /notifications/{id}/deliveries` con token admin → `200`, `{"deliveries": [], "digested": false}`. Vacío porque `EMAIL_ENABLED` está apagado en este `docker-compose.yml` (sin variable definida) y `rule_type=mention` no es de los tipos "urgentes" que dispararían envío inmediato de email de todas formas — comportamiento esperado y documentado, no una falla.
8. `GET /notifications/{id}/deliveries` con token carlos (MEMBER, y además DUEÑO de la notificación) → `403` `{"code":"notification_deliveries_forbidden"}` — confirma sin excepción de dueño, igual que el test automatizado.
9. Smoke WS (opcional, ejecutado): conexión a `ws://.../api/v1/ws/notifications?token=...` con subprotocolo `bearer` → recibe `{"v":1,"type":"connection.ack",...}` de inmediato. Confirma handshake autenticado intacto (spec `realtime-notifications`).
10. Limpieza: `DELETE /comments/{id}` → `204` (soft-delete, único mecanismo disponible por convención del proyecto — "nunca delete físico"). La `Notification`/fila de auditoría resultante queda como dato residual normal, equivalente a cualquier mención real del sistema; no representa un problema de aislamiento ni de esquema.

### Matriz de cumplimiento de especificación

| Requisito | Escenario | Test / Evidencia | Resultado |
|---|---|---|---|
| R1 Puerto `DeliveryChannel` y registro extensible | Canal fake registrado en test recibe fan-out sin tocar el núcleo | `test_notify_registry.py`, `test_notification_repository_fanout.py::test_create_iterates_registered_channels_by_policy` | ✅ COMPLIANT |
| R2 Fan-out único con aislamiento de fallos | Durable en misma tx / best_effort post-commit / falla de uno no afecta a los demás | `test_notification_repository_fanout.py` (2 tests), `test_realtime_manager.py` (WS post-commit intacto, 0 diff) | ✅ COMPLIANT |
| R3 Entrega durable en `notification_deliveries` | Claim atómico / agotamiento reintentos / re-corrida idempotente | `test_notify_dispatcher.py`, `test_notify_store.py` | ✅ COMPLIANT |
| R4 Auditoría `GET /{id}/deliveries` | Admin lista / aislamiento por organización 404 / member 403 (sin excepción de dueño) | `test_notification_deliveries_endpoint.py` + black-box (admin 200, carlos-dueño 403) | ✅ COMPLIANT |
| R5 Tolerancia a atribución de digest | Entrega agregada de digest no rompe endpoint / entrega inmediata conserva atribución exacta | `test_notification_deliveries_endpoint.py::test_digested_notification_reports_digested_true_without_immediate_row`, `test_immediate_delivery_attribution_is_exact_not_mixed_across_notifications` | ✅ COMPLIANT |
| R6 Extensibilidad para canales futuros sin tocar el núcleo | Adaptador hipotético `push_fcm` no requeriría cambios en el núcleo | Prueba estructural vía `Protocol`-based ports + registro mutable (misma evidencia que R1); `ports.py` confirma dos protocolos disjuntos por política (D2) | ✅ COMPLIANT |
| R7 `notifications-inapp`: publicación realtime vía hub sin cambio observable | Creación dispara publicación vía hub / REST autoritativo si canal deshabilitado | `test_realtime_manager.py`, `test_mention_notifications.py` (0 diff) + black-box (`GET /notifications` de carlos muestra la mención) | ✅ COMPLIANT |
| R8 `notifications-inapp`: encolado de entrega email vía hub sin cambio observable | Notificación urgente encola en `notification_deliveries` / no urgente pendiente de digest | `test_email_outbox.py` (adaptado, mismas aserciones) | ✅ COMPLIANT |
| R9 `email-notifications`: adaptador durable sin cambios observables | Comportamiento idéntico tras refactor / `EMAIL_ENABLED` sigue neutralizando | `test_email_dispatch.py`, `test_email_digest.py`, `test_email_outbox.py` (adaptados, mismas aserciones de status/attempts/dedup) + black-box (sin job `delivery_dispatch` registrado con `EMAIL_ENABLED` apagado) | ✅ COMPLIANT |
| R10 `realtime-notifications`: adaptador best-effort sin cambios observables | Comportamiento idéntico tras refactor / falla de publicación no genera fila en `notification_deliveries` | `test_realtime_manager.py`, `test_mention_notifications.py` (0 diff) + black-box WS smoke (`connection.ack`) + `test_best_effort_channel_never_appears_in_deliveries` | ✅ COMPLIANT |

**Resumen de cumplimiento**: 22/22 escenarios (10/10 requisitos) COMPLIANT.

### Correctness (evidencia estática + runtime)
| Requisito | Estado | Notas |
|---|---|---|
| Migración 0013 (rename en sitio, sin tabla nueva) | ✅ Implementado | `ALTER TABLE ... RENAME TO` + `ALTER INDEX` en ambos sentidos (upgrade/downgrade); `alembic check` cero diff |
| `NotificationDelivery` como store genérico | ✅ Implementado | `channel`, `payload` JSONB, `dedup_key` único, mixins estándar del proyecto |
| Fronteras de extracción (núcleo NUNCA importa `notifications.repository`) | ✅ Implementado | `grep -rn "notifications.repository" app/notify app/email app/realtime` solo encuentra menciones en docstrings explicando la regla, cero imports reales |
| Bootstrap del registro de canales vía `db_init.py` | ✅ Implementado | `import app.email.outbox` / `import app.realtime.publisher` en `db_init.py` líneas 24-25, con docstring explicando la corrección (mismo punto usado por `main.py`, Alembic `env.py` y la fixture `engine` de tests) |
| `app/email/models.py` eliminado | ✅ Implementado | Archivo no existe en el árbol actual; todos los imports migraron a `app.notify.models.NotificationDelivery` |

### Coherencia con diseño (design.md)
| Decisión | ¿Seguida? | Notas |
|---|---|---|
| D1 — `app/notify/` como engine sibling (no bajo `modules/`) | ✅ Sí | Confirmado en el árbol de archivos |
| D2 — Dos protocolos disjuntos por política (`DurableChannel`/`BestEffortChannel`), `enqueue`/`deliver` separados | ✅ Sí | `app/notify/ports.py` implementa exactamente el contrato documentado, INSERT delegado al store port |
| D3 — Rename en sitio + despachador genérico reusa contrato transaccional byte a byte | ✅ Sí | Claim atómico `pending→sending`+commit ANTES del send, confirmado en `test_notify_dispatcher.py` |
| D4 — Gating sin flag nuevo (`has_active_durable_channel()` == `EMAIL_ENABLED`) | ✅ Sí | Confirmado en logs de arranque: sin job de despacho registrado con `EMAIL_ENABLED` apagado |
| D5 — InApp no es canal; WS `best_effort`; Email `durable` | ✅ Sí | `repository.create()` persiste `Notification` primero (flush/refresh), luego itera `get_channels()` |
| D6 — Gate admin\|manager sin excepción de dueño; digest opción (b) `notification_id=NULL`+`emailed_at` | ✅ Sí | Confirmado por test automatizado y black-box (carlos, dueño MEMBER, → 403) |

### Desviaciones documentadas — verificadas contra el código
| Desviación | Documentada en | Verificada contra código |
|---|---|---|
| Renombre de índices `ix_email_outbox_*`→`ix_notification_deliveries_*` (ambos sentidos) en la migración 0013 | apply-progress (Learned #1), tasks.md T2.19 | ✅ Confirmado en `0013_rename_email_outbox_to_notification_deliveries.py` líneas 44-52 (upgrade) y 111-119 (downgrade) |
| Bootstrap del registro de canales vía imports en `db_init.py` (no listado originalmente en tasks.md) | apply-progress (Learned #2), tasks.md T2.12 | ✅ Confirmado en `db_init.py` líneas 1-25 (docstring + imports explícitos) |

Ambas desviaciones son correcciones técnicas necesarias, coherentes con el patrón de fronteras del proyecto, sin impacto en el comportamiento observable de los tres canales.

### Issues Found
**CRITICAL**: Ninguno.
**WARNING**: Ninguno.
**SUGGESTION**:
- El endpoint `/deliveries` devolvió lista vacía en la prueba black-box porque `EMAIL_ENABLED` no está seteado en `docker-compose.yml` de este entorno — comportamiento esperado y ya documentado explícitamente en las instrucciones de verify, no una falla del cambio. Si se desea evidencia black-box de una fila `pending`/`sent` real (además de la ya cubierta por 6 tests automatizados con `EMAIL_ENABLED=True` monkeypatcheado), habría que definir `EMAIL_ENABLED=true` en el compose de un entorno de prueba dedicado — no bloquea este verify.

### Verdict
**PASS**

561/561 tests en verde (incluye 22 nuevos + 539 base sin regresión), ruff/mypy limpios, `alembic check` cero diff, round-trip 0012↔0013 sin pérdida de filas, contrato de refactor confirmado sin cambio de comportamiento observable en email/WS/in-app (diff vacío en tests WS, aserciones intactas en tests de email, aislamiento de fallos probado, gate del endpoint probado en automatizado y black-box), 26/26 tareas completas y coherentes con el código, ambas desviaciones documentadas verificadas contra el código real.
