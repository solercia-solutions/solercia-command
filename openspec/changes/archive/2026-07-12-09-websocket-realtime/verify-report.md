# Verify Report — 09 · WebSocket realtime (push in-app en tiempo real)

**Fecha**: 2026-07-12
**Veredicto**: **PASS**
**Modo**: artefactos completos (proposal + specs + design + tasks) — verificación de completitud, corrección y coherencia.

## Resumen ejecutivo

18/18 tareas completas, 466/466 tests en verde (0 fallos), `ruff` y `mypy` limpios, sin migraciones nuevas (head sigue en `0009`), y evidencia black-box real contra el contenedor reconstruido: handshake válido → `connection.ack`, token inválido → rechazo pre-accept (HTTP 403), y un push `notification.created` disparado por una mención real vía REST llegó al socket del destinatario en tiempo real. 0 CRITICAL, 0 WARNING, 0 SUGGESTION.

## 1. Suite completa

Comando: `TEST_AUTH_TOKEN=<token admin> TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test python -m pytest tests/ -q` (entorno local `backend/.venv`, Python 3.14, pytest 9.1.1).

```
466 passed, 1 warning in 123.36s (0:02:03)
```

El único warning es el `SAWarning` preexistente de `test_migrations_baseline.py` sobre ciclos de FK entre `dependencies/organizations/users` (no relacionado con este cambio, ya presente en líneas base anteriores).

Coincide exactamente con lo esperado (466 passed, 0 failed).

## 2. Lint y tipos

```
$ ruff check .
All checks passed!

$ mypy app
Success: no issues found in 168 source files
```

Ambos limpios.

## 3. Contrato contra las delta specs

### `specs/realtime-notifications/spec.md` (6 requirements, 11 escenarios)

| Requirement | Escenario | Test cubridor | Resultado |
|---|---|---|---|
| Handshake autenticado | Token válido | `test_realtime_ws_auth.py::test_valid_token_accepts_and_sends_connection_ack_first` | PASS |
| Handshake autenticado | Token ausente/inválido | `test_missing_token_closes_before_accept`, `test_invalid_token_closes_before_accept`, `test_expired_token_closes_before_accept`, `test_inactive_user_closes_before_accept` | PASS |
| Scoping org/usuario | Aislamiento entre organizaciones | `test_realtime_manager.py::test_isolation_across_organizations` + E2E `test_realtime_push.py::test_mention_push_never_reaches_a_different_organization_socket` | PASS |
| Scoping org/usuario | Aislamiento entre usuarios de la misma org | `test_realtime_manager.py::test_isolation_across_users_in_the_same_organization` | PASS |
| Push en creación | Mención genera push | `test_realtime_push.py::test_mention_via_rest_pushes_notification_created_to_the_recipient_socket` + smoke black-box (sección 4) | PASS |
| Push en creación | Alerta del motor genera push | `test_realtime_push.py::test_alert_evaluator_push_reaches_the_recipient_socket` | PASS |
| Best-effort ante desconexión | Usuario desconectado | `test_realtime_push.py::test_publish_failure_does_not_prevent_persistence_or_rest_recovery` + `test_realtime_manager.py::test_publish_to_unregistered_key_is_a_noop`, `test_best_effort_one_failing_socket_does_not_block_the_other` | PASS |
| Heartbeat / idle-close | Cliente responde a tiempo | `test_realtime_ws_auth.py::test_client_responding_in_time_keeps_the_connection_open` | PASS |
| Heartbeat / idle-close | Cliente inactivo se cierra | `test_realtime_ws_auth.py::test_client_inactive_beyond_idle_timeout_is_closed` | PASS |
| Envelope versionado | Forma del envelope en push | `test_realtime_manager.py::test_envelope_has_versioned_shape`, `test_envelope_carries_arbitrary_data_payload` + smoke black-box (`{v:1, type, ts, data}` observado real) | PASS |

Nota: el fallback `?token=` (auth query param) está cubierto por `test_query_param_fallback_authenticates_when_no_subprotocol`.

### `specs/notifications-inapp/spec.md` (delta ADDED, 1 requirement, 2 escenarios)

| Escenario | Test cubridor | Resultado |
|---|---|---|
| Creación dispara publicación (hook único `NotificationRepository.create()`) | `test_realtime_manager.py::test_buffers_a_serialized_envelope_on_db_info`, `test_flush_pending_pops_before_publishing`, `test_flush_pending_does_not_republish_across_multiple_drains` + E2E `test_realtime_push.py` | PASS |
| REST sigue siendo autoritativo (canal deshabilitado/publisher no disponible → persiste igual) | `test_realtime_push.py::test_publish_failure_does_not_prevent_persistence_or_rest_recovery`, `test_realtime_manager.py::test_flush_pending_swallows_publish_failures` | PASS |

Verificado en código: `NotificationRepository.create()` (`backend/app/modules/notifications/repository.py:114`) es el único call site de `buffer_notification`; `NotificationService` no tiene `create()` propio (confirmado por grep, consistente con el apply).

## 4. Black-box contra el contenedor (obligatorio)

`docker compose up -d --build backend` ejecutado — imagen reconstruida horneando `app/realtime/`. Contenedor arrancó limpio, migró a `0009` (sin cambios), sembró datos demo.

Smoke real con `websockets` 16.1 (dependencia transitiva de `uvicorn[standard]`, ya presente en el venv del proyecto) contra `ws://localhost:8000/api/v1/ws/notifications`:

1. **Token válido (admin, subprotocol `["bearer", token]`)** → `connection.ack` recibido como primer mensaje: `{"v": 1, "type": "connection.ack", "ts": "...", "data": null}`. PASS.
2. **Token inválido** (`"not-a-real-token"`) → conexión rechazada antes del upgrade: `InvalidStatus: server rejected WebSocket connection: HTTP 403` (cierre pre-accept, código de política 1008 vía HTTP 403 del handshake, tal como diseñado en D4). Sin `connection.ack`. PASS.
3. **Push real de extremo a extremo** (no solo ack+rechazo): conectado el socket de `ana@solercia.com` (usuario real seed), el admin crea vía REST un comentario en una tarea real (`POST /tasks/{task_id}/comments`, `201`) mencionando el UUID de Ana. El socket de Ana recibe, sin polling, `notification.created`:
   ```json
   {"v": 1, "type": "notification.created", "ts": "2026-07-12T09:14:53.448926+00:00",
    "data": {"id": "43ca1c5e-...", "recipient_user_id": "6b92e642-...", "rule_type": "mention",
              "title": "Te mencionaron en un comentario", "target_type": "task", ...}}
   ```
   Envelope cumple `{v, type, ts, data}` con `data = NotificationRead` completo, igual que en la spec y en el design. PASS.

Se disparó push real vía mención REST (no fue necesario recurrir a la alternativa documentada de `reminders/dispatch`); el ack, el rechazo y el push end-to-end quedaron probados en vivo contra el contenedor — evidencia black-box completa, no solo el fallback aceptado de suite in-process.

## 5. tasks.md y state.yaml

- `tasks.md`: 18/18 casillas marcadas `[x]` (Fase A: A1-A7, Fase B: B1-B5, Fase C: C1-C6). Coincide con el estado real del código (verificado por lectura directa de `app/realtime/`, `dependencies.py`, `repository.py`, `evaluator.py`, `comments/service.py`, `main.py`).
- 3 commits de fase presentes en `git log`: `e2196a1 feat(realtime): agrega ConnectionManager y publisher...`, `811d410 feat(realtime): agrega handshake autenticado y router...`, `6e1f35a feat(realtime): conecta creación de notificaciones al push...`.
- `state.yaml`: `apply: done`, `apply_summary` coincide con la evidencia (466 tests, 27 nuevos, 3 commits). Sin migraciones nuevas: `alembic current` en el contenedor reconstruido reporta `0009 (head)`.

## Hallazgos

**CRITICAL**: ninguno.
**WARNING**: ninguno.
**SUGGESTION**: ninguno.

## Veredicto final

**PASS**. Los 18 tareas, la suite completa (466/466), lint/tipos, el contrato de ambas delta specs y la evidencia black-box en vivo contra el contenedor están alineados sin desviaciones. El cambio queda listo para `sdd-archive`.
