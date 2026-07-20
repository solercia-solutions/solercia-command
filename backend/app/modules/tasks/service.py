"""Business logic for tasks.

The service derives all methodology-specific behaviour from the project's
Strategy (allowed statuses, estimation mode) so there is no per-methodology
branching scattered across the codebase.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.base import MethodologyStrategy
from app.methodology.board_aware import resolve_board_strategy
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import MemberRead, TaskCreate, TaskRead, TaskUpdate
from app.shared.enums import EstimationMode, Priority
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

if TYPE_CHECKING:
    # Type-only: `tasks` never imports `boards`/`task_links`/`checklists` at
    # module level (design.md C4). Every runtime use is a deferred import
    # inside the method that needs it.
    from app.modules.boards.models import BoardColumn
    from app.modules.labels.schemas import LabelRead
    from app.modules.task_links.schemas import BlockerRef

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
        label_id: Sequence[uuid.UUID] | None = None,
        priority: Priority | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        q: str | None = None,
        task_type: str | None = None,
        parent_task_id: uuid.UUID | None = None,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TaskRead], int]:
        """Return the project's top-level tasks honoring the optional filters.

        Returns ``(tasks, total)`` — see ``TaskRepository.list_for_project``.
        Raises a ``422`` when ``due_from`` is after ``due_to`` (change
        10-busqueda-global, R8) before ever touching the repository.

        ``task_type`` filters by exact equality. ``parent_task_id`` returns
        the direct children of that task; since children are by definition
        NOT top-level, this filter disables the default top-level-only
        restriction of the listing.
        """

        self._validate_due_range(due_from, due_to)
        project = await self._require_project(organization_id, project_id)
        tasks, total = await self.repo.list_for_project(
            organization_id,
            project_id,
            sprint_id=sprint_id,
            status=status,
            assignee_id=assignee_id,
            label_ids=label_id,
            priority=priority,
            due_from=due_from,
            due_to=due_to,
            q=q,
            task_type=task_type,
            parent_task_id=parent_task_id,
            top_level_only=parent_task_id is None,
            pagination=pagination,
        )
        name_map = await self._assignee_name_map(organization_id)
        reads = [
            self._to_read(task, name_map, project_code=project.code) for task in tasks
        ]
        return reads, total

    @staticmethod
    def _validate_due_range(due_from: date | None, due_to: date | None) -> None:
        """Reject an inverted ``due_from``/``due_to`` range (R8)."""

        if due_from is not None and due_to is not None and due_from > due_to:
            raise AppException(
                "La fecha 'due_from' no puede ser posterior a 'due_to'.",
                code="invalid_due_range",
                status_code=422,
            )

    async def get_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskRead:
        """Return a single task (with subtask progress) or raise a 404."""

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        strategy = await resolve_board_strategy(project, self.repo.db)
        name_map = await self._assignee_name_map(organization_id)
        read = self._to_read(task, name_map, project_code=project.code)

        # Populate subtask progress, blocking state, labels and checklist
        # progress only on single-task reads to avoid N+1.
        read.subtask_progress = await self._subtask_progress(task.id, strategy)
        read.is_blocked, read.blockers = await self._blocking_state(task.id)
        read.labels = await self._labels_for_task(task.id)
        read.checklist_progress = await self._checklist_progress(task.id)

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

        strategy = await resolve_board_strategy(project, self.repo.db)
        name_map = await self._assignee_name_map(organization_id)
        read = self._to_read(task, name_map, project_code=project.code)

        read.subtask_progress = await self._subtask_progress(task.id, strategy)
        read.is_blocked, read.blockers = await self._blocking_state(task.id)
        read.labels = await self._labels_for_task(task.id)
        read.checklist_progress = await self._checklist_progress(task.id)

        return read

    async def list_subtasks(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> list[TaskRead]:
        """Return the direct subtasks of a task."""

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        subtasks, _ = await self.repo.list_for_project(
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
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaskRead:
        """Validate against the methodology Strategy and persist a new task.

        When ``data.parent_task_id`` is set the parent rules depend on the
        parent's ``task_type``:

        - Parent ``epic`` — the child KEEPS its requested ``task_type``
          (default ``task``) and MAY carry ``estimation_points``; a nested
          ``epic`` is rejected (``epic_nesting_not_allowed``, an epic can
          never have a parent).
        - Any other parent — the child is coerced to ``subtask`` and
          ``estimation_points`` are rejected (to avoid double-counting story
          points in velocity). A ``subtask`` parent is always rejected
          (``subtask_nesting_not_allowed``): a subtask can never be a parent.
        """

        project = await self._require_project(organization_id, project_id)
        strategy = await resolve_board_strategy(project, self.repo.db)

        # -- Parent/child validation ---------------------------------------
        requested_type = data.task_type or "task"
        is_subtask = False
        if data.parent_task_id is not None:
            # Verify the parent belongs to the same project and organization.
            parent = await self.repo.get(organization_id, data.parent_task_id)
            if parent is None or parent.project_id != project_id:
                raise AppException(
                    "La tarea padre no existe en este proyecto.",
                    code="invalid_parent_task",
                    status_code=422,
                )
            if parent.task_type == "subtask":
                raise AppException(
                    "No se pueden crear sub-subtareas (máximo un nivel de anidación).",
                    code="subtask_nesting_not_allowed",
                    status_code=422,
                )
            if parent.task_type == "epic" and requested_type != "subtask":
                # An epic is a REAL parent: the child keeps its requested
                # type and may carry points. Only a nested epic is forbidden
                # — an epic can never have a parent. An explicit 'subtask'
                # request under an epic falls through to the subtask branch
                # so the "subtasks never carry points" invariant stays
                # airtight for the update guard.
                if requested_type == "epic":
                    raise AppException(
                        "Una épica no puede anidarse bajo otra épica.",
                        code="epic_nesting_not_allowed",
                        status_code=422,
                    )
            else:
                if data.estimation_points is not None:
                    raise AppException(
                        "Las subtareas no admiten puntos de historia para evitar "
                        "el doble conteo del velocity.",
                        code="subtask_points_not_allowed",
                        status_code=422,
                    )
                is_subtask = True

        task_type = "subtask" if is_subtask else requested_type

        status, board_column_id = await self._resolve_create_status_and_column(
            project_id, strategy, data.status, data.board_column_id
        )
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
            board_column_id=board_column_id,
            priority=data.priority,
            assignee_id=data.assignee_id,
            estimation_points=None if is_subtask else data.estimation_points,
            estimation_hours=data.estimation_hours,
            due_date=data.due_date,
            start_date=data.start_date,
            completed_at=self._resolve_completed_at(strategy, status, None),
            task_number=task_number,
            created_by=actor_id,
            updated_by=actor_id,
        )
        task = await self.repo.create(task)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map, project_code=project.code)

    # Fields tracked for TaskHistory (activity-history.md, "Captura automática
    # en mutaciones de usuario" — the exact set the spec requires; notably no
    # ``due_date``, design.md gate correction #3).
    _HISTORY_TRACKED_FIELDS = (
        "status",
        "assignee_id",
        "estimation_points",
        "estimation_hours",
        "sprint_id",
        "priority",
    )

    async def update_task(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        data: TaskUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaskRead:
        """Apply a partial update, re-validating methodology-driven fields.

        A pre-mutation snapshot of the tracked fields is diffed against their
        post-mutation values and recorded via ``record_task_history`` (actor
        type ``user``) BEFORE ``repo.save()`` — its single ``commit()`` seals
        the task mutation and the new history rows in one transaction
        (design.md, "Decisión: detección de cambios por snapshot
        pre-mutación").
        """

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        strategy = await resolve_board_strategy(project, self.repo.db)

        snapshot = {
            field: getattr(task, field) for field in self._HISTORY_TRACKED_FIELDS
        }

        changes = data.model_dump(exclude_unset=True)

        if "status" in changes:
            from app.modules.boards.repository import BoardRepository
            from app.modules.boards.service import BoardService

            board = await BoardRepository(self.repo.db).get_board_with_columns(
                task.project_id
            )
            columns = board.columns if board is not None else []
            target = self._resolve_column_for_status(columns, changes["status"])
            # Same WIP-enforcing code path as PATCH /tasks/{id}/column
            # (design.md, "un solo camino WIP"); commit=False defers the
            # actual write to this method's own save() below so the status
            # move and every other field change land in ONE transaction.
            task = await BoardService(self.repo.db).move_to_column(
                task, target, actor_id=actor_id, enforce_wip=True, commit=False
            )
            task.completed_at = self._resolve_completed_at(
                strategy, task.status, task.completed_at
            )

        # Reject estimation_points update on REAL subtasks (by task_type,
        # not by having a parent): children of an epic keep their own type
        # and may carry points (epics-as-parents rule in create_task).
        if "estimation_points" in changes and task.task_type == "subtask":
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

        await self._record_history_diff(
            organization_id, task, snapshot, actor_id=actor_id
        )

        task.updated_by = actor_id
        task = await self.repo.save(task)
        name_map = await self._assignee_name_map(organization_id)
        return self._to_read(task, name_map, project_code=project.code)

    async def _record_history_diff(
        self,
        organization_id: uuid.UUID,
        task: Task,
        snapshot: dict[str, object],
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Diff ``snapshot`` (pre-mutation) against the task's current in-memory
        values and stage one TaskHistory row per field that actually changed.
        """

        from app.modules.activity.recorder import ACTOR_TYPE_USER, record_task_history

        serialize = self._serialize_history_value
        diff = {
            field: (serialize(before), serialize(getattr(task, field)))
            for field, before in snapshot.items()
            if before != getattr(task, field)
        }
        if diff:
            await record_task_history(
                self.repo.db, organization_id, task.id, actor_id, ACTOR_TYPE_USER, diff
            )

    @staticmethod
    def _serialize_history_value(value: object) -> str | None:
        """Render a tracked field's value as the ``Text`` old/new_value TaskHistory expects."""

        if value is None:
            return None
        if hasattr(value, "value"):  # Enum members (e.g. Priority)
            return str(value.value)
        return str(value)

    async def move_task_column(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        board_column_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> TaskRead:
        """Move a task to ``board_column_id``, deriving ``status`` from its ``status_key``.

        Canonical entry point for board moves (``PATCH /tasks/{id}/column``).
        The column MUST belong to the task's own project board — a column
        that only exists on a DIFFERENT project (or that a fixed methodology
        never seeded, e.g. planner's board has no "In Review" column) is
        rejected the same way an unknown id would be (tasks.md delta,
        "Movimiento a estado no permitido por la strategy").
        """

        from app.modules.boards.repository import BoardRepository
        from app.modules.boards.service import BoardService

        task = await self._require_task(organization_id, task_id)
        project = await self._require_project(organization_id, task.project_id)
        strategy = await resolve_board_strategy(project, self.repo.db)

        board = await BoardRepository(self.repo.db).get_board_with_columns(
            project.id
        )
        columns = board.columns if board is not None else []
        target = next((c for c in columns if c.id == board_column_id), None)
        if target is None:
            raise AppException(
                "La columna indicada no pertenece al board de este proyecto.",
                code="invalid_board_column",
                status_code=422,
            )

        task = await BoardService(self.repo.db).move_to_column(
            task, target, actor_id=actor_id, enforce_wip=True, commit=False
        )
        task.completed_at = self._resolve_completed_at(
            strategy, task.status, task.completed_at
        )
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
    def _resolve_column_for_status(
        columns: Sequence["BoardColumn"], status: str
    ) -> "BoardColumn":
        """Find the column whose ``status_key`` equals ``status`` among ``columns``.

        Raises 422 ``board_has_no_columns`` when the board has none, or 422
        ``invalid_status`` listing the allowed ``status_key`` values when
        ``status`` matches none of them. Used by ``update_task``'s ``status``
        field so it shares the SAME allowed-values contract as
        ``move_task_column``/``_resolve_create_status_and_column``.
        """

        if not columns:
            raise AppException(
                "El board de este proyecto no tiene columnas configuradas. "
                "Agrega al menos una columna antes de crear o mover tareas.",
                code="board_has_no_columns",
                status_code=422,
            )
        column = next((c for c in columns if c.status_key == status), None)
        if column is None:
            allowed = ", ".join(c.status_key for c in columns)
            raise AppException(
                "El estado seleccionado no es válido para esta metodología. "
                f"Estados permitidos: {allowed}.",
                code="invalid_status",
                status_code=422,
            )
        return column

    async def _resolve_create_status_and_column(
        self,
        project_id: uuid.UUID,
        strategy: MethodologyStrategy,
        status: str | None,
        board_column_id: uuid.UUID | None,
    ) -> tuple[str, uuid.UUID | None]:
        """Resolve ``(status, board_column_id)`` for a new task.

        An explicit ``board_column_id`` wins: the resulting ``status`` is that
        column's ``status_key`` (validated to belong to this project's
        board). Otherwise falls back to the existing ``status`` string
        resolution (``_resolve_status``, defaulting to the first allowed
        status — which is the first column by ``order``), and looks up the
        matching column for it (tasks.md delta, "Campo board_column_id").

        `boards` is reached via a deferred import per design.md C4: `tasks`
        never imports `boards.service`/`boards.router` at module level.
        """

        from app.modules.boards.repository import BoardRepository

        board = await BoardRepository(self.repo.db).get_board_with_columns(
            project_id
        )
        columns = board.columns if board is not None else []

        if board_column_id is not None:
            column = next((c for c in columns if c.id == board_column_id), None)
            if column is None:
                raise AppException(
                    "La columna indicada no pertenece al board de este proyecto.",
                    code="invalid_board_column",
                    status_code=422,
                )
            return column.status_key, column.id

        resolved_status = self._resolve_status(strategy, status)
        matched = next((c for c in columns if c.status_key == resolved_status), None)
        return resolved_status, matched.id if matched else None

    async def _subtask_progress(
        self, task_id: uuid.UUID, strategy: MethodologyStrategy
    ) -> float | None:
        """Return the done/total subtask ratio, or ``None`` when not computable.

        Only reachable when the project's board has at least one column — a
        task can only exist under a columnless board's project if it predates
        removal of the last column, which design.md D5 forbids at runtime.
        """

        allowed = strategy.allowed_statuses()
        if not allowed:
            return None
        total, done = await self.repo.get_subtask_counts(task_id, allowed[-1])
        return (done / total) if total > 0 else None

    async def _blocking_state(
        self, task_id: uuid.UUID
    ) -> tuple[bool, list["BlockerRef"]]:
        """Return ``(is_blocked, blockers)`` for a single-task read (design.md,
        "Enriquecer el detalle sin N+1"). Deferred import: `tasks` never
        depends on `task_links` at module level (design.md C4).
        """

        from app.modules.task_links.repository import TaskDependencyRepository
        from app.modules.task_links.schemas import BlockerRef

        rows = await TaskDependencyRepository(self.repo.db).get_incomplete_blockers(
            task_id
        )
        blockers = [BlockerRef(task_id=tid, title=title) for tid, title in rows]
        return (len(blockers) > 0, blockers)

    async def _labels_for_task(self, task_id: uuid.UUID) -> list["LabelRead"]:
        """Return the task's active labels for a single-task read (labels.md).

        Deferred import: `tasks` never depends on `labels`' repository at
        module level (design.md C4) — `LabelRead` is imported directly in
        `tasks.schemas` since it composes `TaskRead`, a lighter, deliberate
        exception documented there.
        """

        from app.modules.labels.repository import LabelRepository
        from app.modules.labels.schemas import LabelRead

        labels = await LabelRepository(self.repo.db).list_labels_for_task(task_id)
        return [LabelRead.model_validate(label) for label in labels]

    async def _checklist_progress(self, task_id: uuid.UUID) -> float | None:
        """Return the done/total ratio across every active checklist of a task.

        ``None`` when the task has no checklist items (checklists.md R7,
        design.md Interfaces/Contracts — same shape as ``subtask_progress``).
        Deferred import: `tasks` never depends on `checklists` at module
        level (design.md C4).
        """

        from app.modules.checklists.service import ChecklistService

        done, total = await ChecklistService(self.repo.db).get_checklist_progress(
            task_id
        )
        return (done / total) if total > 0 else None

    @staticmethod
    def _resolve_status(
        strategy: MethodologyStrategy,
        status: str | None,
        *,
        allow_default: bool = True,
    ) -> str:
        """Validate a status against the methodology or pick a sensible default.

        Raises a 422 ``board_has_no_columns`` when the board has zero columns
        configured — there is no permissive fallback (design.md C2): a
        methodology (including ``custom``) with no columns blocks both
        creation and movement of tasks until at least one column exists.
        """

        allowed = strategy.allowed_statuses()

        if not allowed:
            raise AppException(
                "El board de este proyecto no tiene columnas configuradas. "
                "Agrega al menos una columna antes de crear o mover tareas.",
                code="board_has_no_columns",
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
