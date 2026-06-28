"""Business logic for sprints."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.factory import get_strategy
from app.modules.projects.repository import ProjectRepository
from app.modules.sprints.models import Sprint
from app.modules.sprints.repository import SprintRepository
from app.modules.sprints.schemas import SprintCreate, SprintRead, SprintUpdate
from app.shared.enums import EstimationMode
from app.shared.exceptions import AppException

# Lifecycle values a sprint may take.
_ALLOWED_STATUSES = ("active", "closed")


class SprintService:
    """Orchestrates sprint use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = SprintRepository(db)
        self.projects = ProjectRepository(db)

    async def list_sprints(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[SprintRead]:
        """Return the project's sprints."""

        await self._require_sprints_enabled(organization_id, project_id)
        sprints = await self.repo.list_for_project(organization_id, project_id)
        return [SprintRead.model_validate(sprint) for sprint in sprints]

    async def create_sprint(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: SprintCreate,
    ) -> SprintRead:
        """Create a sprint within a sprint-enabled project."""

        await self._require_sprints_enabled(organization_id, project_id)
        sprint = Sprint(
            project_id=project_id,
            name=data.name,
            goal=data.goal,
            start_date=data.start_date,
            end_date=data.end_date,
            status="active",
        )
        sprint = await self.repo.create(sprint)
        return SprintRead.model_validate(sprint)

    async def update_sprint(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID,
        data: SprintUpdate,
    ) -> SprintRead:
        """Apply a partial update to a sprint."""

        sprint = await self.repo.get(organization_id, sprint_id)
        if sprint is None:
            raise AppException(
                "El sprint no existe o no tienes acceso a él.",
                code="sprint_not_found",
                status_code=404,
            )

        changes = data.model_dump(exclude_unset=True)
        if "status" in changes:
            status = changes["status"]
            if status not in _ALLOWED_STATUSES:
                raise AppException(
                    "El estado del sprint debe ser 'active' o 'closed'.",
                    code="invalid_sprint_status",
                    status_code=422,
                )
            sprint.status = status

        for field in ("name", "goal", "start_date", "end_date"):
            if field in changes:
                setattr(sprint, field, changes[field])

        sprint = await self.repo.save(sprint)
        return SprintRead.model_validate(sprint)

    async def burndown(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        sprint_id: uuid.UUID,
    ) -> dict:
        """Build the burndown series for a sprint.

        ``unit`` is "points" when the project's estimation mode includes points,
        otherwise "tasks". ``total`` is the sum of the sprint tasks' points (or
        the task count). The ideal line drops linearly from ``total`` to ``0``
        between the sprint's start and end dates; the actual line subtracts the
        work completed (by ``completed_at``) on or before each day and is left
        ``None`` for any day after today so the future is not plotted.
        """

        project = await self.projects.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )

        sprint = await self.repo.get_for_project(
            organization_id, project_id, sprint_id
        )
        if sprint is None:
            raise AppException(
                "El sprint no existe en este proyecto.",
                code="sprint_not_found",
                status_code=404,
            )

        strategy = get_strategy(project.methodology)
        unit = (
            "points"
            if strategy.estimation_mode
            in (EstimationMode.points.value, EstimationMode.both.value)
            else "tasks"
        )
        allowed = strategy.allowed_statuses()
        done_status = allowed[-1] if allowed else None

        tasks = await self.repo.list_tasks_for_sprint(
            organization_id, sprint_id
        )

        def work_of(task) -> int:
            return (task.estimation_points or 0) if unit == "points" else 1

        total_points = sum((t.estimation_points or 0) for t in tasks)
        total_tasks = len(tasks)
        completed_tasks = sum(
            1
            for t in tasks
            if done_status is not None and t.status == done_status
        )
        # Total the burndown chart works against, expressed in ``unit``.
        total = total_points if unit == "points" else total_tasks

        days = self._burndown_days(sprint, tasks, total, work_of)

        return {
            "sprint": {
                "id": sprint.id,
                "name": sprint.name,
                "start_date": sprint.start_date,
                "end_date": sprint.end_date,
                "status": sprint.status,
            },
            "total_points": total_points,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "unit": unit,
            "days": days,
        }

    @staticmethod
    def _burndown_days(sprint: Sprint, tasks, total, work_of) -> list[dict]:
        """Return the per-day ideal/actual series for the sprint window."""

        if sprint.start_date is None or sprint.end_date is None:
            return []

        start = sprint.start_date.date()
        end = sprint.end_date.date()
        today = datetime.now(timezone.utc).date()
        num_days = (end - start).days + 1
        if num_days < 1:
            return []

        # (completion_date, work) for every already-completed task.
        completions = [
            (t.completed_at.date(), work_of(t))
            for t in tasks
            if t.completed_at is not None
        ]

        denom = num_days - 1 if num_days > 1 else 1
        days: list[dict] = []
        for i in range(num_days):
            current = start + timedelta(days=i)
            ideal = round(total * (1 - i / denom), 2) if num_days > 1 else 0.0
            if current > today:
                actual = None
            else:
                completed_by = sum(
                    work for date_done, work in completions
                    if date_done <= current
                )
                actual = total - completed_by
            days.append(
                {
                    "date": current.isoformat(),
                    "ideal": ideal,
                    "actual": actual,
                }
            )
        return days

    async def _require_sprints_enabled(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        project = await self.projects.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )
        if not get_strategy(project.methodology).sprints_enabled:
            raise AppException(
                "La metodología de este proyecto no admite sprints.",
                code="sprints_not_enabled",
                status_code=422,
            )
