# ADR 0007 — Burndown del sprint y métricas de rendimiento por colaborador

- **Estado:** Aceptado
- **Fecha:** 2026-06-27
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (secciones 7, 8 «Sprints y burndown» y 9
  «Rendimiento por colaborador»), `docs/API.md` (Sprints → burndown, Vista ejecutiva →
  performance), `docs/adr/0003-mvp-schema-bootstrap.md`,
  `docs/adr/0005-work-items-status-as-column.md`

---

## Contexto

Esta fase agrega dos vistas analíticas sobre el trabajo ya modelado:

1. El **burndown** de un sprint: cuánto alcance queda por terminar día a día, contra un
   ritmo ideal de referencia.
2. El **rendimiento por colaborador**: cuántas tareas y puntos cierra cada persona, cuánta
   carga viva tiene y qué tan a tiempo entrega.

Ambas vistas necesitan saber **cuándo** se terminó cada tarea, no solo **si** está terminada.
El modelo actual solo guarda el `status` vigente (la columna del tablero); no hay rastro del
instante en que una tarea entró a la columna «done». Reconstruir el burndown exige justamente
ese instante: sin él, no se puede ubicar el «trabajo completado hasta el día _d_».

La tentación es introducir una **tabla de historial de eventos** (`task_events`,
`status_transitions`) que registre cada cambio de columna con su marca de tiempo. Es potente,
pero para el alcance actual —una sola línea real de burndown y un puñado de métricas— es
infraestructura desproporcionada: nueva tabla, nuevas escrituras en cada `PATCH`, nuevas
consultas de agregación y un costo de mantenimiento permanente.

Surge además una pregunta de esquema: agregar `completed_at` a `tasks` es una **columna
nueva**. ¿Se necesita una migración Alembic?

## Decisión

### 1. `completed_at` como evento mínimo

Se agrega a `tasks` un único campo nullable `completed_at` (`timestamptz`) y se gestiona en el
**service**, no en el cliente:

```python
# In TaskService.update_task, after resolving the new status:
DONE = strategy.allowed_statuses()[-1]  # the last column IS "done" (ADR 0005)

was_done = task.status == DONE
now_done = new_status == DONE

if now_done and not was_done:
    task.completed_at = datetime.now(timezone.utc)   # entered the done column
elif was_done and not now_done:
    task.completed_at = None                          # moved back out of done
```

`completed_at` es el **dato mínimo** que permite reconstruir el burndown y el rendimiento: con
una sola marca de tiempo por tarea se responde «¿qué trabajo estaba terminado al cierre del día
_d_?» (`completed_at.date() <= d`) sin un historial de transiciones aparte. Se apoya en la
regla de oro del ADR 0005: «done» es siempre `allowed_statuses[-1]`, así que el evento de
completar es coherente entre metodologías y no introduce un concepto nuevo de «terminado».

Es de **solo lectura** en el contrato: no se acepta en `POST` ni en `PATCH`; lo fija y lo
limpia exclusivamente el backend al mover la tarea dentro o fuera de la columna «done».

### 2. Línea ideal lineal

El burndown contrasta dos series por día del rango `[start_date, end_date]` del sprint:

- **`ideal`** — descenso **lineal** de `total` (en `start_date`) a `0` (en `end_date`). Es una
  recta de referencia, independiente de los datos reales.
- **`actual`** — `total` menos el trabajo completado con `completed_at.date() <= d`. **No** se
  proyecta al futuro: `actual = null` para días posteriores a hoy.

```python
# Ideal is a straight reference line; index i = 0 on the start date.
# With N days inclusive, ideal[i] = total * (1 - i / (N - 1)).
def ideal_at(i: int, total: float, n_days: int) -> float:
    if n_days <= 1:
        return 0.0
    return round(total * (1 - i / (n_days - 1)), 1)
```

La unidad del alcance se deriva de la metodología (no se codifica por nombre): `unit = "points"`
cuando `estimation_mode` incluye puntos (`points` o `both`), `"tasks"` en caso contrario. En
modo puntos, `total` es la suma de `estimation_points` (las tareas sin puntos aportan `0`); en
modo tareas, `total` es el conteo de tareas del sprint.

### 3. Fórmulas de rendimiento

Por cada colaborador del tenant (acotable a un sprint con `?sprint_id`):

```
completed_tasks  = tareas asignadas con status == allowed_statuses[-1]   (en «done»)
completed_points = Σ estimation_points de esas tareas terminadas         (sin puntos => 0)
active_count     = tareas asignadas con status != allowed_statuses[-1]   (carga viva)
overdue_count    = tareas asignadas no terminadas con due_date < now

# on_time_rate: solo tareas TERMINADAS que tenían due_date.
denominador = terminadas de la persona con due_date != null
numerador   = de esas, las que cumplieron completed_at.date() <= due_date.date()
on_time_rate = numerador / denominador        (0..1; 0 cuando denominador == 0)
```

`on_time_rate` excluye a propósito las tareas sin `due_date` (no se puede juzgar puntualidad sin
plazo) y las aún sin terminar (todavía no hay desenlace), para que la tasa compare manzanas con
manzanas entre personas.

### 4. Gráfica SVG sin librería

El frontend dibuja el burndown con **SVG nativo, sin librería de gráficas** (sin Chart.js,
D3, ApexCharts ni equivalentes). El endpoint ya entrega los puntos `{ date, ideal, actual }`
listos para mapear a coordenadas; trazar dos `polyline` y unos ejes es código corto y
predecible.

```html
<!-- Two polylines over a fixed viewBox; the API already returns plottable points. -->
<svg viewBox="0 0 320 180" role="img" aria-label="Burndown del sprint">
  <polyline class="burndown-ideal"  points="..." fill="none" />
  <polyline class="burndown-actual" points="..." fill="none" />
</svg>
```

La motivación es de **mantenibilidad y costo**: se evita una dependencia pesada (y su
versionado, su tamaño de bundle y su superficie de seguridad) para una sola gráfica de dos
líneas. Si en el futuro aparecen múltiples gráficas complejas, se reevaluará incorporar una
librería.

### 5. Reseed limpio ahora, Alembic después

La columna `completed_at` se incorpora **sin migración Alembic**. Coherente con el ADR 0003
(«`create_all` + seed idempotente; Alembic diferido»), en esta fase la base se **recrea
limpia** (`docker compose down -v`) y `Base.metadata.create_all` construye el esquema completo,
ya con `completed_at`. El seed de demostración se actualiza para poblar un sprint con tareas
terminadas en distintos días, de modo que el burndown y el rendimiento se vean con datos reales
desde el primer arranque. Las migraciones controladas (Alembic) siguen diferidas hasta salir del
MVP, momento en el que un `ALTER TABLE ... ADD COLUMN completed_at` será el primer cambio
versionado.

## Consecuencias

### Positivas

- **Costo mínimo de esquema:** una sola columna nullable habilita ambas vistas; no hay tabla de
  eventos ni escrituras adicionales por cada `PATCH`.
- **Coherente con la regla de oro:** «done» se sigue derivando de `allowed_statuses[-1]`; el
  burndown y el rendimiento funcionan para cualquier metodología sin condicionales por nombre.
- **Contrato listo para graficar:** el backend entrega series ya calculadas (`ideal`/`actual`,
  `unit`), así que el frontend solo mapea puntos a coordenadas.
- **Sin dependencia de gráficas:** menos bundle, menos versionado, menos superficie que mantener.
- **Arranque demostrable:** con el reseed limpio, el sprint sembrado muestra una línea real que
  baja por debajo de la ideal y métricas de rendimiento variadas sin intervención manual.

### Negativas / costos

- **Sin historial de transiciones:** `completed_at` solo guarda el **último** cruce a «done».
  Si una tarea entra, sale y vuelve a entrar a la columna «done», solo queda la marca más
  reciente. No se pueden reconstruir burndowns de estados intermedios ni auditar el flujo
  completo. Si más adelante se requiere, habrá que introducir la tabla de eventos que aquí se
  evitó.
- **Burndown sensible a `estimation_points`:** en modo puntos, las tareas sin estimar aportan
  `0` al alcance; un sprint mal estimado produce un burndown poco informativo. Es un costo de
  datos, no de diseño.
- **`completed_at` depende del `status` correcto:** si una tarea se marca «done» por error, su
  `completed_at` se fija; al corregirla, se limpia. La métrica es tan buena como la disciplina
  del tablero.
- **SVG manual:** ejes, escalas y accesibilidad (`role`, `aria-label`, claves estables en las
  listas) quedan a cargo del componente, en vez de una librería. Es código propio que hay que
  cuidar, aunque acotado.
- **Migración diferida:** al recrear la base limpia se pierden los datos existentes. Es
  aceptable en el MVP (la decisión del ADR 0003), pero deja de serlo en cuanto haya datos reales:
  ese será el disparador para activar Alembic.

## Alternativas descartadas

- **Tabla de historial de eventos (`task_events`):** rechazada por desproporcionada para el
  alcance actual. Aporta auditoría y burndowns de cualquier estado, pero a cambio de una tabla
  nueva, escrituras en cada transición y agregaciones más caras. Se reconsiderará si surge la
  necesidad de auditoría o de métricas históricas más finas.
- **Calcular «terminado» por un timestamp de `updated_at`:** rechazada porque `updated_at`
  cambia con **cualquier** edición (título, asignación, prioridad), no solo al completar; no
  identifica el evento de cierre.
- **Línea ideal no lineal (por capacidad o por velocidad histórica):** rechazada por ahora; sin
  datos históricos de velocidad, una recta es la referencia más honesta y predecible. Se puede
  refinar cuando existan varios sprints cerrados.
- **Librería de gráficas (Chart.js / D3 / ApexCharts):** rechazada por sobredimensionada para
  dos líneas; agrega peso de bundle y mantenimiento de versión sin beneficio proporcional en
  esta fase.
- **Migración Alembic inmediata para `completed_at`:** rechazada en el MVP por coherencia con el
  ADR 0003; el reseed limpio resuelve el esquema sin el andamiaje de migraciones, que se activa
  al salir del MVP.
</content>
</invoke>
