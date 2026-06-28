"""Business logic for tasks.

The service derives all methodology-specific behaviour from the project's
Strategy (allowed statuses, estimation mode) so there is no per-methodology
branching scattered across the codebase.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.base import MethodologyStrategy
from app.methodology.factory import get_strategy
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import MemberRead, TaskCreate, TaskRead, TaskUpdate
from app.shared.enums import EstimationMode
from app.shared.exceptions import AppException

# Fallback default status for blank-slate (custom) methodologies that expose no
# predefined columns.
_CUSTOM_DEFAULT_STATUS = "todo"


class TaskService:
    """Orchestrates task use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = TaskRepository(db)
        self.projects = ProjectRepository(db)

    # -- members -----------------------------------------------------------

    async def list_members(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[MemberRead]:
        """Return the project's organization members (assignable users)."""

        await self._require_project(organization_id, project_id)
        members = await self.repo.list_org_members(organization_id)
        return [
            MemberRead(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,
                role=str(role.value if hasattr(role, "value") else role),
            )
            for user, role in members
        ]

    # -- tasks -------------------------------------------------------------

    async def list_tasks(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        sprint_id: uuid.UUID | None = None,
        status: str | None = None,
        assignee_id: uuid.UUID | None = None,
    ) -> list[TaskRead]:
        """Return the project's tasks honoring the optional filters."""

        await self._require_project(organization_id, project_id)
        tasks = await self.repo.list_for_project(
            organization_id,
            project_id,
            sprint_id=sprint_id,
            status=status,
            assignee_id=assignee_id,
        )
        name_map = await self._assignee_name_map(organization_id)
        return [self._to_read(task, name_map) for task in tasks]

    async def get_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskRead:
        """Return a single task or raise a 404 ``AppException``."""

        task = await self._require_task(organization_id, task_id)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map)

    async def create_task(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: TaskCreate,
    ) -> TaskRead:
        """Validate against the methodology Strategy and persist a new task."""

        project = await self._require_project(organization_id, project_id)
        strategy = get_strategy(project.methodology)

        status = self._resolve_status(strategy, data.status)
        self._validate_estimation(
            strategy, data.estimation_points, data.estimation_hours
        )
        await self._verify_assignee(organization_id, data.assignee_id)
        await self._verify_sprint(
            organization_id, project_id, data.sprint_id
        )

        task = Task(
            project_id=project_id,
            sprint_id=data.sprint_id,
            title=data.title,
            description=data.description,
            task_type=(data.task_type or "task"),
            status=status,
            priority=data.priority,
            assignee_id=data.assignee_id,
            estimation_points=data.estimation_points,
            estimation_hours=data.estimation_hours,
            due_date=data.due_date,
            start_date=data.start_date,
            completed_at=self._resolve_completed_at(strategy, status, None),
        )
        task = await self.repo.create(task)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map)

    async def update_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        data: TaskUpdate,
    ) -> TaskRead:
        """Apply a partial update, re-validating methodology-driven fields."""

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        strategy = get_strategy(project.methodology)

        changes = data.model_dump(exclude_unset=True)

        if "status" in changes:
            task.status = self._resolve_status(
                strategy, changes["status"], allow_default=False
            )
            # Keep the completion timestamp in sync with the done column.
            task.completed_at = self._resolve_completed_at(
                strategy, task.status, task.completed_at
            )

        # Estimation is validated against the resulting values, not just the
        # incoming ones, so partial edits cannot bypass the methodology mode.
        next_points = (
            changes["estimation_points"]
            if "estimation_points" in changes
            else task.estimation_points
        )
        next_hours = (
            changes["estimation_hours"]
            if "estimation_hours" in changes
            else task.estimation_hours
        )
        if "estimation_points" in changes or "estimation_hours" in changes:
            self._validate_estimation(strategy, next_points, next_hours)
            task.estimation_points = next_points
            task.estimation_hours = next_hours

        if "assignee_id" in changes:
            await self._verify_assignee(organization_id, changes["assignee_id"])
            task.assignee_id = changes["assignee_id"]

        if "sprint_id" in changes:
            await self._verify_sprint(
                organization_id, task.project_id, changes["sprint_id"]
            )
            task.sprint_id = changes["sprint_id"]

        for field in (
            "title",
            "description",
            "priority",
            "task_type",
            "due_date",
            "start_date",
            "order",
            "risk_flag",
            "risk_reason",
        ):
            if field in changes:
                setattr(task, field, changes[field])

        task = await self.repo.save(task)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map)

    async def delete_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        """Soft-delete a task."""

        task = await self._require_task(organization_id, task_id)
        task.is_active = False
        task.deleted_at = datetime.now(timezone.utc)
        await self.repo.save(task)

    # -- helpers -----------------------------------------------------------

    async def _require_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        project = await self.projects.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )
        return project

    async def _require_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task:
        task = await self.repo.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task

    @staticmethod
    def _resolve_status(
        strategy: MethodologyStrategy,
        status: str | None,
        *,
        allow_default: bool = True,
    ) -> str:
        """Validate a status against the methodology or pick a sensible default."""

        allowed = strategy.allowed_statuses()

        if not allowed:
            # Blank-slate methodology: accept any non-empty status.
            cleaned = (status or "").strip()
            if cleaned:
                return cleaned
            if allow_default:
                return _CUSTOM_DEFAULT_STATUS
            raise AppException(
                "Debes indicar un estado válido para la tarea.",
                code="invalid_status",
                status_code=422,
            )

        if status is None:
            if allow_default:
                return allowed[0]
            raise AppException(
                "Debes indicar un estado válido para la tarea.",
                code="invalid_status",
                status_code=422,
            )

        if status not in allowed:
            raise AppException(
                "El estado seleccionado no es válido para esta metodología. "
                f"Estados permitidos: {', '.join(allowed)}.",
                code="invalid_status",
                status_code=422,
            )
        return status

    @staticmethod
    def _resolve_completed_at(
        strategy: MethodologyStrategy,
        status: str,
        current: datetime | None,
    ) -> datetime | None:
        """Return the completion timestamp implied by ``status``.

        The "done" column is the last allowed status. Entering it stamps the
        completion time (preserving an existing one so it is not reset on
        unrelated edits); any other column clears it back to ``None``.
        Blank-slate methodologies (no allowed statuses) have no done column,
        so completion is never tracked for them.
        """

        allowed = strategy.allowed_statuses()
        done = allowed[-1] if allowed else None
        if done is not None and status == done:
            return current or datetime.now(timezone.utc)
        return None

    @staticmethod
    def _validate_estimation(
        strategy: MethodologyStrategy,
        points: int | None,
        hours: float | None,
    ) -> None:
        """Reject estimation values the methodology mode does not support."""

        mode = strategy.estimation_mode
        points_allowed = mode in (
            EstimationMode.points.value,
            EstimationMode.both.value,
        )
        hours_allowed = mode in (
            EstimationMode.hours.value,
            EstimationMode.both.value,
        )

        if points is not None and not points_allowed:
            raise AppException(
                "Esta metodología no admite estimación por puntos.",
                code="invalid_estimation",
                status_code=422,
            )
        if hours is not None and not hours_allowed:
            raise AppException(
                "Esta metodología no admite estimación por horas.",
                code="invalid_estimation",
                status_code=422,
            )

    async def _verify_assignee(
        self, organization_id: uuid.UUID, assignee_id: uuid.UUID | None
    ) -> None:
        if assignee_id is None:
            return
        if not await self.repo.is_org_member(organization_id, assignee_id):
            raise AppException(
                "El usuario asignado no pertenece a tu organización.",
                code="invalid_assignee",
                status_code=422,
            )

    async def _verify_sprint(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        sprint_id: uuid.UUID | None,
    ) -> None:
        if sprint_id is None:
            return
        # Imported lazily to avoid a module import cycle at load time.
        from app.modules.sprints.repository import SprintRepository

        sprint_repo = SprintRepository(self.repo.db)
        sprint = await sprint_repo.get_for_project(
            organization_id, project_id, sprint_id
        )
        if sprint is None:
            raise AppException(
                "El sprint indicado no existe en este proyecto.",
                code="invalid_sprint",
                status_code=422,
            )

    async def _assignee_name_map(
        self, organization_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        members = await self.repo.list_org_members(organization_id)
        return {user.id: user.full_name for user, _ in members}

    @staticmethod
    def _to_read(
        task: Task, name_map: dict[uuid.UUID, str]
    ) -> TaskRead:
        task.assignee_name = (
            name_map.get(task.assignee_id) if task.assignee_id else None
        )
        return TaskRead.model_validate(task)
