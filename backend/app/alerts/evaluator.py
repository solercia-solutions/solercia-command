"""Alert evaluator — runs all enabled strategies for all organizations."""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.registry import get_strategy
from app.modules.alert_rules.models import AlertRule
from app.modules.notifications.repository import NotificationRepository
from app.modules.organizations.models import Organization
from app.realtime.publisher import flush_pending

logger = logging.getLogger("solercia.alerts")


async def evaluate_organization(db: AsyncSession, organization_id: uuid.UUID) -> int:
    """Run all enabled alert rules for one organization.

    Returns the count of new notifications created.
    """
    rules_result = await db.execute(
        select(AlertRule).where(
            AlertRule.organization_id == organization_id,
            AlertRule.enabled.is_(True),
            AlertRule.is_active.is_(True),
        )
    )
    rules = rules_result.scalars().all()

    notification_repo = NotificationRepository(db)
    created = 0

    for rule in rules:
        strategy = get_strategy(rule.rule_type)
        if strategy is None:
            logger.warning("No strategy registered for rule_type=%s", rule.rule_type)
            continue
        try:
            candidates = await strategy.evaluate(db, organization_id, rule.threshold_params)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Strategy %s failed for org %s", rule.rule_type, organization_id
            )
            continue

        for candidate in candidates:
            # IDEMPOTENCY: skip if an active notification with this dedup_key exists
            if await notification_repo.exists_active(organization_id, candidate.dedup_key):
                continue
            await notification_repo.create(
                organization_id=candidate.organization_id,
                recipient_user_id=candidate.recipient_user_id,
                rule_type=candidate.rule_type,
                title=candidate.title,
                body=candidate.body,
                target_type=candidate.target_type,
                target_id=candidate.target_id,
                dedup_key=candidate.dedup_key,
            )
            created += 1

    await db.commit()
    # One drain per commit: evaluate_all_organizations reuses this SAME
    # session across N organizations, and flush_pending pops the buffer
    # atomically so an earlier organization's payloads are never re-sent
    # here (design.md D2, gate correction).
    await flush_pending(db)
    logger.info(
        "Alert evaluation for org %s: %d new notifications.", organization_id, created
    )
    return created


async def evaluate_all_organizations(db: AsyncSession) -> int:
    """Run alert evaluation for every active organization.

    NOTE: In a multi-worker deployment, a distributed Redis lock should be used
    here to prevent concurrent evaluations. Not implemented in this slice.

    TODO: Add Redis lock via ``redis.lock("alerts:eval:lock", timeout=300)``
    before evaluating to ensure only one worker runs evaluation at a time.
    """
    result = await db.execute(
        select(Organization).where(Organization.is_active.is_(True))
    )
    orgs = result.scalars().all()

    total = 0
    for org in orgs:
        total += await evaluate_organization(db, org.id)
    return total
