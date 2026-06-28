"""Abstract methodology Strategy contract."""

from abc import ABC, abstractmethod


class MethodologyStrategy(ABC):
    """Strategy describing how a methodology configures a project board.

    Concrete strategies expose the default board columns, the allowed task
    statuses and feature flags (sprints, estimation mode, backlog). The
    :meth:`to_info` payload is what the API surfaces to the frontend.
    """

    #: Stable identifier matching the ``Methodology`` enum value.
    name: str = "base"

    @abstractmethod
    def default_columns(self) -> list[str]:
        """Return the ordered board columns created for a new project."""

    @abstractmethod
    def allowed_statuses(self) -> list[str]:
        """Return the task statuses this methodology permits."""

    @property
    @abstractmethod
    def sprints_enabled(self) -> bool:
        """Whether sprints are available for this methodology."""

    @property
    @abstractmethod
    def estimation_mode(self) -> str:
        """Estimation mode value (see :class:`EstimationMode`)."""

    @property
    @abstractmethod
    def has_backlog(self) -> bool:
        """Whether a dedicated backlog is available."""

    def to_info(self) -> dict:
        """Serialize the strategy configuration for API responses."""

        return {
            "methodology": self.name,
            "default_columns": self.default_columns(),
            "allowed_statuses": self.allowed_statuses(),
            "sprints_enabled": self.sprints_enabled,
            "estimation_mode": self.estimation_mode,
            "has_backlog": self.has_backlog,
        }
