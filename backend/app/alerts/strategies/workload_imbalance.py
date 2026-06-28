"""WorkloadImbalanceStrategy — user with too many active tasks."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.enums import MemberRole


class WorkloadImbalanceStrategy(AlertStrategy):
    rule_type = "workload_imbalance"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        max_tasks = threshold_params.get("max_active_tasks", 8)

        # Count active (not completed) tasks per assignee within this org
        result = await db.execute(
            select(Task.assignee_id, func.count(Task.id).label("task_count"))
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
                Task.assignee_id.isnot(None),
                Task.completed_at.is_(None),
            )
            .group_by(Task.assignee_id)
            .having(func.count(Task.id) > max_tasks)
        )
        overloaded = result.all()  # list of (assignee_id, count)
        if not overloaded:
            return []

        # Get admin recipients (OrganizationMember has no is_active field)
        admins_result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == MemberRole.admin,
            )
        )
        admins = admins_result.scalars().all()
        if not admins:
            return []

        candidates = []
        for assignee_id, count in overloaded:
            for admin in admins:
                candidates.append(
                    AlertCandidate(
                        organization_id=organization_id,
                        rule_type=self.rule_type,
                        recipient_user_id=admin.user_id,
                        title="Sobrecarga de trabajo detectada",
                        body=f"Un colaborador tiene {count} tareas activas (límite: {max_tasks}).",
                        # Recipient must be part of the dedup key: otherwise the
                        # first admin's notification suppresses every other admin's.
                        dedup_key=f"workload_imbalance:{assignee_id}:{admin.user_id}",
                        target_type="user",
                        target_id=assignee_id,
                    )
                )
        return candidates
