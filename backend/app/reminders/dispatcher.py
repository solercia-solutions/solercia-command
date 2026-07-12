"""Reminder dispatcher — fires due manual reminders and evaluates enabled rules.

Concurrency (design.md Decision 4, gate correction): a manual reminder is
never transitioned via ``session.add()`` on a loaded ORM object — that would
issue an unconditional ``UPDATE ... WHERE id=:id`` and could silently
overwrite a concurrent cancellation (READ COMMITTED does not protect against
this TOCTOU race). Instead ``_claim_reminder`` issues a single conditional
``UPDATE ... WHERE id=:id AND status='scheduled' RETURNING id`` via SQL Core
(``db.execute``): only a reminder still ``scheduled`` at the moment of the
UPDATE is claimed. If the claim returns no row, the reminder was cancelled
concurrently (or already processed) and is silently skipped — it is NEVER
overwritten. The same guard is reused for the ``skipped`` transition.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.repository import NotificationRepository
from app.modules.reminders.models import Reminder, ReminderRule
from app.modules.tasks.models import Task
from app.reminders.registry import get_strategy
from app.shared.enums import ReminderStatus

logger = logging.getLogger("solercia.reminders")


async def _claim_reminder(
    db: AsyncSession,
    reminder_id: uuid.UUID,
    new_status: ReminderStatus,
    *,
    fired_at: datetime | None = None,
) -> bool:
    """Atomically transition a reminder FROM ``scheduled``.

    Returns ``True`` if the claim succeeded (the reminder was still
    ``scheduled`` and is now ``new_status``), ``False`` if it was no longer
    ``scheduled`` (concurrently cancelled or already processed).
    """
    values: dict[str, ReminderStatus | datetime] = {"status": new_status}
    if fired_at is not None:
        values["fired_at"] = fired_at

    stmt = (
        update(Reminder)
        .where(Reminder.id == reminder_id, Reminder.status == ReminderStatus.scheduled)
        .values(**values)
        .returning(Reminder.id)
    )
    result = await db.execute(stmt)
    return result.first() is not None


async def _dispatch_manual_reminders(db: AsyncSession, now: datetime) -> int:
    """Fire (or skip) every due manual reminder. Returns the count of notifications created."""
    notification_repo = NotificationRepository(db)
    created = 0

    result = await db.execute(
        select(Reminder).where(
            Reminder.status == ReminderStatus.scheduled,
            Reminder.remind_at <= now,
            Reminder.is_active.is_(True),
        )
    )
    due_reminders = result.scalars().all()

    for reminder in due_reminders:
        task: Task | None = None
        if reminder.task_id is not None:
            task_result = await db.execute(
                select(Task).where(Task.id == reminder.task_id)
            )
            task = task_result.scalar_one_or_none()

            task_unavailable = (
                task is None or not task.is_active or task.completed_at is not None
            )
            if task_unavailable:
                await _claim_reminder(db, reminder.id, ReminderStatus.skipped)
                continue

        claimed = await _claim_reminder(
            db, reminder.id, ReminderStatus.fired, fired_at=now
        )
        if not claimed:
            continue  # concurrent cancellation — never overwrite it

        dedup_key = f"reminder_manual:{reminder.id}"
        if await notification_repo.exists_active(reminder.organization_id, dedup_key):
            continue
        await notification_repo.create(
            organization_id=reminder.organization_id,
            recipient_user_id=reminder.user_id,
            rule_type="reminder",
            title="Recordatorio",
            body=reminder.message,
            target_type="task" if reminder.task_id else None,
            target_id=reminder.task_id,
            dedup_key=dedup_key,
        )
        created += 1

    return created


async def _dispatch_rule_reminders(db: AsyncSession) -> int:
    """Evaluate every enabled ReminderRule. Returns the count of notifications created."""
    notification_repo = NotificationRepository(db)
    created = 0

    rules_result = await db.execute(
        select(ReminderRule).where(
            ReminderRule.enabled.is_(True),
            ReminderRule.is_active.is_(True),
        )
    )
    rules = rules_result.scalars().all()

    for rule in rules:
        strategy = get_strategy(rule.rule_type)
        if strategy is None:
            logger.warning(
                "No reminder strategy registered for rule_type=%s", rule.rule_type
            )
            continue
        try:
            candidates = await strategy.evaluate(
                db, rule.organization_id, rule.user_id, rule.params
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Reminder strategy %s failed for user %s", rule.rule_type, rule.user_id
            )
            continue

        for candidate in candidates:
            if await notification_repo.exists_active(
                candidate.organization_id, candidate.dedup_key
            ):
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

    return created


async def dispatch_reminders(db: AsyncSession) -> int:
    """Fire due manual reminders and evaluate enabled ReminderRules.

    Single ``db.commit()`` at the end — mirrors ``app.alerts.evaluator.
    evaluate_organization``. Returns the total count of notifications created.
    """
    now = datetime.now(UTC)
    created = await _dispatch_manual_reminders(db, now)
    created += await _dispatch_rule_reminders(db)

    await db.commit()
    logger.info("Reminder dispatch: %d new notifications.", created)
    return created
