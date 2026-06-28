"""AlertRule service — business logic for alert rule management."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alert_rules.models import AlertRule
from app.modules.alert_rules.repository import AlertRuleRepository
from app.modules.alert_rules.schemas import AlertRuleUpdate
from app.shared.exceptions import AppException


class AlertRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = AlertRuleRepository(db)

    async def list_rules(self, org_id: uuid.UUID) -> list[AlertRule]:
        return await self.repo.list_by_org(org_id)

    async def update_rule(
        self, org_id: uuid.UUID, rule_id: uuid.UUID, data: AlertRuleUpdate
    ) -> AlertRule:
        rule = await self.repo.get(org_id, rule_id)
        if rule is None:
            raise AppException(
                detail="Regla de alerta no encontrada.",
                code="ALERT_RULE_NOT_FOUND",
                status_code=404,
            )
        return await self.repo.update(rule, data)
