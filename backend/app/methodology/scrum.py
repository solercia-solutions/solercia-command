"""Scrum methodology: sprint-driven board with story-point estimation."""

from app.methodology.base import MethodologyStrategy
from app.shared.enums import EstimationMode

_COLUMNS = ["To Do", "In Progress", "In Review", "Done"]


class ScrumStrategy(MethodologyStrategy):
    """Sprint-based board with a backlog and story-point estimation."""

    name = "scrum"

    def default_columns(self) -> list[str]:
        return list(_COLUMNS)

    def allowed_statuses(self) -> list[str]:
        return list(_COLUMNS)

    @property
    def sprints_enabled(self) -> bool:
        return True

    @property
    def estimation_mode(self) -> str:
        return EstimationMode.points.value

    @property
    def has_backlog(self) -> bool:
        return True
