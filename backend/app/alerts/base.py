"""Abstract alert strategy contract."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AlertCandidate:
    """A candidate notification produced by a strategy evaluation."""

    organization_id: uuid.UUID
    rule_type: str
    recipient_user_id: uuid.UUID
    title: str
    body: str
    dedup_key: str
    target_type: str | None = None
    target_id: uuid.UUID | None = None


class AlertStrategy(ABC):
    """Strategy contract for evaluating a single alert rule type."""

    #: Stable string matching AlertRule.rule_type
    rule_type: str = "base"

    @abstractmethod
    async def evaluate(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        threshold_params: dict,
    ) -> list[AlertCandidate]:
        """Evaluate the rule for the given org. Return candidates to notify."""
