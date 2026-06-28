"""AlertRule repository — database access for AlertRule model."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alert_rules.models import AlertRule
from app.modules.alert_rules.schemas import AlertRuleUpdate


class AlertRuleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(self, organization_id: uuid.UUID) -> list[AlertRule]:
        """Return active alert rules for an organization."""
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.organization_id == organization_id,
                AlertRule.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get(
        self, organization_id: uuid.UUID, rule_id: uuid.UUID
    ) -> AlertRule | None:
        result = await self.db.execute(
            select(AlertRule).where(
                AlertRule.organization_id == organization_id,
                AlertRule.id == rule_id,
                AlertRule.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def update(self, rule: AlertRule, data: AlertRuleUpdate) -> AlertRule:
        if data.enabled is not None:
            rule.enabled = data.enabled
        if data.threshold_params is not None:
            rule.threshold_params = data.threshold_params
        self.db.add(rule)
        await self.db.flush()
        await self.db.refresh(rule)
        return rule
