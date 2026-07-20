# Verify Report: 26 · Administración de empresas y empresa activa

**Fecha**: 2026-07-20
**Rama**: `feat/admin-empresas`
**HEAD verificado**: `9a8c4af` (rango de trabajo `3579b3b..9a8c4af`, 10 commits sobre `preview`)
**Modo**: Strict TDD activo — artefactos completos (proposal + 3 specs + design + tasks) — verificación por lectura de código + ejecución real de la suite completa de pytest contra Postgres de test (`solercia_test`) + `ng build` de producción + ciclo real `upgrade head → downgrade -1 → upgrade head` de Alembic contra una base descartable.

## Veredicto final

**PASS WITH WARNINGS**

## Resumen ejecutivo

0 CRITICAL, 2 WARNING, 0 SUGGESTION. Suite completa del backend en **1249 passed, 0 failed** (1210 preexistentes del cambio 25 ya archivado + 39 nuevos), `ng build --configuration production` verde, migración 0021 verificada con dedup+unique+reversibilidad tanto por test dedicado como por un ciclo real `upgrade head → downgrade -1 → upgrade head` ejecutado en esta verificación contra una base descartable, los 4 gotchas del design confirmados con tests o código nombrados uno por uno, los tests de aislamiento del cambio 25 (`test_cross_tenant_isolation.py`, 52 tests) siguen verdes con el resolver nuevo, la protección "la empresa nunca queda sin admin" está testeada en member y en delete, y cada requisito de los 3 specs tiene su test o evidencia de código mapeada explícitamente. Los 2 WARNING son desviaciones de diseño documentadas por el propio apply, ninguna rompe un requisito del spec.

## 1. Completitud de tareas (tasks.md)

`rg "^\- \[ \]" tasks.md` → 2 coincidencias: **10.6** y **12.4**, ambas marcadas explícitamente `PENDIENTE (requiere navegador/./gestion.sh levantado, no ejecutable por el agente en este entorno)` con el detalle exacto de qué falta verificar en vivo (selector de empresa en 2 empresas + manejo de error; CRUD de miembros end-to-end en la UI). Todas las demás tareas de las Fases 0–13 (incluidas 13.1–13.5 de cierre) están `[x]`. `state.yaml` reporta `phases.apply: done`, `phases.verify: pending` (se actualiza a `done` al cierre de este reporte). Coincide exactamente con lo declarado en `sdd/26-admin-empresas/apply-progress`.

## 2. Evidencia de ejecución

| Comando | Resultado | Detalle |
|---|---|---|
| `cd backend && TEST_DATABASE_URL=... pytest -q` | ✅ **1249 passed**, 0 failed, 1 warning en 338.41s | El warning es el mismo `SAWarning` preexistente de SQLAlchemy por ciclo de FK `dependencies/organizations/users`, no relacionado con este cambio. Coincide exactamente con el número declarado por el apply (1210 baseline + 39 nuevos). |
| `pytest tests/test_active_organization.py -v` | ✅ 7 passed en 3.09s | Los 3 gotchas backend + resolución de header + `require_org_admin`, ver Sección 3. |
| `pytest tests/test_org_member_unique_migration.py -v` | ✅ 3 passed en 2.69s | Dedup, rechazo de duplicado post-constraint, downgrade sin pérdida de filas — contra base descartable `solercia_test_org_member_unique`. |
| `pytest tests/test_cross_tenant_isolation.py -v` | ✅ **52 passed** en 30.58s | Batería completa del cambio 25 sin ninguna regresión con el resolver de empresa activa nuevo (ver Sección 4). |
| `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` contra base descartable `solercia_verify_migration` (creada y destruida en esta verificación, fuera de `solercia_test`) | ✅ head llega a `0021`; downgrade deja `current=0020` sin error; upgrade vuelve a `0021 (head)` | Cadena completa desde `0001` hasta `0021` se aplica limpia sobre una base vacía; el ciclo down→up confirma reversibilidad real, no solo el test dedicado. |
| `source ~/.nvm/nvm.sh && nvm use 22.22.3 && npx ng build --configuration production` | ✅ build verde en 5.85s | Bundle inicial 993.90 kB, incluye el lazy chunk `organizations-page-component` (19.79 kB) confirmando que la ruta admin existe y compila. |
| `git log --oneline preview..feat/admin-empresas` | ✅ 10 commits | `3579b3b` (resolver+require_org_admin) … `9a8c4af` (docs cierre); coincide con el conteo declarado por el apply. |
| `git diff --stat` (rango completo) | 31 archivos, 4207 inserciones, 20 borrados (18 archivos de código backend+frontend, resto artefactos OpenSpec) | Ningún archivo de `backend/app/modules/auth/{service,router}.py` aparece en el diff (ver Sección 6, desviación 1). |

**Número exacto solicitado por el usuario**: la suite completa reporta **1249 passed, 0 failed** — coincide exactamente con "1249 tests verdes (1210 baseline + 39 nuevos)".

## 3. Los 4 gotchas del design como tests/código reales

| Gotcha | Verificación | Evidencia |
|---|---|---|
| (a) Autorización target-scoped sobre `/{id}` — NUNCA depende del header | `test_require_org_admin_uses_route_target_not_the_header` (admin de Y, miembro no-admin de X, header irrelevante porque `require_org_admin` nunca recibe el header) + `test_require_org_admin_non_member_of_route_target_returns_404` (404, no 403, para no revelar existencia) + `test_require_org_admin_member_but_not_admin_returns_403` | `backend/tests/test_active_organization.py:162-236` — los 3 PASSED. `require_org_admin` (`backend/app/dependencies.py:206`) resuelve la membresía directamente desde `organization_id` de la ruta, sin recibir ni consultar el header. |
| (b) Header de empresa ajena → 403 | `test_header_for_foreign_organization_returns_403` (`code == "not_a_member"`) + `test_malformed_header_returns_403_never_422` (UUID malformado → 403, nunca 422) | `test_active_organization.py:126-154` — ambos PASSED. `dependencies.py:142-169`: comentario explícito "NEVER 404 ... never 200", código `not_a_member` en ambas ramas. |
| (c) Sin header → primera membresía (retrocompatibilidad) | `test_without_header_falls_back_to_first_membership_by_created_at`: usuario con 2 membresías (`created_at` explícito para evitar empate), sin header, el tema devuelto es el de la empresa MÁS ANTIGUA | `test_active_organization.py:88-102` — PASSED. Reforzado por los 1249 tests globales (la inmensa mayoría no envía el header y siguen verdes) y por los 52 de `test_cross_tenant_isolation.py`. |
| (d) Logout limpia `sp-active-org` | Revisión de código (sin harness de frontend, out of scope del proposal) | `frontend/src/features/auth/auth.service.ts:123-132` (`clearSession()`): `localStorage.removeItem(ACTIVE_ORG_KEY)` junto a `TOKEN_KEY`, con comentario explícito del gotcha; `ACTIVE_ORG_KEY` se importa desde `active-org.store.ts:10` (`'sp-active-org'`). Confirmado por lectura directa de ambos archivos. |

## 4. Migración 0021 — dedup + unique + reversibilidad

Dos capas de evidencia, ambas ejecutadas en esta verificación:

1. **Test dedicado** `backend/tests/test_org_member_unique_migration.py` (contra base descartable `solercia_test_org_member_unique`, mismo patrón que `test_boards_backfill_migration.py`): `test_dedup_keeps_the_oldest_membership_row` (siembra 2 filas duplicadas con `created_at` distinto vía SQL crudo tras `upgrade 0020`, sube a `0021`, queda 1 fila y es la de `created_at` mínimo con su rol), `test_unique_constraint_rejects_new_duplicate_after_upgrade` (tras `0021`, insertar otro duplicado lanza `asyncpg.UniqueViolationError`), `test_downgrade_removes_constraint_without_losing_rows` (downgrade a `0020` elimina la constraint sin cambiar el conteo de filas). **3/3 PASSED**.
2. **Ciclo real ejecutado en esta verificación** contra una base descartable nueva (`solercia_verify_migration`, creada y destruida solo para esta prueba, sin tocar `solercia_test`): `alembic upgrade head` aplica limpio `0001→0021` (incluye `0020→0021, unique_org_member`); `alembic current` confirma `0021 (head)`; `alembic downgrade -1` baja a `0020` sin error; `alembic upgrade head` vuelve a `0021 (head)` sin error. Reversibilidad confirmada con evidencia de ejecución directa, no solo por el test.

Ambas capas coinciden con `multi-tenancy` — Requirement "Unicidad de membresía por empresa y usuario" y sus 3 escenarios.

## 5. Aislamiento cross-tenant del cambio 25 con el resolver nuevo

`backend/tests/test_cross_tenant_isolation.py` — **52/52 PASSED** en esta ejecución, sin ninguna modificación a ese archivo por parte de este cambio (`git diff --stat` no lo lista). El meta-test `test_all_modules_are_classified` también pasa, confirmando que el módulo `organizations/` (extendido con CRUD/miembros en este cambio) sigue clasificado correctamente. Ningún test de la batería de 25 cambió de comportamiento: el resolver nuevo cae al mismo fallback ("primera membresía") cuando esos tests no envían el header `X-Organization-Id`, exactamente como exige la Decisión 1 del design ("fallback conserva TODOS los tests y el WS actuales").

## 6. Trazabilidad de requisitos → tests/evidencia

### organizations-admin

| Requirement | Test(s) / evidencia |
|---|---|
| R1 — Bootstrap de admin al crear empresa | `test_create_organization_bootstraps_creator_as_admin`, `test_create_organization_duplicate_slug_is_rejected`, `test_create_organization_requires_auth` (`test_organizations_crud.py`) |
| R2 — Permisos por rol lectura/escritura empresa y miembros | `test_get_organization_{any_member_can_read,non_member_returns_404,requires_auth}`, `test_update_organization_{as_admin_persists_name,rejected_for_member_role,non_member_returns_404}`, `test_delete_organization_{as_admin_soft_deletes,rejected_for_member_role,non_member_returns_404}` (`test_organizations_crud.py`); `test_list_members_{any_member_can_read,non_member_returns_404}`, `test_add_member_rejected_for_member_role`, `test_update_member_role_rejected_for_member_role`, `test_remove_member_rejected_for_member_role` (`test_organizations_members.py`) |
| R3 — Unicidad de membresía + protección "sin admin" | `test_add_member_duplicate_is_rejected`; `test_update_member_role_demoting_the_only_admin_is_rejected`, `test_remove_member_removing_the_only_admin_is_rejected` (`test_organizations_members.py`); + Sección 4 (migración) |
| R4 — Resolución de empresa activa por header con fallback | `test_active_organization.py` completo (Sección 3) |
| R5 — "Mis empresas" y `/auth/me` reflejan la empresa activa | `test_mine_lists_every_organization_with_its_role`, `test_mine_requires_auth`, `test_auth_me_reflects_the_header_supplied_organization` (`test_organizations_crud.py`) |

### frontend-org-switcher (sin harness de frontend, out of scope del proposal — evidencia de código, archivo y símbolo)

| Requirement | Evidencia de código |
|---|---|
| R1 — Selector en el layout | `frontend/src/features/organizations/org-switcher.component.ts` (`OrgSwitcherComponent`, consume `organizations.service.ts#mine()`); proyectado en `frontend/src/app/app.component.ts` `[header-actions]` |
| R2 — Cambio refresca todo el contexto | `active-org.store.ts#ActiveOrgStore.setActiveOrg()` (línea 33-37): persiste `sp-active-org` y ejecuta `window.location.reload()` — recarga íntegra en vez de reset selectivo (Decisión 5 del design) |
| R3 — Interceptor inyecta el header | `frontend/src/features/auth/auth.interceptor.ts` (`withActiveOrg`, líneas 46-53 y 76-79); `handle401` (líneas 96-133) preserva el header también en el retry post-refresh |
| R4 — Estado de error no rompe el layout | `org-switcher.component.ts#selectOrganization()` (líneas 151-174): llama `GET /organizations/{id}` ANTES de persistir; solo en `next` invoca `setActiveOrg`/reload; en `error` solo setea `this.error`, sin tocar el store — el contexto anterior queda intacto |
| R5 — Textos en español colombiano formal | `frontend/src/assets/i18n/es-CO.json#orgSwitcher` — confirmado: "Selecciona", "Verifica", "Inténtalo", "Cambia" (tuteo formal, tildes correctas, cero voseo) |

### multi-tenancy

| Requirement | Test(s) |
|---|---|
| R2 modificado — resolución de empresa activa header+fallback | `test_active_organization.py` (Sección 3) + `test_cross_tenant_isolation.py` (Sección 5, sin regresión) |
| Unicidad de membresía (added) | `test_org_member_unique_migration.py` (Sección 4) |

## 7. Protección "la empresa nunca queda sin admin"

Testeada en dos operaciones distintas, no solo una: `test_update_member_role_demoting_the_only_admin_is_rejected` (el único admin intenta degradarse a `member` → 409 `last_admin_protected`, la membresía permanece intacta, confirmado con una segunda consulta post-intento) y `test_remove_member_removing_the_only_admin_is_rejected` (el único admin intenta removerse → mismo rechazo). Implementación: `service.py#_reject_if_last_admin()` (líneas 287-292) consulta `repository.py#count_admins()` antes de aplicar el cambio, en ambos flujos (`update_member_role` y `remove_member`).

## 8. Auditoría de calidad de aserciones (Strict TDD, paso 5f)

Escaneados los 4 archivos de test nuevos (`test_active_organization.py`, `test_org_member_unique_migration.py`, `test_organizations_crud.py`, `test_organizations_members.py`, más las adiciones a `test_realtime_ws_auth.py`) contra los patrones prohibidos:

- `rg "assert True$|assert 1 == 1"` → 0 coincidencias.
- Único `for` fuera de `test_cross_tenant_isolation.py` (ya auditado en el verify de 25) aparece en `test_organizations_members.py:179`: es un loop de BÚSQUEDA (resuelve el `membership.id` propio del caller recorriendo el listado), no un loop de ASERCIONES — el `assert own_membership_id is not None` posterior al loop fallaría si la colección estuviera vacía o el elemento no apareciera; no es un ghost-loop.
- Todos los tests HTTP combinan código de estado + valor de negocio (`code`, `role`, `data`), o HTTP + segunda consulta post-operación para confirmar que la entidad protegida no cambió — ningún smoke-test-only, ninguna aserción de detalle de implementación.
- Los tests de WebSocket (`test_valid_hint_selects_the_named_membership`, `test_hint_for_foreign_organization_closes_before_accept`) ejercen conexión real vía `TestClient.websocket_connect`, con `monkeypatch` sobre `manager.register` para capturar el `org_id` resuelto (mock quirúrgico, no reemplaza la aserción de comportamiento) y `pytest.raises(WebSocketDisconnect)` con `code == 1008`.

**Calidad de aserciones**: ✅ Sin hallazgos — todas las aserciones ejercitan comportamiento real vía HTTP/WebSocket contra el ASGI app o contra Alembic/Postgres reales.

### TDD Compliance

| Check | Resultado | Detalle |
|-------|--------|---------|
| Evidencia TDD reportada | ✅ | `tasks.md` documenta `[RED]`/`[GREEN]` por tarea (1.1-1.8, 2.1-2.5, 3.1-3.10, 4.1-4.12, 5.1-5.6) con el comando de verificación exacto por fase. |
| Todas las tareas backend tienen tests | ✅ | Fases 1-6 (Lote 1) — 100% con `[RED]`/`[GREEN]` explícito. |
| RED confirmado (archivos existen) | ✅ | Los 4 archivos de test nuevos existen y contienen los tests declarados. |
| GREEN confirmado (tests pasan) | ✅ | 1249/1249 en ejecución real de esta verificación. |
| Triangulación adecuada | ✅ | Cada requirement con múltiples escenarios tiene un test por escenario (happy + error + permisos), ver Sección 6. |
| Red de seguridad en archivos modificados | ✅ | `dependencies.py`, `organizations/{repository,service,router}.py`, `realtime/router.py` modificados; suite completa (1249) confirma cero regresión. |

**TDD Compliance**: 6/6 checks pasados.

## 9. Coherencia con design.md

| Decisión de diseño | Seguida? | Notas |
|---|---|---|
| Decisión 1 — resolución por header validado, fallback compatible | ✅ Sí | Confirmado en Sección 3 |
| Decisión 2 — target-scoped con `MemberRole.admin`, no RBAC catalog | ✅ Sí | `require_org_admin` usa `MemberRole`, no `require_admin`; confirmado en Sección 3 |
| Decisión 3 — migración 0021 dedup + unique reversible | ✅ Sí | Confirmado en Sección 4 |
| Decisión 4 — bootstrap transaccional sin superadmin global | ✅ Sí | `create_with_admin` (repository.py:39) crea org+membership en un commit |
| Decisión 5 — recarga completa tras el switch | ✅ Sí | `ActiveOrgStore.setActiveOrg()` — confirmado en Sección 6 |

Sin desviaciones que rompan un requisito del spec (ver Sección 10 para las 2 desviaciones documentadas, no bloqueantes).

## Issues

### CRITICAL
Ninguno.

### WARNING

1. **`auth/me` no requirió el cambio de código que preveía `design.md`** (no bloqueante). El design (`File Changes`, línea 66) esperaba modificar `backend/app/modules/auth/service.py`/`router.py` para que `auth/router.py` pasara el `membership` ya resuelto por `get_current_membership` a `build_user_read`, en vez de recalcular con `primary_organization_id`. La implementación encontró que `auth/router.py` YA reenviaba `membership.organization_id` (no `primary_organization_id`), por lo que el escenario "`/auth/me` cambia según el header enviado" quedó cubierto sin tocar esos archivos — confirmado por `git diff --stat` sin listar `auth/{service,router}.py` y por `test_auth_me_reflects_the_header_supplied_organization` PASSED. Es una simplificación positiva (menos superficie tocada), no una desviación que rompa el requirement organizations-admin R5, pero se señala porque el design.md documentó un cambio que no ocurrió.
2. **Página de administración ubicada en `pages/admin/organizations/` en vez de `features/manage-organizations/**`** (no bloqueante). El design (`File Changes`, línea 68) y el proposal (`Affected Areas`) proponían `frontend/src/features/manage-organizations/**`; la implementación la ubicó en `frontend/src/pages/admin/organizations/organizations-page.component.ts`, replicando el patrón real ya existente de las páginas admin hermanas (`users`, `roles`, `menus`, `dependencies`, todas bajo `pages/admin/{name}/`). Consistencia deliberada con la convención vigente del proyecto, documentada explícitamente en el apply-progress; no afecta ningún escenario del spec `frontend-org-switcher` (todos verificados por código en Sección 6) ni la ruta lazy `/admin/organizations` (confirmada por el chunk `organizations-page-component` en el build de la Sección 2).

### SUGGESTION
Ninguno.

## Conclusión

13/13 fases completas salvo 2 tareas explícitamente flagged como verificación manual en navegador (10.6, 12.4 — fuera del alcance ejecutable por el agente, código completo y `ng build` verde), 12/12 requisitos de los 3 specs cubiertos con evidencia de ejecución real (1249 passed, 0 failed) o evidencia de código nombrada archivo+símbolo para el frontend (sin harness, out of scope del proposal), los 4 gotchas del design confirmados uno por uno con tests o código, migración 0021 verificada con test dedicado Y con un ciclo real `upgrade→downgrade→upgrade` ejecutado en esta verificación, aislamiento cross-tenant del cambio 25 intacto (52/52), protección "sin admin" testeada en dos flujos distintos, `ng build` de producción verde. Los 2 WARNING son desviaciones de diseño documentadas y justificadas, ninguna rompe un requirement. **Veredicto: PASS WITH WARNINGS**.
