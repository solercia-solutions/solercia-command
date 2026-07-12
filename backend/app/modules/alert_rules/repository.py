"""AlertRule repository — database access for AlertRule model."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.alert_rules.models import AlertRule
from app.modules.alert_rules.schemas import AlertRuleUpdate
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /alert-rules``. First entry is the
# default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "rule_type": AlertRule.rule_type,
    "enabled": AlertRule.enabled,
    "created_at": AlertRule.created_at,
}


class AlertRuleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[AlertRule], int]:
        """Return ``(rules, total)`` — active alert rules for an organization."""
        stmt = select(AlertRule).where(
            AlertRule.organization_id == organization_id,
            AlertRule.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            rows, total = await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)
            return list(rows), total

        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())
        return rows, len(rows)

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
