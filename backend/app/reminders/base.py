"""Base contracts for the reminder rule engine — mirrors app/alerts/base.py.

Unlike ``AlertStrategy`` (org-wide), ``ReminderRuleStrategy.evaluate`` is
scoped to a single user: every ``ReminderRule`` is personal
(``ReminderRule.user_id``), so the dispatcher evaluates one rule at a time
for its owner instead of iterating every member of the organization.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReminderCandidate:
    """A candidate notification produced by a reminder rule evaluation."""

    organization_id: uuid.UUID
    recipient_user_id: uuid.UUID
    title: str
    body: str
    dedup_key: str
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    #: Family recorded on Notification.rule_type — shared by every reminder
    #: origin (manual + every rule type), see design.md "dedup_key
    #: determinista y namespaced".
    rule_type: str = "reminder"


class ReminderRuleStrategy(ABC):
    """Strategy contract for evaluating a single ``ReminderRule`` type."""

    #: Stable string matching ReminderRule.rule_type
    rule_type: str = "base"

    @abstractmethod
    async def evaluate(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        params: dict,
    ) -> list[ReminderCandidate]:
        """Evaluate the rule for the given user. Return candidates to notify."""
