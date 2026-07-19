# Proposal: 21 · Jerarquía de proyectos

## Intent

OLA 2, ítem 4a. Hoy `Project` es plano: no existe `parent_project_id` y cada proyecto es una isla. Un jefe sobre una sombrilla ("Seguridad de la Información") que agrupa subproyectos (Desarrollo, Seguridad) no puede ver un avance consolidado. El dashboard (`_build_projects_progress`) calcula `done/total` por proyecto de forma independiente, sin agregación jerárquica. Se necesita que el avance de los subproyectos componga el del padre (Desarrollo 8/10 + Seguridad 10/10 → sombrilla 18/20). Es la base estructural de los cambios 23 (plantillas) y 24 (árbol visual).

## Scope

### In Scope
- `parent_project_id` (self-FK, nullable) en `Project`, con índice; padre e hijo en el mismo `organization_id` y activos.
- Validación en create/reparent: rechazo de auto-padre, de ciclos y de profundidad excesiva (límite razonable a fijar en design).
- Agregación recursiva vía **CTE recursivo de PostgreSQL** para hacer roll-up de `done/total` sobre todos los descendientes.
- Endpoints: árbol del proyecto y avance consolidado por nivel (respetando tenant y soft delete).
- Cada subproyecto conserva su metodología (Strategy pattern intacto).
- **Nota obligatoria**: el apply DEBE actualizar el documento ER (`docs/diagrams/er-model.md` por instrucción; el ER vigente en el repo es `docs/DATA-MODEL.md` — resolver la ruta en design/apply).

### Out of Scope
- Vista de árbol visual (cambio **24**; además `frontend-frozen`).
- Plantillas organizacionales que autogeneran jerarquía (cambio **23**).
- Mover/fusionar tareas entre proyectos; PATCH/DELETE de proyectos (deuda conocida, no aquí).
- Jerarquías o roll-up entre tenants distintos.

## Capabilities

### New Capabilities
- `project-hierarchy`: relación padre-hijo, validación de ciclos/profundidad, árbol y avance consolidado por CTE.

### Modified Capabilities
- `projects`: `Project` gana `parent_project_id` y validación de jerarquía en la creación.

## Approach

- **Modelo**: `parent_project_id` nullable (patrón `code`, ADR 0003) con índice; misma organización, activo.
- **Validación**: caminar ancestros o CTE para detectar ciclo; guard de profundidad máxima.
- **Agregación**: CTE recursivo acota el subárbol (filtrando `organization_id` + `is_active`) y suma `done` vs `total`. Reto clave: "done" depende de la metodología (último estado permitido por proyecto) — design decide cómo reconcilia el CTE esa semántica por proyecto.
- **API**: endpoint de árbol anidado + endpoint de avance por nodo y consolidado.

## Decisiones para design
- Qué cuenta como "actividad" del roll-up: tareas `done` vs total, ponderación (conteo vs puntos/horas), si `cancelled`/subtareas cuentan.
- Cómo el CTE reconcilia el "done" dependiente de metodología (SQL puro vs precálculo por proyecto).
- Valor del límite de profundidad y reglas de reparentado.
- Forma y rutas de los endpoints; migración (create_all vs ALTER Alembic).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/modules/projects/models.py` | Modified | `parent_project_id` self-FK + índice |
| `backend/app/modules/projects/{repository,service}.py` | Modified | CTE recursivo, validación ciclos/profundidad |
| `backend/app/modules/projects/{router,schemas}.py` | Modified | Endpoints árbol + avance consolidado |
| `backend/alembic/versions/00XX_*.py` | New (posible) | ALTER para bases existentes |
| `docs/DATA-MODEL.md` (ER) | Modified | Actualizar diagrama en apply |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Rendimiento del CTE recursivo en árboles grandes | Med | Índice en `parent_project_id`; límite de profundidad; agregación en una consulta |
| Ciclos al reparentar dejan la jerarquía inconsistente | Med | Validación obligatoria en create/reparent antes de persistir |
| Fuga entre tenants en el roll-up | High | Filtro `organization_id` en cada nivel del CTE; test de aislamiento |
| Reconciliar "done" por metodología dentro del CTE | Med | Decisión explícita en design; test por metodología |
| Ruta del doc ER ambigua (`docs/diagrams/er-model.md` vs `docs/DATA-MODEL.md`) | Low | Resolver en design/apply |

## Rollback Plan

Cambio aditivo. Revertir el merge; si se aplicó ALTER Alembic, ejecutar su `downgrade` (elimina `parent_project_id`). Los proyectos existentes quedan planos (`parent_project_id = NULL`); ningún dato de tarea se altera.

## Dependencies

- `depends_on: 02-contrato-api` — paginación/envelope estándar reutilizados por los endpoints.

## Success Criteria

- [ ] `Project` acepta `parent_project_id` con padre/hijo en la misma organización y activos.
- [ ] Auto-padre, ciclos y exceso de profundidad son rechazados con error claro.
- [ ] El endpoint de avance devuelve el roll-up correcto en todos los niveles (18/20 en el ejemplo).
- [ ] El endpoint de árbol refleja la jerarquía sin cruzar la frontera de organización (test de aislamiento).
- [ ] Cada subproyecto conserva su metodología.
- [ ] Todo el código nace con prueba en rojo (TDD estricto): happy path + error + permisos/aislamiento.
- [ ] El apply actualiza el documento ER.
