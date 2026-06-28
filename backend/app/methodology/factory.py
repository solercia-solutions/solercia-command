"""Factory that resolves a :class:`MethodologyStrategy` from a methodology value."""

from app.methodology.base import MethodologyStrategy
from app.methodology.custom import CustomStrategy
from app.methodology.kanban import KanbanStrategy
from app.methodology.planner import PlannerStrategy
from app.methodology.scrum import ScrumStrategy
from app.shared.enums import Methodology
from app.shared.exceptions import AppException

# Map every methodology to its concrete strategy class.
_STRATEGIES: dict[Methodology, type[MethodologyStrategy]] = {
    Methodology.planner: PlannerStrategy,
    Methodology.kanban: KanbanStrategy,
    Methodology.scrum: ScrumStrategy,
    Methodology.custom: CustomStrategy,
}


def get_strategy(methodology: Methodology | str) -> MethodologyStrategy:
    """Return the strategy instance for the given methodology.

    Accepts either a :class:`Methodology` member or its string value. Raises an
    :class:`AppException` with a Spanish message for unknown methodologies.
    """

    try:
        key = methodology if isinstance(methodology, Methodology) else Methodology(methodology)
    except ValueError as exc:
        raise AppException(
            "La metodología seleccionada no es válida.",
            code="invalid_methodology",
            status_code=422,
        ) from exc

    strategy_cls = _STRATEGIES[key]
    return strategy_cls()
