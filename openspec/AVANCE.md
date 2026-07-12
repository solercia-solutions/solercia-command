# Avance del plan — Solercia Project Manager

**Fuente del plan**: [CLAUDE.md](../CLAUDE.md) (prioridad de implementación, fases 1-4).
**Convención**: cada cambio futuro se ejecuta como un ciclo SDD completo en su propia carpeta `openspec/changes/NN-nombre/` (explore → proposal → spec → design → tasks → apply → verify → archive). El `state.yaml` de cada carpeta es la fuente de verdad de su estado. TDD estricto obligatorio (`strict_tdd: true` en [config.yaml](config.yaml); test command: `cd backend && pytest tests/ -v`). Lo YA construido está documentado como specs as-built en `openspec/specs/`.
**Última actualización**: 2026-07-12 (cambios 01-05 y 11 completados; 11-blindaje-baseline archivado — backfill de tests as-built con TDD estricto de 10 capacidades críticas: auth, users-admin, rbac-catalog, multi-tenancy, projects, tasks, methodology-strategies, alert-engine, notifications-inapp, dashboard-executive; matriz de permisos y aislamiento multi-tenant; suite crece de 258 a 382 tests, ruff/mypy limpios; 5 cambios backend pendientes; frontend EN PAUSA por la migración a @solercia/ui).

## Mapa visual del plan

```mermaid
flowchart TD
    B0["Línea base as-built<br/>14 capacidades backend documentadas<br/>openspec/specs/"]

    C01["01 · Fundación TDD<br/>BD de test + Alembic + ruff/mypy"]
    C02["02 · Contrato API<br/>paginación + auditoría + docs"]
    C03["03 · Boards persistentes<br/>Board/BoardColumn + WIP + custom"]
    C04["04 · Labels, checklists<br/>y dependencias tarea-tarea"]
    C05["05 · Trabajo realizado<br/>TimeLog + ActivityLog + cruce"]
    C11["11 · Blindaje baseline<br/>backfill TDD + permisos + aislamiento"]
    C06["06 · Reminders<br/>manuales y por regla"]
    C07["07 · Assets SDMujer<br/>activos + licencias + alertas"]
    C08["08 · Email notifications<br/>digest configurable"]
    C09["09 · WebSocket realtime<br/>push in-app"]
    C10["10 · Búsqueda global<br/>+ filtros avanzados"]

    FE["Frontend Angular 20<br/>cycle2-design-system<br/>EN PAUSA — espera @solercia/ui"]

    B0 --> C01
    C01 --> C02
    C01 --> C11
    C02 --> C03 --> C04
    C02 --> C05
    C02 --> C06 --> C07 --> C08
    C02 --> C09
    C04 --> C10
    C05 --> C10

    FE -.bloqueado por @solercia/ui.- B0

    class B0 done
    class C01 done
    class C02 done
    class C03 done
    class C04 done
    class C05 done
    class C11 done
    class FE inprogress
    class C06,C07,C08,C09,C10 pending

    classDef done fill:#22c55e,stroke:#166534,color:#ffffff
    classDef inprogress fill:#eab308,stroke:#854d0e,color:#000000
    classDef pending fill:#9ca3af,stroke:#4b5563,color:#ffffff
```

**Leyenda**: 🟩 completado (línea base) · 🟨 en pausa/bloqueado · ⬜ pendiente

---

## Lo construido (línea base as-built, 2026-07-11)

Las 14 capacidades existentes están documentadas en `openspec/specs/`. Ninguna nació con ciclo SDD (son pre-SDD); sus escenarios Given/When/Then servirán para el backfill de tests. La trazabilidad completa capacidad → cambio de origen (línea base y ciclos SDD archivados) está en [specs/README.md](specs/README.md).

| Capacidad | Spec | Estado de tests |
|-----------|------|-----------------|
| Autenticación (JWT + refresh cookie) | [specs/auth/spec.md](specs/auth/spec.md) | CERO tests |
| Administración de usuarios | [specs/users-admin/spec.md](specs/users-admin/spec.md) | CERO tests |
| Catálogo RBAC (roles + menús + áreas) | [specs/rbac-catalog/spec.md](specs/rbac-catalog/spec.md) | CERO tests |
| Multi-tenancy (row-level) | [specs/multi-tenancy/spec.md](specs/multi-tenancy/spec.md) | CERO tests |
| Proyectos | [specs/projects/spec.md](specs/projects/spec.md) | Solo velocity (indirecto) |
| Estrategias de metodología | [specs/methodology-strategies/spec.md](specs/methodology-strategies/spec.md) | CERO tests |
| Tareas | [specs/tasks/spec.md](specs/tasks/spec.md) | Parcial: by-key (13) + subtasks (4); CRUD/PATCH sin cubrir |
| Sprints | [specs/sprints/spec.md](specs/sprints/spec.md) | Parcial: close + velocity (8) |
| Comentarios y menciones | [specs/comments-mentions/spec.md](specs/comments-mentions/spec.md) | Cubierto: comments (6) + menciones (7) |
| Adjuntos | [specs/attachments/spec.md](specs/attachments/spec.md) | Cubierto: attachments (5) |
| Notificaciones in-app | [specs/notifications-inapp/spec.md](specs/notifications-inapp/spec.md) | Endpoints sin tests (creación por mención cubierta indirecto) |
| Motor de alertas | [specs/alert-engine/spec.md](specs/alert-engine/spec.md) | CERO tests |
| Vista ejecutiva | [specs/dashboard-executive/spec.md](specs/dashboard-executive/spec.md) | CERO tests |
| Convenciones de API | [specs/api-conventions/spec.md](specs/api-conventions/spec.md) | Sin tests transversales |

Total tras cambio 11: **382 tests en 24 archivos** (`backend/tests/`; 43 en baseline + 296 en cambios 01-05 + 43 en cambio 11 = 382; crecimiento con TDD estricto en cada ciclo).

---

## Roadmap de cambios backend

Todos pendientes. Cada uno se ejecutará como ciclo SDD completo (`openspec/changes/NN-nombre/`) con TDD estricto.

| # | Cambio | Alcance | Estado | Specs producidas/modificadas |
|---|--------|---------|--------|------------------------------|
| 01 | `01-fundacion-tdd` | Infraestructura de pruebas (BD `solercia_test` en docker-compose, fixtures compartidos en conftest, venv documentado); migración Alembic inicial descriptiva + adopción de Alembic como flujo (hoy el esquema se crea con `create_all`); ruff + mypy. **PRIORIDAD 1: desbloquea el TDD estricto de todo lo demás.** | 🟩 Completado | [dev-tooling](specs/dev-tooling/spec.md) (nueva) · [api-conventions](specs/api-conventions/spec.md) (modificada) |
| 02 | `02-contrato-api` | Paginación estándar (`?page&size&sort&order` + meta), auditoría `created_by`/`updated_by` automática, refresco del contrato (docs/API.md desactualizado: no lista comments, attachments, notifications, alert-rules, by-key, subtasks, velocity, close). | 🟩 Completado | [api-conventions](specs/api-conventions/spec.md) (modificada: paginación + auditoría) |
| 03 | `03-boards-persistentes` | Entidades Board/BoardColumn persistidas, `board_column_id` en Task, límites WIP (kanban), configuración de columnas en runtime (hoy la metodología custom es inutilizable: devuelve columnas vacías sin API para configurarlas). | 🟩 Completado | [boards](specs/boards/spec.md) (nueva) · [methodology-strategies](specs/methodology-strategies/spec.md) y [tasks](specs/tasks/spec.md) (modificadas) |
| 04 | `04-labels-checklists-dependencias` | Label/TaskLabel, TaskChecklist/ChecklistItem, TaskDependency (blocks/is_blocked_by) + estrategia de alerta `blocked_task`. | 🟩 Completado | [labels](specs/labels/spec.md), [checklists](specs/checklists/spec.md), [task-dependencies](specs/task-dependencies/spec.md) (nuevas) · [alert-engine](specs/alert-engine/spec.md) (modificada) |
| 05 | `05-trabajo-realizado` | TaskTimeLog + ActivityLog/TaskHistory + cruce "trabajo asignado vs realizado" en el dashboard ejecutivo (capacidad transversal clave del producto). | 🟩 Completado | [time-logs](specs/time-logs/spec.md), [activity-history](specs/activity-history/spec.md) (nuevas) · [dashboard-executive](specs/dashboard-executive/spec.md) (modificada) |
| 11 | `11-blindaje-baseline` | Blindaje de la línea base: backfill de TDD de las 10 capacidades as-built sin tests (auth, users-admin, rbac-catalog, multi-tenancy, projects, tasks, methodology-strategies, alert-engine, notifications-inapp, dashboard-executive) + matriz de permisos + aislamiento multi-tenant + 1 bugfix real (usuarios soft-borrados en listado). | 🟩 Completado | [test-coverage-baseline](specs/test-coverage-baseline/spec.md) (nueva) |
| 06 | `06-reminders` | Recordatorios manuales y automáticos por regla. | ⬜ Pendiente | — |
| 07 | `07-assets-sdmujer` | Asset + AssetLicense + AssetTask + estrategias de alerta `license_expiring`/`license_expired` (Fase 3 completa del CLAUDE.md). | ⬜ Pendiente | — |
| 08 | `08-email-notifications` | Canal email con digest configurable. | ⬜ Pendiente | — |
| 09 | `09-websocket-realtime` | Push in-app en tiempo real. | ⬜ Pendiente | — |
| 10 | `10-busqueda-global` | Búsqueda global + filtros avanzados. | ⬜ Pendiente | — |

---

## Frontend — EN PAUSA

- El ciclo [changes/cycle2-design-system/](changes/cycle2-design-system/) (sistema de diseño del frontend Angular 20) está **ON-HOLD**: proposal y design completos, tasks parcial (Fases 0-1 ejecutadas).
- **Bloqueante**: la migración a la librería compartida `@solercia/ui`, descrita en [docs/PLAN_MIGRACION_SOLERCIA_UI.md](../docs/PLAN_MIGRACION_SOLERCIA_UI.md). En solercia_flows corresponde al programa **07 · Súper Front @sol/ui (E0–E7)**.
- **Regla dura**: ningún cambio SDD debe tocar `frontend/` hasta levantar el bloqueo (constraint `frontend-frozen` en config.yaml).

---

## Deuda transversal detectada (2026-07-11) y resoluciones

### Resuelto en cambio 01-fundacion-tdd
- ✅ **Migraciones Alembic**: Baseline Alembic creada y adoptada como flujo de verdad; cambios de modelo posteriores vía `--autogenerate`.
- ✅ **Tests de integración**: BD `solercia_test` provisionada en docker-compose; fixtures compartidos en conftest; 43 tests existentes + nuevos pasan sin regresiones.
- ✅ **Linting y type-checking**: ruff + mypy adoptados con línea base limpia (cero hallazgos); comandos documentados.

### Resuelto en cambio 02-contrato-api
- ✅ **Paginación estándar**: 11 endpoints paginables (`?page&size&sort&order`), validación de límites, whitelist de campos ordenables, opt-in (sin params = comportamiento actual).
- ✅ **Auditoría automática**: `created_by`/`updated_by` en 11 modelos SoftDeleteMixin, pobladasautomáticamente desde usuario autenticado, exposición en respuestas.
- ✅ **Documentación API refrescada**: docs/API.md actualizado con paginación, auditoría y 4 módulos antes no documentados (comments, attachments, notifications, alert-rules).

### Resuelto en cambio 05-trabajo-realizado
- ✅ **Cruce "trabajo asignado vs realizado"**: TaskTimeLog (entradas de tiempo propias) + TaskHistory (changelog automático append-only) + bloque `work_gap` en dashboard ejecutivo (`hours_logged` vs `hours_estimated`, `tasks_assigned` vs `tasks_with_activity`, `no_recent_activity` con umbral configurable).
- ✅ **Permisos de tiempo**: edición/borrado estrictamente del dueño (sin excepción de rol), lectura ajena permitida solo a admin/manager.
- ✅ **Integración transversal**: TaskHistory capturada automática en PATCH de tareas y cierre de sprints; `record_task_history` integrado en tasks/service.py y sprints/service.py.
- ✅ **Cobertura TDD**: 258 tests (43 nuevos: time_logs, activity, dashboard work_gap); 3 suites nuevas todas verdes; ruff/mypy limpios.

### Aún pendiente (tras cambio 11)
- **Deuda documentada del código**:
  - `UserRepository.get_in_org` sin filtro `is_active` (pre-existente, prior a cambio 11; bug identificado y corregido en commit `40631fa`).
  - `get_current_membership`: tie-break por `created_at` (comportamiento determinista correcto, pero no documentado con la razón de la ordenación por timestamp).
  - `viewer` sin gate de rol en el dominio (acceso de lectura concedido a todos los miembros; no aplica `require_role()` granular).
  - `mypy` configurado para excluir `backend/tests/` (decisión preexistente; después del crecimiento de ~150 tests nuevos tipados con dataclasses en cambio 11, podría valer la pena evaluar tipar tests también en cambios futuros, fuera de alcance).
- **Documentación desactualizada**: docs/METHODOLOGY-FEATURES.md no refleja el código actual.
- **TODO de lock distribuido Redis** en el evaluador de alertas (REDIS_URL declarado y sin uso).
