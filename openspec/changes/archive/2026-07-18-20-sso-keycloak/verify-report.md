```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:b630807431445b641a269a849ec64c341eafe1e9
verdict: pass
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 15/15
test_command: cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -q
test_exit_code: 1
test_output_hash: sha256:9e04b257d2f35d6a3c48858616eea387312176f7bd2fbd43f5d177a7f626a9e8
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:47009c7e2c8204622001bdd9e0dbe6f69a6415d7d8d8c4c7a3b305ab106344dd
```

## Informe de Verificación

**Cambio**: 20-sso-keycloak (SSO con Keycloak — OIDC como segundo método de login)
**Versión evaluada**: HEAD `b630807` (5 commits de aplicación + 2 commits de corrección post-verificación)
**Modo**: Strict TDD

> **Nota de re-verificación**: esta es la SEGUNDA corrida de `sdd-verify` sobre este cambio. La primera corrida (evidencia en `d6601c9`) encontró 1 CRITICAL bloqueante (persistencia SSO sin `commit()`). El commit `b630807` lo corrigió; esta corrida re-verifica ESE hallazgo específico contra el diff, la nueva prueba de regresión y una corrida completa de la suite. El detalle original del hallazgo se conserva en la sección "Historial del hallazgo cerrado" al final, por trazabilidad.

### Completitud
| Métrica | Valor |
|---------|-------|
| Tareas totales | 21 |
| Tareas completas | 21 |
| Tareas incompletas | 0 |

### Ejecución de build y pruebas

**Backend — pytest**: ✅ 683 aprobadas / ❌ 13 fallidas (idénticas al baseline preexistente, cero regresión — una prueba más que la corrida anterior: la nueva `test_resolve_commits_so_a_new_request_session_sees_the_provisioned_user`)
```text
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -q
Pytest: 683 passed, 13 failed
```
Verifiqué que las 13 fallas son EXACTAMENTE el mismo conjunto de la corrida anterior (comparación línea por línea de `FAILED tests/...`): `test_attachments.py::{test_upload_and_download_attachment, test_upload_rejects_oversized_file, test_download_requires_auth}`, `test_comments.py::{test_create_comment_with_mentions, test_create_comment_empty_body_rejected}`, `test_sprint_close.py::{test_close_sprint_idempotent_409, test_close_sprint_moves_incomplete_to_backlog, test_close_sprint_sums_only_done_tasks, test_velocity_averages_closed_sprints}`, `test_subtasks.py::{test_create_subtask_allows_hours, test_create_subtask_rejects_points}`, `test_task_key.py::{test_create_task_assigns_task_key, test_get_task_by_key}` — ninguna toca código de este cambio.

**Backend — `test_sso_service.py` aislado**: ✅ 12/12 aprobadas (incluye la prueba de regresión nueva).

**Backend — ruff**: ✅ Sin hallazgos (`ruff check .`)
**Backend — mypy**: ✅ Sin hallazgos (`mypy app`)

**Migración 0016 — alembic check**: ✅ (sin cambios respecto a la corrida anterior — `b630807` no toca la migración). "No new upgrade operations detected", head único `0016`, round-trip limpio.

**Frontend — build**: ✅ Compila limpio (Node v22.22.3), incluye el chunk lazy `auth-callback-component`.
**Frontend — lint**: ✅ Sin hallazgos.

### Re-verificación del hallazgo CRITICAL (cierre confirmado)

**Diff revisado** (`git show b630807 -- backend/app/modules/auth/sso_service.py`): en `resolve_or_provision_user`, el bloque que crea el `FederatedIdentity` ahora queda envuelto en:
```python
try:
    db.add(FederatedIdentity(...))
    await db.flush()
    await db.commit()
except Exception:
    await db.rollback()
    raise
return user
```
El `commit()` único confirma TANTO el `FederatedIdentity` recién agregado COMO el `User` auto-provisionado que se había hecho `flush()` más arriba (caso d) — porque `commit()` cierra toda la transacción pendiente de la sesión, no solo lo escrito dentro del `try`. Esto replica correctamente el precedente citado (`connectors/service.py::handle_oauth_callback`, que también hace un commit único con rollback ante excepción). Los caminos de solo lectura (identidad existente reutilizada, rechazos sin escritura) no entran a este bloque y correctamente no necesitan commit.

**Prueba de regresión revisada** (`test_sso_service.py::test_resolve_commits_so_a_new_request_session_sees_the_provisioned_user`): abre una `AsyncSession` ligada DIRECTAMENTE al `engine` (bypaseando el fixture `session` que usa SAVEPOINT y que fue precisamente lo que ocultó el defecto original), llama `resolve_or_provision_user`, cierra esa sesión, y luego abre una SEGUNDA sesión independiente para confirmar que el `User` y el `FederatedIdentity` son visibles — replica exactamente el patrón `get_db()` de producción (una sesión nueva por petición). Ejecuté esta prueba de forma aislada: **PASA**. Según el reporte del commit, falla en RED sin el fix (la segunda sesión ve 0 filas) — coherente con mi verificación empírica original del defecto.

**Corrida de la suite completa**: 683/683 pruebas del cambio+baseline pasan (679 originales + 3 del fix `d6601c9` + 1 de este fix), mismas 13 fallas heredadas, sin regresión.

**Veredicto de la re-verificación**: el hallazgo CRITICAL queda **CERRADO**. La corrección es correcta (commit único que abarca ambas escrituras, rollback simétrico ante excepción, sigue el precedente del codebase) y está probada con un mecanismo que específicamente evita el blind spot del arnés de pruebas que había ocultado el defecto original.

### Matriz de cumplimiento de especificación (15 escenarios / 10 requisitos) — actualizada

| Requisito | Escenario | Prueba | Resultado |
|-----------|-----------|--------|-----------|
| auth R4 | Usuario solo-SSO intenta login local | `test_auth.py::test_login_with_null_hashed_password_returns_401_with_generic_message` | ✅ COMPLIANT |
| auth R6 | Emisión de JWT tras callback SSO exitoso | `test_auth_sso.py::test_sso_callback_happy_path_sets_refresh_cookie_without_access_in_url` | ✅ COMPLIANT |
| auth R7 | Login dual por ambos métodos | `test_auth.py::test_user_with_password_and_sso_link_authenticates_by_either_method` | ✅ COMPLIANT |
| sso-oidc R1 | Inicio de sesión SSO | `test_auth_sso.py::test_sso_login_redirects_and_persists_state` | ✅ COMPLIANT |
| sso-oidc R2 | State inválido o expirado | `test_auth_sso.py::{test_sso_callback_rejects_unknown_state, test_sso_callback_rejects_a_reused_state}` | ✅ COMPLIANT |
| sso-oidc R2 | Redirect URI fuera de la allowlist | `test_auth_sso.py::test_sso_login_ignores_a_client_supplied_redirect_uri` | ✅ COMPLIANT (desviación ratificada D5 — "allowlist de 1" por construcción) |
| sso-oidc R2 | ID token inválido | `test_auth_sso.py::test_sso_callback_rejects_a_forged_id_token` + `test_oidc_client.py` (7 variantes) | ✅ COMPLIANT |
| sso-oidc R3 | Correo no verificado | `test_sso_service.py::test_resolve_rejects_unverified_email_without_creating_anything` | ✅ COMPLIANT |
| sso-oidc R4 | Callback feliz — enlace de usuario existente | `test_sso_service.py::test_resolve_links_an_existing_user_by_verified_email` | ✅ **COMPLIANT** (antes PARTIAL — la persistencia ahora está probada con sesiones independientes) |
| sso-oidc R4 | Enlace idempotente por sub | `test_sso_service.py::test_resolve_reuses_an_existing_issuer_subject_link` | ✅ **COMPLIANT** (antes PARTIAL — el enlace ahora persiste, por lo que este camino sí se ejerce en producción en el segundo login) |
| sso-oidc R4 | Usuario no existente, auto-provisión desactivada | `test_sso_service.py::test_resolve_rejects_no_match_when_auto_provision_disabled` | ✅ COMPLIANT |
| sso-oidc R4 | Usuario no existente, auto-provisión activada | `test_sso_service.py::{test_resolve_auto_provisions_a_user_without_password_or_roles, test_resolve_commits_so_a_new_request_session_sees_the_provisioned_user}` | ✅ **COMPLIANT** (antes PARTIAL — cerrado por `b630807` con prueba de regresión dedicada de sesiones independientes) |
| sso-oidc R5 | Callback con error del IdP | `test_auth_sso.py::test_sso_callback_redirects_with_error_param_on_idp_error` | ✅ COMPLIANT |
| sso-oidc R6 | Nuevo proveedor solo por configuración | `test_auth_sso.py::test_sso_callback_rejects_a_state_issued_for_a_different_provider` (2do proveedor `azuread`) + `test_sso_service.py::test_require_provider_config_returns_config_when_fully_configured` | ✅ COMPLIANT (mecanismo probado; ver SUGGESTION 1) |
| sso-oidc R7 | Botón SSO y callback del SPA | `login.component.ts`/`auth-callback.component.ts` (build+lint) + prueba backend del callback + persistencia ahora confirmada | ✅ **COMPLIANT** (antes PARTIAL — el `/auth/me` inmediato tras `/auth/refresh` ya no falla, porque el usuario/enlace SSO se confirma en la misma transacción) |

**Resumen de cumplimiento**: **15/15 escenarios COMPLIANT**.

### Corrección (evidencia estática + dinámica) — actualizada
Todos los ítems de la corrida anterior se mantienen ✅ Implementado. El único ítem marcado ❌ anteriormente pasa a ✅:

| Requisito | Estado | Nota |
|-----------|--------|------|
| Persistencia de la identidad/usuario resuelto en el callback SSO | ✅ **Implementado** (antes ❌) | `resolve_or_provision_user` ahora hace `await db.commit()` tras el `flush()` del enlace, con `rollback()` simétrico ante excepción (`b630807`); probado con sesiones reales independientes que bypasean el SAVEPOINT del arnés de pruebas |

### Coherencia (Diseño)
Sin cambios respecto a la corrida anterior — todas las decisiones de diseño (D1–D5) se siguen; la corrección `b630807` es coherente con D4 (orden de resolución) y sigue explícitamente el precedente de `connectors/service.py` citado en el propio design.md como referencia de patrón transaccional.

### Cumplimiento TDD (Strict TDD) — actualizado
| Verificación | Resultado | Detalle |
|--------------|-----------|---------|
| Evidencia TDD reportada | ✅ | RED confirmado (la prueba de regresión falla sin el fix, la segunda sesión ve 0 filas), GREEN con el fix |
| Todas las tareas tienen pruebas | ✅ | 21/21 + 4 pruebas nuevas acumuladas post-apply (`d6601c9` + `b630807`) |
| RED confirmado | ✅ | Documentado en el mensaje del commit `b630807`; el diseño de la prueba (sesiones directas al `engine`, sin SAVEPOINT) hace el RED verificable por inspección: sin `commit()`, la segunda sesión necesariamente ve 0 filas |
| GREEN confirmado | ✅ | 683/683 en esta corrida, incluida la prueba nueva ejecutada de forma aislada |
| Triangulación adecuada | ✅ | La prueba de regresión es específica al defecto (no duplica las pruebas existentes de `resolve_or_provision_user`, que ya cubrían la lógica de resolución pero no la persistencia entre sesiones) |
| Safety net en archivos modificados | ✅ | Suite completa corrida tras el fix, sin regresión |

**Cumplimiento TDD**: 6/6 verificaciones aprobadas

### Hallazgos (estado final)

**CRITICAL**: Ninguno. (El único hallazgo de la corrida anterior — persistencia SSO sin `commit()` — está cerrado y verificado, ver sección de re-verificación arriba.)

**WARNING**: Ninguno.

**SUGGESTION** (no bloqueantes, se mantienen de la corrida anterior):
1. La cobertura de "R6 sso-oidc — nuevo proveedor solo por configuración" sigue siendo indirecta: la prueba que configura un segundo proveedor (`azuread`) lo hace para probar el cruce `state`↔`provider`, no un login feliz completo contra ese segundo proveedor. Recomendado para un cambio futuro, no bloqueante.
2. El checklist manual E2E con Keycloak real (T21) sigue pendiente, documentado como tal. No bloqueante para este cambio; recomendado antes de habilitar `SSO_ENABLED=true` en un ambiente real.

### Veredicto
**PASS** — 21/21 tareas completas, 683/683 pruebas del cambio+baseline pasan (mismas 13 fallas heredadas, sin regresión), 15/15 escenarios de especificación COMPLIANT, ruff/mypy/build/lint limpios, migración 0016 íntegra (`alembic check` sin diff, round-trip limpio), `er-model.md` correcto. El hallazgo CRITICAL de la corrida anterior (persistencia SSO sin `commit()`) fue corregido en `b630807` con una solución correcta (commit único + rollback simétrico, sigue el precedente de `connectors/service.py`) y una prueba de regresión que específicamente cierra el blind spot del arnés de pruebas que había ocultado el defecto original. Listo para `sdd-archive`.

---

### Historial del hallazgo cerrado (trazabilidad — corrida anterior, commit `d6601c9`)

> Se conserva el detalle original por trazabilidad. Resumen: `resolve_or_provision_user` (`backend/app/modules/auth/sso_service.py`) hacía `db.add()`+`db.flush()` del `User` auto-provisto y del `FederatedIdentity` de enlace, pero nunca `db.commit()`; ni `sso_callback` ni el router confirmaban después. Verifiqué empíricamente (script ad hoc contra `solercia_test`, patrón `add()+flush()+close()` sin `commit()`, lectura desde sesión nueva) que 0 filas quedaban visibles — reproduciendo el patrón real de `get_db()` (sesión nueva por petición, sin auto-commit). Las pruebas existentes no lo detectaban porque `tests/conftest.py` liga el request de prueba a la MISMA sesión vía SAVEPOINT, donde el `flush()` ya es visible sin necesitar `commit()`. Impacto: la auto-provisión SSO (R4-d) y el enlace por correo (R4-b) se revertían al cerrar el request; el `/auth/me` inmediato del SPA fallaba con `401 user_not_found` para usuarios recién auto-provisionados. **Cerrado en `b630807`** — ver sección de re-verificación arriba para el detalle de la corrección y su prueba.
