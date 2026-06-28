"""Custom methodology: empty defaults so the project owner defines its own board."""

from app.methodology.base import MethodologyStrategy
from app.shared.enums import EstimationMode


class CustomStrategy(MethodologyStrategy):
    """Blank-slate methodology; columns and statuses are user-defined."""

    name = "custom"

    def default_columns(self) -> list[str]:
        return []

    def allowed_statuses(self) -> list[str]:
        return []

    @property
    def sprints_enabled(self) -> bool:
        return False

    @property
    def estimation_mode(self) -> str:
        return EstimationMode.none.value

    @property
    def has_backlog(self) -> bool:
        return False
