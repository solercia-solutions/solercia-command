"""TaskAtRiskStrategy — tasks near due_date with no recent activity."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.comments.models import TaskComment
from app.modules.projects.models import Project
from app.modules.tasks.models import Task


class TaskAtRiskStrategy(AlertStrategy):
    rule_type = "task_at_risk"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        days_before = threshold_params.get("days_before", 3)
        inactive_days = threshold_params.get("inactive_days", 3)
        now = datetime.now(UTC)
        cutoff_due = now + timedelta(days=days_before)
        cutoff_inactive = now - timedelta(days=inactive_days)

        # "Untouched" cross-check: a task the team is actively commenting on is
        # not at risk even if its updated_at is stale. Exclude tasks with any
        # recent comment within the inactivity window.
        recent_comment = exists().where(
            TaskComment.task_id == Task.id,
            TaskComment.is_active.is_(True),
            TaskComment.created_at >= cutoff_inactive,
        )

        # Tasks approaching due_date that are not done and have had no recent activity
        result = await db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
                Task.due_date.isnot(None),
                Task.due_date >= now,              # not yet overdue
                Task.due_date <= cutoff_due,       # but within threshold
                Task.completed_at.is_(None),
                Task.updated_at < cutoff_inactive, # no updates recently
                ~recent_comment,                   # and no recent comments
            )
        )
        tasks = result.scalars().all()

        candidates = []
        for task in tasks:
            if task.assignee_id is None:
                continue
            candidates.append(
                AlertCandidate(
                    organization_id=organization_id,
                    rule_type=self.rule_type,
                    recipient_user_id=task.assignee_id,
                    title="Tarea en riesgo",
                    body=(
                        f'La tarea "{task.title}" vence en {days_before} días '
                        f'y no ha tenido actividad en los últimos {inactive_days} días.'
                    ),
                    dedup_key=f"task_at_risk:{task.id}",
                    target_type="task",
                    target_id=task.id,
                )
            )
        return candidates
