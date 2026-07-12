# Propuesta: Boards persistentes — Board/BoardColumn, board_column_id, límites WIP y configuración runtime

## Intent

Hoy las columnas del tablero son listas EFÍMERAS de strings devueltas por la strategy: no existe entidad `Board`/`BoardColumn` persistida, `Task` no tiene `board_column_id`, no hay límites WIP (kanban queda incompleto frente al CLAUDE.md) y la metodología `custom` es INUTILIZABLE (devuelve columnas vacías y no hay API para configurarlas). Este cambio persiste el tablero por proyecto sembrándolo desde `strategy.default_columns()`, añade `board_column_id` a `Task` con semántica de movimiento coherente con `allowed_statuses()`, aplica límites WIP en kanban y expone una API de configuración de columnas en runtime que hace usable a `custom` — sin romper la regla de oro: el comportamiento se lee DESDE la strategy, nunca con `if methodology == ...`.

## Scope

### In Scope
- **Entidades persistidas**: `Board` (1 por proyecto) y `BoardColumn` (name, order, wip_limit?, status_key), sembradas desde `strategy.default_columns()` al crear el proyecto.
- **`board_column_id`** (FK nullable) en `Task` + endpoint de movimiento entre columnas; el `status` resultante DEBE pertenecer a `allowed_statuses()` de la strategy del proyecto.
- **Límite WIP por columna** (kanban), validado al mover (409/422 cuando se excede).
- **API de configuración runtime** de columnas: renombrar, reordenar, agregar y quitar, con reglas para columnas que aún contienen tareas. Esto es lo que hace usable a `custom`.

### Out of Scope
- Cualquier cambio en `frontend/` (congelado, constraint `frontend-frozen`): sin drag&drop, sin UI de tablero.
- Swimlanes, sub-columnas y políticas WIP avanzadas (por persona, por tipo de tarea).
- Múltiples boards por proyecto (1 board por proyecto en este ciclo).
- Cambio de metodología de un proyecto ya creado (re-siembra).

## Capabilities

### New Capabilities
- `boards`: entidades `Board`/`BoardColumn` persistidas, siembra desde la strategy, movimiento de tareas entre columnas, límites WIP y API de configuración en runtime.

### Modified Capabilities
- `tasks`: agrega `board_column_id` y la semántica de movimiento entre columnas (el `status` se deriva de la columna destino y se valida contra la strategy).
- `methodology-strategies`: `default_columns()` deja de ser efímero y pasa a ser la fuente de siembra; para `custom`, el conjunto de columnas persistidas se vuelve la fuente de `allowed_statuses()` (la strategy delega en el board persistido).

## Approach

- **Módulo nuevo** `backend/app/modules/boards/` (router → service → repository → models) siguiendo el patrón obligatorio. `Board` 1:1 con `Project`; `BoardColumn` 1:N con `status_key` = el string de estado que la tarea adopta al entrar.
- **Siembra**: el service de creación de proyecto invoca `strategy.default_columns()` y persiste columnas ordenadas (para `custom`, board sin columnas hasta configurarlas).
- **Movimiento**: `PATCH` mueve la tarea a una columna, fija `task.status = column.status_key`, valida contra `allowed_statuses()` y, en kanban, cuenta tareas activas en la columna destino contra `wip_limit` → 409/422.
- **Regla de oro**: el service resuelve la strategy vía factory; para `custom`, `allowed_statuses()` deriva de las columnas persistidas. Cero condicionales por metodología dispersos.
- **Migración Alembic** (aditiva, encadenada tras `02`): tablas `boards`/`board_columns` + `board_column_id`; backfill que siembra boards de proyectos existentes desde su strategy y mapea `Task.status` → columna por `status_key`.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `backend/app/modules/boards/` | New | Módulo completo (router/service/repository/models/schemas) |
| `backend/app/modules/tasks/` | Modified | `board_column_id`, endpoint de movimiento, `status` desde columna |
| `backend/app/methodology/` | Modified | `custom` deriva `allowed_statuses()` de columnas persistidas |
| `backend/alembic/versions/` | New | Tablas boards/board_columns + `board_column_id` + backfill |

## Risks

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Migración de `Task.status` (string) a columna deja tareas huérfanas si el status no mapea a ninguna columna | Media | Backfill por `status_key`; status sin columna → columna por defecto (primera) y se registra |
| `custom` sin columnas: tareas sin estado válido | Media | Board vacío bloquea creación/movimiento hasta configurar ≥1 columna |
| Carreras al validar WIP en movimientos concurrentes | Media | Conteo + validación dentro de la transacción; decidir bloqueo en design |
| Quitar/renombrar columna con tareas dentro | Alta | Reglas explícitas (reasignar o rechazar) definidas en spec |
| Apply arranca antes del contrato de `02` (paginación/auditoría, cadena Alembic) | Media | `depends_on: 02-contrato-api` (orden de apply) |

## Rollback Plan

Revertir la migración Alembic (drop `board_column_id`, drop `board_columns`/`boards`); eliminar el módulo `boards/`; `Task` vuelve a operar solo con `status`. Cada pieza es independiente y reversible.

## Dependencies

- **`02-contrato-api`** (orden de apply): los endpoints nuevos/modificados DEBEN seguir el contrato de paginación/auditoría que aterriza `02`, y las migraciones Alembic se encadenan linealmente. Spec y design pueden avanzar en paralelo sin esperar a `02`.

## Success Criteria

- [ ] Al crear un proyecto se persiste su `Board` con las columnas de `strategy.default_columns()`.
- [ ] `Task` tiene `board_column_id`; el movimiento fija `status` desde la columna y rechaza estados fuera de `allowed_statuses()`.
- [ ] En kanban, mover a una columna que excede su `wip_limit` responde 409/422.
- [ ] La API de configuración runtime permite renombrar/reordenar/agregar/quitar columnas, con reglas claras para columnas con tareas; `custom` queda usable.
- [ ] Ningún condicional `if methodology ==` nuevo: el comportamiento se lee desde la strategy.
- [ ] Migración Alembic siembra boards de proyectos existentes y mapea `status`→columna sin dejar tareas en estado inválido.
- [ ] Tests TDD cubren: siembra, movimiento válido/ inválido, tope WIP, configuración runtime con y sin tareas, y `custom` de extremo a extremo.
