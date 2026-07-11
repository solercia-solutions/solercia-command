"""Alert rules router — manage configurable alert rules per organization."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_membership, require_admin
from app.modules.alert_rules.schemas import AlertRuleRead, AlertRuleUpdate
from app.modules.alert_rules.service import AlertRuleService
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


@router.get("", response_model=dict)
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
) -> dict:
    """List active alert rules for the caller's organization."""
    service = AlertRuleService(db)
    rules = await service.list_rules(membership.organization_id)
    return {
        "data": [AlertRuleRead.model_validate(r).model_dump() for r in rules],
        "message": "Reglas de alerta obtenidas.",
        "meta": {"total": len(rules)},
    }


@router.patch("/{rule_id}", response_model=dict)
async def update_alert_rule(
    rule_id: uuid.UUID,
    data: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    membership: OrganizationMember = Depends(get_current_membership),
    _: User = Depends(require_admin),
) -> dict:
    """Update an alert rule's enabled status or threshold parameters (admin only)."""
    service = AlertRuleService(db)
    rule = await service.update_rule(membership.organization_id, rule_id, data)
    await db.commit()
    return {
        "data": AlertRuleRead.model_validate(rule).model_dump(),
        "message": "Regla de alerta actualizada.",
        "meta": {},
    }
