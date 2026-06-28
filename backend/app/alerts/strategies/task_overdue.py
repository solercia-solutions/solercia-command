"""TaskOverdueStrategy — tasks past due_date without completed_at."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.projects.models import Project
from app.modules.tasks.models import Task


class TaskOverdueStrategy(AlertStrategy):
    rule_type = "task_overdue"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
                Task.due_date < now,
                Task.completed_at.is_(None),
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
                    title="Tarea vencida",
                    body=f'La tarea "{task.title}" venció sin ser completada.',
                    dedup_key=f"task_overdue:{task.id}",
                    target_type="task",
                    target_id=task.id,
                )
            )
        return candidates
