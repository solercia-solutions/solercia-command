"""Kanban methodology: flow-based board with optional hour estimates."""

from app.methodology.base import MethodologyStrategy
from app.shared.enums import EstimationMode

_COLUMNS = ["Backlog", "Doing", "Done"]


class KanbanStrategy(MethodologyStrategy):
    """Continuous-flow board without sprints; estimation in hours is optional."""

    name = "kanban"

    def default_columns(self) -> list[str]:
        return list(_COLUMNS)

    def allowed_statuses(self) -> list[str]:
        return list(_COLUMNS)

    @property
    def sprints_enabled(self) -> bool:
        return False

    @property
    def estimation_mode(self) -> str:
        return EstimationMode.hours.value

    @property
    def has_backlog(self) -> bool:
        return False
