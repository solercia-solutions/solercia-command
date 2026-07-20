# Design: 35 · Avance esperado vs. real (semáforo, tendencia y refuerzo)

## Technical Approach

Módulo nuevo Screaming `app/modules/progress/` (`models`, `schemas`, `repository`,
`service`, `router`). `ProgressService` calcula la tarjeta "hoy" on-demand reusando
`WorkCalendarResolver.resolve` (28) para los días laborales, `TaskRepository` para
las tareas y `ProjectRepository._subtree_ids_select` (CTE existente) para acotar el
subárbol; `project_kind` (27) marca las áreas (raíces `area`). Un job semanal del
scheduler APScheduler existente persiste `project_progress_snapshot`, fuente de la
tendencia de 4 semanas. El refuerzo es una `AlertStrategy` nueva registrada en
`_STRATEGIES`, evaluada por el job horario actual. El front consume `/progress/*`
desde un `entities/progress/` nuevo; `dashboard.service` no se toca. **Requiere 27 y
28 aplicados** (head real en disco = 0020).

## Architecture Decisions

### D1: Fórmula del esperado — escalón por due date + fallback lineal en días laborales

`weight(task) = estimation_hours or 1`. Dos vías, una sola suma:

```
total       = Σ weight(t)                             # tareas activas del proyecto
exp_dated   = Σ weight(t)  para  t.due_date.date() <= today       # escalón
# tareas SIN due_date: reparto lineal sobre los días laborales del rango del proyecto
range       = [min(start_date|created_at), max(due_date | today)]
frac        = working_days(range.start → min(today, range.end)) / working_days(range)   # 28
exp_undated = frac · Σ weight(t sin due)
expected_pct = round((exp_dated + exp_undated) / total · 100)
real_pct     = round(Σ weight(t con completed_at) / total · 100)
deviation    = expected_pct − real_pct                # + = retrasado
```

| Opción | Tradeoff | Decisión |
|---|---|---|
| **Escalón por due date + lineal (días laborales) para las sin fecha** | Determinista, testeable por conjuntos; usa el calendario del 28 sólo donde aporta | **Elegida** |
| Acumulado puro `Σ due≤t / Σ total` | No modela tareas sin due; ignora el calendario | Rechazada |
| Proporcional por días transcurridos "en curso" | Depende de estados intermedios ambiguos entre metodologías | Rechazada |

Ejemplo (`today=2026-07-20`; 8h, L–V): T1(10h, due 07-10, done), T2(6h, due 07-15),
T3(4h, due 07-31), T4(sin horas, sin due). `total=21`; `exp_dated=T1+T2=16` (T3 futura
no cuenta); T4 lineal `frac≈0.61` → `exp_undated≈0.61`; `expected≈16.6/21=79%`.
`real=10/21=48%`. `deviation=31%` → **rojo** (>15%).

### D2: Snapshots semanales como fuente de la tendencia

Tabla `project_progress_snapshot(id, organization_id, project_id, week_start Date,
expected_pct, real_pct, deviation, created_at)`, `UNIQUE(project_id, week_start)`
(`week_start` = lunes ISO; reemplaza el `captured_week` tentativo de state.yaml). Job
`project_progress_snapshot` con `CronTrigger(day_of_week="mon")` añadido en
`start_scheduler` (ancla estable, sin drift del `IntervalTrigger`); upsert por semana
ISO de cada proyecto de cada org activa. Backfill on-demand **sólo del real**
(reconstruible por `completed_at`); el esperado histórico queda "sin dato" (no
revisionista). Tendencia = últimas 4 filas; semanas faltantes = gap.

### D3: Rollup por CTE de scoping + agregación en Python

Reusa `_subtree_ids_select` (CTE existente) para acotar el subárbol, carga esas tareas
y agrega los pesos en Python como **una sola bolsa del área** (NO promedio de
porcentajes por proyecto). El CTE aporta el scoping; Python la métrica, porque la
fórmula (días laborales + resolución de calendario) no es SQL puro — mismo reparto que
el 28. Áreas = raíces con `project_kind == area`.

### D4: Endpoints (envelope `{data, message, meta}`)

| Endpoint | Rol | Notas |
|---|---|---|
| `GET /progress/projects?project_kind=&rollup=subtree&project_id=` | miembro | tarjetas hoy + tendencia; `rollup=subtree` agrega el área |
| `GET /progress/monthly-report?month=YYYY-MM&area_id=` | miembro | corte mensual por área (llega / necesita refuerzo / adelantado) |
| `GET/PUT /organizations/me/progress-thresholds` | GET miembro / PUT `require_admin` | umbrales verde/amarillo |

### D5: Refuerzo como `AlertStrategy` nueva

`ProjectReinforcementStrategy(rule_type="project_reinforcement")` en `_STRATEGIES` +
fila en `_DEFAULT_ALERT_RULES` (`{"min_deviation": null}` → usa el umbral rojo de la
empresa). `evaluate` recorre proyectos activos, computa la tarjeta y, si
`deviation > umbral`, emite `AlertCandidate`. Horas: `N = (expected_fin_semana −
real_actual) · total_hours / 100`; sin horas estimadas, `N` se expresa en tareas.
Destinatarios: `lead_user_id` si existe, si no los admin. `dedup_key =
project_reinforcement:{project_id}:{iso_week}:{recipient}` (una vez por
semana/proyecto/persona, como `sprint_at_risk`). Texto (es-CO formal, tuteo): título
"Refuerzo sugerido en {proyecto}", cuerpo "El proyecto va {deviation}% por debajo de
lo esperado; refuerza cerca de {N} horas esta semana para ponerte al día."

### D6: UI — el front consume `/progress`, dashboard intacto

`entities/progress/{model,service}.ts` nuevo; widget `widgets/progress-cards/`
(semáforo + sparkline/lista de 4 semanas) en `pages/executive`; corte mensual como
página `pages/progress-report`. `dashboard.service` y `/dashboard/executive` no
cambian (menor blast radius; segunda llamada lazy del front). Umbrales de empresa como
dos columnas `Numeric` en `organizations` (patrón aditivo de `theme`), default 5/15.

## Data Flow

```
GET /progress/projects
   │  ProjectRepo._subtree_ids_select  (scoping subárbol/área)
   ▼
ProgressService.card(project | subtree)
   ├─ TaskRepository.list            (tareas activas)
   ├─ WorkCalendarResolver.resolve   (días laborales)      ← 28
   └─ SnapshotRepository.last_4      (tendencia)
        │
        ▼  expected / real / deviation / semaphore / trend / reinforcement_hours

scheduler ── weekly (CronTrigger lun) ─▶ upsert project_progress_snapshot
          └─ hourly (existente) ───────▶ ProjectReinforcementStrategy.evaluate ─▶ Notification (dedup)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `app/modules/progress/{__init__,models,schemas,repository,service,router}.py` | Create | ProgressService, SnapshotRepository, ProgressCard, modelo snapshot, endpoints |
| `app/modules/organizations/models.py` | Modify | + `threshold_green_pct`, `threshold_amber_pct` (Numeric, NOT NULL, default 5/15) |
| `app/modules/organizations/{schemas,router}.py` | Modify | GET/PUT `/organizations/me/progress-thresholds` |
| `app/alerts/strategies/project_reinforcement.py` | Create | `ProjectReinforcementStrategy` |
| `app/alerts/registry.py` | Modify | registrar `project_reinforcement` |
| `app/alerts/scheduler.py` | Modify | + job semanal de snapshots (`CronTrigger` lunes) |
| `app/db_init.py` | Modify | + fila `project_reinforcement` en `_DEFAULT_ALERT_RULES` |
| `app/main.py` | Modify | registrar router `progress` |
| `alembic/versions/00XXa_add_progress_thresholds.py` | Create | columnas umbral en `organizations` (aditiva) |
| `alembic/versions/00XXb_add_project_progress_snapshot.py` | Create | tabla snapshot + UNIQUE |
| `frontend/src/entities/progress/{progress.model,progress.service}.ts` | Create | cliente `/progress` |
| `frontend/src/widgets/progress-cards/*`, `pages/executive/*`, `pages/progress-report/*` | Create/Modify | tarjetas semáforo + tendencia; corte mensual |
| `backend/tests/**` | Create | contratos TDD fórmula/snapshot/rollup/alerta/permisos/migración |

## Interfaces / Contracts

```python
class Semaphore(str, Enum):
    green = "green"; amber = "amber"; red = "red"

class TrendPoint(BaseModel):
    week_start: date; expected_pct: Decimal; real_pct: Decimal

class ProgressCard(BaseModel):
    project: ProjectRef                       # id, name, project_kind, methodology
    expected_pct: Decimal; real_pct: Decimal; deviation: Decimal
    semaphore: Semaphore
    trend: list[TrendPoint]                   # <= 4; huecos = sin dato
    reinforcement_hours: Decimal | None

class ProgressThresholds(BaseModel):          # PUT body
    green_max_pct: Decimal = Field(ge=0, le=100)   # default 5
    amber_max_pct: Decimal = Field(ge=0, le=100)   # default 15; validator: > green_max_pct

class ProgressService:
    async def card(org_id, project_id, *, rollup=False) -> ProgressCard
    async def list_cards(org_id, *, project_kind=None) -> list[ProgressCard]
    async def snapshot_week(org_id) -> int    # job semanal: upsert por semana ISO
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | expected: escalón `due<=today`; fallback lineal en días laborales; real ponderado horas vs conteo; deviation; semáforo por umbral | `ProgressService` con calendario fijo |
| Unit | `ProgressThresholds`: 0–100, `amber>green` | validación Pydantic |
| Integration | rollup subárbol = bolsa de tareas del área; áreas por `project_kind` | fixtures árbol (27) |
| Integration | snapshot upsert por semana ISO; tendencia 4 filas; backfill real; esperado histórico "sin dato" | job + repo |
| Integration | alerta refuerzo: dispara sobre umbral, horas `N`, dedup week/proyecto/persona; destinatario lead→admin | `evaluator` |
| Integration | permisos: GET abierto; PUT thresholds ADMIN (403 otros) | `client` |
| Migration | upgrade añade columnas + tabla; downgrade elimina; reversible | Alembic up/down |
| Regresión | scoping multi-tenant; `/dashboard/executive` intacto; suite verde | suite completa |

## Threat Matrix

N/A — sin routing dinámico, shell, subprocesos, automatización VCS/PR, clasificación
de ejecutables ni integración de procesos. El job semanal es interno a APScheduler
(mismo proceso), no shell. El riesgo es de dominio (fórmula del esperado, ruido de la
alerta), mitigado en D1 (determinismo) y D5 (dedup semanal + umbral configurable).

## Migration / Rollout

Dos migraciones aditivas y reversibles encadenadas tras el head real (cadena esperada
27→…→28→este; head en disco `0020`). **(a)** `threshold_green_pct`/`threshold_amber_pct`
`NOT NULL server_default` 5/15 → backfill implícito, luego retira el `server_default`.
**(b)** tabla `project_progress_snapshot` + `UNIQUE(project_id, week_start)`. El
`down_revision` se **reancla a `alembic current`** en apply (patrón 27/28). `downgrade`
elimina columnas y tabla; sin pérdida de datos preexistentes; la vista ejecutiva vuelve
al `percent_done` actual.

## Open Questions

- [ ] Destinatarios del refuerzo: default `lead_user_id` → admin (segunda ronda del proposal). No bloqueante.
- [ ] Orden de aplicación: 27 y 28 deben estar aplicados antes; fijar `down_revision` al head real. No bloqueante.
