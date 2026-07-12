"""task_due_soon reminder rule strategy — mirrors app/alerts/strategies/task_at_risk.py.

Unlike the alert strategies (org-wide, one candidate per admin), this evaluates
a SINGLE user's own assigned tasks — ``ReminderRule`` is personal.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.reminders.base import ReminderCandidate, ReminderRuleStrategy


class TaskDueSoonStrategy(ReminderRuleStrategy):
    rule_type = "task_due_soon"

    async def evaluate(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        params: dict,
    ) -> list[ReminderCandidate]:
        lead_days = params.get("lead_days", 3)
        now = datetime.now(UTC)
        cutoff = now + timedelta(days=lead_days)

        result = await db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
                Task.assignee_id == user_id,
                Task.due_date.isnot(None),
                Task.due_date <= cutoff,
                Task.completed_at.is_(None),
            )
        )
        tasks = result.scalars().all()

        candidates = []
        for task in tasks:
            assert task.due_date is not None  # guaranteed by the WHERE clause above
            candidates.append(
                ReminderCandidate(
                    organization_id=organization_id,
                    recipient_user_id=user_id,
                    title="Tarea próxima a vencer",
                    body=f'La tarea "{task.title}" vence pronto.',
                    dedup_key=(
                        f"reminder_due_soon:{task.id}:{user_id}:"
                        f"{task.due_date.strftime('%Y-%m-%d')}"
                    ),
                    target_type="task",
                    target_id=task.id,
                )
            )
        return candidates
