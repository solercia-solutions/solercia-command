# ADR 0005 — El estado de la tarea es su columna del tablero

- **Estado:** Aceptado
- **Fecha:** 2026-06-27
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (secciones 7, 8 y 9), `docs/API.md` (Tareas y
  Sprints), `docs/adr/0002-configurable-methodology-strategy.md`

---

## Contexto

Esta fase incorpora las **tareas** (work items) y los **sprints**, y con ellos el tablero
operativo del proyecto. Un tablero tipo Jira/Planner muestra columnas y tarjetas que se
arrastran entre columnas. La pregunta de diseño es **cómo modelar las columnas y el estado**
de una tarea.

El enfoque tradicional crea una tabla `board` y una tabla `column` por proyecto, y la tarea
guarda un `column_id` (FK). Eso implica:

- Sembrar columnas al crear cada proyecto y mantenerlas sincronizadas con la metodología.
- Una FK `task.column_id` que hay que resolver para saber «en qué estado está» la tarea.
- Lógica para reordenar, renombrar y migrar columnas, más una fuente de verdad **duplicada**:
  las columnas viven a la vez en la metodología (Strategy) y en la base de datos.

Pero en Solercia PM las columnas **ya están definidas** por la metodología del proyecto a
través del patrón Strategy (ADR 0002). Cada Strategy expone `allowed_statuses()`, que **es la
misma lista** que `default_columns()`:

```python
class ScrumStrategy(MethodologyStrategy):
    name = "scrum"

    def default_columns(self) -> list[str]:
        return ["To Do", "In Progress", "In Review", "Done"]

    def allowed_statuses(self) -> list[str]:
        # The board columns ARE the allowed statuses.
        return ["To Do", "In Progress", "In Review", "Done"]
```

Tener una tabla `column` además de esto duplicaría una información que la Strategy ya posee
como única fuente de verdad.

## Decisión

**No** hay tabla `board` ni `column`. Las **columnas del tablero son los
`allowed_statuses` de la Strategy**, y el **estado de una tarea es su columna**.

1. `Task.status` es un **string** (no un enum global). Se valida en la **capa de service**
   contra `get_strategy(project.methodology).allowed_statuses()`.
2. El **estado por defecto** de una tarea nueva es `allowed_statuses[0]` (la primera columna).
3. **Mover una tarjeta** de columna es `PATCH /tasks/{id}` con un `status` perteneciente a
   `allowed_statuses`. El orden dentro de la columna se persiste en `task.order`.
4. El enum `TaskStatus` de `app/shared/enums.py` **no** gobierna `Task.status`. Existe como
   vocabulario genérico, pero los estados reales los dicta la Strategy por proyecto
   (`Backlog | Doing | Done` en kanban, `Sin iniciar | En curso | Completada` en planner).

```python
class TaskService:
    async def create(self, project: Project, data: TaskCreate) -> Task:
        strategy = get_strategy(project.methodology)
        allowed = strategy.allowed_statuses()

        status = data.status or (allowed[0] if allowed else None)
        if status not in allowed:
            raise AppException(
                f"El estado «{status}» no es válido para este proyecto. "
                f"Estados permitidos: {', '.join(allowed)}.",
                code="invalid_task_status",
                status_code=422,
            )
        # ... persist with validated status
```

### Una sola persona asignada (`assignee_id`), no M:N

Una tarea referencia **a lo sumo una** persona mediante `assignee_id` (FK nullable a
`users`). Se descarta, para esta fase, una relación muchos-a-muchos (tabla
`task_assignees`).

- **A favor del `assignee_id` único:** modela la pregunta operativa del MVP —«¿quién es
  responsable de esto?»—, simplifica la vista ejecutiva (`by_assignee`, `workload`) y evita
  una tabla puente y sus *joins*. Reasignar es `PATCH` con otro `assignee_id`; desasignar es
  `null`.
- **Costo:** no se puede registrar colaboración formal de varias personas en una tarea. Si
  el producto lo requiere, se añade después una tabla `task_assignees` sin romper el contrato
  actual: `assignee_id` puede conservarse como «responsable principal» y la M:N como
  colaboradores.

### Backlog y sprints

- El **backlog no es una tabla aparte**: es el conjunto de tareas del proyecto con
  `sprint_id = null`. «Mover al sprint» es asignar `sprint_id`; «devolver al backlog» es
  ponerlo en `null`. Esto evita duplicar las tareas en dos almacenes.
- Los **sprints** (`status: active | closed`) solo existen cuando la Strategy declara
  `sprints_enabled = true` (scrum). El service rechaza crear sprints en metodologías que no
  los habilitan, manteniendo la coherencia con `methodology_info`.

## Consecuencias

### Positivas

- **Una sola fuente de verdad:** las columnas y los estados viven únicamente en la Strategy;
  no hay que sincronizar una tabla `column` con la metodología.
- **Menos esquema y menos *joins*:** sin tablas `board`/`column` ni `task_assignees`; el
  tablero se arma con un `GROUP BY status` sobre `allowed_statuses`.
- **Abierto/cerrado heredado de la Strategy:** una metodología nueva define sus columnas en
  su Strategy y el tablero funciona sin tocar el modelo de datos.
- **Frontend simple:** el tablero se deriva de `methodology_info.allowed_statuses` (ver ADR
  0006); mover una tarjeta es un `PATCH` de `status`.

### Negativas / costos

- **Validación en el service, no en la base de datos:** al ser texto libre, la integridad de
  `status` depende de la capa de service. Se mitiga centralizando esa validación contra
  `allowed_statuses` y cubriéndola con pruebas.
- **Metodología `custom`:** su Strategy devuelve `allowed_statuses` vacío, por lo que un
  proyecto custom no tiene columnas hasta que la persona usuaria las defina. La
  parametrización del tablero para `custom` queda **fuera del alcance** de esta fase; el
  contrato de la Strategy ya reserva ese punto de extensión.
- **Renombrar una columna en la Strategy** dejaría tareas con el `status` antiguo. Mientras
  las columnas sean fijas por código no ocurre; cuando `custom` sea parametrizable se
  necesitará una migración de estados, decisión que se registrará en su momento.
- **Un solo responsable por tarea** hasta que el producto justifique la M:N (ver arriba).

## Alternativas descartadas

- **Tablas `board` + `column` con `task.column_id`:** rechazada por duplicar la fuente de
  verdad (la metodología ya define las columnas) y por añadir esquema y sincronización sin
  beneficio en el MVP.
- **`Task.status` como enum global (`TaskStatus`):** rechazada porque obligaría a que todas
  las metodologías compartieran el mismo conjunto de estados, rompiendo la premisa de que
  cada metodología define su propio tablero.
- **Relación M:N de asignación desde el MVP:** aplazada por complejidad innecesaria frente a
  la pregunta operativa actual; el diseño permite incorporarla luego sin ruptura.
