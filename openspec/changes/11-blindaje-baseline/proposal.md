# Proposal: 11 · Blindaje de la línea base (backfill de tests as-built con TDD)

## Intent

Las capacidades as-built pre-SDD nacieron sin ninguna prueba. La suite actual (258 tests verdes) cubre lo construido en 01-05, pero módulos críticos y sensibles a seguridad siguen con **CERO tests**: `auth`, `multi-tenancy`, `rbac-catalog`, el motor de alertas completo y las estrategias de metodología. Cualquier regresión en autenticación o en el aislamiento por `organization_id` es hoy invisible hasta producción. Antes de construir 06-10 hay que blindar la base: convertir los escenarios Dado/Cuando/Entonces que ya viven en `openspec/specs/*/spec.md` en la fuente de la verdad de una batería de tests que congele el comportamiento actual.

## Scope

### In Scope (mayormente test-only)
- Backfill de tests con TDD (rojo primero) para: `auth`, `users-admin`, `rbac-catalog`, `multi-tenancy`, `projects`, `tasks` (CRUD/PATCH/filtros hoy sin cubrir), `methodology-strategies` (4 estrategias), `alert-engine` (4 estrategias + evaluator + scheduler + dedup), `notifications-inapp` + `alert_rules`, `dashboard-executive`.
- **Transversal — permisos**: matriz admin/manager/member/viewer por endpoint.
- **Transversal — aislamiento**: tests con **dos organizaciones** que prueban que los datos jamás se cruzan.
- Si un test revela un bug real de producción, se corrige de forma **mínima y documentada**, con su propio rollback.

### Out of Scope (non-goals)
- Funcionalidad nueva, endpoints nuevos o refactors (más allá del bugfix mínimo).
- Cualquier cambio en `frontend/` (constraint `frontend-frozen`).
- El roadmap 06-10 (reminders, assets, email, websocket, búsqueda).
- Cobertura de capacidades ya cubiertas (comments, attachments, boards, labels, checklists, dependencias, time-logs, activity, sprints-close/velocity).

## Capabilities

> Cambio test-only: los specs as-built ya existen y **son el contrato de tests**, no se crean ni modifican requisitos.

### New Capabilities
- None.

### Modified Capabilities
- None a nivel de requisito. **Excepción**: si un bugfix cambia comportamiento observable de una capacidad, esa corrección lleva su delta spec en esta carpeta.

## Approach

TDD estricto: por cada capacidad, escribir la prueba en rojo derivada del escenario Dado/Cuando/Entonces del spec correspondiente, luego verde. Una o varias suites nuevas en `backend/tests/` por capacidad, reutilizando fixtures de `conftest.py` (01-fundacion-tdd). `multi-tenancy` usa fixtures de dos orgs y afirma cero cruce en cada endpoint tenant-scoped. Permisos: parametrizar admin/manager/member/viewer. Todo bug encontrado se aísla, se documenta y se corrige mínimo con rollback propio.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/tests/` | New | Suites de backfill por capacidad + permisos + aislamiento |
| `backend/tests/conftest.py` | Modified | Fixtures de dos organizaciones y de roles si faltan |
| `backend/app/modules/*` | Modified (condicional) | Solo si un test revela bug real; mínimo y documentado |
| `backend/alembic/` | Modified (improbable) | Solo si un bugfix exige cambio de esquema |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Backfill destapa bugs en auth/multi-tenancy | Med | Corrección mínima, documentada, con rollback; delta spec si cambia comportamiento |
| Doble sistema de roles (MemberRole vs RBAC) complica la matriz de permisos | Med | Documentar el rol efectivo por endpoint; probar el comportamiento vigente, no el ideal |
| Fugas entre tenants no detectadas por falta de datos de la 2.ª org | Med | Fixture obligatorio de dos orgs con datos poblados en cada suite tenant-scoped |
| Scheduler/dedup del motor de alertas difícil de testear (tiempo, locks) | Med | Aislar reloj/entradas; probar dedup por idempotencia, no por timing real |
| Volumen alto de tests supera el presupuesto de revisión (400 líneas) | High | Fragmentar en PRs por capacidad; test-only reduce riesgo por PR |

## Rollback Plan

Cambio esencialmente aditivo (test-only): revertir el/los commits elimina las suites sin afectar producción. Cualquier corrección en código de producción se entrega aislada y con rollback propio documentado; si toca esquema, `alembic downgrade` de esa migración. Correcciones en `auth`/`multi-tenancy` se revierten de forma independiente del backfill de tests.

## Dependencies

- `depends_on: 01-fundacion-tdd` — BD `solercia_test`, fixtures de `conftest.py` y flujo Alembic.
- `openspec/specs/*/spec.md` (as-built) como fuente de la verdad de cada test.

## Success Criteria

- [ ] Las 10 capacidades objetivo tienen suites de tests verdes derivadas de sus escenarios Dado/Cuando/Entonces.
- [ ] `multi-tenancy`: cada endpoint tenant-scoped probado con dos organizaciones sin cruce de datos.
- [ ] Matriz de permisos admin/manager/member/viewer verificada por endpoint.
- [ ] `alert-engine`: 4 estrategias + evaluator + scheduler + dedup cubiertos.
- [ ] Toda prueba nace en rojo (TDD estricto); la suite completa queda verde con ruff/mypy limpios.
- [ ] Cualquier bugfix de producción queda documentado con su rollback (y delta spec si cambia comportamiento).
