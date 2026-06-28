# Estado de características por metodología — Solercia Project Manager

Este documento es el **insumo de planeación** para decidir qué construir a continuación.
Para cada metodología muestra qué características debería tener, cuál es su estado real
en el código hoy (27 jun 2026) y qué falta para considerarla funcionalmente completa.

Las conclusiones se basan en lectura directa del código; cada afirmación cita el archivo
de referencia.

> **Leyenda de estado**
>
> | Símbolo | Significado |
> |---------|-------------|
> | ✅ | Implementado y funcional (backend + frontend) |
> | 🟡 | Parcialmente implementado (falta una capa o tiene limitaciones conocidas) |
> | ❌ | No implementado |

---

## Fundamento: el contrato Strategy

Todas las metodologías implementan `MethodologyStrategy`
(`backend/app/methodology/base.py`) y exponen:

| Propiedad / método | Tipo | Qué define |
|--------------------|------|------------|
| `default_columns()` | `list[str]` | Columnas creadas al inicializar un proyecto |
| `allowed_statuses()` | `list[str]` | Valores de estado válidos para las tareas |
| `sprints_enabled` | `bool` | Si la pestaña de sprints aparece en el workspace |
| `estimation_mode` | `str` | `none` / `points` / `hours` / `both` |
| `has_backlog` | `bool` | Si la pestaña de backlog aparece en el workspace |

El frontend lee estos valores desde `methodology_info` devuelto por la API
(`project-workspace.component.ts` líneas 489–521) y no tiene ni un solo
`if (methodology === 'scrum')` disperso en el código. Esta separación es sólida y
correcta.

---

## 1. Planner

> Estilo Microsoft Planner: buckets como columnas, estados simples, sin sprints ni
> estimación.

**Configuración actual** (`backend/app/methodology/planner.py`):
- Columnas por defecto: `Sin iniciar | En curso | Completada`
- Estimation mode: `none`
- Sprints: `false` · Backlog: `false`

### Matriz de características

| Característica | ¿La necesita? | Estado | Nota / gap |
|----------------|:---:|:---:|------------|
| Columnas/buckets por defecto | Sí | ✅ | 3 columnas fijas: Sin iniciar / En curso / Completada (`planner.py`) |
| Estados permitidos por metodología | Sí | ✅ | Idénticos a las columnas; validados en `TaskService._resolve_status` |
| Tablero con drag & drop | Sí | ✅ | CDK DragDrop con `cdkDropListGroup` en `board-column.component.ts` |
| Vista cuadrícula / grid de tareas | Sí | ❌ | Solo existe la vista tablero (columnas). No hay modo cuadrícula/grid |
| Sin estimación (points ni hours) | Sí | ✅ | `estimation_mode = none`; los campos no aparecen en el modal |
| Sin sprints | Sí | ✅ | Pestaña Sprints no se muestra |
| Sin backlog | Sí | ✅ | Pestaña Backlog no se muestra |
| Código incremental de tarea (PLAN-1) | Sí | ❌ | No existe campo `task_code` ni secuencia por proyecto en el modelo (`tasks/models.py`) |
| Subtareas | Sí | 🟡 | `parent_task_id` existe en el modelo (`models.py` línea 53), pero no hay lógica de servicio, endpoint ni UI para crear/ver subtareas |
| Comentarios / observaciones | Sí | ❌ | No existe módulo `comments`; ni modelo, ni endpoint, ni UI |
| Adjuntar archivos | Sí | ❌ | No existe módulo `attachments`; ni almacenamiento, ni endpoint, ni UI |
| Etiquetas | Opcional | ❌ | No existe módulo `labels`; ni modelo, ni endpoint, ni UI |
| Asignación de responsable | Sí | ✅ | Campo `assignee_id` en modelo y en el modal (`task-modal.component.ts`) |
| Fecha límite (due_date) | Sí | ✅ | Campo en modelo, editable en modal, `isOverdue()` en `workspace.model.ts` |
| Prioridad (low/medium/high/critical) | Sí | ✅ | Enum `Priority`; chip de color en `task-card.component.ts` |
| Tipo de ítem (tarea/bug/historia/épica) | Opcional | ✅ | Campo `task_type` en modelo y en modal |
| Indicador de riesgo | Sí | 🟡 | `risk_flag` / `risk_reason` en modelo y en `dashboard.service.py`; no hay UI para marcar riesgo desde el tablero |
| Vista ejecutiva | Sí | 🟡 | El servicio `DashboardService.executive()` existe y calcula métricas; no hay página de dashboard en el frontend (no se encontró componente dashboard en `src/app/features/`) |
| Dependencias entre tareas | No | — | Planner no las necesita |
| WIP limits | No | — | Planner no los necesita |

**Gaps críticos para Planner:**
1. Vista cuadrícula/grid (petición explícita del usuario).
2. Código incremental de tarea.
3. Comentarios/observaciones.
4. Adjuntos.
5. UI de subtareas (modelo ya tiene `parent_task_id`).

---

## 2. Kanban

> Flujo continuo, WIP limits, sin sprints.

**Configuración actual** (`backend/app/methodology/kanban.py`):
- Columnas por defecto: `Backlog | Doing | Done`
- Estimation mode: `hours`
- Sprints: `false` · Backlog: `false`

> **Nota de diseño:** La columna "Backlog" en Kanban es una columna de tablero
> (no una pestaña separada). `has_backlog = false`, por lo que no hay pestaña
> "Backlog" en el workspace. Las tareas sin sprint simplemente viven en la columna
> "Backlog" del tablero.

### Matriz de características

| Característica | ¿La necesita? | Estado | Nota / gap |
|----------------|:---:|:---:|------------|
| Columnas por defecto | Sí | ✅ | Backlog / Doing / Done (`kanban.py`) |
| WIP limits por columna | Sí | ❌ | No existe campo `wip_limit` en ningún modelo de columna. No hay enforcement ni UI |
| Flujo continuo (sin sprints) | Sí | ✅ | `sprints_enabled = false` |
| Estimación en horas | Sí | ✅ | `estimation_mode = hours`; campo `estimation_hours` (Decimal) en modelo; el modal lo muestra condicionalmente (`showHours()`) |
| Tablero con drag & drop | Sí | ✅ | Mismo CDK DragDrop del board |
| Columnas configurables (agregar/eliminar) | Deseable | ❌ | Las columnas están hardcodeadas en la strategy; no hay endpoint para crear/eliminar columnas en runtime |
| Código incremental de tarea | Sí | ❌ | No existe (igual que Planner) |
| Subtareas | Deseable | 🟡 | Modelo soporta `parent_task_id`; sin servicio ni UI |
| Comentarios / observaciones | Sí | ❌ | No existe módulo `comments` |
| Adjuntar archivos | Sí | ❌ | No existe módulo `attachments` |
| Etiquetas | Sí | ❌ | No existe módulo `labels` |
| Asignación de responsable | Sí | ✅ | Mismo que Planner |
| Fecha límite | Sí | ✅ | Mismo que Planner |
| Prioridad | Sí | ✅ | Mismo que Planner |
| Indicador de riesgo | Sí | 🟡 | Backend calcula `at_risk` en dashboard; sin UI desde el tablero |
| Vista ejecutiva | Sí | 🟡 | Mismo gap que Planner |
| Dependencias entre tareas | Deseable | ❌ | Sin modelo de dependencia task→task; el módulo `admin/dependencies` es independiente del sistema de tareas |

**Gaps críticos para Kanban:**
1. WIP limits (característica definitoria del método — su ausencia es un gap mayor).
2. Columnas configurables en runtime (hoy solo son las 3 hardcodeadas).
3. Código incremental, comentarios, adjuntos (mismos que Planner).

---

## 3. Scrum

> Backlog + sprints + story points Fibonacci + workflow To Do → In Progress → In Review → Done.

**Configuración actual** (`backend/app/methodology/scrum.py`):
- Columnas por defecto: `To Do | In Progress | In Review | Done`
- Estimation mode: `points`
- Sprints: `true` · Backlog: `true`

### Matriz de características

| Característica | ¿La necesita? | Estado | Nota / gap |
|----------------|:---:|:---:|------------|
| Columnas por defecto | Sí | ✅ | 4 columnas con labels en español en `workspace.model.ts:statusDisplay()` |
| Story points (Fibonacci) | Sí | 🟡 | Campo `estimation_points: int` en modelo (`models.py` línea 81); el modal muestra el input (`showPoints()`). **Gap**: no hay validación Fibonacci (1,2,3,5,8,13,21); acepta cualquier entero |
| Backlog (pestaña) | Sí | ✅ | Pestaña "Backlog" aparece cuando `has_backlog = true`; lista tareas con `sprint_id == null` (`backlogTasks` computed en workspace) |
| Asignar tareas a sprint desde backlog | Sí | ✅ | Dropdown "Mover a sprint" en la pestaña Backlog (`project-workspace.component.ts` línea 216–230) |
| Crear sprint (nombre, meta, fechas) | Sí | ✅ | Formulario en pestaña Sprints; `SprintService.create_sprint()` en backend |
| Cerrar / reactivar sprint | Sí | 🟡 | Botón "Cerrar / Reactivar" cambia `status`: `active ↔ closed` (`sprints/service.py`). **Gap**: no hay wizard de cierre que redistribuya tareas incompletas al siguiente sprint o al backlog |
| Burndown chart | Sí | ✅ | `SprintService.burndown()` en backend (ideal vs actual, unidad: points o tasks). `BurndownChartComponent` SVG en frontend; se muestra al hacer clic en un sprint |
| Velocity (puntos completados por sprint) | Sí | ❌ | No existe endpoint `/sprints/velocity`; no hay UI. El servicio de performance (`dashboard/service.py`) calcula `on_time_rate` por colaborador, pero no velocity histórica por sprint |
| Vista de sprints como cuadrícula de tiempo (estilo Jira roadmap) | Deseable | ❌ | La pestaña Sprints muestra una lista vertical de sprints, no una cuadrícula temporal |
| Tablero con drag & drop | Sí | ✅ | Mismo board CDK que las demás metodologías |
| Código incremental de tarea (PROJ-1) | Sí | ❌ | No existe campo `task_code` ni secuencia por proyecto |
| Subtareas | Sí | 🟡 | `parent_task_id` en modelo; sin servicio ni UI |
| Comentarios / observaciones | Sí | ❌ | No existe módulo `comments` |
| Adjuntar archivos | Sí | ❌ | No existe módulo `attachments` |
| Etiquetas | Sí | ❌ | No existe módulo `labels` |
| Dependencias entre tareas (blocks/blocked_by) | Sí | ❌ | Sin modelo de dependencia entre tareas |
| Asignación de responsable | Sí | ✅ | |
| Fecha límite y fecha de inicio | Sí | ✅ | Campos `due_date` y `start_date` en modelo y modal |
| Prioridad | Sí | ✅ | |
| Tipo de ítem (epic/story/task/bug) | Sí | ✅ | Enum `TaskType` en `enums.py` y dropdown en modal |
| Indicador de riesgo | Sí | 🟡 | Backend calcula `at_risk`; sin UI desde el tablero |
| Vista ejecutiva con métricas de sprint | Sí | 🟡 | `DashboardService.performance()` calcula métricas por colaborador; sin página de dashboard en frontend |

**Gaps críticos para Scrum:**
1. Velocity histórica (característica Scrum fundamental — sin ella el equipo no puede proyectar capacidad).
2. Validación Fibonacci en story points (hoy acepta cualquier número).
3. Wizard de cierre de sprint (redistribución de tareas incompletas).
4. Vista cuadrícula de tiempo para sprints.
5. Código incremental, comentarios, adjuntos, dependencias entre tareas.

---

## 4. Custom

> Blank slate: la organización define columnas, estados y modo de estimación.

**Configuración actual** (`backend/app/methodology/custom.py`):
- Columnas por defecto: `[]` (vacías)
- Estimation mode: `none` (hardcodeado)
- Sprints: `false` · Backlog: `false`
- Fallback en `TaskService`: `_CUSTOM_DEFAULT_STATUS = "todo"` (línea visible en `tasks/service.py`)

### Matriz de características

| Característica | ¿La necesita? | Estado | Nota / gap |
|----------------|:---:|:---:|------------|
| Columnas definibles por el usuario | Sí | ❌ | La strategy retorna `[]`; el frontend muestra "Esta metodología no define columnas de tablero". No existe endpoint para agregar columnas a un proyecto Custom ni tabla `board_columns` en el modelo |
| Estados personalizados por proyecto | Sí | ❌ | `allowed_statuses()` retorna `[]`; sin API para definirlos |
| Modo de estimación configurable | Deseable | ❌ | `estimation_mode` está hardcodeado a `none` en `CustomStrategy`; no hay campo de configuración por proyecto |
| Sprints opcionales | Deseable | ❌ | `sprints_enabled = false` hardcodeado; no hay forma de activarlo per-proyecto |
| Backlog opcional | Deseable | ❌ | `has_backlog = false` hardcodeado |
| Tablero funcional | Sí | ❌ | Sin columnas no hay tablero que renderizar (el componente muestra mensaje de aviso) |
| Todas las demás características (comentarios, adjuntos, código, subtareas) | Sí | ❌ | Mismo gap universal que las otras metodologías |

**Estado real de Custom hoy:** la metodología existe como enum y es seleccionable al crear un proyecto, pero el proyecto resultante tiene un tablero vacío e inutilizable. Es la metodología con más trabajo pendiente porque requiere un sistema de configuración de columnas/estados que hoy no existe en ninguna capa.

---

## 5. Bugs y peticiones pendientes — cruce con gaps

Cada petición se mapea a las metodologías que impacta y al gap correspondiente.

| Petición | Metodologías | Estado | Dependencias |
|----------|:---:|:---:|-------------|
| **Código incremental por proyecto** (PROJ-1, ID reiniciando en 1): campo `task_code` en modelo + secuencia PostgreSQL por proyecto + display en card y URL `/task/[COD]-[N]` | Todas | ❌ | Requiere migración Alembic, nueva columna en `tasks`, lógica en `TaskService.create_task()`, actualización de `TaskRead` schema y `task-card.component.ts` |
| **Subtareas como tareas completas** (con los mismos campos; decisión pendiente: ¿con estimación?): activar `parent_task_id` en servicio, nuevo endpoint `POST /tasks/{id}/subtasks`, UI anidada en modal | Todas | 🟡 | `parent_task_id` ya existe en el modelo. Falta: servicio, endpoint, UI. La decisión de si las subtareas llevan estimación propia afecta la regla de `_validate_estimation` |
| **Comentarios / observaciones con @menciones** (notificación cuando exista el motor): módulo nuevo `comments` con modelo `TaskComment` | Todas | ❌ | Independiente de otros gaps. Las @menciones quedan sin notificación hasta que exista el motor de alertas |
| **Adjuntar archivos a tareas y observaciones**: módulo `attachments`, integración con almacenamiento (S3 / MinIO / disco) | Todas | ❌ | Requiere decisión de infraestructura de almacenamiento antes de implementar |
| **Vista cuadrícula / grid de tareas** (estilo Microsoft Planner con tarjetas en cuadrícula en lugar de columnas): nuevo modo de visualización en el workspace, togglable | Planner | ❌ | Independiente del backend. Solo requiere nuevo componente Angular y el botón para cambiar de vista |
| **Bug: tablero se desborda con >4 columnas** (la última columna se corta): el contenedor usa `overflow-x-auto` y cada columna tiene `w-72 shrink-0`; revisar el wrapping del contenedor padre | Todas | 🟡 | Probable fix de 1–2 líneas de CSS en `project-workspace.component.ts` (línea 167). Verificar en pantallas <1400px con 4+ columnas |
| **Cierre de sprint + redistribución de tareas incompletas**: wizard que al cerrar un sprint mueva las tareas `status != done` al backlog o al siguiente sprint | Scrum | 🟡 | El endpoint de cierre existe (`PATCH /sprints/{id}` cambia `status` a `closed`). Falta: lógica de redistribución en `SprintService.update_sprint()` y UI de wizard en el frontend |
| **Vista de sprints como cuadrícula de tiempo** (tipo Jira roadmap / línea de tiempo): pestaña nueva o modo adicional en la pestaña Sprints | Scrum | ❌ | Requiere nuevo componente Angular. El backend ya retorna `start_date` y `end_date` por sprint |
| **Velocity** (puntos completados/done por sprint, por equipo, promedio, proyección de backlog): nuevo endpoint `GET /projects/{id}/velocity` que agrega `estimation_points` de tareas completadas por sprint | Scrum | ❌ | Requiere nuevo método en `SprintService` o en `DashboardService`. El campo `completed_at` en tareas ya permite calcularlo. Depende de cierre de sprint correcto |
| **Motor de alertas** (reglas configurables + APScheduler + canales in-app/email + cruce con trabajo real): módulo nuevo `alerts` con `AlertRule`, `AlertNotification`, scheduler, WebSocket | Todas | ❌ | El gap mayor del sistema. Depende de varios módulos aún no creados: `comments` para menciones, `activity_log` para cruce de tiempo real. Es una capa horizontal independiente de las metodologías, pero las reglas de alerta varían por metodología (ej: sprints en Scrum) |

---

## 6. Resumen de gaps priorizados

### (a) Base del modelo de tarea

Estos gaps son universales y bloquean características que trascienden cualquier metodología:

1. **`task_code` incremental por proyecto** — sin esto no hay URL canónica de tarea ni identidad estable para citar en comentarios, PRs o notificaciones. Implica migración Alembic + secuencia PostgreSQL + cambio en `TaskService` y `TaskRead`.
2. **Servicio de subtareas** — el modelo tiene `parent_task_id` pero el servicio y los endpoints no lo usan. No hay validación de profundidad máxima ni de subtareas circulares. La decisión de si las subtareas llevan estimación propia está pendiente.
3. **Módulo `labels`** — falta tabla, FK en `tasks`, endpoints y UI. Bloquea filtrado por etiqueta en el backlog.
4. **Módulo `comments`** — bloquea observaciones con @menciones y la columna de actividad del modal.
5. **Módulo `attachments`** — requiere decisión de almacenamiento (S3 / MinIO).
6. **Dependencias entre tareas** (`blocks` / `is_blocked_by`) — sin esto Scrum no puede representar el grafo de dependencias de un sprint.

### (b) UI / tablero

1. **Bug de desbordamiento con >4 columnas** — CSS en `project-workspace.component.ts` (línea 167). Prioridad alta porque bloquea Scrum (4 columnas) y cualquier Kanban con más columnas.
2. **Vista cuadrícula para Planner** — nuevo modo de visualización; bajo costo relativo (solo frontend).
3. **WIP limits en Kanban** — requiere campo `wip_limit` en modelo de columna (que aún no existe como tabla propia) y enforcement en el servicio.
4. **UI para columnas Custom** — requiere crear tabla `board_columns`, endpoints CRUD y formulario en el workspace. Es la precondición para que la metodología Custom sea usable.
5. **UI de subtareas** (anidado en modal) — depende del gap (a.2).
6. **UI de riesgo desde el tablero** — pequeño; el campo existe, falta solo el control en `task-card.component.ts`.

### (c) Sprints / métricas

1. **Velocity** — endpoint nuevo y panel en la pestaña Sprints. Depende de que el cierre de sprint sea correcto.
2. **Wizard de cierre de sprint** — lógica de redistribución de tareas incompletas. Prioridad media-alta para Scrum.
3. **Vista cuadrícula de tiempo de sprints** — cosmética pero diferenciadora; bajo riesgo de implementación.
4. **Validación Fibonacci en story points** — pequeña adición en `TaskService._validate_estimation()`.
5. **Página de dashboard en frontend** — los datos existen en `DashboardService.executive()` y `performance()`; falta el componente Angular y la ruta.

### (d) Alertas / notificaciones

Este bloque es el de mayor superficie y está completamente sin implementar:

1. **Módulo `alerts`** — `AlertRule` (reglas configurables), `AlertNotification` (log de notificaciones generadas), estrategias por tipo de alerta.
2. **Scheduler** (APScheduler / Celery Beat) — job periódico que evalúa reglas. Redis ya está aprovisionado (`docker-compose`) pero no se usa.
3. **WebSocket / push** — para notificaciones en tiempo real.
4. **Email digest** — configurable por usuario.
5. **Módulo `activity_log`** — necesario para el cruce de trabajo real vs. tareas asignadas (alerta de discrepancia).

**Dependencias críticas entre ítems:**

```
task_code ──────────────────────────────────► comments (citar tareas en comentarios)
parent_task_id (modelo) ──► servicio subtareas ──► UI subtareas
board_columns (tabla) ──────────────────────────► Custom methodology usable
sprint closure (correcto) ──► velocity ──────────► proyección de backlog
comments ──────────────────► motor de alertas (@menciones)
activity_log ──────────────► motor de alertas (cruce trabajo real)
```

---

## Apéndice: resumen rápido por metodología

| Metodología | Funcional como MVP | Gaps bloqueantes |
|-------------|:---:|-----------------|
| **Planner** | 🟡 Parcial | Vista grid, código incremental, comentarios |
| **Kanban** | 🟡 Parcial | WIP limits, columnas configurables en runtime |
| **Scrum** | 🟡 Parcial | Velocity, wizard cierre sprint, validación Fibonacci |
| **Custom** | ❌ No usable | Toda la capa de configuración de columnas/estados |

El núcleo común que bloquea las 4 metodologías es la tríada:
**código incremental + comentarios + adjuntos**. Implementar estas tres
capacidades en el modelo de tarea desbloquea el 80 % de las peticiones
pendientes del usuario.
