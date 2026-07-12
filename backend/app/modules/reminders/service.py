"""Business logic for reminders and reminder rules.

Every use-case is scoped to the caller's own resources; there is no
supervisor/admin exemption (specs/reminders/spec.md, "Aislamiento
multi-tenant y personal"). ``_require_owned``/``_require_owned_rule`` raise a
plain ``404`` (never ``403``) for both cross-tenant and cross-user access —
the repository already filters by ``organization_id`` + ``user_id``, so
"belongs to someone else" and "does not exist" are indistinguishable by
design.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reminders.models import Reminder, ReminderRule
from app.modules.reminders.repository import ReminderRepository, ReminderRuleRepository
from app.modules.reminders.schemas import (
    ReminderCreate,
    ReminderResponse,
    ReminderRuleCreate,
    ReminderRuleResponse,
    ReminderRuleUpdate,
    ReminderUpdate,
)
from app.shared.enums import ReminderStatus
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


class ReminderService:
    """Orchestrates reminder use-cases for a single owner within an organization."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ReminderRepository(db)

    async def create_reminder(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReminderCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ReminderResponse:
        """Create a manual reminder for the authenticated caller. Always ``scheduled``."""
        reminder = Reminder(
            organization_id=org_id,
            user_id=user_id,
            task_id=data.task_id,
            remind_at=data.remind_at,
            message=data.message,
            status=ReminderStatus.scheduled,
            created_by=actor_id,
            updated_by=actor_id,
        )
        reminder = await self.repo.create(reminder)
        return ReminderResponse.model_validate(reminder)

    async def get_reminder(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReminderResponse:
        """Return a single reminder owned by the caller."""
        reminder = await self._require_owned(org_id, reminder_id, user_id)
        return ReminderResponse.model_validate(reminder)

    async def list_reminders(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        status_filter: ReminderStatus | None,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[ReminderResponse], int]:
        """Return ``(reminders, total)`` owned by the caller, optionally by status."""
        rows, total = await self.repo.list_for_user(
            org_id, user_id, status_filter, pagination
        )
        return [ReminderResponse.model_validate(row) for row in rows], total

    async def update_reminder(
        self,
        org_id: uuid.UUID,
        reminder_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReminderUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ReminderResponse:
        """Edit ``remind_at``/``message``. Only allowed while ``status=scheduled``."""
        reminder = await self._require_owned(org_id, reminder_id, user_id)
        self._require_scheduled(reminder, "editarlo")

        changes = data.model_dump(exclude_unset=True)
        if "remind_at" in changes:
            reminder.remind_at = changes["remind_at"]
        if "message" in changes:
            reminder.message = changes["message"]

        reminder.updated_by = actor_id
        reminder = await self.repo.save(reminder)
        return ReminderResponse.model_validate(reminder)

    async def cancel_reminder(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Cancel (soft) a scheduled reminder. The scheduler will skip it afterwards."""
        reminder = await self._require_owned(org_id, reminder_id, user_id)
        self._require_scheduled(reminder, "cancelarlo")
        reminder.status = ReminderStatus.cancelled
        await self.repo.save(reminder)

    # -- helpers -------------------------------------------------------------

    async def _require_owned(
        self, org_id: uuid.UUID, reminder_id: uuid.UUID, user_id: uuid.UUID
    ) -> Reminder:
        reminder = await self.repo.get(org_id, reminder_id, user_id)
        if reminder is None:
            raise AppException(
                "El recordatorio no existe o no tienes acceso a él.",
                code="reminder_not_found",
                status_code=404,
            )
        return reminder

    @staticmethod
    def _require_scheduled(reminder: Reminder, verb: str) -> None:
        if reminder.status != ReminderStatus.scheduled:
            raise AppException(
                f"Solo se puede {verb} un recordatorio programado (status=scheduled).",
                code="reminder_not_scheduled",
                status_code=422,
            )


class ReminderRuleService:
    """Orchestrates reminder-rule use-cases for a single owner within an organization."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = ReminderRuleRepository(db)

    async def create_rule(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReminderRuleCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ReminderRuleResponse:
        """Create a personal reminder rule (e.g. ``task_due_soon``). Always ``enabled``."""
        rule = ReminderRule(
            organization_id=org_id,
            user_id=user_id,
            rule_type=data.rule_type,
            enabled=True,
            params={"lead_days": data.lead_days},
            created_by=actor_id,
            updated_by=actor_id,
        )
        rule = await self.repo.create(rule)
        return ReminderRuleResponse.model_validate(rule)

    async def list_rules(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[ReminderRuleResponse], int]:
        """Return ``(rules, total)`` owned by the caller."""
        rows, total = await self.repo.list_for_user(org_id, user_id, pagination)
        return [ReminderRuleResponse.model_validate(row) for row in rows], total

    async def update_rule(
        self,
        org_id: uuid.UUID,
        rule_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ReminderRuleUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> ReminderRuleResponse:
        """Edit ``enabled``/``lead_days`` of a personal reminder rule."""
        rule = await self._require_owned_rule(org_id, rule_id, user_id)

        changes = data.model_dump(exclude_unset=True)
        if "enabled" in changes:
            rule.enabled = changes["enabled"]
        if "lead_days" in changes:
            rule.params = {**rule.params, "lead_days": changes["lead_days"]}

        rule.updated_by = actor_id
        rule = await self.repo.save(rule)
        return ReminderRuleResponse.model_validate(rule)

    # -- helpers -------------------------------------------------------------

    async def _require_owned_rule(
        self, org_id: uuid.UUID, rule_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReminderRule:
        rule = await self.repo.get(org_id, rule_id, user_id)
        if rule is None:
            raise AppException(
                "La regla de recordatorio no existe o no tienes acceso a ella.",
                code="reminder_rule_not_found",
                status_code=404,
            )
        return rule
