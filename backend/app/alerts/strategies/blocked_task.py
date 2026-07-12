"""BlockedTaskStrategy — tasks blocked by an unfinished task for too long.

Selects active ``task_dependencies`` edges where BOTH the blocker and the
blocked task are still incomplete (``completed_at IS NULL``, the same
unblock criterion as ``TaskService._blocking_state`` — design.md gate
correction #3) and the edge itself is older than ``threshold_params``'s
day threshold. Notifies the blocked task's assignee.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.projects.models import Project
from app.modules.task_links.models import TaskDependency
from app.modules.tasks.models import Task

#: Default threshold_params key (design.md, "Decisión: Estrategia de alerta
#: blocked_task" — resolved as a dedicated key, not shared with task_at_risk).
#: ``days`` is accepted as a fallback alias: alert-blocked-task.md's
#: scenarios literally reference ``threshold_params.days``.
_DEFAULT_BLOCKED_DAYS = 3


class BlockedTaskStrategy(AlertStrategy):
    rule_type = "blocked_task"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        blocked_days = threshold_params.get(
            "blocked_days", threshold_params.get("days", _DEFAULT_BLOCKED_DAYS)
        )
        cutoff = datetime.now(UTC) - timedelta(days=blocked_days)

        blocker = aliased(Task)
        blocked = aliased(Task)

        result = await db.execute(
            select(TaskDependency, blocked)
            .join(blocker, blocker.id == TaskDependency.blocker_task_id)
            .join(blocked, blocked.id == TaskDependency.blocked_task_id)
            .join(Project, Project.id == blocked.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                TaskDependency.is_active.is_(True),
                TaskDependency.created_at <= cutoff,
                blocker.is_active.is_(True),
                blocker.completed_at.is_(None),
                blocked.is_active.is_(True),
                blocked.completed_at.is_(None),
            )
        )

        candidates = []
        for _dependency, blocked_task in result.all():
            if blocked_task.assignee_id is None:
                continue
            candidates.append(
                AlertCandidate(
                    organization_id=organization_id,
                    rule_type=self.rule_type,
                    recipient_user_id=blocked_task.assignee_id,
                    title="Tarea bloqueada",
                    body=(
                        f'La tarea "{blocked_task.title}" lleva más de '
                        f'{blocked_days} días bloqueada por otra tarea sin completar.'
                    ),
                    dedup_key=f"blocked_task:{blocked_task.id}",
                    target_type="task",
                    target_id=blocked_task.id,
                )
            )
        return candidates
