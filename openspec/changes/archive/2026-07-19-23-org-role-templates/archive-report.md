# Archive Report: 23-org-role-templates

**Date**: 2026-07-19  
**Change**: 23-org-role-templates (Plantillas organizacionales de alto cargo)  
**Status**: ✅ ARCHIVED  
**Artifact Store Mode**: hybrid  

## Executive Summary

Cambio 23-org-role-templates completado, verificado y archivado. Implementación de plantillas organizacionales de alto cargo que generan árboles jerárquicos de proyectos con responsable, idempotente por reconciliación. 26/26 tareas completadas, 1041 tests passed (31 nuevos), 6/6 requisitos implementados, 15/15 escenarios verificados. Specs fusionadas en openspec/specs/{org-role-templates,projects}.

## Artifact Traceability

Artefactos recuperados en fase archive y registrados con sus observation IDs de Engram:

| Artefacto | ID Engram | Tipo | Versión |
|-----------|-----------|------|---------|
| Proposal | 1642 | architecture | 2026-07-18 19:15:56 |
| Spec (org-role-templates) | 1650 | architecture | 2026-07-18 19:21:28 |
| Design | 1654 | architecture | 2026-07-18 19:23:59 (revisión 2) |
| Tasks | 1664 | architecture | 2026-07-18 19:37:43 (revisión 2) |
| Verify-Report | 1746 | architecture | 2026-07-19 10:36:42 |

## Implementation Summary

### Capabilities Delivered

**New**: `org-role-templates` — plantillas de perfil organizacional, nodos, instanciación idempotente a árbol de proyectos con responsable.

**Modified**: `projects` — nuevo campo `lead_user_id` (FK users, ON DELETE SET NULL, nullable, configurable por instanciación).

### Specification Compliance

#### org-role-templates (5 Requisitos / 12 Escenarios)

| Requisito | Escenarios | Estado |
|-----------|-----------|--------|
| Catálogo de plantillas de sistema sembradas | 2 | ✅ COMPLIANT |
| Instanciación genera el árbol con responsable | 2 | ✅ COMPLIANT |
| Idempotencia por reconciliación | 3 | ✅ COMPLIANT |
| Validaciones de instanciación | 3 | ✅ COMPLIANT |
| Aislamiento multi-tenant | 2 | ✅ COMPLIANT |

#### projects (delta) (1 Requisito / 3 Escenarios)

| Requisito | Escenarios | Estado |
|-----------|-----------|--------|
| Responsable (lead_user_id) del proyecto | 3 | ✅ COMPLIANT |

**Total**: 15/15 escenarios verificados en verde.

### Test Coverage

| Métrica | Valor |
|---------|-------|
| Tests totales pasados | 1041 |
| Tests fallidos (legacy, sin relación) | 13 |
| Tests nuevos del cambio | 31 |
| Cobertura de especificación | 15/15 escenarios |
| Capas de prueba | Unit (6), Integration (25), E2E (0) |
| Archivos de test del cambio | 4 (3 nuevos + 1 delta) |

### Quality Assurance

**Build**: ✅ Pasó (ruff check + mypy app, 266 archivos)

**TDD Compliance**: ✅ 100% (RED→GREEN→VERIFY por lote)

**Migración Alembic**: ✅ Verificada (0018: 3 tablas + lead_user_id, downgrade reversible, alembic check sin diff)

**Design Decisions**: 3/3 seguidas sin desviación (seeder idempotente, ledger, transacción única)

### Correcciones 4R (Post-Apply Review)

**CRITICAL** (encontrado y corregido):
- POST /projects aceptaba lead_user_id de no-miembro sin validar membresía → fijo con forzado lead_user_id=None en create_project

**WARNING** (encontrados y corregidos):
1. Instanciación concurrente sin lock → captura IntegrityError + retry único
2. Catálogo sin unique natural key → índices parciales en migración + __table_args__
3. code_exists sin test directo → test forward-looking con soft-delete
4. Cardinalidades ER → corregidas en docs/diagrams/er-model.md Dominio 7

**SUGGESTION**: Ninguna

## Spec Sync Summary

### Nuevos specs creados

**Path**: `openspec/specs/org-role-templates/spec.md`  
**Type**: Full spec (no delta)  
**Source**: Delta de cambio (copiado como spec completo, nueva capability)  
**Requirements**: 5 (catálogo, instanciación, idempotencia, validaciones, aislamiento)  
**Scenarios**: 12  

### Specs actualizados (delta aplicado)

**Path**: `openspec/specs/projects/spec.md`  
**Type**: Modified (ADDED: 1 requisito)  
**Delta Source**: `openspec/changes/23-org-role-templates/specs/projects/spec.md`  
**Change**: Agregar R7 (Responsable/lead_user_id) + 3 escenarios post-merge  
**Requirements después**: Originales (R1-R6) + R7 nuevo  
**Scenarios después**: Originales + 3 nuevos de R7  

## File Changes (Apply Phase)

| File | Action | Commits |
|------|--------|---------|
| `alembic/versions/0018_add_org_role_templates.py` | Create | 2d5fd3d |
| `app/modules/org_role_templates/{models,repository,service,router,schemas,seeder}.py` | Create | 2529051, 8194c38 |
| `app/modules/projects/models.py` | Modify | 2d5fd3d |
| `app/modules/projects/schemas.py` | Modify | 2d5fd3d |
| `app/modules/projects/service.py` | Modify | 954dbba, a515b1b |
| `app/modules/projects/repository.py` | Modify | f3969c9 (bug real) |
| `app/db_init.py` | Modify | 2529051 |
| `app/main.py` | Modify | 8194c38 |
| `docs/diagrams/er-model.md` | Modify | 2d5fd3d, f3969c9 |

## Test Evidence

**Build Command**: `cd backend && ruff check . && mypy app`  
**Test Command**: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v`  
**Test Result**: 1041 passed, 13 failed (legacy only)  

**Key Tests** (hardening 4R):
- `test_instantiate_concurrent_calls_reconcile_instead_of_500` — concurrencia real con asyncpg
- `test_post_projects_ignores_explicit_lead_user_id_of_other_org` — forzado null en create_project
- `test_post_projects_rejects_explicit_code_of_soft_deleted_project` — bug real code_exists
- `test_instantiate_commits_so_a_new_session_sees_the_created_projects` — persistencia real cross-sesión
- `test_rollup_from_change_21_reports_correctly_over_instantiated_oap_ti_tree` — roll-up del 21 sobre árbol

## Commits Delivered

| Commit | Lote | Descripción |
|--------|------|-------------|
| 2d5fd3d | 1 | Migración 0018 + modelos + lead_user_id + ER |
| 954dbba | 2 | Refactor _create_project_unit sin commit |
| 2529051 | 3 | Repository + service + seeder (5 plantillas) |
| 8194c38 | 4 | Router + schemas + wiring |
| a515b1b | 5 | Idempotencia + multi-tenant + checkpoint |
| f3969c9 | — | Correcciones 4R (CRITICAL + 4 WARNING) |

**Total**: 6 commits en rama `feat/consume-solercia-ui`

## Dependencies

**Depends On**: 21-project-hierarchy (transitiva 02-contrato-api)

**Affected By**: Migraciones concurrentes (0015 connectors, 0016 federated-identities, 0017 GLPI) aterrizaron entre design y apply → rebase de down_revision="0014" a "0017" materializado sin incidentes.

## Constraints Applied

- backend-only ✅ (sin cambios frontend, frontend-frozen)
- frontend-frozen ✅ (deuda de UI para follow-up)
- strict-tdd ✅ (RED→GREEN→VERIFY por lote, 100% cobertura de specs)

## Deviations & Decisions

### Design-Time Assumptions vs. As-Built

| Asunción | Realidad | Impacto |
|----------|----------|---------|
| `down_revision="0014"` asumido en design.md | Head real en apply fue `0017` (3 migraciones concurrentes) | Rebase materializado, previsto y anticipado en design.md "Open Questions" |
| OrgRoleTemplate.organization_id nullable (no TenantMixin) | Correcto, tabla de sistema requiere nullable | Ninguno |
| OrganizationMember: "miembro activo" = fila existe | Correcto (no SoftDeleteMixin en OrganizationMember) | Validación es_org_member implementada |
| Fixture session/client (SAVEPOINT) no prueba commit real | Lección leída en lote 5 | Test de persistencia cross-sesión agregado (conexiones asyncpg directo a engine) |

### Decisions Made During Apply (Post-Design)

1. **Retry por concurrencia** (corrección 4R) — captura IntegrityError + rollback + re-lectura + retry único. No documentado en design.md pero no contradice, es endurecimiento aditivo.

2. **Forzado de lead_user_id=null en create_project** (CRITICAL 4R) — post-merge verificó que POST /projects aceptaba lead_user_id sin validar membresía. Fix fuerza None cuando viene del payload, solo OrgRoleTemplateService.instantiate puede fijarlo.

3. **Índices únicos parciales del catálogo** (WARNING 4R) — 2 índices (system_name WHERE org IS NULL, org_name WHERE org IS NOT NULL) para evitar colisiones naturales.

## Known Limitations & Future Work

| Tema | Estado | Futuro |
|------|--------|--------|
| CRUD de plantillas propias por organización | Out of Scope | Follow-up 23.x (modelo soporta extensibilidad) |
| UI para gestión de plantillas | Out of Scope | Follow-up, frontend-frozen |
| Mover/fusionar tareas | Out of Scope | Deuda del 21 |
| PATCH/DELETE de proyectos | Out of Scope | Deuda del 21 |
| Cobertura de código configurada | No configurada | Recomendación: pytest-cov en requirements.txt |
| Cross-tenant plantillas o roll-up | Out of Scope | Riesgo bajo, plantillas solo lectura |

## Archive Contents

```
openspec/changes/archive/2026-07-19-23-org-role-templates/
├── proposal.md              ← propuesta completa
├── design.md                ← diseño técnico
├── tasks.md                 ← 26/26 tareas completadas
├── verify-report.md         ← verdict PASS
├── state.yaml               ← estado final (archive: done)
├── archive-report.md        ← este archivo
└── specs/
    ├── org-role-templates/
    │   └── spec.md          ← spec completo (nueva capability)
    └── projects/
        └── spec.md          ← delta (R7 agregado)
```

## Next Steps

### Completed
- ✅ Proposal & Design fase: completadas
- ✅ Implementation (apply): 6 commits, 26/26 tareas
- ✅ Verification: PASS (1041 tests, 15/15 escenarios)
- ✅ Spec Sync: org-role-templates creado, projects actualizado
- ✅ Archive: folder moved, report persisted

### Recommendations for Follow-Up
1. **Coverage tool setup** — agregar pytest-cov a requirements.txt para medición cuantitativa
2. **UI de plantillas** (23-follow-up) — crear views para CRUD de plantillas propias (modelo ya soporta)
3. **Dashboard widget** — mostrar responsables (lead_user_id) en la vista ejecutiva
4. **Documentación de extensibilidad** — agregar guía de cómo crear nuevas plantillas organizacionales

## Sign-Off

**Change Archived**: 23-org-role-templates  
**Archive Date**: 2026-07-19  
**Observation IDs (Engram)**:
- Proposal: #1642
- Spec: #1650
- Design: #1654
- Tasks: #1664
- Verify-Report: #1746
- Archive-Report: (persisted as sdd/23-org-role-templates/archive-report)

**Status**: READY FOR NEXT CHANGE

---

*This archive report constitutes the final audit trail of change 23-org-role-templates. All artifacts, test evidence, and implementation commits are immutable within this archive. No further modifications to this change are permitted outside the context of maintenance or documented follow-up changes.*
