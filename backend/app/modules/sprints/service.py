"""Business logic for sprints."""

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.board_aware import resolve_board_strategy
from app.methodology.factory import get_strategy
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.sprints.models import Sprint
from app.modules.sprints.naming import next_sprint_name
from app.modules.sprints.repository import SprintRepository
from app.modules.sprints.schemas import (
    BacklogAggregate,
    SprintCreate,
    SprintListItem,
    SprintRead,
    SprintUpdate,
    VelocityRead,
    VelocitySprintEntry,
)
from app.shared.enums import EstimationMode
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

# Lifecycle values a sprint may take.
_ALLOWED_STATUSES = ("draft", "active", "closed")


class SprintService:
    """Orchestrates sprint use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = SprintRepository(db)
        self.projects = ProjectRepository(db)

    async def list_sprints(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[SprintListItem], int, BacklogAggregate]:
        """Return ``(sprints, total, backlog)`` for the project.

        ``aggregate_tasks_by_sprint`` is called EXACTLY ONCE regardless of how
        many sprints the project has (design.md D1 — one grouped query, no
        N+1); its ``None`` key is the backlog aggregate.
        """

        await self._require_sprints_enabled(organization_id, project_id)
        sprints, total = await self.repo.list_for_project(
            organization_id, project_id, pagination
        )
        aggregates = await self.repo.aggregate_tasks_by_sprint(
            organization_id, project_id
        )

        items = [
            SprintListItem(
                **SprintRead.model_validate(sprint).model_dump(),
                story_count=aggregates.get(sprint.id, (0, 0.0))[0],
                estimation_hours_sum=aggregates.get(sprint.id, (0, 0.0))[1],
            )
            for sprint in sprints
        ]
        backlog_count, backlog_hours = aggregates.get(None, (0, 0.0))
        backlog = BacklogAggregate(
            story_count=backlog_count, estimation_hours_sum=backlog_hours
        )
        return items, total, backlog

    async def create_sprint(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: SprintCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SprintRead:
        """Create a sprint within a sprint-enabled project.

        ``name`` blank/omitted (change 29-sprint-borrador): auto-named from
        the project's most recently created sprint via ``next_sprint_name``.
        ``status`` is derived from the presence of BOTH dates — ``active``
        when both ``start_date``/``end_date`` are given (retrocompatible with
        the previous hardcoded behavior), ``draft`` otherwise.
        """

        project = await self._require_sprints_enabled(organization_id, project_id)

        name = data.name
        if name is None:
            previous = await self.repo.last_for_project(organization_id, project_id)
            name = next_sprint_name(previous.name if previous else None, project.code)

        status = "active" if data.start_date and data.end_date else "draft"

        sprint = Sprint(
            project_id=project_id,
            name=name,
            goal=data.goal,
            start_date=data.start_date,
            end_date=data.end_date,
            status=status,
            created_by=actor_id,
            updated_by=actor_id,
        )
        sprint = await self.repo.create(sprint)
        return SprintRead.model_validate(sprint)

    async def suggest_next_name(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> str:
        """Return the SUGGESTED name for the project's next sprint.

        Reuses the exact same computation as ``create_sprint``'s auto-name
        fallback (``repo.last_for_project`` + ``next_sprint_name``) but never
        persists anything — no ``INSERT``/``commit``, purely a read.
        """

        project = await self._require_sprints_enabled(organization_id, project_id)
        previous = await self.repo.last_for_project(organization_id, project_id)
        return next_sprint_name(previous.name if previous else None, project.code)

    async def update_sprint(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID,
        data: SprintUpdate,
        *,
        actor_id: uuid.UUID | None = None,
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

        # Name/goal/dates are applied FIRST so the "status=active" dates
        # guard below evaluates the state RESULTING from this same payload
        # (e.g. status + dates sent together in one PATCH), not the state
        # before the request (Reconciliación #3 — the guard applies to ANY
        # transition mechanism, not only POST /sprints/{id}/start).
        for field in ("name", "goal", "start_date", "end_date"):
            if field in changes:
                setattr(sprint, field, changes[field])

        if "status" in changes:
            status = changes["status"]
            if status not in _ALLOWED_STATUSES:
                raise AppException(
                    "El estado del sprint debe ser 'draft', 'active' o 'closed'.",
                    code="invalid_sprint_status",
                    status_code=422,
                )
            if status == "active" and (
                sprint.start_date is None or sprint.end_date is None
            ):
                raise AppException(
                    "El sprint necesita fecha de inicio y fin antes de iniciarse.",
                    code="sprint_missing_dates",
                    status_code=422,
                )
            sprint.status = status

        sprint.updated_by = actor_id
        sprint = await self.repo.save(sprint)
        return SprintRead.model_validate(sprint)

    async def start_sprint(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> SprintRead:
        """Transition a ``draft`` sprint to ``active`` (mirrors ``close_sprint``).

        404 if the sprint doesn't exist/isn't in this org; 409
        ``sprint_already_started`` if already ``active``; 422
        ``sprint_already_closed`` if ``closed`` (Reconciliación #2 — the same
        ``code`` as the 409 of ``/close``, distinguished by ``status_code``
        and endpoint); 422 ``sprint_missing_dates`` if either date is absent.
        """

        sprint = await self.repo.get(organization_id, sprint_id)
        if sprint is None:
            raise AppException(
                "El sprint no existe o no tienes acceso a él.",
                code="sprint_not_found",
                status_code=404,
            )

        if sprint.status == "active":
            raise AppException(
                "Este sprint ya está iniciado.",
                code="sprint_already_started",
                status_code=409,
            )

        if sprint.status == "closed":
            raise AppException(
                "Este sprint ya está cerrado y no puede iniciarse.",
                code="sprint_already_closed",
                status_code=422,
            )

        if sprint.start_date is None or sprint.end_date is None:
            raise AppException(
                "El sprint necesita fecha de inicio y fin antes de iniciarse.",
                code="sprint_missing_dates",
                status_code=422,
            )

        sprint.status = "active"
        sprint.updated_by = actor_id
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

        strategy = await resolve_board_strategy(project, self.projects.db)
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
        today = datetime.now(UTC).date()
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

    async def close_sprint(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID,
        target_sprint_id: uuid.UUID | None = None,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> dict:
        """Close a sprint: tally completed points and move incomplete tasks.

        Idempotent on the 409 path — re-closing an already-closed sprint returns
        a conflict so callers can detect duplicates without silent no-ops.

        The entire operation (task moves + sprint update) is committed in a single
        transaction via ``repo.save()``.
        """

        sprint = await self.repo.get(organization_id, sprint_id)
        if sprint is None:
            raise AppException(
                "El sprint no existe o no tienes acceso a él.",
                code="sprint_not_found",
                status_code=404,
            )

        if sprint.status == "closed":
            raise AppException(
                "El sprint ya está cerrado.",
                code="sprint_already_closed",
                status_code=409,
            )

        if target_sprint_id is not None:
            target = await self.repo.get_for_project(
                organization_id, sprint.project_id, target_sprint_id
            )
            if target is None:
                raise AppException(
                    "El sprint destino no existe en este proyecto.",
                    code="target_sprint_not_found",
                    status_code=404,
                )
            if target.status == "closed":
                raise AppException(
                    "No puedes mover tareas a un sprint que ya está cerrado.",
                    code="target_sprint_closed",
                    status_code=422,
                )

        completed_points = await self.repo.sum_done_points_for_sprint(
            organization_id, sprint_id
        )
        moved_task_ids = await self.repo.count_and_move_incomplete_tasks(
            organization_id, sprint_id, target_sprint_id, actor_id
        )
        tasks_moved = len(moved_task_ids)

        if moved_task_ids:
            from app.modules.activity.recorder import (
                ACTOR_TYPE_SYSTEM,
                record_task_history,
            )

            old_value = str(sprint_id)
            new_value = str(target_sprint_id) if target_sprint_id is not None else None
            for moved_task_id in moved_task_ids:
                await record_task_history(
                    self.repo.db,
                    organization_id,
                    moved_task_id,
                    None,
                    ACTOR_TYPE_SYSTEM,
                    {"sprint_id": (old_value, new_value)},
                )

        sprint.status = "closed"
        sprint.closed_at = datetime.now(UTC)
        sprint.completed_points = completed_points
        sprint.updated_by = actor_id
        sprint = await self.repo.save(sprint)

        return {
            "sprint": SprintRead.model_validate(sprint),
            "tasks_moved": tasks_moved,
        }

    async def velocity(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> VelocityRead:
        """Return the velocity report for a project.

        ``series`` contains every closed sprint ordered by ``closed_at`` so the
        frontend can plot a velocity trend chart. ``average_velocity`` is the
        arithmetic mean of ``completed_points`` across all closed sprints.
        ``backlog_points`` counts unassigned + incomplete task points.
        ``projected_sprints`` estimates how many more sprints are needed at the
        current average pace (``None`` when average is zero).
        """

        project = await self.projects.get(organization_id, project_id)
        if project is None:
            raise AppException(
                "El proyecto no existe o no tienes acceso a él.",
                code="project_not_found",
                status_code=404,
            )

        closed_sprints = await self.repo.list_closed_for_project(
            organization_id, project_id
        )

        series = [
            VelocitySprintEntry(
                sprint_id=s.id,
                name=s.name,
                completed_points=s.completed_points,
                closed_at=s.closed_at,
            )
            for s in closed_sprints
        ]

        average_velocity = (
            sum(e.completed_points for e in series) / len(series)
            if series
            else 0.0
        )

        backlog_points = await self.repo.count_backlog_points_for_project(
            organization_id, project_id
        )

        projected_sprints = (
            math.ceil(backlog_points / average_velocity)
            if average_velocity > 0
            else None
        )

        return VelocityRead(
            series=series,
            average_velocity=average_velocity,
            backlog_points=backlog_points,
            projected_sprints=projected_sprints,
        )

    async def _require_sprints_enabled(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project:
        """Return the resolved project, or raise if sprints aren't enabled.

        The single point of reading ``get_strategy(project.methodology)
        .sprints_enabled`` in this module (never ``if methodology == ...``).
        Returns the ``Project`` (not just ``None``) so callers that need it —
        e.g. ``create_sprint``'s ``project.code`` for auto-naming — don't
        have to re-fetch it.
        """

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
        return project
