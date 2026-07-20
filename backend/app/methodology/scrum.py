"""Scrum methodology: sprint-driven board with Jira-style dual estimation."""

from app.methodology.base import MethodologyStrategy
from app.shared.enums import EstimationMode

_COLUMNS = ["To Do", "In Progress", "In Review", "Done"]


class ScrumStrategy(MethodologyStrategy):
    """Sprint-based board with a backlog and Jira-style dual estimation.

    Estimation mode is ``both``: tasks estimate with story points (the value
    velocity/burndown aggregate) and may additionally carry a time-tracking
    original estimate in ``estimation_hours``, mirroring how a Jira scrum
    board combines story points with time tracking.
    """

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
        return EstimationMode.both.value

    @property
    def has_backlog(self) -> bool:
        return True
