# Design: 25 · Aislamiento multiempresa (scoping por organization_id)

## Technical Approach

Batería sistemática de tests de fuga cross-tenant, backend-only, TDD, que fija la invariante "una consulta autenticada como empresa A jamás devuelve ids de empresa B". No introduce filtro global de SQLAlchemy: se conserva el scoping manual query-por-query verificado en la auditoría (`ProjectRepository.get` filtra `organization_id`; `TaskRepository` hace join a `Project` y filtra `organization_id`). El contrato de detalle cross-tenant ya existe (`ProjectService.get_project` → `AppException(status_code=404, code="project_not_found")`) y se generaliza a todos los módulos. Superficie global-por-diseño (`Menu` sin `TenantMixin`; `OrgRoleTemplate` con `organization_id IS NULL` + `is_system=True`) se prueba como catálogo compartido, no como fuga. Suite base: 1158 tests.

## Architecture Decisions

### Decisión 1: arquitectura de la batería — archivo dedicado + factories por módulo + meta-test

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| **Archivo único `tests/test_cross_tenant_isolation.py`: matriz de módulos + seed-helpers por módulo sobre `two_orgs` + meta-test de cobertura** | Contrato de seguridad en un solo lugar auditable; el meta-test enumera módulos y falla si uno queda sin clasificar; factories heterogéneas (comment necesita task, license necesita asset) quedan aisladas sin acoplar el fixture compartido | **Elegida** |
| B. Un test de fuga por módulo en su archivo existente | Descubribilidad pobre, sin enforcement central, el meta-test no los localiza; fácil olvidar al agregar módulo | Rechazada |
| C. Extender `_seed_org_data` para sembrar los ~28 módulos | Fixture usada por tests ajenos se vuelve frágil; cada módulo nuevo ripplea en seed compartido | Rechazada (solo core barato) |

`two_orgs` (`conftest.py:376-475`) se mantiene como base (org/user/project/task/alert_rule/notification). Entidades pesadas por módulo se construyen con **seed-helpers co-ubicados** sobre A y B. El **meta-test** introspecta los paquetes `app/modules/*/` (filesystem) y afirma que cada uno pertenece a `TENANT_SCOPED ∪ GLOBAL ∪ INFRA_NO_READ`; un módulo nuevo sin clasificar rompe la suite → fuerza triaje.

### Decisión 2: patrón de aserción

| Superficie | Contrato |
|--------|----------|
| Listados / búsqueda global / dashboards-métricas | 200; `ids ⊆ A`; `b.<entity>.id ∉ ids` |
| Detalle / update / delete por id de B autenticado como A | **404** (nunca 403 —confirmaría existencia—, nunca 200) |
| Recursos anidados (comments/checklists de task de B) | 404 vía join al padre scoping |

Verificado en 3 repositories: `get()` filtra `organization_id` y devuelve `None` → el service traduce a 404. Se fija el mismo contrato para todos.

### Decisión 3: superficie global-por-diseño

`menus` y plantillas `system` (`organization_id IS NULL`) se prueban con aserción **inversa**: `ids_vistos_por_A == ids_vistos_por_B` y el set sembrado presente para ambas → compartir NO es fuga. `org_role_templates` recibe AMBOS tests: catálogo compartido para `is_system=True` y aislamiento para plantillas org-scoped (`organization_id IS NOT NULL`).

### Decisión 4: estrategia ante fugas

Fuga detectada → corrección **mínima** en el repository dueño (`WHERE organization_id` o join al padre + filtro), nunca refactor global ni event listener de SQLAlchemy. TDD: test en rojo → fix mínimo → verde. El scoping manual permanece.

### Decisión 5: sin migraciones

Cambio aditivo (tests + doc). Si un test revela columna faltante (módulo sin `organization_id` ni padre para join), se documenta y **escala al cambio dueño**; 25 no agrega migración.

## Data Flow

    two_orgs (siembra A,B) ─► seed-helper por módulo (entidad en A y en B)
         │
         ▼
    client auth como A ─► endpoint (list / detail / search / dashboard)
         │
         ▼
    assert: ids ⊆ A · b.id ∉ ids · detail(b.id) → 404
         │
    meta-test: introspecta app/modules/* ─► cada módulo ∈ {SCOPED ∪ GLOBAL ∪ INFRA}

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/tests/test_cross_tenant_isolation.py` | Create | Batería por módulo + tests de catálogo compartido + meta-test de cobertura |
| `backend/tests/conftest.py` | Modify | Solo si se añaden seed-helpers reutilizables; `two_orgs` core intacto |
| `backend/app/modules/*/repository.py` | Modify | Condicional: únicamente si un test revela fuga (scope mínimo) |

## Interfaces / Contracts

```python
TENANT_SCOPED: frozenset[str]   # projects, tasks, sprints, boards, ...
GLOBAL: frozenset[str]          # menus; org_role_templates (system)
INFRA_NO_READ: frozenset[str]   # módulos sin superficie de lectura tenant
# meta-test: set(dir(app/modules/*)) == TENANT_SCOPED | GLOBAL | INFRA_NO_READ
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (repo) | Scoping por `organization_id`/join padre | `two_orgs` + factory; assert ids |
| Integration (HTTP) | list/detail/search/dashboard cross-tenant | `client` auth como A vs datos de B |
| Meta | Todo módulo clasificado en la matriz | Introspección de `app/modules/*` |
| Contract (global) | menus + plantillas system compartidas | Aserción inversa A == B |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. Solo tests + posibles cláusulas `WHERE` en repositories.

## Migration / Rollout

Sin migración. Rollback: revertir commits de tests y de cualquier fix de scoping de forma aislada.

## Open Questions

- [ ] Ninguna bloqueante. Frontera con 26-admin-empresas ratificada: 25 congela el contrato sin tocar la resolución de empresa activa (`app/dependencies.py:128-146`).
