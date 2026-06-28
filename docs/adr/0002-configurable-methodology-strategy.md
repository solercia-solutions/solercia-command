# ADR 0002 — Metodología configurable por proyecto con patrón Strategy

- **Estado:** Aceptado
- **Fecha:** 2026-06-26
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (sección 4), `docs/API.md` (POST `/projects`)

---

## Contexto

Cada proyecto en Solercia PM trabaja con una **metodología** distinta:
`planner`, `kanban`, `scrum` o `custom`. La metodología no es solo una etiqueta: gobierna el
comportamiento del proyecto en varios ejes:

| Atributo           | Significado                                                       |
| ------------------ | ---------------------------------------------------------------- |
| `board_columns`    | Columnas por defecto del tablero.                                |
| `allowed_statuses` | Estados de tarea permitidos.                                     |
| `sprints_enabled`  | Si la metodología habilita sprints.                              |
| `estimation_mode`  | Modo de estimación (`none`, `hours`, `story_points`, …).         |
| `has_backlog`      | Si la metodología expone un backlog.                             |

Una persona usuaria elige la metodología al **crear el proyecto**, y a partir de ahí el
sistema debe comportarse en consecuencia: qué columnas mostrar, qué transiciones permitir,
si ofrecer sprints, cómo estimar y si hay backlog.

El problema de diseño es **dónde** vive ese comportamiento. La tentación es resolverlo con
condicionales dispersos:

```python
# Anti-patrón: lógica de metodología regada por el código
def default_columns(methodology: str) -> list[str]:
    if methodology == "kanban":
        return ["To Do", "In Progress", "Done"]
    elif methodology == "scrum":
        return ["Backlog", "To Do", "In Progress", "Review", "Done"]
    elif methodology == "planner":
        return ["Not started", "In progress", "Completed"]
    # ... y este mismo if se repite para sprints, estimación, backlog, estados...
```

Ese enfoque produce el mismo `if methodology == ...` repetido en múltiples lugares
(columnas, sprints, estimación, estados, backlog). Cada metodología nueva obliga a tocar
todos esos puntos, y es fácil olvidar uno. Es frágil, difícil de probar y viola el principio
abierto/cerrado.

## Decisión

Encapsulamos el comportamiento de cada metodología en una **Strategy**: una clase por
metodología que expone el mismo contrato, seleccionada por proyecto a través de una
**factory**.

```python
from dataclasses import dataclass
from enum import Enum


class Methodology(str, Enum):
    PLANNER = "planner"
    KANBAN = "kanban"
    SCRUM = "scrum"
    CUSTOM = "custom"


@dataclass(frozen=True)
class MethodologyProfile:
    board_columns: list[str]
    allowed_statuses: list[str]
    sprints_enabled: bool
    estimation_mode: str   # "none" | "hours" | "story_points"
    has_backlog: bool


class MethodologyStrategy:
    """Contract every methodology must satisfy."""

    def profile(self) -> MethodologyProfile:
        raise NotImplementedError


class ScrumStrategy(MethodologyStrategy):
    def profile(self) -> MethodologyProfile:
        return MethodologyProfile(
            board_columns=["Backlog", "To Do", "In Progress", "Review", "Done"],
            allowed_statuses=["todo", "in_progress", "review", "done"],
            sprints_enabled=True,
            estimation_mode="story_points",
            has_backlog=True,
        )


class KanbanStrategy(MethodologyStrategy):
    def profile(self) -> MethodologyProfile:
        return MethodologyProfile(
            board_columns=["To Do", "In Progress", "Done"],
            allowed_statuses=["todo", "in_progress", "done"],
            sprints_enabled=False,
            estimation_mode="none",
            has_backlog=False,
        )


class PlannerStrategy(MethodologyStrategy):
    def profile(self) -> MethodologyProfile:
        return MethodologyProfile(
            board_columns=["Not started", "In progress", "Completed"],
            allowed_statuses=["not_started", "in_progress", "completed"],
            sprints_enabled=False,
            estimation_mode="none",
            has_backlog=False,
        )


class CustomStrategy(MethodologyStrategy):
    def profile(self) -> MethodologyProfile:
        return MethodologyProfile(
            board_columns=["To Do", "In Progress", "Done"],
            allowed_statuses=["todo", "in_progress", "done"],
            sprints_enabled=True,
            estimation_mode="hours",
            has_backlog=True,
        )


_REGISTRY: dict[Methodology, MethodologyStrategy] = {
    Methodology.PLANNER: PlannerStrategy(),
    Methodology.KANBAN: KanbanStrategy(),
    Methodology.SCRUM: ScrumStrategy(),
    Methodology.CUSTOM: CustomStrategy(),
}


def strategy_for(methodology: Methodology) -> MethodologyStrategy:
    """Factory: resolve the Strategy for a given methodology."""
    return _REGISTRY[methodology]
```

El service consume la Strategy sin conocer condicionales de metodología:

```python
class ProjectService:
    def __init__(self, repo: ProjectRepository) -> None:
        self._repo = repo

    async def create(
        self, data: ProjectCreate, organization_id: UUID
    ) -> Project:
        strategy = strategy_for(data.methodology)   # one lookup, no if-chains
        profile = strategy.profile()
        project = Project(
            name=data.name,
            description=data.description,
            methodology=data.methodology,
            status="active",
            organization_id=organization_id,
        )
        # profile.board_columns / sprints_enabled / estimation_mode / has_backlog
        # drive board bootstrap and downstream behavior.
        return await self._repo.add(project)
```

## Por qué no condicionales dispersos

- **Open/Closed:** agregar una metodología nueva es crear una clase Strategy y registrarla
  en la factory; **no** se modifica el `ProjectService` ni ningún `if` existente.
- **Un único lugar de verdad por metodología:** todo el comportamiento de `scrum` vive en
  `ScrumStrategy`. No hay que cazar cinco `if methodology == "scrum"` repartidos.
- **Testeabilidad:** cada Strategy se prueba de forma aislada por su contrato; el service se
  prueba con una Strategy de prueba inyectada.
- **Cohesión y legibilidad:** el contrato (`MethodologyProfile`) declara explícitamente los
  ejes de variación, evitando que el comportamiento quede implícito en condicionales.

## Consecuencias

### Positivas

- Extensión sin modificación: nuevas metodologías sin tocar la lógica existente.
- Comportamiento de cada metodología centralizado y autodocumentado.
- Reglas de negocio (columnas, estados, sprints, estimación, backlog) probables por unidad.

### Negativas / costos

- **Más clases y archivos** que un puñado de `if`. Para cuatro metodologías el costo es
  bajo y se amortiza al crecer.
- **Indirección:** entender el comportamiento exige abrir la Strategy correspondiente. Lo
  compensa que el contrato `MethodologyProfile` es explícito.
- La metodología `custom` necesitará, fuera del MVP, una forma de **parametrizar** su perfil
  (columnas y estados definidos por la persona usuaria) en lugar de valores fijos; la
  Strategy ya reserva ese punto de extensión.

## Alternativas descartadas

- **Cadenas de `if/elif` o `match` dispersas:** rechazadas por violar open/closed y dispersar
  el comportamiento (ver Contexto).
- **Tabla de configuración pura en base de datos sin Strategy:** flexible, pero mueve toda la
  lógica a datos y complica validación y pruebas en el MVP. Se considerará para `custom`
  parametrizable más adelante, apoyada en el mismo contrato de Strategy.
