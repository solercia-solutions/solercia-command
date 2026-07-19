# Tasks: 23 · Plantillas organizacionales de alto cargo

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~430 (migración+modelos ~120, service/reconciliación ~120, seeder ~90, router/schemas ~60, delta `projects` ~40) — design.md, "Forecast de tamaño" |
| Riesgo de presupuesto (400 líneas) | Medium |
| Entregas encadenadas recomendadas | No (slice único autónomo; se fragmenta en 5 lotes/commits, no en PRs de GitHub) |
| Split sugerido | Lote 1 (migración+modelos+ER) → Lote 2 (extracción `_create_project_unit`) → Lote 3 (repository+service+seeder) → Lote 4 (router+wiring) → Lote 5 (idempotencia+multi-tenant+checkpoint) |
| Estrategia de entrega | exception-ok — commits directos a `feat/consume-solercia-ui`, un commit por lote, sin PR |
| Estrategia de encadenado | size-exception — aceptada por el usuario |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

Nota: `Chained PRs recommended: No` se refiere a ausencia de cadena de Pull Requests en GitHub. El trabajo SÍ se fragmenta en 5 lotes/commits secuenciales en orden TDD (RED→GREEN→VERIFY), cada uno dejando la suite completa en verde con ruff/mypy limpios.

**Convención de rojo**: cada tarea RED corre primero con una aserción invertida (ej. esperar 0 tablas donde debería haber 3, o esperar que SÍ se duplique un proyecto) y se confirma el fallo; luego se corrige a la aserción real y se re-ejecuta hasta verde.

### Suggested Work Units

| Unit | Objetivo | Commit | Test enfocado | Arnés de ejecución | Frontera de rollback |
|------|----------|--------|----------------|---------------------|------------------------|
| 1 | Migración 0015 (3 tablas + `lead_user_id`) + modelos + ER doc + compat `projects` | 1 | `pytest tests/test_org_role_templates_migration.py tests/test_projects.py -v` | `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` contra `solercia_test_migrations` (real, sin mocks) | revertir el commit elimina la migración 0015, las 3 tablas, `lead_user_id` y el ajuste del ER; `alembic downgrade` a `0014` restaura el esquema previo exacto |
| 2 | Extraer `_create_project_unit()` sin commit, preservando contrato de `create_project` | 2 | `pytest tests/test_projects.py -v` | ASGI in-process (`client`/`session`, sin servidor real) — `POST /projects` real de punta a punta | revertir el commit restaura el cuerpo monolítico de `create_project`; no toca migración/esquema, aislado a `service.py` |
| 3 | `org_role_templates`: repository + service de instanciación (reconciliación `is_active`) + seeder de 5 plantillas | 3 | `pytest tests/test_org_role_templates_service.py -v` | unit puro (orden/validación, sin BD) + BD real para verificar `seed_default()` idempotente | revertir el commit elimina repository/service/seeder nuevos; `db_init.seed_default()` vuelve a su forma previa; ningún módulo existente se toca |
| 4 | Router + schemas + wiring en `main.py` | 4 | `pytest tests/test_org_role_templates_api.py -v` | ASGI in-process, actores vía `make_member`/`rbac_admin` | revertir el commit quita el router de `main.py` y los endpoints; la capa service/repository del Unit 3 queda intacta pero inalcanzable por HTTP |
| 5 | Idempotencia (reconciliación, fallo a mitad) + multi-tenant + checkpoint final | 5 | `cd backend && pytest tests/ -v` | ASGI in-process con `two_orgs`; doble instanciación real; fallo forzado en el 4.º de 5 proyectos para verificar rollback transaccional | revertir el commit elimina solo los escenarios agregados a `test_org_role_templates_api.py`; los Units 1-4 quedan intactos y funcionales |

## Lote 0 — Gate previa (sin commit)

- [x] 0.1 [Gate] Verificar en vivo: `cd backend && alembic current` reporta head `0014` (si no, rebasar `down_revision` de 1.6 al head real); `rg "async def validate_parent|async def create_project" app/modules/projects/service.py` confirma ambas firmas del design del 21 en disco. Si algo no coincide → BLOQUEADO, reportar al orquestador antes de seguir.
  DESVIACIÓN: el head real en vivo era `0017` (no `0014`) — migraciones 0015 (connectors), 0016 (federated identities) y 0017 (GLPI) aterrizaron entre el diseño del 23 y este apply. Migración rebasada a `0018_add_org_role_templates.py` con `down_revision="0017"`, tal como anticipaba el design.md ("Open Questions"). `validate_parent`/`create_project` confirmados en disco.

## Lote 1 — Migración 0018 + modelos + ER doc + compatibilidad `lead_user_id` (Commit 1)

- [x] 1.1 RED `backend/tests/test_org_role_templates_migration.py`: `alembic upgrade head` crea `org_role_templates`, `org_role_template_nodes`, `org_role_template_instantiations` y `projects.lead_user_id`; `alembic downgrade -1` revierte las 4 en orden inverso; `alembic check` sin diff (paridad con 0008/0014).
- [x] 1.2 RED `backend/tests/test_projects.py` (extiende la suite del cambio 11): "proyecto sin plantilla mantiene `lead_user_id=null`" y "listado `/projects` expone `lead_user_id` por elemento" (specs/projects delta, R1).
- [x] 1.3 [Models] `app/modules/projects/models.py`: agregar `lead_user_id: Mapped[uuid.UUID | None]` FK `users.id` `ondelete="SET NULL"`, `index=True`.
- [x] 1.4 [Models] Crear `app/modules/org_role_templates/models.py`: `OrgRoleTemplate` (`organization_id` FK `organizations` CASCADE nullable, `is_system`, `name`), `OrgRoleTemplateNode` (`template_id` FK CASCADE, `parent_node_id` FK self CASCADE|None, `name`, `default_methodology=planner`, `order`), `OrgRoleTemplateInstantiation` (`organization_id`, `template_id`, `node_id`, `lead_user_id`, `project_id`, `UniqueConstraint(org,template,node,lead)`).
- [x] 1.5 [Schemas] `app/modules/projects/schemas.py`: agregar `lead_user_id` a `ProjectCreate` (opcional) y `ProjectRead`.
- [x] 1.6 [Migration] Crear `alembic/versions/0018_add_org_role_templates.py` (`down_revision="0017"`): `create_table` de las 3 tablas + `add_column`/`create_foreign_key`/`create_index` de `projects.lead_user_id`; `downgrade()` en orden inverso.
- [x] 1.7 [Docs] Actualizar `docs/diagrams/er-model.md`: agregar las 3 tablas nuevas (Dominio 7) y la relación `projects.lead_user_id → users.id`, en el MISMO commit que la migración.
- [x] 1.8 VERIFY `pytest tests/test_org_role_templates_migration.py tests/test_projects.py -v` → verde (13/13); `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` limpio + `alembic check` sin diff contra `solercia_test_migrations`. Commit `feat(org-role-templates): agrega tablas de plantillas, lead_user_id y actualiza el modelo ER`.

## Lote 2 — Extracción de `_create_project_unit()` sin commit (Commit 2)

- [ ] 2.1 RED `backend/tests/test_projects.py`: no-regresión explícita — `POST /projects` sigue devolviendo 201 y persistiendo en una sola llamada (aserción invertida primero: esperar que NO se persista, confirmar rojo).
- [ ] 2.2 [Service] `app/modules/projects/service.py`: extraer `_create_project_unit()` (valida strategy, resuelve `code`, `add`+`flush`, `seed_board`, fija `lead_user_id`, valida `parent` vía `validate_parent`) SIN `commit`; `create_project` público = `_create_project_unit()` + `repo.save()` (conserva firma y contrato).
- [ ] 2.3 VERIFY `pytest tests/test_projects.py tests/test_board_aware_strategy.py -v` → verde, sin regresión. Commit `refactor(projects): extrae _create_project_unit sin commit, preservando el contrato de create_project`.

## Lote 3 — Repository + service de instanciación + seeder (Commit 3)

- [ ] 3.1 RED `backend/tests/test_org_role_templates_service.py` (unit, sin BD): orden de recorrido padre→hijo del árbol; `lead_user_id` no-miembro rechaza antes de crear nada; mapeo nodo→proyecto (nombre, `default_methodology`, `parent_project_id` encadenado).
- [ ] 3.2 [Repository] `app/modules/org_role_templates/repository.py`: queries de árbol por `template_id`/`parent_node_id`, ledger por `(org, template, lead)`, `is_org_member(organization_id, user_id)`.
- [ ] 3.3 [Service] `app/modules/org_role_templates/service.py`: `instantiate(organization_id, template_id, lead_user_id, actor_id)` — recorre árbol padre→hijo; por nodo: ledger con `project.is_active=true` → reusa; sin fila o `is_active=false` → `ProjectService._create_project_unit()` + insert/actualiza fila del ledger (preserva `UNIQUE`); un único `commit` al final.
- [ ] 3.4 RED `backend/tests/test_org_role_templates_service.py` (seeder): `db_init.seed_default()` deja sembradas exactamente 5 plantillas de sistema (`organization_id=null`, `is_system=true`); segunda corrida no duplica.
- [ ] 3.5 [Seeder] Crear `app/modules/org_role_templates/seeder.py` con `ensure_system_templates(session)` (patrón `_ensure_*`, catálogo de las 5 plantillas del spec); invocar desde `app/db_init.py::seed_default()`.
- [ ] 3.6 VERIFY `pytest tests/test_org_role_templates_service.py -v` → verde. Commit `feat(org-role-templates): agrega repository, service de instanciación y seeder de las 5 plantillas`.

## Lote 4 — Router + schemas + wiring (Commit 4)

- [ ] 4.1 RED `backend/tests/test_org_role_templates_api.py`: `GET /org-role-templates` lista 5; `GET /{id}` expone árbol completo (OAP-TI: sombrilla + 2 ramas + 8 equipos); `POST /{id}/instantiate` plana → 5 proyectos con `lead_user_id`+`methodology=planner`; OAP-TI → 11 proyectos en 3 niveles; `member` → 403, `manager`/`admin` → 200.
- [ ] 4.2 [Schemas] `app/modules/org_role_templates/schemas.py`: `OrgRoleTemplateRead`, `OrgRoleTemplateNodeRead` (árbol), `InstantiateRequest{lead_user_id}`.
- [ ] 4.3 [Router] `app/modules/org_role_templates/router.py`: `GET ""`, `GET "/{id}"` (cualquier miembro autenticado), `POST "/{id}/instantiate"` (`require_role(admin, manager)`); errores `lead_not_member` 422, `template_not_found` 404, `forbidden` 403.
- [ ] 4.4 [Wiring] `app/main.py`: `app.include_router(org_role_templates_router, prefix=API_PREFIX)`.
- [ ] 4.5 VERIFY `pytest tests/test_org_role_templates_api.py -v` → verde. Commit `feat(org-role-templates): expone GET/POST de plantillas e instanciación vía API`.

## Lote 5 — Idempotencia + multi-tenant + checkpoint final (Commit 5)

- [ ] 5.1 RED `backend/tests/test_org_role_templates_api.py`: reinstanciación sin cambios → 0 proyectos nuevos; nodo "PIGA" soft-deleted → reinstanciación recrea SOLO ese nodo sin duplicar el resto; fallo forzado a mitad (4.º de 5) → 0 proyectos persistidos (rollback transaccional).
- [ ] 5.2 RED `backend/tests/test_org_role_templates_api.py` (con `two_orgs`): `lead_user_id` sin membresía en la org del solicitante → 422 + 0 proyectos; instanciación de plantilla de sistema desde org A escribe SOLO en A; árboles de A y B generados de la misma plantilla no se filtran entre sí.
- [ ] 5.3 VERIFY checkpoint — `cd backend && pytest tests/ -v` completo verde, `ruff check .`, `mypy app` limpios. Commit `test(org-role-templates): blinda idempotencia por reconciliación y aislamiento multi-tenant`.

## Trazabilidad de requisitos

`org-role-templates`: catálogo sembrado R1 (3.4-3.5, 4.1) · instanciación con responsable R2 (4.1-4.4) · idempotencia por reconciliación R3 (5.1) · validaciones de instanciación R4 (3.1, 3.3, 4.1) · aislamiento multi-tenant R5 (5.2). `projects` (delta): responsable/`lead_user_id` R1 (1.2, 1.3, 1.5, 4.1).
