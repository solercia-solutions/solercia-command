```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:ad18a44b7349b1c33948c5c4a02a643c0d0f14114592a4f5d9614171bfe264bb
verdict: pass
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 19/19
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test TEST_AUTH_TOKEN=*** ./.venv/bin/python -m pytest tests/ -q
test_exit_code: 0
test_output_hash: sha256:ad18a44b7349b1c33948c5c4a02a643c0d0f14114592a4f5d9614171bfe264bb
build_command: cd backend && ./.venv/bin/ruff check . && ./.venv/bin/mypy app
build_exit_code: 0
build_output_hash: sha256:ruff-clean-mypy-184-files-clean
```

## Verification Report

**Cambio**: 08-email-notifications
**Versión**: N/A (primera versión de la capacidad)
**Modo**: Strict TDD (según `state.yaml` constraint `strict-tdd`)

### Completitud

| Métrica | Valor |
|---------|-------|
| Tareas totales | 40 |
| Tareas completas | 40 |
| Tareas incompletas | 0 |

Todas las tareas en `openspec/changes/08-email-notifications/tasks.md` están marcadas `[x]` con notas de implementación consistentes con el código real (commits `c4adee8`, `0fe516b`, `1d9ddc7`, `7b22ed4`).

### Ejecución de build y pruebas

**Build (ruff + mypy)**: ✅ Aprobado
```text
$ cd backend && ./.venv/bin/ruff check .
All checks passed! (exit 0)

$ cd backend && ./.venv/bin/mypy app
Success: no issues found in 184 source files (exit 0)
```

**Pruebas**: ✅ 539 pasaron / ❌ 0 fallaron / ⚠️ 0 omitidas
```text
$ cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
  TEST_AUTH_TOKEN=<token fresco via login admin@solercia.com> \
  ./.venv/bin/python -m pytest tests/ -q
539 passed, 1 warning in 139.88s
```
El único warning es un `SAWarning` preexistente de SQLAlchemy sobre ciclos de FK entre `dependencies/organizations/users` al ordenar tablas para `alembic check`; no es una regresión introducida por este cambio (no afecta ninguna prueba ni el resultado de `alembic check`).

Subconjunto enfocado de las 41 pruebas nuevas de email-notifications, ejecutado también de forma aislada para trazabilidad exacta nombre-de-test → requisito:
```text
$ pytest tests/test_email_policy.py tests/test_email_templates.py tests/test_email_sender.py \
  tests/test_email_outbox.py tests/test_email_dispatch.py \
  tests/test_notification_preferences.py tests/test_email_digest.py -v
41 passed in 6.48s
```

**Cobertura**: no se ejecutó `--cov` (no forma parte del comando estándar de este proyecto); no aplicable como bloqueo — la matriz de cumplimiento de escenarios (abajo) es la evidencia de cobertura funcional exigida por el spec.

### Migraciones (alembic)

- `alembic history`: cadena `0010 → 0011 (add_email_outbox) → 0012 (add_notification_preferences)` confirmada, sin bifurcaciones.
- Verificación independiente en BD Postgres desechable (`solercia_verify_tmp`, creada y destruida para esta verificación): `alembic upgrade head` limpio → `alembic check` **"No new upgrade operations detected"** (cero diff) → `alembic downgrade 0009` limpio (revierte 0012→0011→0010→0009 sin error) → `alembic upgrade head` de vuelta limpio → `alembic check` de nuevo cero diff.
- Nota: `alembic check` contra `solercia_test` (la BD persistente de pruebas) reporta "Target database is not up to date" — esto es **esperado y no es un defecto**: `solercia_test` se construye vía `Base.metadata.create_all()` en los fixtures de pytest (nunca corre `alembic upgrade`), documentado explícitamente en `tests/test_migrations_baseline.py` ("nunca colisiona con el `create_all`-based fixture"). La prueba automatizada `test_alembic_check_reports_no_diff_after_upgrade` (parte de los 539) ya valida `alembic check` limpio contra una BD temporal propia y pasó.

### Matriz de cumplimiento de especificación

**email-notifications** (9 requisitos, 16 escenarios):

| Requisito | Escenario | Test | Resultado |
|-----------|-----------|------|-----------|
| R1 Puerto EmailSender agnóstico | Adaptador console en desarrollo/tests | `test_email_sender.py::test_console_sender_captures_message_in_memory_without_network` | ✅ COMPLIANT |
| R1 Puerto EmailSender agnóstico | Cambiar de adaptador no toca el dominio | `test_email_sender.py::test_get_email_sender_returns_{console,smtp}_*` + inspección estática (`app/email/outbox.py` solo importa `get_email_sender` de `sender.py`, nunca instancia `ConsoleEmailSender`/`SmtpEmailSender` directamente) | ✅ COMPLIANT |
| R2 Interruptor EMAIL_ENABLED | Interruptor apagado | `test_email_outbox.py::test_email_disabled_urgent_notification_persists_without_outbox_row` | ✅ COMPLIANT |
| R3 Envío inmediato de urgentes | Licencia vencida dispara correo inmediato | `test_email_outbox.py::test_urgent_notification_enqueues_outbox_row_and_marks_emailed_at` + `test_email_dispatch.py::test_dispatch_sends_pending_row_and_marks_sent` | ✅ COMPLIANT |
| R3 Envío inmediato de urgentes | Fallo de envío no rompe la operación | `test_email_dispatch.py::test_dispatch_failure_leaves_row_pending_and_retryable` | ✅ COMPLIANT |
| R4 Preferencia de digest por usuario | Usuario con digest diario | `test_email_digest.py::test_digest_groups_unread_notifications_and_marks_emailed_at` | ✅ COMPLIANT |
| R4 Preferencia de digest por usuario | Usuario sin digest sigue recibiendo urgentes | `test_email_digest.py::test_none_preference_never_generates_a_digest` (combinado con R3, que confirma que el urgente es independiente de la preferencia) | ✅ COMPLIANT |
| R5 Alcance y marcado del digest | Digest agrupa orígenes distintos en un solo correo | `test_email_digest.py::test_digest_groups_unread_notifications_and_marks_emailed_at` | ✅ COMPLIANT |
| R6 Idempotencia del envío | Digest corrido dos veces no duplica | `test_email_digest.py::test_digest_rerun_after_marking_finds_nothing_to_send` | ✅ COMPLIANT |
| R6 Idempotencia del envío | Reintento de outbox no duplica | `test_email_dispatch.py::test_dispatch_retry_reuses_same_dedup_key_no_duplicate_row` | ✅ COMPLIANT |
| R6 Idempotencia del envío | Agotamiento de reintentos → failed sin reintento infinito | `test_email_dispatch.py::test_dispatch_exhausted_retries_ends_in_failed_with_error_log` + `test_email_digest.py::test_digest_outbox_exhausted_retries_notifications_stay_visible` | ✅ COMPLIANT |
| R7 CRUD de preferencias | GET sin registro previo devuelve defaults | `test_notification_preferences.py::test_get_without_existing_row_returns_none_defaults` + black-box `GET /api/v1/notification-preferences` contra contenedor reconstruido | ✅ COMPLIANT |
| R7 CRUD de preferencias | PUT con frecuencia inválida | `test_notification_preferences.py::test_put_invalid_frequency_returns_422_with_detail` + black-box `PUT frequency=hourly` → 422 confirmado en vivo | ✅ COMPLIANT |
| R7 CRUD de preferencias | PUT válido persiste y es legible | `test_notification_preferences.py::test_put_valid_persists_and_is_readable_by_subsequent_get` + black-box `PUT frequency=daily` → `GET` posterior refleja el cambio, confirmado en vivo | ✅ COMPLIANT |
| R8 Aislamiento multi-tenant | Digest aislado entre dos organizaciones | `test_email_dispatch.py::test_dispatch_never_crosses_organization_boundaries` + `test_notification_preferences.py::test_preference_never_crosses_organizations` + `test_email_digest.py::test_digest_isolated_between_two_organizations` | ✅ COMPLIANT |
| R9 Plantillas ES formal | Correo urgente usa tuteo formal | `test_email_templates.py::test_render_immediate_uses_formal_tuteo_not_voseo` + `test_render_digest_uses_formal_tuteo_not_voseo` | ✅ COMPLIANT |

**notifications-inapp (delta ADDED)** (1 requisito, 3 escenarios):

| Requisito | Escenario | Test | Resultado |
|-----------|-----------|------|-----------|
| R10 Encolado de entrega email en la creación | Notificación urgente se encola para envío inmediato | `test_email_outbox.py::test_urgent_notification_enqueues_outbox_row_and_marks_emailed_at` | ✅ COMPLIANT |
| R10 Encolado de entrega email en la creación | Notificación no urgente queda pendiente de digest | `test_email_outbox.py::test_non_urgent_notification_does_not_enqueue_outbox_row` | ✅ COMPLIANT |
| R10 Encolado de entrega email en la creación | REST sigue autoritativo si el email falla o está deshabilitado | `test_email_outbox.py::test_email_disabled_urgent_notification_persists_without_outbox_row` + `test_email_dispatch.py::test_dispatch_failure_leaves_row_pending_and_retryable` + suite base `test_notifications_inapp.py` (contrato REST sin cambios, dentro de los 539) | ✅ COMPLIANT |

**Resumen de cumplimiento**: 19/19 escenarios COMPLIANT (9 requisitos de `email-notifications` + 1 delta de `notifications-inapp` = 10 requisitos, ambos totalmente cubiertos).

### Corrección (evidencia estática) — contratos arquitectónicos del cambio

| Requisito de diseño | Estado | Notas |
|----------------------|--------|-------|
| Puerto agnóstico — `EMAIL_BACKEND` no toca dominio | ✅ Implementado | `app/email/sender.py` define `EmailSender` (Protocol) + `ConsoleEmailSender`/`SmtpEmailSender` + `get_email_sender()` factory por `settings.EMAIL_BACKEND`. `app/email/outbox.py` y `app/email/digest.py` importan solo `get_email_sender`, nunca una clase adaptadora concreta. |
| Único despachador — sin drain inline en el evaluador | ✅ Implementado | `git diff a127e0c..HEAD -- backend/app/alerts/evaluator.py` → **diff vacío**, confirmado en esta verificación. El único punto de despacho es el job `email_dispatch` registrado por `register_email_jobs` en `app/email/scheduler.py`. |
| Claim + COMMIT antes del send | ✅ Implementado | `dispatch_outbox` en `app/email/outbox.py`: `UPDATE ... WHERE status='pending' RETURNING` + `db.commit()` antes de invocar `EmailSender.send`, según T18/D3. Confirmado por `test_dispatch_failure_leaves_row_pending_and_retryable` (la fila persiste `pending` tras fallo de envío posterior al claim). |
| Failed terminal + log ERROR sin re-digest | ✅ Implementado | `test_dispatch_exhausted_retries_ends_in_failed_with_error_log` y `test_digest_outbox_exhausted_retries_notifications_stay_visible` confirman estado terminal `failed`, log de `ERROR` con `dedup_key`, y ausencia de re-intento/re-digest. |
| Digest idempotente | ✅ Implementado | `dedup_key` único + filtro `emailed_at IS NULL`; confirmado por `test_digest_rerun_after_marking_finds_nothing_to_send`. |
| Preferencias 422/aislamiento | ✅ Implementado | Validación `Literal["none","daily","weekly"]` en `schemas.py`; confirmado por tests unitarios y black-box en vivo (`PUT frequency=hourly` → 422). |
| `EMAIL_BACKEND` default `console` | ✅ Implementado | `app/config.py`: `EMAIL_BACKEND: str = "console"`; confirmado — la suite completa nunca toca red real. |
| Frontera de imports (`app/email/*` solo importa `notifications.models`, nunca `.repository`) | ✅ Implementado | Confirmado con `rg -n "import" app/email/{outbox,digest,models}.py` — únicamente `app.modules.notifications.models`, `app.modules.users.models`, `app.config`, `app.database`, `app.shared.*`. |

### Coherencia (Design)

| Decisión | ¿Seguida? | Notas |
|----------|-----------|-------|
| D1 — Engine `app/email/` (no `modules/email/`); `NotificationPreference` en `modules/notifications/` | ✅ Sí | Confirmado por estructura de archivos y `db_init.py`. |
| D2 — Outbox transaccional, hook único en `create()`, frontera de imports | ✅ Sí | `repository.py::create()` llama `enqueue_immediate_email` justo después de `buffer_notification`; frontera de imports respetada. |
| D3 — Único despachador vía job APScheduler, claim+commit antes del send | ✅ Sí | Confirmado arriba (diff vacío de `evaluator.py` + patrón claim/commit). |
| D4 — Digest con doble idempotencia y fallo permanente acotado | ✅ Sí | Confirmado por tests de digest y agotamiento de reintentos. |
| D5 — Clasificación `email_class` (`license_expired` único IMMEDIATE) | ✅ Sí | Confirmado por `test_email_policy.py` (8 casos). |
| D6 — Plantillas Python puras sin Jinja; preferencia default `none` | ✅ Sí | `app/email/templates.py` sin dependencia de Jinja; default `none` confirmado por GET sin registro. |
| D6 (sugerencia de path) — `GET/PUT /notifications/preferences` | ⚠️ Desviación documentada | Implementado como `GET/PUT /api/v1/notification-preferences` (path plano), siguiendo el contrato vinculante de `specs/email-notifications/spec.md` en lugar de la sugerencia de `design.md`. Documentado en `tasks.md` ("Ajustes sobre design.md", punto 2). No rompe ningún escenario del spec — al contrario, es lo que el spec exige literalmente. |
| D8 — Puerto `EmailSender` + adaptadores `console`/`smtp` | ✅ Sí | Confirmado arriba. |
| Migración "única" (Migration/Rollout de design.md) | ⚠️ Desviación documentada | Dividida en dos migraciones (`0011_add_email_outbox`, `0012_add_notification_preferences`) por la invariante de `alembic check` (modelo ORM y migración en el mismo commit — precedente `06-reminders`). Documentado en `tasks.md` ("Ajustes sobre design.md", punto 1). Cadena de migraciones verificada limpia en esta verificación (upgrade/downgrade/upgrade sin diff). |

### Desviaciones documentadas (tasks.md / apply-progress) — verificadas

1. **`DigestFrequency` adelantado al Lote B** (T26): el enum se añadió en el mismo commit que `EmailOutboxStatus` por economía de edición del archivo `shared/enums.py`; sin efecto de esquema hasta el Lote C. Verificado: no introduce comportamiento antes de tiempo (el enum puro no tiene efecto sin la tabla `notification_preferences`, creada en 0012). No bloqueante.
2. **Bugfix real fuera de alcance**: `backend/alembic/env.py` — `fileConfig(...)` usaba el default `disable_existing_loggers=True`, lo que deshabilitaba silenciosamente los loggers `solercia.*` cada vez que un test invocaba Alembic en el mismo proceso, rompiendo aserciones `caplog` sobre logs de `ERROR` en agotamiento de reintentos — pero solo quando corría la suite completa (dependiente del orden), nunca en aislamiento. Corregido con `disable_existing_loggers=False`. Verificado: el archivo está presente con el fix (`disable_existing_loggers=False` confirmado en la ejecución completa de 539 pruebas, incluyendo `test_migrations_baseline.py` y `test_boards_backfill_migration.py`, que invocan Alembic en proceso).

### Verificación black-box contra contenedor Docker (obligatoria)

Se detectó que el contenedor `backend` en ejecución (49 min de antigüedad) estaba **desactualizado** respecto al código de este cambio (`alembic current` reportaba `0010 (head)`, sin las migraciones 0011/0012). Se ejecutó `docker compose up -d --build backend` para reconstruir con el código actual, como exige el protocolo de verificación.

| Verificación | Resultado |
|--------------|-----------|
| `alembic current` tras rebuild | `0012 (head)` ✅ |
| Arranque del contenedor | `Application startup complete`, sin errores en logs, seed y scheduler inicializados correctamente ✅ |
| Jobs registrados en logs (`EMAIL_ENABLED` no seteado → default `False`) | Solo `Alert Engine Evaluation` y `Reminder Dispatch`; **ningún job `email_dispatch`/`email_digest` registrado** — gating correcto confirmado ✅ |
| `GET /api/v1/notification-preferences` (token admin, sin registro previo) | `200`, `{"frequency": "none", "hour": 8, "weekday": null}` ✅ |
| `PUT /notification-preferences {frequency: daily, hour: 8}` | `200`; `GET` posterior refleja `daily` ✅ |
| `PUT /notification-preferences {frequency: hourly, hour: 8}` | `422`, `detail`/`errors` con `"Input should be 'none', 'daily' or 'weekly'"` ✅ |
| Restauración final a `frequency=none` | `200`; `GET` final confirma `none` ✅ |
| SMTP real configurado | No — `EMAIL_BACKEND`/`SMTP_*` sin overrides en `docker-compose.yml` ni en el entorno del contenedor; se usa el default `console` del código ✅ |
| Logs tras las llamadas black-box | Sin errores, sin trazas de `email_dispatch`/`email_digest` ✅ |

### Issues encontrados

**CRITICAL**: Ninguno.

**WARNING**: Ninguno. (Las dos desviaciones respecto a `design.md` — path de preferencias y división de migración — están documentadas, no bloqueantes, y no contradicen ningún escenario vinculante del spec; se registran como coherencia parcial, no como hallazgo bloqueante.)

**SUGGESTION**:
- El contenedor Docker de desarrollo local quedó desactualizado (49 min) respecto al código ya mergeado a `main`; no es un defecto del cambio, pero conviene que el flujo de trabajo local reconstruya el contenedor tras cada tanda de commits de un cambio SDD antes de dar por buena una verificación manual, para evitar falsos negativos de "alembic no está al día".
- No se ejecutó `pytest --cov`; si el proyecto adopta un umbral de cobertura en el futuro, sería conveniente añadirlo al comando estándar de verificación.

### Veredicto

**PASS**

539/539 pruebas pasando (498 base + 41 nuevas), `ruff`/`mypy` limpios, cadena de migraciones 0010→0011→0012 con upgrade/downgrade verificados sin diff, único despachador confirmado (diff vacío de `evaluator.py`), puerto `EmailSender` agnóstico confirmado por estructura de imports, y verificación black-box contra el contenedor reconstruido confirma el contrato REST de preferencias (200/200/422/200) y el gating correcto de `EMAIL_ENABLED=False` (ningún job de email registrado). Las 40/40 tareas de `tasks.md` están completas y corresponden al código real. Sin hallazgos CRITICAL ni WARNING bloqueantes.
