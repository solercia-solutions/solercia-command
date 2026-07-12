"""Data-access layer for reminders and reminder rules.

Both entities are strictly personal: every query scopes by ``user_id`` (owner)
IN ADDITION to ``organization_id`` — mirrors ``NotificationRepository.get``
(scoping by recipient too, so a peer in the same org can't mutate a resource
by guessing its id). This is what makes the 404-not-403 isolation contract
(specs/reminders/spec.md, R2/R4) hold without any extra service-layer check.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.reminders.models import Reminder, ReminderRule
from app.shared.enums import ReminderStatus
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /reminders``. First entry is the default
# order when pagination is requested without an explicit ``sort``.
REMINDER_SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "remind_at": Reminder.remind_at,
    "created_at": Reminder.created_at,
    "status": Reminder.status,
}

# Whitelist for ``?sort=`` on ``GET /reminder-rules``.
RULE_SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": ReminderRule.created_at,
    "rule_type": ReminderRule.rule_type,
    "enabled": ReminderRule.enabled,
}


class ReminderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: ReminderStatus | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Reminder], int]:
        """Return ``(reminders, total)`` owned by ``user_id``, most recent first."""
        query = select(Reminder).where(
            Reminder.organization_id == org_id,
            Reminder.user_id == user_id,
            Reminder.is_active.is_(True),
        )
        if status_filter is not None:
            query = query.where(Reminder.status == status_filter)

        if pagination is not None and pagination.requested:
            return await paginate(self.db, query, pagination, REMINDER_SORTABLE_FIELDS)

        query = query.order_by(Reminder.remind_at.desc())
        result = await self.db.execute(query)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, user_id: uuid.UUID
    ) -> Reminder | None:
        """Return a single reminder scoped to org + owner, or ``None``."""
        result = await self.db.execute(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.organization_id == org_id,
                Reminder.user_id == user_id,
                Reminder.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, reminder: Reminder) -> Reminder:
        """Persist a new reminder and return the refreshed instance."""
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def save(self, reminder: Reminder) -> Reminder:
        """Flush pending changes on an attached reminder and return it refreshed."""
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder


class ReminderRuleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[ReminderRule], int]:
        """Return ``(rules, total)`` owned by ``user_id``."""
        query = select(ReminderRule).where(
            ReminderRule.organization_id == org_id,
            ReminderRule.user_id == user_id,
            ReminderRule.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, query, pagination, RULE_SORTABLE_FIELDS)

        query = query.order_by(ReminderRule.created_at.desc())
        result = await self.db.execute(query)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, org_id: uuid.UUID, rule_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReminderRule | None:
        """Return a single rule scoped to org + owner, or ``None``."""
        result = await self.db.execute(
            select(ReminderRule).where(
                ReminderRule.id == rule_id,
                ReminderRule.organization_id == org_id,
                ReminderRule.user_id == user_id,
                ReminderRule.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, rule: ReminderRule) -> ReminderRule:
        """Persist a new rule and return the refreshed instance."""
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def save(self, rule: ReminderRule) -> ReminderRule:
        """Flush pending changes on an attached rule and return it refreshed."""
        await self.db.commit()
        await self.db.refresh(rule)
        return rule
