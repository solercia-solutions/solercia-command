# Tasks: 09 · WebSocket realtime (push in-app en tiempo real)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~500-600 (engine ~220, hooks ~30, tests ~300) |
| Riesgo de presupuesto (400 líneas) | Medium |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Lote A → Lote B → Lote C |
| Estrategia de entrega | exception-ok — size:exception aceptada por el usuario, entrega por lotes |
| Estrategia de encadenado | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

Apply de 09 corre al final de la serialización vigente (orden 11→10→06→09); depende de **02-contrato-api** ya aplicado (auth-user, `NotificationRead`). Sin migraciones (confirmado en design).

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test | Runtime harness | Rollback |
|------|----------|--------|---------------|------------------|----------|
| A | `ConnectionManager` + publisher + schemas + config | `feat(realtime): ...` | `pytest tests/test_realtime_manager.py -v` | N/A — doubles WS, sin app real | borrar `app/realtime/` |
| B | Auth WS: helper extraído + router | `feat(realtime): ...` | `pytest tests/test_realtime_ws_auth.py -v` | Starlette TestClient contra app ASGI | revertir `router.py`+`dependencies.py` |
| C | Hook `create()` + drains + `main.py` | `feat(realtime): ...` | `pytest tests/test_realtime_push.py -v` | TestClient WS+REST, `TEST_DATABASE_URL` | apagar `WS_ENABLED` o revertir 3 hooks |

## Fase A — Infraestructura realtime (Commit 1)

- [x] A1 `backend/app/realtime/__init__.py`: paquete nuevo.
- [x] A2 `backend/app/realtime/schemas.py`: `Envelope{v,type,ts,data}` (`type` Literal del catálogo); `make_envelope()`.
- [x] A3 RED `backend/tests/test_realtime_manager.py`: register/unregister; aislamiento — publish a (orgA,userX) nunca llega a (orgB,userY); multi-pestaña (2 sockets mismo user, ambos reciben); best-effort (1 `send_json` que lanza no bloquea al otro). Todo fallando.
- [x] A4 GREEN `backend/app/realtime/manager.py`: `ConnectionManager` (`dict[(org_id,user_id), set[WebSocket]]`, sin lock); `register`/`unregister`/`publish` sobre snapshot `list(sockets)`, try/except+log por socket.
- [x] A5 GREEN `backend/app/realtime/publisher.py`: `NotificationPublisher` Protocol; `buffer_notification(db,n)` serializa `NotificationRead` en `db.info["realtime_pending"]`; `flush_pending(db)` hace **pop atómico** (`db.info.pop("realtime_pending", [])`) ANTES de publicar, try/except+log por envío.
- [x] A6 GREEN `backend/app/config.py`: `WS_ENABLED: bool = True`, `WS_HEARTBEAT_SECONDS: int = 30`, `WS_IDLE_TIMEOUT_SECONDS: int = 90`.
- [x] A7 VERIFY `pytest tests/test_realtime_manager.py -v`; `ruff check app/realtime`; `mypy app/realtime`.

## Fase B — Auth WS + router (Commit 2)

- [x] B1 RED `backend/tests/test_realtime_ws_auth.py`: token válido→accept+`connection.ack` primer mensaje (`v=1`); token ausente/inválido/expirado/usuario inactivo→close ANTES de accept (sin upgrade). Todo fallando.
- [x] B2 GREEN `backend/app/dependencies.py`: extraer `authenticate_access_token(db, token) -> User` con la misma lógica/`AppException` (`invalid_token`/`user_not_found`) hoy inline en `get_current_user`; `get_current_user` delega sin cambiar código ni mensaje.
- [x] B3 GREEN `backend/app/realtime/router.py`: `@router.websocket("/ws/notifications")`; token de `Sec-WebSocket-Protocol` (`"bearer, <token>"`) o `?token=` fallback; `AppException`→`close()` antes de `accept()`; válido→`accept(subprotocol="bearer")`→`connection.ack`→`manager.register`. Org = primera membresía (igual que REST).
- [x] B4 GREEN Heartbeat en `router.py`: `ping` cada `WS_HEARTBEAT_SECONDS`; sin `pong` en `WS_IDLE_TIMEOUT_SECONDS`→close; `finally: manager.unregister(...)`.
- [x] B5 VERIFY `pytest tests/test_realtime_ws_auth.py tests/test_auth.py -v` — sin regresión REST.

## Fase C — Integración push (Commit 3)

- [ ] C1 RED `backend/tests/test_realtime_push.py`: WS conectado + mención vía REST (mismo TestClient)→`notification.created` con `NotificationRead`; socket de otro user/org no recibe nada; alerta materializada por el evaluador→push; `WS_ENABLED=False` o publish falla→notificación igual persistida y recuperable en `GET /notifications`. Override `app.dependency_overrides[get_db]` con engine `NullPool` propio sobre `TEST_DATABASE_URL` creado DENTRO del loop del TestClient (PROHIBIDO el `get_db` real); limpieza explícita + `dispose()` en teardown. Todo fallando.
- [ ] C2 GREEN `backend/app/modules/notifications/repository.py::create()`: tras `flush`/`refresh`, `buffer_notification(self.db, notification)` — único hook (`NotificationService` no tiene `create()`).
- [ ] C3 GREEN `backend/app/alerts/evaluator.py::evaluate_organization`: tras `await db.commit()`, `await flush_pending(db)`.
- [ ] C4 GREEN `backend/app/modules/comments/service.py::_dispatch_mention_notifications`: dentro de `if created_any:`, tras el commit, `await flush_pending(self._db)`.
- [ ] C5 GREEN `backend/app/main.py`: `if settings.WS_ENABLED: app.include_router(realtime_router, prefix=API_PREFIX)`.
- [ ] C6 VERIFY `cd backend && pytest tests/ -v` completo; sin regresión en menciones/alertas/notifications; `ruff check .`; `mypy app`.

## Trazabilidad de requisitos

Handshake autenticado · scoping org/usuario · push en creación · best-effort · heartbeat/idle-close · envelope versionado (`specs/realtime-notifications`). Publicación en la creación · REST autoritativo (`specs/notifications-inapp`).
