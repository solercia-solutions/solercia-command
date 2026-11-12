# Archive Report: 21-project-hierarchy

**Change**: `21-project-hierarchy` — Jerarquía de proyectos con roll-up de avance
**Archived on**: 2026-07-18
**Artifact Store Mode**: hybrid
**Cycle Status**: COMPLETE

## Executive Summary

El cambio **21-project-hierarchy** ha completado exitosamente el ciclo SDD completo (proposal → spec → design → tasks → apply → verify → archive). Se agregó la capacidad de jerarquía padre-hijo en proyectos con validación de ciclos/profundidad y agregación recursiva de avance (roll-up CTE). La verificación confirma 588 pruebas en verde (cero regresiones), ER actualizado, y todas las deudas trazadas documentadas.

## Cycle Phases

| Fase | Estado | Artefacto Engram | Observación ID |
|------|--------|------------------|----------------|
| proposal | ✅ done | sdd/21-project-hierarchy/proposal | 1621 |
| spec | ✅ done | sdd/21-project-hierarchy/spec | 1631 |
| design | ✅ done | sdd/21-project-hierarchy/design | 1628 |
| tasks | ✅ done | sdd/21-project-hierarchy/tasks | 1634 |
| apply | ✅ done | (no artefacto explícito) | — |
| verify | ✅ done | sdd/21-project-hierarchy/verify-report | 1673 |
| archive | ✅ done | sdd/21-project-hierarchy/archive-report | (this document) |

## Scope Resolution

### Capabilities Delivered

**New**: `project-hierarchy`
- Relación padre-hijo (`parent_project_id`) en `Project` con self-FK nullable
- Validación: mismo tenant, padre activo, sin ciclos, profundidad ≤ 5
- Endpoints: árbol jerárquico (`GET /{id}/tree`), avance consolidado (`GET /{id}/progress`), reparentado (`PATCH /{id}/parent`)
- Roll-up de avance por CTE recursivo: conteo de tareas, `cancelled` excluidas, subtareas incluidas, "done" por metodología (último estado permitido de cada proyecto)
- Permisos: lecturas abiertas a cualquier rol, `PATCH .../parent` requiere admin/manager

**Modified**: `projects`
- `POST /projects` acepta `parent_project_id` opcional
- `GET /projects`, `GET /projects/{id}` exponen `parent_project_id`

### Out of Scope (Documented Debt)

- Vista de árbol visual en frontend (cambio 24)
- Plantillas organizacionales (cambio 23)
- Endpoint DELETE/PATCH de proyectos (forward-looking invariante: soft-delete de padre con hijos activos rechazado)
- Estado `cancelled` en Task (aún no implementado en el resto del sistema)

## Test Results

**Suite Completa**: 588 passed / 13 failed
- Las 13 fallas son idénticas a las preexistentes documentadas en `conftest.py` (servidor vivo black-box tests, `TEST_AUTH_TOKEN` vacío)
- **Cero regresiones**: baseline preapply 548/13 → postapply 588/13

**Suite Focalizada (jerarquía + regresión)**: 45/45 PASSED
- 40 pruebas nuevas de proyecto-hierarchy (migración, repository, validación, endpoints)
- 5 pruebas preexistentes de `test_projects.py` (red de seguridad)

**Build**: ✅ `ruff check app/` y `mypy app/` limpios (189 archivos)

**Migration**: `0014_add_project_parent_id` cadena íntegra 0001→0014, head único, `alembic check` sin diff

## Spec Compliance

**Coverage**: 11/11 requisitos trazados, 26/28 escenarios testeo runtime
- R8 (invariante soft-delete) quedó sin tarea de implementación: no existe endpoint DELETE de proyectos en la API hoy; requisito trazado como forward-looking en el spec (honestidad de planeación, no omisión silenciosa)
- Exclusión de `cancelled` del denominador (R6) trazada como deuda conocida (estado aún no alcanzable en ninguna metodología)

**Task Completion**: 29/29 completas
- Lote A: migración + modelo + CTE repository (1.1–1.12)
- Lote B: validación + service + endpoints (2.1–2.13)
- Lote C: actualización ER + pulido + verificación (3.1–3.4)

## Commits Delivered

| Commit | Mensaje | Líneas | Lote |
|--------|---------|--------|------|
| c4249c6 | feat(projects): migracion 0014, self-FK parent_project_id y CTE de jerarquia | ~430 | A |
| 0740b94 | feat(projects): validacion de jerarquia, reparentado y endpoints de arbol/avance | ~780 | B |
| 6f9d4f2 | docs(projects): actualiza ER model con jerarquia de proyectos | ~30 | C |
| af792b9 | fix(projects): guarda profundidad en CTEs descendentes + row lock en reparent | ~40 | Fix post-review 4R |

**Total**: ~1.280 líneas (producción ~460 + pruebas TDD ~750 + docs ~30)

## Verification Notes

### 4R Review Gate (Post-Apply)

- **Risk**: CRITICAL → corregido en af792b9 (ciclo no guardado en CTEs descendentes de altura/subtree)
- **Reliability**: 2 WARNINGs → corregidos (orden sin ORDER BY determinista; invariante soft-delete trazado como forward-looking)
- **Readability**: ✅ Aprobado
- **Resilience**: ✅ Aprobado

Review receipt: `reviewGate.result: allow` (documentado en el historial de apply-progress)

### Known Issues & Mitigations

| Issue | Tipo | Mitigation |
|-------|------|-----------|
| Ciclo no guardado en CTE descendentes | CRITICAL | Corregido commit af792b9: row lock en `reparent`, guarda en los 3 CTEs (altura/subtree/rollup) |
| Orden de hermanos sin ORDER BY | WARNING | Corregido af792b9: `ORDER BY column_order, id` en `fetch_subtree` |
| Invariante R8 sin test de API | SUGGESTION/Deuda | Trazado en spec como forward-looking (no existe endpoint DELETE hoy); patrón consistente con `BoardRepository.lock_column` |
| Discrepancia de conteo de tareas | WARNING (docs) | 29 vs 30 mencionadas en prompts — conteo directo de tasks.md = 29 ✓ |

## Data Migration Impact

- **Aditivo**: nueva columna `parent_project_id` nullable, ningún proyecto existente afectado (`parent_project_id = NULL` por defecto)
- **Reversible**: `alembic downgrade -1` elimina columna e índice sin pérdida de datos
- **No afecta tareas**: ningún cambio en Task o campos relacionados

## Artifacts Moved to Archive

```
openspec/changes/archive/2026-07-18-21-project-hierarchy/
├── proposal.md
├── design.md
├── tasks.md
├── verify-report.md
├── state.yaml
├── specs/
│   ├── project-hierarchy/
│   │   └── spec.md (completamente nueva)
│   └── projects/
│       └── spec.md (delta ADDED fusionado)
└── archive-report.md (this file)
```

## Merged into Main Specs

- `openspec/specs/project-hierarchy/spec.md` ← creada (nueva capability)
- `openspec/specs/projects/spec.md` ← fusionada (R5-R6 ADDED, 5 escenarios nuevos)

## Documentation Updated

- `docs/diagrams/er-model.md`: relación padre-hijo agregada al CORE cluster (self-FK `PROJECTS |o--o{ PROJECTS : "es hijo de"`)
- `openspec/OLA_2.md`: tabla de estado, fila 21 → verify ☑ + archive ☑

## Dependencies Status

- `depends_on: 02-contrato-api` ✅ already archived
- Required by: 22-intake-classifier (desbloqueado), 23-org-role-templates (desbloqueado), 24-hierarchy-tree-view (desbloqueado)

## Rollback Procedure

1. `git revert -m 1 {merge-commit}` (si fue merge) o `git revert {commit}` (si fue squash)
2. `alembic downgrade -1` (elimina `parent_project_id` + índice)
3. Proyectos existentes quedan planos; tareas intactas

## Engram Observation IDs

Para trazabilidad completa:
- Proposal: #1621
- Spec: #1631
- Design: #1628
- Tasks: #1634
- Verify Report: #1673
- Archive Report: (generado en esta sesión)

## Next Steps

- ✅ Todos los dependientes (`22`, `23`, `24`) pueden proceder inmediatamente
- ✅ SDD fase archive completa
- ✅ Cambio listo para producción

---

**Archived by**: SDD Archive Executor (v2.0)
**Timestamp**: 2026-07-18T20:35:00Z
**Status**: CLOSED
