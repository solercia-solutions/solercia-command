"""SprintAtRiskStrategy — active sprint with < 50% points at 75% elapsed time."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.base import AlertCandidate, AlertStrategy
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.shared.enums import MemberRole


class SprintAtRiskStrategy(AlertStrategy):
    rule_type = "sprint_at_risk"

    async def evaluate(
        self, db: AsyncSession, organization_id, threshold_params: dict
    ) -> list[AlertCandidate]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Sprint)
            .join(Project, Project.id == Sprint.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Sprint.is_active.is_(True),
                Sprint.status == "active",
                Sprint.start_date.isnot(None),
                Sprint.end_date.isnot(None),
            )
        )
        sprints = result.scalars().all()

        # Get admin recipients for the org (OrganizationMember has no is_active)
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
        for sprint in sprints:
            total_secs = (sprint.end_date - sprint.start_date).total_seconds()
            if total_secs <= 0:
                continue
            elapsed_secs = (now - sprint.start_date).total_seconds()
            progress_ratio = elapsed_secs / total_secs

            if progress_ratio < 0.75:
                continue  # not yet at 75% elapsed

            # Count total points in this sprint
            total_pts_result = await db.execute(
                select(func.coalesce(func.sum(Task.estimation_points), 0))
                .where(Task.sprint_id == sprint.id, Task.is_active.is_(True))
            )
            total_pts = total_pts_result.scalar_one() or 0
            if total_pts == 0:
                continue  # no estimated tasks, cannot evaluate

            # Count done (completed_at is not null) points
            done_pts_result = await db.execute(
                select(func.coalesce(func.sum(Task.estimation_points), 0))
                .where(
                    Task.sprint_id == sprint.id,
                    Task.is_active.is_(True),
                    Task.completed_at.isnot(None),
                )
            )
            done_pts = done_pts_result.scalar_one() or 0
            completion_ratio = done_pts / total_pts

            if completion_ratio >= 0.5:
                continue  # sprint is on track

            pct_elapsed = int(progress_ratio * 100)
            pct_done = int(completion_ratio * 100)
            for admin in admins:
                candidates.append(
                    AlertCandidate(
                        organization_id=organization_id,
                        rule_type=self.rule_type,
                        recipient_user_id=admin.user_id,
                        title="Sprint en riesgo",
                        body=(
                            f'El sprint "{sprint.name}" lleva {pct_elapsed}% del tiempo '
                            f'transcurrido pero solo {pct_done}% de los puntos completados.'
                        ),
                        # Recipient must be part of the dedup key: otherwise the
                        # first admin's notification suppresses every other admin's.
                        dedup_key=f"sprint_at_risk:{sprint.id}:{admin.user_id}",
                        target_type="sprint",
                        target_id=sprint.id,
                    )
                )
        return candidates
