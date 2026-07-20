# Tasks: 26 · Administración de empresas y empresa activa

## Gate de dependencia (bloqueante)

El **apply** de este cambio NO puede iniciar hasta que `25-multiempresa-scoping` complete `apply` + `verify` + `archive` (`state.yaml` → `apply_gating`). El resolver de empresa activa de este cambio asume que el aislamiento por `organization_id` ya quedó endurecido y auditado por la batería `test_cross_tenant_isolation.py` del cambio 25. Si al iniciar la Fase 1 el cambio 25 sigue en `apply: pending` o no está bajo `openspec/changes/archive/`, DETENER y esperar — no adelantar ningún commit de este archivo.

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~510–570 backend (resolver+`require_org_admin` ~60, service/repo/schemas CRUD+members ~150, migración 0021 ~50, WS hint ~20, tests ~250) + ~250–320 frontend (store ~50, service/model ~90, páginas admin ~140, selector ~40, interceptor/auth ~20) — total ~760–890 |
| 400-line budget risk | High — el design.md ya lo marca explícito (`400-line budget risk: High`, `Decision needed before apply: Yes`); dos dominios (resolución de tenant + CRUD/members) más frontend de switcher y páginas admin no caben en una unidad chica sin fragmentar la invariante de seguridad (header validado + target-scoped) |
| Chained PRs recommended | El design.md sugiere 3 PRs encadenados; se **anula** esa sugerencia y se aprueba, como en el cambio 25, `size:exception` con **single-pr**: commits escalonados dentro de una sola integración a `preview`, sin PRs de GitHub separados. Motivo: el resolver de empresa activa (Lote 1) y el switcher de frontend (Lote 2) comparten el mismo contrato de header/gotchas y revisarlos por separado duplicaría el contexto de seguridad sin reducir el riesgo real |
| Suggested split | Lote 1 (backend: resolver + migración + CRUD + miembros) → Lote 2 (frontend: store + interceptor + selector) → Lote 3 (páginas admin) |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No (anulado; ver nota de la tabla)
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Lote | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|------|----------|--------|----------------------|------------------|--------------------|
| U1 | 1 | Resolver de empresa activa (header validado + fallback) + `require_org_admin` target-scoped | 1 — `feat(dependencies): resuelve la empresa activa por header y agrega require_org_admin` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_active_organization.py -q` | Pytest contra Postgres real de test | Revert commit; nadie más depende aún de `require_org_admin` |
| U2 | 1 | Migración 0021 (dedup + unique reversible) | 2 — `feat(alembic): agrega 0021 unique organization_members con dedup reversible` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_org_member_unique_migration.py -q` | Pytest + Alembic contra base descartable (patrón `test_boards_backfill_migration.py`) | `alembic downgrade -1`; revert commit |
| U3 | 1 | CRUD de empresas (bootstrap, lectura, actualización, baja lógica) | 3 — `feat(organizations): agrega CRUD de empresas con bootstrap de admin` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_crud.py -q` | Pytest contra Postgres real de test | Revert commit; theme queda intacto (rutas separadas) |
| U4 | 1 | Gestión de miembros (alta/baja/rol + protección "sin admin") | 4 — `feat(organizations): agrega gestion de miembros con proteccion de unico admin` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_members.py -q` | Ídem | Revert commit |
| U5 | 1 | `GET /organizations/mine`, `/auth/me` refleja empresa activa, hint de empresa en WS | 5 — `feat(organizations): agrega mis-empresas y refleja empresa activa en auth/me` | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_crud.py tests/test_realtime_ws_auth.py -q` | Ídem | Revert commit |
| U6 | 1 | Regresión completa del backend + reversibilidad de la migración | 6 — cierre del Lote 1 (sin cambios de producción si U1–U5 no dejaron pendientes) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Ídem | Revert commit aislado si aparece un fix |
| U7 | 2 | Store de empresa activa (signal + `sp-active-org`) + limpieza en logout | 7 — `feat(auth): agrega store de empresa activa y limpia sp-active-org en logout` | Manual (sin harness de frontend, out of scope del proposal) — revisión de código + `ng build` | N/A | Revert commit |
| U8 | 2 | Interceptor inyecta `X-Organization-Id` | 8 — `feat(auth): inyecta X-Organization-Id en el interceptor` | Manual + `ng build` | N/A | Revert commit |
| U9 | 2 | Entidad `organization` (modelo + servicio CRUD/miembros) | 9 — `feat(organization): agrega entidad y servicio de empresas` | Manual + `ng build` | N/A | Revert commit |
| U10 | 2 | Selector de empresa activa en el layout + manejo de error | 10 — `feat(header): agrega selector de empresa activa con recarga completa` | Manual (`./gestion.sh` + prueba en navegador) + `ng build` | N/A | Revert commit |
| U11 | 3 | Página admin de empresas (CRUD) | 11 — `feat(admin): agrega pagina de administracion de empresas` | Manual + `ng build` | N/A | Revert commit |
| U12 | 3 | Página admin de miembros + ruta lazy | 12 — `feat(admin): agrega pagina de gestion de miembros de empresa` | Manual + `ng build` | N/A | Revert commit |
| U13 | — | Cierre: suite verde + migración up/down/up + commit final | 13 — cierre de la ola (solo si quedó algún fix pendiente) | `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` | Pytest + Alembic | Revert commit aislado por corrección |

## Fase 0 — Preparación (lectura de fixtures y patrones existentes)

- [x] 0.1 Verificar el gate de dependencia: `openspec/changes/25-multiempresa-scoping/state.yaml` con `phases.apply == done`, `phases.verify == done`, `phases.archive == done` (o el cambio ya movido a `openspec/changes/archive/`). Si no se cumple, DETENER — no continuar con la Fase 1.
- [x] 0.2 Leer `backend/app/dependencies.py:128-197` (`get_current_membership`, `require_role`, `require_admin`, `_has_admin_role`) — el resolver actual toma siempre la primera membresía por `created_at`; `require_admin` es RBAC (catálogo), separado de `MemberRole` (membresía).
- [x] 0.3 Leer `backend/app/modules/organizations/{models,repository,service,router}.py` — el módulo ya existe (theme de organización); el CRUD/miembros se agrega SIN tocar `/organizations/me/theme`.
- [x] 0.4 Leer fixtures reutilizables en `backend/tests/conftest.py`: `make_member` (líneas 204-242, factory por rol), `rbac_admin` (245-267), `two_orgs`/`_seed_org_data`/`TwoOrgs` (355-476).
- [x] 0.5 Leer `backend/app/modules/roles/router.py` como plantilla de envelope (`{data}`/`{data, meta}`) y de paginación (`app/shared/pagination.py`) para el listado de empresas/miembros.
- [x] 0.6 Leer `backend/tests/test_boards_backfill_migration.py` como plantilla de test de migración con dedup + reversibilidad contra una base descartable (`_recreate_backfill_database`, `command.upgrade`/`command.downgrade`).
- [x] 0.7 Leer `backend/app/realtime/router.py:36-91` (`_extract_token`, `_resolve_organization_id`) y `backend/tests/test_realtime_ws_auth.py` (patrón `?token=` fallback) como plantilla del hint de empresa en WS.
- [x] 0.8 Confirmar cabeza de Alembic: `0020_add_theme_to_organizations.py` es la última revisión; la nueva migración es `0021_unique_org_member.py revises 0020`.

## Lote 1 — Backend: resolver + migración + CRUD + miembros

### Fase 1 — Resolver de empresa activa y `require_org_admin` (Commit 1)

- [x] 1.1 [RED] gotcha (3) — sin header, cae al comportamiento previo: test con `two_orgs`/`make_member` — usuario con dos membresías, request SIN `X-Organization-Id`, `get_current_membership` resuelve la primera por `created_at` (idéntico a hoy; garantiza que la suite existente sin header no se rompe). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_active_organization.py -q` → falla (`get_current_membership` aún no acepta `Request`).
- [x] 1.2 [RED] Header válido resuelve la empresa activa (Scenario spec organizations-admin/multi-tenancy): usuario miembro de X e Y, request con `X-Organization-Id: <Y>` → el scope resuelto es Y, no X. Verify: mismo comando.
- [x] 1.3 [RED] gotcha (2) — header de empresa ajena → 403 `not_a_member`, nunca 404 ni 200: usuario sin membresía en Z, header `X-Organization-Id: <Z>` → 403. Verify.
- [x] 1.4 [RED] Header con UUID malformado (`X-Organization-Id: no-es-un-uuid`) → 403 (mismo código; NUNCA 422). Verify.
- [x] 1.5 [GREEN] Implementar `get_current_membership(request: Request, db, user)`: lee `X-Organization-Id`; ausente → comportamiento actual (primera por `created_at`); presente → valida UUID + `WHERE user_id AND organization_id`, 403 `not_a_member` si no hay fila o el UUID es inválido. Verify: 1.1–1.4 verdes.
- [x] 1.6 [RED] gotcha (1) — autorización sobre `/{id}` es target-scoped, NUNCA depende del header: (a) usuario admin de Y pero miembro no-admin de X envía `X-Organization-Id: <X>` y llama `PATCH /organizations/{Y}` → 200 (el gate mira la empresa de la RUTA, no el header); (b) el mismo usuario envía `X-Organization-Id: <Y>` pero llama sobre `{Z}` (donde no es miembro) → 404, no 403 (no revela existencia). Verify.
- [x] 1.7 [GREEN] Implementar `require_org_admin(organization_id: uuid.UUID)` en `dependencies.py`: carga la membresía del caller EN LA EMPRESA DE LA RUTA (no la del header/`get_current_membership`); 404 si no es miembro, 403 (`forbidden`) si `role != MemberRole.admin`. Verify: 1.6 verde.
- [x] 1.8 Confirmar que ningún test previo sin header cambió de resultado: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_org_theme.py tests/test_multi_tenancy.py -q` → verde sin modificar esos archivos.

### Fase 2 — Migración 0021: dedup + unique reversible (Commit 2)

- [x] 2.1 [RED] Test de migración (`backend/tests/test_org_member_unique_migration.py`, patrón de `test_boards_backfill_migration.py`): base descartable, `upgrade` a `0020`, sembrar por SQL crudo 2 filas duplicadas `(organization_id, user_id)` con `created_at` distinto y rol distinto, `upgrade` a `0021` → queda exactamente 1 fila y es la de `created_at` mínimo. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_org_member_unique_migration.py -q` → falla (`0021` no existe).
- [x] 2.2 [RED] Test: tras `0021`, insertar otra fila duplicada `(organization_id, user_id)` por SQL crudo → la base la rechaza (constraint única). Verify.
- [x] 2.3 [RED] Test: `downgrade` a `0020` → la constraint desaparece y el conteo de filas de `organization_members` no cambia respecto al estado post-dedup (no se pierden filas). Verify.
- [x] 2.4 [GREEN] Crear `backend/alembic/versions/0021_unique_org_member.py` (`revises 0020`): `upgrade()` — SQL crudo que borra duplicados conservando `MIN(created_at)` por `(organization_id, user_id)`, luego `op.create_unique_constraint("uq_organization_members_org_user", "organization_members", ["organization_id", "user_id"])`; `downgrade()` — `op.drop_constraint(...)`. Verify: 2.1–2.3 verdes.
- [x] 2.5 Reversibilidad manual local: `upgrade head` → `downgrade -1` → `upgrade head` sin error contra la base de test.

### Fase 3 — CRUD de empresas (Commit 3)

- [x] 3.1 [RED] `POST /organizations` happy path: usuario autenticado crea empresa (nombre+slug válidos) → 201, empresa creada, membresía `admin` del creador en el mismo commit (Scenario "Creación exitosa deja al creador como admin"). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_crud.py -q`.
- [x] 3.2 [RED] `POST /organizations` error: slug duplicado → error de validación/conflicto, no crea la empresa (Scenario "Slug duplicado es rechazado"). Verify.
- [x] 3.3 [RED] `POST /organizations` permisos: sin token → 401. Verify.
- [x] 3.4 [RED] `GET /organizations/{id}` happy: cualquier miembro (rol `member` o `admin`) lee su empresa. Verify.
- [x] 3.5 [RED] `GET /organizations/{id}` permisos/error: usuario sin membresía en esa empresa → 404, sin revelar existencia (Scenario "No miembro recibe 404 al leer"); sin token → 401. Verify.
- [x] 3.6 [RED] `PATCH /organizations/{id}` happy: admin de esa empresa actualiza `name`. Verify.
- [x] 3.7 [RED] `PATCH /organizations/{id}` permisos: rol `member` → 403, la empresa permanece intacta (Scenario "Rol no admin recibe 403 al escribir"); no miembro → 404. Verify.
- [x] 3.8 [RED] `DELETE /organizations/{id}` happy: admin da de baja lógica (`is_active=False`), NUNCA física. Verify.
- [x] 3.9 [RED] `DELETE /organizations/{id}` permisos: rol `member` → 403; no miembro → 404. Verify.
- [x] 3.10 [GREEN] Crear `schemas.py` (`OrganizationCreate`, `OrganizationUpdate`, `OrganizationRead`); extender `repository.py` (`create`, `update`, `soft_delete`, `get_membership(user_id, organization_id)`); extender `service.py` con `OrganizationService` (bootstrap transaccional: crea `Organization` + `OrganizationMember(role=admin)` en un solo `commit`; CRUD delegando en `require_org_admin` salvo `GET`=miembro); extender `router.py` (rutas nuevas; `/me/theme` intacto). Verify: 3.1–3.9 verdes.

### Fase 4 — Gestión de miembros (Commit 4)

- [x] 4.1 [RED] `GET /organizations/{id}/members` happy: miembro lista miembros con su rol. Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_members.py -q`.
- [x] 4.2 [RED] `GET .../members` permisos: no miembro → 404. Verify.
- [x] 4.3 [RED] `POST /organizations/{id}/members` happy: admin agrega un usuario existente por correo con un rol. Verify.
- [x] 4.4 [RED] `POST .../members` error: alta duplicada del mismo par `(organization_id, user_id)` → conflicto, sin duplicar la membresía (Scenario "Alta duplicada es rechazada"). Verify.
- [x] 4.5 [RED] `POST .../members` permisos: rol `member` → 403. Verify.
- [x] 4.6 [RED] `PATCH /organizations/{id}/members/{member_id}` happy: admin cambia el rol de OTRO miembro. Verify.
- [x] 4.7 [RED] `PATCH .../members/{member_id}` error: el único admin intenta degradarse a sí mismo a `member` → rechazado, la membresía admin permanece intacta (Scenario "Degradar o remover al único admin es rechazado"). Verify.
- [x] 4.8 [RED] `PATCH .../members/{member_id}` permisos: rol `member` → 403. Verify.
- [x] 4.9 [RED] `DELETE /organizations/{id}/members/{member_id}` happy: admin remueve a un miembro no-admin. Verify.
- [x] 4.10 [RED] `DELETE .../members/{member_id}` error: el único admin intenta removerse a sí mismo → rechazado (misma protección "sin admin"). Verify.
- [x] 4.11 [RED] `DELETE .../members/{member_id}` permisos: rol `member` → 403. Verify.
- [x] 4.12 [GREEN] Extender `repository.py` (`list_members`, `add_member`, `update_member_role`, `remove_member`, `count_admins(organization_id)`); `service.py` con `OrganizationMemberService` (valida "sin admin" antes de degradar/remover); `router.py` (`GET`=miembro, resto `require_org_admin`). Verify: 4.1–4.11 verdes.

### Fase 5 — "Mis empresas", `/auth/me` y hint de empresa en WS (Commit 5)

- [x] 5.1 [RED] `GET /organizations/mine` happy: usuario miembro de X (`admin`) e Y (`member`) recibe ambas con su rol correspondiente (Scenario "Usuario con varias empresas ve todas con su rol"). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_organizations_crud.py -q`.
- [x] 5.2 [RED] `GET /organizations/mine` sin token → 401. Verify.
- [x] 5.3 [RED] `GET /auth/me` con `X-Organization-Id: <Y>` refleja el contexto y el rol de Y, no de X (Scenario "/auth/me cambia según el header enviado"); sin header, conserva el comportamiento actual (primera membresía). Verify.
- [x] 5.4 [GREEN] Repository `list_mine(user_id)`; router `GET /organizations/mine`; ajustar `app/modules/auth/router.py` para pasar el `membership` YA resuelto por `get_current_membership` (con header) a `build_user_read`/`auth/service.py`, en vez de recalcular siempre con `primary_organization_id` ignorando el header. Verify: 5.1–5.3 verdes.
- [x] 5.5 [RED] Extensión de consistencia (no bloqueante — design.md Open Questions la deja fuera de lo obligatorio, pero se cubre para no dejar el WS desalineado del resolver REST): `_resolve_organization_id` en `app/realtime/router.py` acepta un hint de empresa (`?org_id=`) — hint válido (membresía del usuario) → usa esa empresa; hint de empresa ajena → cierre `1008` ANTES de accept; sin hint → fallback idéntico al actual (primera membresía). Verify: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_realtime_ws_auth.py -q`.
- [x] 5.6 [GREEN] Implementar el hint en `_resolve_organization_id`. Verify: 5.5 verde + el resto de `test_realtime_ws_auth.py`/`test_realtime_push.py` intacto.

### Fase 6 — Regresión y cierre del Lote 1 (Commit 6)

- [x] 6.1 Suite completa del backend sin regresión: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` → todos verdes (preexistentes de 25 ya archivado + los nuevos de este lote).
- [x] 6.2 Reversibilidad end-to-end de la migración 0021: `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` sin error.
- [x] 6.3 Confirmar los 3 gotchas backend propagados en Fase 1 siguen verdes de forma aislada: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest tests/test_active_organization.py -v`.
- [x] 6.4 Commit convencional (si 6.1–6.3 no generaron cambios de producción adicionales a U1–U5, este commit puede fusionarse con el de U5; en caso contrario, commit de cierre): `fix(organizations): cierra regresiones detectadas en el resolver de empresa activa` (solo si aplica).

## Lote 2 — Frontend: store de empresa activa + interceptor + selector

### Fase 7 — Store de empresa activa (signal + `sp-active-org`) (Commit 7)

- [x] 7.1 Crear `frontend/src/features/organizations/active-org.store.ts`: signal `activeOrgId` hidratado desde `localStorage.getItem('sp-active-org')` (patrón try/catch de `layout-shell.component.ts` `readPersistedCollapsed`/`persistCollapsed` — falla silenciosa si `localStorage` no está disponible); `setActiveOrg(id: string)` persiste la clave y ejecuta `window.location.reload()` (Decisión 5 del design: recarga completa, sin reset selectivo de stores).
- [x] 7.2 gotcha (4) — limpiar `sp-active-org` en `clearSession()`/logout: modificar `frontend/src/features/auth/auth.service.ts#clearSession()` para remover también `sp-active-org` (junto a `sp-token`), evitando que tras el login de otro usuario en el mismo navegador el header apunte a una empresa ajena (403 en toda la sesión).
- [x] 7.3 Verify (sin harness de pruebas de frontend, Out of Scope del proposal): revisión de código — `clearSession()` borra ambas claves; `setActiveOrg` no lanza si `localStorage` no está disponible; `ng build` sin errores de compilación.

### Fase 8 — Interceptor inyecta el header (Commit 8)

- [x] 8.1 Modificar `frontend/src/features/auth/auth.interceptor.ts`: inyectar `X-Organization-Id` con el valor vigente de `ActiveOrgStore` en toda petición autenticada, salvo en `isAuthEndpoint` (mismo criterio que el bearer `Authorization`: omitir en `/auth/login|refresh|logout`).
- [x] 8.2 Verify manual: sin empresa activa aún (primer login, antes de `GET /organizations/mine`), el header simplemente se omite — el backend cae al fallback de la primera membresía, sin romper el flujo de login. `ng build` sin errores.

### Fase 9 — Entidad `organization` (modelo + servicio CRUD/miembros) (Commit 9)

- [x] 9.1 Crear `frontend/src/entities/organization/organization.model.ts`: tipos `Organization`, `OrganizationMember`, `OrganizationMembership` (empresa + rol del usuario, para el selector y "mis empresas").
- [x] 9.2 Crear `frontend/src/entities/organization/organizations.service.ts` (mismo patrón que `org-theme.api.ts`, envelope `{data}`/`{data, meta}`): `mine()`, `create(payload)`, `get(id)`, `update(id, payload)`, `remove(id)`, `listMembers(id)`, `addMember(id, payload)`, `updateMemberRole(id, memberId, role)`, `removeMember(id, memberId)`.
- [x] 9.3 Verify manual: `ng build` sin errores; tipos consumidos correctamente por el selector y las páginas admin de los Lotes 2/3.

### Fase 10 — Selector de empresa activa en el layout (Commit 10)

- [x] 10.1 Crear el componente selector (`frontend/src/widgets/header/ui/org-switcher.component.ts` o carpeta equivalente en `features/organizations/`) que consume `organizations.service.ts#mine()`: lista las empresas del usuario con su rol, resalta la activa (Scenario "Selector lista las empresas del usuario").
- [x] 10.2 Con una sola empresa, el selector la muestra como activa sin obligar a elegir (Scenario "Usuario con una sola empresa").
- [x] 10.3 Proyectar el selector en `[header-actions]` de `frontend/src/app/app.component.ts`, junto al toggle de tema existente.
- [x] 10.4 Manejo de error (Scenario "Falla al cambiar de empresa conserva el contexto anterior"): si el cambio falla (red o 403), mostrar un mensaje de error legible y NO invocar `setActiveOrg`/reload hasta confirmar éxito — el layout conserva el contexto de la empresa anterior sin datos parciales de la nueva.
- [x] 10.5 Textos en español colombiano formal, tuteo (etiquetas, `aria-label`, estado vacío, mensajes de error) — nunca voseo rioplatense (Scenario "Tuteo formal en las etiquetas del selector").
- [ ] 10.6 PENDIENTE (requiere navegador/`./gestion.sh` levantado, no ejecutable por el agente en este entorno): usuario en 2 empresas ve ambas en el selector; cambiar de empresa recarga la página y refleja la nueva (menús, `/auth/me`, tema); simular un error (empresa inexistente) y confirmar que el layout no se rompe y conserva el contexto previo. Código completo y `ng build` verde; falta la verificación manual en vivo.

## Lote 3 — Páginas admin (CRUD de empresas y miembros)

### Fase 11 — Página de administración de empresas (Commit 11)

- [x] 11.1 Crear `frontend/src/features/manage-organizations/` con la página de listado + detalle de empresa (mismo patrón que `roles-page.component.ts`: `SolDataTableComponent`, `SolModalComponent`, `ReactiveFormsModule`, `SolPageHeaderComponent`).
- [x] 11.2 CRUD de empresa desde la UI (crear, editar nombre/slug, baja lógica); la UI puede ocultar acciones si el rol de la empresa activa no es `admin`, pero el backend SIEMPRE re-valida con `require_org_admin` (la UI es cosmética, no el control de acceso real).
- [x] 11.3 Textos en español colombiano formal, tuteo.

### Fase 12 — Página de gestión de miembros + ruta lazy (Commit 12)

- [x] 12.1 Extender la página (o subpágina) con el listado de miembros y su rol, alta por correo, cambio de rol, remoción — con confirmación explícita al intentar degradar/remover al único admin (mensaje que refleja el rechazo 4xx del backend, sin dejar la UI en un estado inconsistente).
- [x] 12.2 Agregar ruta lazy en `frontend/src/pages/admin/admin.routes.ts`: `{ path: 'organizations', loadComponent: () => import(...).then((m) => m.OrganizationsPageComponent) }` (mismo patrón que `users`/`roles`/`menus`/`dependencies`).
- [x] 12.3 Textos en español colombiano formal, tuteo.
- [ ] 12.4 PENDIENTE (requiere navegador/`./gestion.sh` levantado, no ejecutable por el agente en este entorno): crear empresa, agregar miembro por correo, cambiar rol, intentar degradar al único admin (rechazado con mensaje claro), eliminar miembro no-admin. Código completo y `ng build` verde; falta la verificación manual en vivo.

## Fase 13 — Cierre de la ola: suite verde + migración reversible + commit final

- [ ] 13.1 Suite completa del backend: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test .venv/bin/python -m pytest -q` → verde (Lote 1 completo + regresión de 25 ya archivado, sin excepciones).
- [ ] 13.2 Migración reversible end-to-end (repetir tras cualquier ajuste posterior a 6.2): `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` sin error.
- [ ] 13.3 Confirmar los 4 gotchas propagados siguen verdes de forma aislada: los 3 backend (`tests/test_active_organization.py`, target-scoped/ajena/sin-header) y el frontend (`clearSession()` limpia `sp-active-org` — revisión de código, Fase 7.2).
- [ ] 13.4 `ng build` de producción del frontend sin errores (Lotes 2 y 3 completos).
- [ ] 13.5 Commit convencional final en español, resumiendo el cierre de la ola (solo si 13.1–13.4 generaron cambios de producción no cubiertos por los commits 1–12; en caso contrario no aporta un commit nuevo): `feat(organizations): cierra la administracion de empresas y el selector de empresa activa`.

## Trazabilidad de requisitos

- organizations-admin R1 (bootstrap de admin al crear empresa) · 3.1, 3.2, 3.3, 3.10
- organizations-admin R2 (permisos por rol en lectura/escritura de empresa y miembros) · 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.5, 4.8, 4.11
- organizations-admin R3 (unicidad de membresía y protección "sin admin") · 2.1, 2.2, 2.4, 4.4, 4.7, 4.10, 4.12
- organizations-admin R4 (resolución de empresa activa por header con fallback) · 1.1, 1.2, 1.3, 1.4, 1.5
- organizations-admin R5 ("mis empresas" y `/auth/me` reflejan la empresa activa) · 5.1, 5.2, 5.3, 5.4
- frontend-org-switcher R1 (selector en el layout) · 9.1, 9.2, 10.1, 10.2
- frontend-org-switcher R2 (cambio de empresa refresca todo el contexto) · 7.1, 10.3, 10.6
- frontend-org-switcher R3 (interceptor inyecta el header) · 8.1, 8.2
- frontend-org-switcher R4 (estado de error no rompe el layout) · 10.4
- frontend-org-switcher R5 (textos en español colombiano formal) · 10.5, 11.3, 12.3
- multi-tenancy R2 modificado (resolución de empresa activa header + fallback) · 1.1, 1.2, 1.3, 1.4, 1.5, 1.8
- multi-tenancy — unicidad de membresía (added) · 2.1, 2.2, 2.3, 2.4, 6.2
- Gotcha (1) autorización `/{id}` target-scoped, nunca depende del header activo · 1.6, 1.7, 6.3, 13.3
- Gotcha (2) header de empresa ajena → 403 · 1.3, 6.3, 13.3
- Gotcha (3) sin header → primera membresía, suite existente intacta · 1.1, 1.8, 6.1, 6.3, 13.1, 13.3
- Gotcha (4) logout limpia `sp-active-org` · 7.2, 13.3
- Gate de dependencia (25 debe archivar antes del apply del 26) · 0.1, Gate de dependencia (encabezado)
