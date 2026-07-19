# Design: 23 · Plantillas organizacionales de alto cargo

## Technical Approach

Módulo nuevo `org_role_templates/` (models → repository → service → router) con **tres tablas** + columna aditiva `projects.lead_user_id`. La plantilla es dato: `org_role_templates` (cabecera, `organization_id` nullable + `is_system`) y `org_role_template_nodes` (árbol nombre/metodología/orden/padre). La instanciación recorre el árbol y crea cada proyecto con el núcleo de `ProjectService` del 21 (encadenando `parent_project_id`, respetando `PROJECT_HIERARCHY_MAX_DEPTH=5`, ya en `config.py:52`) y `lead_user_id` = la persona seleccionada. La idempotencia se resuelve con un **ledger** `org_role_template_instantiations` (no por nombre). Migración `0018` (encadena a `0017` del 21). Las 5 plantillas de sistema se siembran en `db_init.seed_default` (patrón del repo: el catálogo RBAC se siembra ahí, no en migración). TDD estricto.

## Architecture Decisions

### Decisión 1: siembra — seeder idempotente vs `bulk_insert` en migración

Evidencia: el repo NO siembra datos en migraciones (`bulk_insert` = 0 en `alembic/versions/`); el catálogo RBAC (roles, menús, dependencias, reglas de alerta) usa funciones `_ensure_*` idempotentes en `db_init.seed_default` (`db_init.py:287-425`), corridas en cada arranque.

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| `bulk_insert` en la migración | Determinista, pero rompe el patrón del repo, complica el downgrade y fija IDs/orden en SQL crudo | Rechazada |
| **Seeder idempotente en `db_init`** (`ensure_system_templates`, org NULL, key = nombre) | Consistente con RBAC; el árbol vive como dato en `org_role_templates/seeder.py`; re-arranque no duplica | **Elegida** |

### Decisión 2: idempotencia — ledger vs nombre vs marcador en `projects`

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Match por nombre bajo el padre | Frágil: los proyectos generados son editables/renombrables → reinstanciar duplicaría | Rechazada |
| Marcador `generated_from_template_id` en `projects` | Acopla `projects` al módulo de plantillas y amplía la superficie ratificada (solo `lead_user_id`) | Rechazada |
| **Ledger `org_role_template_instantiations`** `(org, template, node, lead)→project` con `UNIQUE(org,template,node,lead)` | Estado aislado; reconciliación exacta e inmune a renombres; downgrade limpio; `projects` solo gana `lead_user_id` | **Elegida** |

**Reconciliación con `is_active`**: la fila del ledger solo se **reusa** cuando el `project` referenciado sigue `is_active=true`. Si el proyecto fue soft-deleted (`is_active=false`), el nodo se trata como **faltante**: se crea de nuevo vía `_create_project_unit()` y se **actualiza** (nunca se inserta duplicado) el `project_id` de la fila existente del ledger, preservando `UNIQUE(org, template, node, lead)`. Esto cierra el escenario "Reinstanciación reconcilia el nodo faltante" (specs/org-role-templates/spec.md:64-67).

### Decisión 3: transacción única — extraer núcleo sin commit de `create_project`

Evidencia: `ProjectRepository.create/save` hacen `db.commit()` (`repository.py:98,106`) y `create_project` commitea por proyecto (`service.py:133`) → incompatible con "todo o nada". Se extrae `_create_project_unit()` (valida strategy, resuelve `code`, `add`+`flush`, `seed_board`, fija `lead_user_id`, valida `parent` con la caminata de ancestros del 21 — `openspec/changes/21-project-hierarchy/design.md`, Decisión 3: ciclo/profundidad/tenant acotados por `MAX_DEPTH`) **sin commit**. `create_project` público = unit + `repo.save` (conserva su contrato). La instanciación llama al unit por nodo faltante y hace **un** commit final.

## Data Flow

    POST /org-role-templates/{id}/instantiate {lead_user_id}
      → require_role(admin, manager)
      → validar lead = miembro activo (org del solicitante)
      → cargar árbol de nodos + ledger (org, template, lead)
      → por nodo padre→hijo:
          ledger con project is_active=true      → reusar
          sin fila | project is_active=false     → _create_project_unit(parent, lead)
                                                    + insertar fila (nueva)
                                                    | UPDATE project_id (fila existente, preserva UNIQUE)
      → commit único → árbol de proyectos con roll-up (21) encima

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/modules/org_role_templates/{models,repository,service,router,schemas,seeder}.py` | Create | 3 tablas, reconciliación, endpoints, spec de las 5 plantillas |
| `app/modules/projects/models.py` | Modify | `lead_user_id` FK `users` `SET NULL`, `index=True` |
| `app/modules/projects/schemas.py` | Modify | `ProjectCreate.lead_user_id?`; `ProjectRead.lead_user_id` |
| `app/modules/projects/service.py` | Modify | extraer `_create_project_unit`; validar membresía del lead |
| `app/db_init.py` | Modify | importar modelos nuevos + `ensure_system_templates(session)` en `seed_default` |
| `alembic/versions/0018_add_org_role_templates.py` | Create | 3 tablas + `projects.lead_user_id`; `down_revision="0017"`; downgrade completo |
| `docs/diagrams/er-model.md` (o `docs/DATA-MODEL.md`) | Modify (apply) | 3 tablas + relación de cabeza |

## Interfaces / Contracts

```python
class OrgRoleTemplateNode(Base):            # árbol de la plantilla
    template_id: FK org_role_templates(CASCADE)
    parent_node_id: FK self(CASCADE) | None  # None = sombrilla
    name: str; default_methodology: Methodology = planner; order: int

class OrgRoleTemplateInstantiation(Base):   # ledger idempotente
    organization_id; template_id; node_id; lead_user_id; project_id
    __table_args__ = (UniqueConstraint(org, template, node, lead),)

class InstantiateRequest(BaseModel):
    lead_user_id: uuid.UUID
```

Rutas: `GET /org-role-templates`, `GET /{id}` (árbol), `POST /{id}/instantiate` (`require_role(admin, manager)`), `GET /{id}/instantiation?lead_user_id=` (estado, cualquier miembro). Errores: `lead_not_member` (422), `template_not_found` (404 cross-tenant/inexistente), `forbidden` (403). Envelope `{data, meta}` del 02.

Árbol OAP‑TI (3 niveles, 11 proyectos): OAP‑TI → {Planeación → 4 equipos, Tecnología → 4 equipos}. Las demás plantillas son planas (2 niveles: sombrilla → equipos). Metodología por defecto `planner`, configurable por nodo.

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | orden padre→hijo; validación de lead; mapeo nodo→proyecto | pytest sin BD |
| Integration | cada plantilla genera su árbol (OAP‑TI 3 niveles = 11 proyectos con roll-up del 21 encima); doble instanciación = 0 nuevos; nodo borrado → solo el faltante recreado; lead no miembro → 422 + rollback; cross-tenant (system template escribe solo en org del solicitante, lead ajeno rechazado, template ajeno no visible); member → 403, admin/manager → 200 | httpx AsyncClient + fixtures 01/02/21 |
| Migration | `upgrade head` crea 3 tablas + `lead_user_id`; `downgrade` revierte; `alembic check` sin diff (paridad 0008/0014) | BD `solercia_test_migrations` |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocess, automatización VCS/PR, clasificación de ejecutables ni integración de procesos.

## Migration / Rollout

Aditiva `0018` (`down_revision="0017"`). `upgrade`: `create_table` de las 3 tablas + `add_column`/`create_foreign_key`/`create_index` de `projects.lead_user_id`. `downgrade`: drop de `lead_user_id` (índice→fk→columna) y de las 3 tablas en orden inverso. Los modelos declaran los mismos índices (`index=True`) para paridad `create_all`/migración. Rollback: revertir merge + `downgrade`; los proyectos generados quedan como proyectos normales del 21 (pierden la marca de cabeza), ninguna tarea se altera.

## Open Questions

- [ ] Ruta del doc ER (`docs/diagrams/er-model.md` vs `docs/DATA-MODEL.md`): el apply usa la primera si existe.
- [x] `down_revision` exacto: `0017` (verificado en vivo en apply, el head real después de que las migraciones de connectors/federated-identities/GLPI aterrizaran).

## Forecast de tamaño (para sdd-tasks)

Estimado ~430 líneas. **400-line budget risk: Medium.** `Decision needed before apply: No`. `Chained PRs recommended: No` (slice único autónomo; si crece, separar seeder+migración como PR previo).
