"""Planner methodology: simple checklist-style board, no sprints or backlog."""

from app.methodology.base import MethodologyStrategy
from app.shared.enums import EstimationMode

_COLUMNS = ["Sin iniciar", "En curso", "Completada"]


class PlannerStrategy(MethodologyStrategy):
    """Lightweight planner with three linear states and no estimation."""

    name = "planner"

    def default_columns(self) -> list[str]:
        return list(_COLUMNS)

    def allowed_statuses(self) -> list[str]:
        return list(_COLUMNS)

    @property
    def sprints_enabled(self) -> bool:
        return False

    @property
    def estimation_mode(self) -> str:
        return EstimationMode.none.value

    @property
    def has_backlog(self) -> bool:
        return False
