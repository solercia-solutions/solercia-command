# Tasks: 25 · Aislamiento multiempresa (scoping por organization_id)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~1500–1650 (mayormente `test_cross_tenant_isolation.py` nuevo: meta-test+constantes ~60, seed-helpers ~180, ~25 módulos tenant-scoped × ~45 líneas (listado+detalle-404+update/delete-rechazado) ~1125, superficie global (menus/org_role_templates) ~50, conectores+cuentas conectadas ~70; correcciones en `repository.py` 0–150 según fugas) |
| 400-line budget risk | High — inherente al alcance (28 módulos), no a mala descomposición; Decisión 1 del design exige archivo único auditable |
| Chained PRs recommended | No — merge local a `preview`, sin PR nuevo; commits escalonados dentro de una sola integración |
| Suggested split | U1 infraestructura → U2 proyecto/ejecución → U3 colaboración → U4 personas/permisos/global → U5 búsqueda/panorama → U6 activos/integraciones → U7 conectores → U8 correcciones+verde+commit |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U1 | Archivo + meta-test de cobertura + seed-helpers | 1 — `test(multi-tenant): agrega infraestructura de la bateria de aislamiento cross-tenant` | `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py::test_all_modules_are_classified -v` | Pytest contra Postgres real de test (sin UI; backend-only) | Revert commit; archivo nuevo, nada más depende de él aún |
| U2 | Tests proyecto y ejecución (10 módulos) | 2 — `test(multi-tenant): agrega tests de aislamiento para proyecto y ejecucion` | `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "projects or tasks or sprints or boards or dependencies or task_links or checklists or time_logs or activity or labels" -v` | Ídem | Revert commit; solo agrega tests |
| U3 | Tests colaboración (4 módulos) | 3 — `test(multi-tenant): agrega tests de aislamiento para colaboracion` | `... pytest backend/tests/test_cross_tenant_isolation.py -k "comments or attachments or notifications or reminders" -v` | Ídem | Revert commit |
| U4 | Tests personas/permisos + superficie global (4 módulos) | 4 — `test(multi-tenant): agrega tests de aislamiento y catalogo compartido para personas y permisos` | `... pytest backend/tests/test_cross_tenant_isolation.py -k "users or roles or org_role_templates or menus" -v` | Ídem | Revert commit |
| U5 | Tests búsqueda y panorama (2 módulos) | 5 — `test(multi-tenant): agrega tests de aislamiento para busqueda y panorama` | `... pytest backend/tests/test_cross_tenant_isolation.py -k "search or dashboard" -v` | Ídem | Revert commit |
| U6 | Tests activos e integraciones (6 módulos) | 6 — `test(multi-tenant): agrega tests de aislamiento para activos e integraciones` | `... pytest backend/tests/test_cross_tenant_isolation.py -k "assets or alert_rules or intake or glpi_sync or jira_import or organizations" -v` | Ídem | Revert commit |
| U7 | Tests conectores (org + usuario) | 7 — `test(multi-tenant): agrega tests de aislamiento de conectores por organizacion y usuario` | `... pytest backend/tests/test_cross_tenant_isolation.py -k connector -v` | Ídem | Revert commit |
| U8 | Correcciones (si aplica) + suite completa verde | 8 — `fix(scoping): cierra fugas cross-tenant detectadas por la bateria` (solo si U2–U7 detectaron fugas) | `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests -q` | Ídem | Revert commit aislado por módulo corregido; si no hubo fugas, U8 no genera commit de fix |

## Fase 0 — Preparación (lectura de fixtures existentes)

- [x] 0.1 Leer `backend/tests/conftest.py:368-476` (`TwoOrgs`, `_seed_org_data`, fixture `two_orgs`) y confirmar campos disponibles por org: `organization, user, token, project, task, alert_rule, notification`.
- [x] 0.2 Leer `backend/tests/test_multi_tenancy.py` (patrón ya usado para `projects`: `@pytest.mark.asyncio(loop_scope="session")` + `@skip_no_db`, `client.get(..., headers=_auth(token))`, `ids = {row["id"] for row in response.json()["data"]}`) como plantilla a generalizar.
- [x] 0.3 Confirmar clasificación de los 28 módulos de `app/modules/*`: `TENANT_SCOPED` = projects, tasks, sprints, boards, dependencies, task_links, checklists, time_logs, activity, labels, comments, attachments, notifications, reminders, users, roles, search, dashboard, assets, alert_rules, intake, glpi_sync, jira_import, organizations, connectors (25); `GLOBAL` = menus, org_role_templates (2); `INFRA_NO_READ` = auth (1, sin superficie de lectura cross-tenant: solo login/refresh/logout/me).

## Fase 1 — Infraestructura del archivo + meta-test (Commit 1)

- [x] 1.1 [RED] Crear `backend/tests/test_cross_tenant_isolation.py`: `TENANT_SCOPED`, `GLOBAL`, `INFRA_NO_READ` como frozensets **vacíos** + `test_all_modules_are_classified` (introspecciona `os.listdir("app/modules")`, ignora `__pycache__`/`__init__.py`, afirma unión total). Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py::test_all_modules_are_classified -v` → falla listando los 28 módulos sin clasificar (RED confirmado).
- [x] 1.2 [GREEN] Completar los 3 frozensets con la clasificación de 0.3. Verify: mismo comando → verde.
- [x] 1.3 Agregar seed-helpers locales al archivo (no tocar `two_orgs` core) para entidades no cubiertas por `_seed_org_data`: sprint, board, dependency, task_link, checklist, label, time_log, comment, attachment, reminder, asset+license, connector+connected_account, org_role_template, glpi_sync link, jira_import job. Verify: `pytest backend/tests/test_cross_tenant_isolation.py --collect-only` sin errores.
  - Nota: los helpers de proyecto/ejecución (sprint, board, dependency-area, task_link, checklist, checklist-item, time_log, task_history, label) quedaron co-ubicados en Fase 1; los de comments/attachments/reminders/assets+license/connector+connected_account/org_role_template/glpi_sync/jira_import se agregan en su fase correspondiente (3/6/7) para mantener el archivo legible incrementalmente.

## Fase 2 — Proyecto y ejecución, 10 módulos (Commit 2)

- [ ] 2.1 [RED] Tests de listado (`ids⊆A`, `b.id∉ids`), detalle-404 cross-tenant y update/delete-rechazado para projects, tasks, sprints, boards, dependencies, task_links, checklists, time_logs, activity, labels. Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "projects or tasks or sprints or boards or dependencies or task_links or checklists or time_logs or activity or labels" -v`
- [ ] 2.2 Si algún caso queda rojo, registrar módulo+endpoint en bloque `# FUGAS DETECTADAS` al final del archivo (corrección diferida a Fase 8); si todo verde, continuar.

## Fase 3 — Colaboración, 4 módulos (Commit 3)

- [ ] 3.1 [RED] Mismo contrato (listado/detalle-404/update-delete) para comments, attachments, notifications, reminders. Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "comments or attachments or notifications or reminders" -v`
- [ ] 3.2 Registrar fugas si aparecen (mismo bloque de 2.2).

## Fase 4 — Personas, permisos y superficie global, 4 módulos (Commit 4)

- [ ] 4.1 [RED] Tests de aislamiento para users, roles; para org_role_templates: aislamiento de plantillas org-scoped (`organization_id IS NOT NULL`) **y** catálogo compartido para `is_system=True` (aserción inversa `ids_A == ids_B`); para menus: catálogo compartido (aserción inversa) sin `TenantMixin`. Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "users or roles or org_role_templates or menus" -v`
- [ ] 4.2 Registrar fugas si aparecen.

## Fase 5 — Búsqueda y panorama, 2 módulos (Commit 5)

- [ ] 5.1 [RED] Tests de fuga para search (búsqueda global no revela ids de B) y dashboard (`/executive`, `/performance` solo agregan datos de A). Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "search or dashboard" -v`
- [ ] 5.2 Registrar fugas si aparecen.

## Fase 6 — Activos e integraciones, 6 módulos (Commit 6)

- [ ] 6.1 [RED] Tests de fuga para assets (+ AssetLicense), alert_rules, intake, glpi_sync (`/unmatched`, `/links` no exponen ids de B), jira_import (import contra `connector_id` de B autenticado como A → 404), organizations. Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k "assets or alert_rules or intake or glpi_sync or jira_import or organizations" -v`
- [ ] 6.2 Registrar fugas si aparecen.

## Fase 7 — Conectores por organización y por usuario (Commit 7)

- [ ] 7.1 [RED] Test: `Connector` de A no aparece en `GET /connectors` de B (`UNIQUE(organization_id, provider)`); test: `ConnectedAccount` del usuario X en A no es visible ni sus credenciales Fernet por el usuario Y de A. Verify: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -k connector -v`
- [ ] 7.2 Registrar fugas si aparecen (no esperadas — `app/modules/connectors/models.py` ya las previene por diseño).

## Fase 8 — Correcciones + suite completa verde + commit (Commit 8)

- [ ] 8.1 [FIX] Si 2.2/3.2/4.2/5.2/6.2/7.2 registraron fugas: corregir cada `repository.py` dueño (`WHERE organization_id` o join al padre; **sin** filtro global de SQLAlchemy). Verify por módulo: repetir el comando `-k` de la fase correspondiente → verde.
- [ ] 8.2 Confirmar que `app/dependencies.py:128-146` y `app/modules/auth/service.py:34-44` (resolución de empresa activa) no fueron modificados: `git diff --stat` sobre esos archivos vacío.
- [ ] 8.3 Meta-test + batería completa: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests/test_cross_tenant_isolation.py -v` → todos verdes.
- [ ] 8.4 Suite completa del backend sin regresión: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest backend/tests -q` → ≥1158 preexistentes + los nuevos, todos verdes.
- [ ] 8.5 Commit final (solo si 8.1 generó cambios de producción; en caso contrario U8 no aporta commit nuevo).

## Trazabilidad de requisitos

- Aislamiento cross-tenant (listado/detalle-404/update-delete) · 1.1,1.2,2.1,2.2,3.1,3.2,4.1(users/roles),4.2,5.1,5.2,6.1,6.2,8.1,8.3,8.4
- Superficie global por diseño (menus, org_role_templates system) · 1.2,4.1,4.2
- Aislamiento de conectores por organización y por usuario · 1.2,1.3,7.1,7.2
- No regresión y scoping manual sin filtro global · 8.1,8.3,8.4
- Frontera con el cambio 26 (resolución de empresa activa intacta) · 0.3,8.2
