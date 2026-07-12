# Design: Labels, checklists y dependencias tarea-tarea + alerta blocked_task

## Technical Approach

Tres módulos aditivos `router → service → repository` que reutilizan los mixins existentes. **Tenant scoping (corrección de gate 2026-07-11)**: las entidades nuevas (`Label`, `TaskChecklist`, `ChecklistItem`, `TaskDependency`) llevan `TenantMixin` (columna `organization_id` directa) con filtros row-level en sus repositories, siguiendo el precedente real de las entidades hijas de tarea (`TaskComment` y `Attachment` usan `TenantMixin` directo) y la regla de CLAUDE.md («columna `organization_id` en toda entidad tenant-scoped»); el scope transitivo vía `Project` queda descartado. La tabla de asociación `TaskLabel` sigue la convención probada de `UserRole`/`RoleMenu` (id surrogate `PkMixin` + `UniqueConstraint`, sin `SoftDelete`, borrado físico al desvincular); `TaskDependency` NO sigue esa convención: la spec exige `SoftDeleteMixin` y desenlace por borrado suave (ver modelo de datos). Las entidades de dominio (`Label`, `TaskChecklist`, `ChecklistItem`) llevan `SoftDeleteMixin` y, por herencia de 02, `AuditMixin`. El detalle de tarea se enriquece con el mismo patrón de consultas dedicadas de `get_subtask_counts` (sin relaciones ORM sobre `Task`, consistente con el estilo explícito del repo). La alerta reutiliza `AlertStrategy` + registry + seed idempotente por `rule_type`.

## Architecture Decisions

### Decisión: Módulo/tabla/clase para dependencias (evitar colisión)

| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Módulo `task_links/`, tabla `task_dependencies`, clase `TaskDependency`, endpoints en `/tasks/{id}/dependencies` (router propio) | Aísla del módulo `dependencies/` (áreas, clase `Dependency`); recurso task-céntrico | **Elegida** |
| Anidar dentro de `tasks/` | Infla el módulo de tareas; mezcla responsabilidades | Rechazada |
| Reusar `dependencies/` | Colisión directa tabla `dependencies`/clase `Dependency` | Rechazada |

**Rationale**: nombres físicamente distintos → cero impacto en áreas organizacionales.

### Decisión: Arista dirigida canónica (no doble fila blocks/is_blocked_by)

**Choice**: una sola fila dirigida `TaskDependency(blocker_task_id, blocked_task_id)` con semántica fija "blocker bloquea a blocked". `is_blocked_by` es la vista inversa (aristas entrantes), nunca una fila aparte. El payload acepta `type` para interpretar dirección, pero persiste canónico. `UniqueConstraint(blocker_task_id, blocked_task_id)`; rechazo de auto-lazo y de par duplicado.

**Inversión de dirección (corrección de gate 2026-07-11, resuelve la open question)**: con `type=is_blocked_by`, la arista se invierte ANTES de persistir al canónico `blocks`: el `related_task_id` del payload pasa a ser `blocker_task_id` y la tarea del path (`/tasks/{id}/dependencies`) pasa a ser `blocked_task_id`. Con `type=blocks` no hay inversión (tarea del path = `blocker_task_id`, `related_task_id` = `blocked_task_id`). Ambas direcciones se leen siempre desde la arista canónica.

**Nomenclatura spec ↔ design (corrección de gate 2026-07-11)**: la spec (`specs/task-dependencies.md`) usa `task_id` (origen) y `depends_on_task_id` (tarea bloqueante); en este design equivalen a `blocked_task_id` y `blocker_task_id` respectivamente. Los escenarios Gherkin literales de la spec se leen con esta equivalencia; no hay diferencia semántica.
**Alternatives considered**: dos filas por relación (redundante, invita a inconsistencia y complica ciclos).
**Rationale**: media arista por relación simplifica detección de ciclos y lecturas; estándar tipo Jira.

### Decisión: Detección de ciclos por DFS en el servicio

**Choice**: antes de insertar `X→Y`, cargar en **una sola query** todas las aristas del proyecto (`task_dependencies` join `tasks` del mismo `project_id`, **filtrando `is_active == true`** — corrección de gate 2026-07-11: las aristas desenlazadas por borrado suave no participan del grafo), construir adyacencia y hacer DFS desde `Y` siguiendo aristas `blocks`; si alcanza `X`, la arista cerraría un ciclo → `422`. Cubre directo y transitivo. Complejidad `O(V+E)` por inserción, acotada al tamaño del proyecto (aceptable para MVP).
**Alternatives considered**: CTE recursivo en Postgres (más rápido a gran escala, menos testeable con TDD); sin validación (deuda). 
**Rationale**: grafo por proyecto es pequeño; DFS en el service es determinista y verificable con test rojo del ciclo primero.

### Decisión: Modelo de datos

*(Tabla corregida por gate 2026-07-11: `TaskDependency` con SoftDelete; `Tenant` = `TenantMixin` con `organization_id` directo.)*

| Entidad | Mixins | Claves/Constraints |
|---------|--------|--------------------|
| `Label` | Pk, Timestamp, SoftDelete, Audit(02), Tenant | `project_id` FK; `UniqueConstraint(project_id, name)`; `color` |
| `TaskLabel` | Pk, Timestamp | FK `task_id`/`label_id` CASCADE; `UniqueConstraint(task_id, label_id)`; hard delete |
| `TaskChecklist` | Pk, Timestamp, SoftDelete, Audit, Tenant | `task_id` FK; `title`; `order` (col `checklist_order`) |
| `ChecklistItem` | Pk, Timestamp, SoftDelete, Audit, Tenant | `checklist_id` FK; `content`; `is_done`; `order` (col `item_order`) |
| `TaskDependency` | Pk, Timestamp, SoftDelete, Tenant | FK `blocker_task_id`/`blocked_task_id`; `UniqueConstraint`; `created_at` alimenta la alerta; **unlink = `is_active=False`, nunca DELETE físico** |

**Rationale**: `TaskLabel` reproduce la convención `Role`/`UserRole`. `TaskDependency` hereda `SoftDeleteMixin` porque la spec (`specs/task-dependencies.md`, requisito "Desenlazar y listar dependencias") exige borrado suave — la spec gana sobre la convención de asociación. El tenant scoping es directo con `TenantMixin` (corrección de gate 2026-07-11): menor superficie de fugas entre tenants (el filtro row-level no depende de un `join` correcto en cada query) y consistencia con el precedente real de `TaskComment`/`Attachment`. Consecuencia obligatoria del borrado suave: la carga de aristas para el DFS de ciclos y el cálculo de `is_blocked` DEBEN filtrar `is_active == true`.

### Decisión: Estrategia de alerta `blocked_task`

**Choice**: `BlockedTaskStrategy(rule_type="blocked_task")`. Selecciona `task_dependencies` donde el blocker sigue incompleto (`blocker.completed_at IS NULL`), el blocked incompleto, y `dependency.created_at < now - blocked_days`. Recipiente = `blocked.assignee_id` (se omite si es `None`, patrón de `task_at_risk`). `dedup_key = f"blocked_task:{blocked_task_id}"` (una notificación por tarea bloqueada). `threshold_params` default `{"blocked_days": 3}`. Seed añade la 5.ª regla en `_DEFAULT_ALERT_RULES`, idempotente por `rule_type` (mecánica existente de `_ensure_alert_rules`).
**Rationale**: reutiliza el contrato `AlertCandidate` + idempotencia de `exists_active` del evaluator sin tocar el motor.

### Decisión: Enriquecer el detalle sin N+1

**Choice**: en `get_task`/`get_task_by_key` (lecturas de una sola tarea) se agregan 3 consultas acotadas: `list_labels_for_task` (join `TaskLabel`), `get_checklist_progress` (agregado `COUNT`, espejo de `get_subtask_counts`) y `get_incomplete_blockers` (aristas con `is_active == true` — corrección de gate 2026-07-11 — cuyo blocker tiene `completed_at IS NULL`). `TaskRead` expone `labels[]`, `checklist_progress`, `is_blocked`, `blockers[]`. El filtro `label_id` en la lista se resuelve con `join` a `TaskLabel` en `list_for_project`.

**Desviación declarada — criterio de desbloqueo (corrección de gate 2026-07-11)**: la spec levanta el bloqueo cuando el bloqueador está en estado "completado o cancelado", pero hoy no existe ningún estado `cancelled` en el código (verificado por el gate: cero hits). El criterio implementable hoy es `completed_at IS NOT NULL`. Cuando exista un estado terminal de cancelación (p. ej. vía metodología `custom`), deberá incorporarse al criterio de desbloqueo. Queda como deuda trazada, no como omisión silenciosa.
**Alternatives considered**: `selectinload` sobre relaciones nuevas en `Task` (rompe el estilo sin-relaciones y no aporta en lectura de una tarea). Se reserva `selectinload` batcheado si a futuro la lista embebe labels.
**Rationale**: detalle = una tarea → sin N+1 por construcción; consistente con `subtask_progress`.

## Data Flow

    POST /tasks/{X}/dependencies (type→blocker=X,blocked=Y)
      → service.link: load edges(project) → DFS(Y →blocks→ …) alcanza X? → 422 ciclo
                                          → else INSERT TaskDependency(X,Y)

    scheduler → evaluator → BlockedTaskStrategy.evaluate(threshold)
      → edges con blocker incompleto & created_at<now-Xd → AlertCandidate(recipient=blocked.assignee)
      → exists_active(dedup_key)? no → Notification

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/app/modules/labels/{models,schemas,repository,service,router}.py` | Create | `Label` + `TaskLabel`, CRUD, link/unlink |
| `backend/app/modules/checklists/{models,schemas,repository,service,router}.py` | Create | `TaskChecklist` + `ChecklistItem` + endpoints |
| `backend/app/modules/task_links/{models,schemas,repository,service,router}.py` | Create | `TaskDependency`, link/unlink/list, ciclos |
| `backend/app/modules/tasks/{schemas,service,repository,router}.py` | Modify | detalle enriquecido + filtro `label_id` |
| `backend/app/alerts/strategies/blocked_task.py` | Create | estrategia |
| `backend/app/alerts/registry.py` | Modify | registrar `blocked_task` |
| `backend/app/db_init.py` | Modify | `_DEFAULT_ALERT_RULES` += seed idempotente; import de modelos nuevos |
| `backend/app/main.py` | Modify | montar routers nuevos |
| `backend/alembic/versions/xxxx_add_labels_checklists_task_deps.py` | Create | tablas nuevas; `down_revision` = head de 02 (`add_audit_fields`) |

## Interfaces / Contracts

```python
class TaskDependencyLink(BaseModel):     # type ∈ {blocks, is_blocked_by}
    related_task_id: uuid.UUID; type: str = "blocks"
# TaskRead += labels: list[LabelRead]; checklist_progress: float|None
#            is_blocked: bool; blockers: list[BlockerRef]
```

**Paginación (corrección de gate 2026-07-11)**: los list endpoints nuevos (labels y task_links/dependencias) se cablean al contrato de `openspec/changes/02-contrato-api/design.md`: `pagination_params` como dependencia, `paginate()` para envolver la respuesta y `SORTABLE_FIELDS` propio por módulo — incluida la corrección de ese design: el helper fusiona claves de `meta`, nunca las elimina.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | DFS de ciclos (directo/transitivo/auto-lazo), progreso de checklist, dedup_key | pytest sin BD |
| Integration | CRUD label + filtro `label_id`; checklist en `GET /tasks/{id}`; link/unlink/list + ciclo `422`; `blocked_task` genera notificación deduplicada; seed idempotente | httpx AsyncClient + fixtures |

## Migration / Rollout

Una revisión Alembic aditiva encadenada tras 02 (`down_revision` = head de `add_audit_fields`). Todo aditivo → rollback = `downgrade` (drop de tablas), quitar registro de la estrategia y la regla seed. Sin cambios destructivos.

## Open Questions

- [x] `type=is_blocked_by` invierte (blocker=related, blocked=X) antes de persistir canónico — **Resuelto (gate 2026-07-11)**: confirmado; con `type=is_blocked_by`, `related_task_id` → `blocker_task_id` y la tarea del path → `blocked_task_id`. Ver "Decisión: Arista dirigida canónica".
- [ ] ¿`blocked_days` compartido con `task_at_risk` o parámetro propio? Se propone propio (`blocked_days`, default 3).

## Correcciones de gate (2026-07-11) — VINCULANTES para la fase de tasks

1. **SoftDelete en `TaskDependency` (CRITICAL)**: hereda Pk + Timestamp + SoftDelete; unlink = `is_active=False`, nunca DELETE físico. La carga de aristas para el DFS de ciclos y el cálculo de `is_blocked` DEBEN filtrar `is_active == true`.
2. **Dirección canónica**: con `type=is_blocked_by` la arista se invierte antes de persistir (`related_task_id` → `blocker_task_id`; tarea del path → `blocked_task_id`). Ambas direcciones se leen desde la arista canónica.
3. **Criterio de desbloqueo**: la cláusula "cancelado" de la spec no es implementable hoy (no existe estado `cancelled` en el código); el criterio es `completed_at IS NOT NULL` y la cancelación queda como deuda trazada.
4. **Tenant scoping**: `Label`, `TaskChecklist`, `ChecklistItem` y `TaskDependency` llevan `TenantMixin` (`organization_id` directo) + filtros row-level en repos, siguiendo el precedente de `TaskComment`/`Attachment`.
5. **Paginación**: los list endpoints de labels y task_links usan `pagination_params` + `paginate()` + `SORTABLE_FIELDS` según el design de 02 (el helper fusiona claves de `meta`, nunca las elimina).
6. **Nomenclatura**: spec `task_id`/`depends_on_task_id` ≡ design `blocked_task_id`/`blocker_task_id`.
