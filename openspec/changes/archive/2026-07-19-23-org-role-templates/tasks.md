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

## Lote 0 — Gate previa (sin commit)

- [x] 0.1 [Gate] Verificar en vivo: `cd backend && alembic current` reporta head real; `rg "async def validate_parent|async def create_project" app/modules/projects/service.py` confirma ambas firmas del design del 21 en disco.
  **DESVIACIÓN**: el head real en vivo era `0017` (no `0014`). Migración rebasada a `0018_add_org_role_templates.py` con `down_revision="0017"`.

## Lote 1 — Migración 0018 + modelos + ER doc + compatibilidad `lead_user_id` (Commit 2d5fd3d)

- [x] 1.1 RED `backend/tests/test_org_role_templates_migration.py`
- [x] 1.2 RED `backend/tests/test_projects.py` (extiende la suite del cambio 21)
- [x] 1.3 [Models] `app/modules/projects/models.py`: agregar `lead_user_id`
- [x] 1.4 [Models] Crear `app/modules/org_role_templates/models.py`: 3 modelos
- [x] 1.5 [Schemas] `app/modules/projects/schemas.py`: agregar `lead_user_id`
- [x] 1.6 [Migration] Crear `alembic/versions/0018_add_org_role_templates.py`
- [x] 1.7 [Docs] Actualizar `docs/diagrams/er-model.md`
- [x] 1.8 VERIFY verde (13/13)

## Lote 2 — Extracción de `_create_project_unit()` sin commit (Commit 954dbba)

- [x] 2.1 RED `backend/tests/test_projects.py`: no-regresión
- [x] 2.2 [Service] `app/modules/projects/service.py`: extraer `_create_project_unit()`
- [x] 2.3 VERIFY verde (12/12 + 38/38 del 21)

## Lote 3 — Repository + service de instanciación + seeder (Commit 2529051)

- [x] 3.1 RED `backend/tests/test_org_role_templates_service.py` (unit, sin BD)
- [x] 3.2 [Repository] `app/modules/org_role_templates/repository.py`
- [x] 3.3 [Service] `app/modules/org_role_templates/service.py`: `instantiate()`
- [x] 3.4 RED `backend/tests/test_org_role_templates_service.py` (seeder)
- [x] 3.5 [Seeder] Crear `app/modules/org_role_templates/seeder.py`
- [x] 3.6 VERIFY verde (9/9)

## Lote 4 — Router + schemas + wiring (Commit 8194c38)

- [x] 4.1 RED `backend/tests/test_org_role_templates_api.py`
- [x] 4.2 [Schemas] `app/modules/org_role_templates/schemas.py`
- [x] 4.3 [Router] `app/modules/org_role_templates/router.py`
- [x] 4.4 [Wiring] `app/main.py`: incluir router
- [x] 4.5 VERIFY verde (6/6)

## Lote 5 — Idempotencia + multi-tenant + checkpoint final (Commit a515b1b)

- [x] 5.1 RED `backend/tests/test_org_role_templates_api.py`: idempotencia, reconciliación, rollback
- [x] 5.2 RED `backend/tests/test_org_role_templates_api.py` (con `two_orgs`): multi-tenant + extras
- [x] 5.3 VERIFY checkpoint completo verde

**ESTADO: APPLY COMPLETO** (2026-07-19) — las 26 tareas marcadas [x]. Suite final: 1041 passed / 13 failed (mismas legacy).

## Correcciones 4R (Commit f3969c9)

- [x] CRITICAL: POST /projects forzaba lead_user_id=None correctamente
- [x] WARNING 1: instanciación concurrente → captura IntegrityError + retry
- [x] WARNING 2: índices únicos parciales del catálogo
- [x] WARNING 3: code_exists sin test directo → test forward-looking
- [x] WARNING 4: cardinalidades ER → corregidas en er-model.md

## Trazabilidad de requisitos

`org-role-templates`: catálogo R1 · instanciación R2 · idempotencia R3 · validaciones R4 · aislamiento R5. `projects`: responsable R7.
