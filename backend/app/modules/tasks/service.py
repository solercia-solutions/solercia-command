"""Business logic for tasks.

The service derives all methodology-specific behaviour from the project's
Strategy (allowed statuses, estimation mode) so there is no per-methodology
branching scattered across the codebase.
"""

import re
import uuid
from datetime import UTC, datetime

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

# Regex to parse a human task key like "SDM-7" or "PLT2-123".
_KEY_RE = re.compile(r"^([A-Z0-9]{2,10})-(\d+)$", re.IGNORECASE)


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
        """Return the project's top-level tasks honoring the optional filters."""

        project = await self._require_project(organization_id, project_id)
        tasks = await self.repo.list_for_project(
            organization_id,
            project_id,
            sprint_id=sprint_id,
            status=status,
            assignee_id=assignee_id,
            top_level_only=True,
        )
        name_map = await self._assignee_name_map(organization_id)
        return [self._to_read(task, name_map, project_code=project.code) for task in tasks]

    async def get_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskRead:
        """Return a single task (with subtask progress) or raise a 404."""

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        strategy = get_strategy(project.methodology)
        name_map = await self._assignee_name_map(organization_id)
        read = self._to_read(task, name_map, project_code=project.code)

        # Populate subtask progress only on single-task reads to avoid N+1.
        allowed = strategy.allowed_statuses()
        done_status = allowed[-1] if allowed else _CUSTOM_DEFAULT_STATUS
        total, done = await self.repo.get_subtask_counts(task.id, done_status)
        read.subtask_progress = (done / total) if total > 0 else None

        return read

    async def get_task_by_key(
        self, organization_id: uuid.UUID, key: str
    ) -> TaskRead:
        """Resolve a human task key (e.g. 'SDM-7') within the organization.

        Parses the key into project code + task number, then fetches both the
        project (to verify tenant) and the task.
        """

        match = _KEY_RE.match(key.strip().upper())
        if not match:
            raise AppException(
                "El identificador de tarea no es válido. Usa el formato 'CODIGO-N' (ej. 'SDM-7').",
                code="invalid_task_key",
                status_code=422,
            )
        code, number_str = match.group(1), match.group(2)
        task_number = int(number_str)

        project = await self.projects.get_by_code(organization_id, code)
        if project is None:
            raise AppException(
                f"No se encontró ningún proyecto con el código '{code}'.",
                code="project_not_found",
                status_code=404,
            )

        task = await self.repo.get_by_project_and_number(
            organization_id, project.id, task_number
        )
        if task is None:
            raise AppException(
                f"La tarea '{key}' no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )

        strategy = get_strategy(project.methodology)
        name_map = await self._assignee_name_map(organization_id)
        read = self._to_read(task, name_map, project_code=project.code)

        allowed = strategy.allowed_statuses()
        done_status = allowed[-1] if allowed else _CUSTOM_DEFAULT_STATUS
        total, done = await self.repo.get_subtask_counts(task.id, done_status)
        read.subtask_progress = (done / total) if total > 0 else None

        return read

    async def list_subtasks(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[TaskRead]:
        """Return the direct subtasks of a task."""

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        subtasks = await self.repo.list_for_project(
            organization_id,
            task.project_id,
            parent_task_id=task_id,
        )
        name_map = await self._assignee_name_map(organization_id)
        return [self._to_read(st, name_map, project_code=project.code) for st in subtasks]

    async def create_task(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: TaskCreate,
    ) -> TaskRead:
        """Validate against the methodology Strategy and persist a new task.

        When ``data.parent_task_id`` is set the service enforces the subtask
        business rules: task_type is coerced to 'subtask' and estimation_points
        are rejected (to avoid double-counting story points in velocity).
        """

        project = await self._require_project(organization_id, project_id)
        strategy = get_strategy(project.methodology)

        # -- Subtask validation -------------------------------------------
        is_subtask = data.parent_task_id is not None
        if is_subtask:
            assert data.parent_task_id is not None  # narrows for the type checker
            # Verify the parent belongs to the same project and organization.
            parent = await self.repo.get(organization_id, data.parent_task_id)
            if parent is None or parent.project_id != project_id:
                raise AppException(
                    "La tarea padre no existe en este proyecto.",
                    code="invalid_parent_task",
                    status_code=422,
                )
            if parent.parent_task_id is not None:
                raise AppException(
                    "No se pueden crear sub-subtareas (máximo un nivel de anidación).",
                    code="subtask_nesting_not_allowed",
                    status_code=422,
                )
            if data.estimation_points is not None:
                raise AppException(
                    "Las subtareas no admiten puntos de historia para evitar "
                    "el doble conteo del velocity.",
                    code="subtask_points_not_allowed",
                    status_code=422,
                )

        task_type = "subtask" if is_subtask else (data.task_type or "task")

        status = self._resolve_status(strategy, data.status)
        if not is_subtask:
            self._validate_estimation(
                strategy, data.estimation_points, data.estimation_hours
            )
        await self._verify_assignee(organization_id, data.assignee_id)
        await self._verify_sprint(organization_id, project_id, data.sprint_id)

        # Allocate task_number atomically (UPDATE ... RETURNING in same txn).
        task_number = await self.repo.allocate_task_number(project_id)

        task = Task(
            project_id=project_id,
            sprint_id=data.sprint_id,
            parent_task_id=data.parent_task_id,
            title=data.title,
            description=data.description,
            task_type=task_type,
            status=status,
            priority=data.priority,
            assignee_id=data.assignee_id,
            estimation_points=None if is_subtask else data.estimation_points,
            estimation_hours=data.estimation_hours,
            due_date=data.due_date,
            start_date=data.start_date,
            completed_at=self._resolve_completed_at(strategy, status, None),
            task_number=task_number,
        )
        task = await self.repo.create(task)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map, project_code=project.code)

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
            task.completed_at = self._resolve_completed_at(
                strategy, task.status, task.completed_at
            )

        # Reject estimation_points update on subtasks.
        if "estimation_points" in changes and task.parent_task_id is not None:
            raise AppException(
                "Las subtareas no admiten puntos de historia.",
                code="subtask_points_not_allowed",
                status_code=422,
            )

        next_points = changes.get("estimation_points", task.estimation_points)
        next_hours = changes.get("estimation_hours", task.estimation_hours)
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
        return self._to_read(task, name_map, project_code=project.code)

    async def delete_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> None:
        """Soft-delete a task."""

        task = await self._require_task(organization_id, task_id)
        task.is_active = False
        task.deleted_at = datetime.now(UTC)
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
        allowed = strategy.allowed_statuses()
        done = allowed[-1] if allowed else None
        if done is not None and status == done:
            return current or datetime.now(UTC)
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
        task: Task,
        name_map: dict[uuid.UUID, str],
        *,
        project_code: str | None = None,
    ) -> TaskRead:
        task.assignee_name = (
            name_map.get(task.assignee_id) if task.assignee_id else None
        )
        read = TaskRead.model_validate(task)
        if project_code and task.task_number is not None:
            read.task_key = f"{project_code}-{task.task_number}"
        return read
