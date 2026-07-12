"""Business logic for the executive ("vista de jefe") dashboard.

Everything is derived from each project's methodology Strategy so the metrics
stay correct regardless of how many columns a board has:

* ``first`` allowed status   -> not started.
* ``last`` allowed status    -> done.
* anything in between         -> in progress.

All figures are scoped to the caller's organization.
"""

import uuid
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.board_aware import resolve_board_strategy
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskRead


class _StatusBounds:
    """First/last allowed status for a project, with derived task predicates."""

    __slots__ = ("first", "last")

    def __init__(self, first: str | None, last: str | None) -> None:
        self.first = first
        self.last = last

    def is_done(self, status: str) -> bool:
        return self.last is not None and status == self.last

    def is_in_progress(self, status: str) -> bool:
        # Neither the first ("not started") nor the last ("done") column.
        return status != self.first and not self.is_done(status)

    def is_active(self, status: str) -> bool:
        # Anything not yet in the final/done column counts as active work.
        return not self.is_done(status)


class DashboardService:
    """Computes the executive dashboard for an organization."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.tasks = TaskRepository(db)

    async def executive(self, organization_id: uuid.UUID) -> dict:
        """Build the full executive payload for the caller's organization."""

        now = datetime.now(UTC)
        projects, _ = await self.projects.list_by_org(organization_id)
        projects = list(projects)
        tasks = list(await self.tasks.list_for_org(organization_id))
        members = await self.tasks.list_org_members(organization_id)

        name_map = {user.id: user.full_name for user, _ in members}
        bounds = await self._bounds_for_all(projects)

        by_assignee = self._build_by_assignee(tasks, bounds, name_map, members)
        at_risk = self._build_at_risk(tasks, bounds, name_map, now)
        workload = self._build_workload(tasks, bounds, name_map, members)
        projects_progress = self._build_projects_progress(
            projects, tasks, bounds
        )
        totals = self._build_totals(projects, tasks, bounds, now)

        return {
            "by_assignee": by_assignee,
            "at_risk": at_risk,
            "workload": workload,
            "projects_progress": projects_progress,
            "totals": totals,
        }

    async def performance(
        self,
        organization_id: uuid.UUID,
        sprint_id: uuid.UUID | None = None,
    ) -> dict:
        """Build per-collaborator performance metrics for the organization.

        When ``sprint_id`` is given the figures are restricted to that sprint's
        tasks. ``on_time_rate`` is the fraction of a collaborator's completed
        tasks (that carry a due date) finished on or before it; it is ``None``
        when the collaborator has no completed task with a due date, so the
        frontend can show "sin datos" instead of a misleading 100%.
        """

        now = datetime.now(UTC)
        projects, _ = await self.projects.list_by_org(organization_id)
        projects = list(projects)
        tasks = list(await self.tasks.list_for_org(organization_id))
        if sprint_id is not None:
            tasks = [task for task in tasks if task.sprint_id == sprint_id]
        members = await self.tasks.list_org_members(organization_id)

        bounds = await self._bounds_for_all(projects)

        # Per-user accumulators; private "_ontime_*" keys are stripped at the end.
        stats: dict[uuid.UUID, dict] = {
            user.id: {
                "user": {"id": user.id, "full_name": user.full_name},
                "completed_tasks": 0,
                "completed_points": 0,
                "active_count": 0,
                "overdue_count": 0,
                "_ontime_total": 0,
                "_ontime_hit": 0,
            }
            for user, _ in members
        }

        for task in tasks:
            if task.assignee_id is None:
                continue
            acc = stats.get(task.assignee_id)
            if acc is None:
                continue
            bound = bounds.get(task.project_id)
            if bound is None:
                continue

            if bound.is_done(task.status):
                acc["completed_tasks"] += 1
                acc["completed_points"] += task.estimation_points or 0
                if task.due_date is not None and task.completed_at is not None:
                    acc["_ontime_total"] += 1
                    if task.completed_at.date() <= task.due_date.date():
                        acc["_ontime_hit"] += 1
            else:
                acc["active_count"] += 1
                if task.due_date is not None and task.due_date < now:
                    acc["overdue_count"] += 1

        collaborators: list[dict] = []
        for user, _ in members:
            acc = stats[user.id]
            ontime_total = acc.pop("_ontime_total")
            ontime_hit = acc.pop("_ontime_hit")
            acc["on_time_rate"] = (
                ontime_hit / ontime_total if ontime_total else None
            )
            collaborators.append(acc)

        collaborators.sort(
            key=lambda row: (row["completed_points"], row["completed_tasks"]),
            reverse=True,
        )

        return {"collaborators": collaborators, "generated_at": now}

    # -- builders ----------------------------------------------------------

    def _build_by_assignee(
        self, tasks, bounds, name_map, members
    ) -> list[dict]:
        """Per assignee: their in-progress tasks and active task count."""

        in_progress: dict[uuid.UUID, list[TaskRead]] = {}
        active_count: dict[uuid.UUID, int] = {}

        for task in tasks:
            if task.assignee_id is None:
                continue
            bound = bounds.get(task.project_id)
            if bound is None:
                continue
            if bound.is_active(task.status):
                active_count[task.assignee_id] = (
                    active_count.get(task.assignee_id, 0) + 1
                )
            if bound.is_in_progress(task.status):
                in_progress.setdefault(task.assignee_id, []).append(
                    self._to_read(task, name_map)
                )

        result: list[dict] = []
        for user, _ in members:
            count = active_count.get(user.id, 0)
            if count == 0:
                continue
            result.append(
                {
                    "user": {"id": user.id, "full_name": user.full_name},
                    "in_progress": in_progress.get(user.id, []),
                    "active_count": count,
                }
            )
        result.sort(key=lambda row: row["active_count"], reverse=True)
        return result

    def _build_at_risk(self, tasks, bounds, name_map, now) -> list[TaskRead]:
        """Tasks overdue-and-not-done OR explicitly flagged at risk."""

        at_risk: list[TaskRead] = []
        for task in tasks:
            bound = bounds.get(task.project_id)
            if bound is None:
                continue
            if self._is_at_risk(task, bound, now):
                at_risk.append(self._to_read(task, name_map))
        return at_risk

    def _build_workload(
        self, tasks, bounds, name_map, members
    ) -> list[dict]:
        """Active task count per organization member (full team picture)."""

        active_count: dict[uuid.UUID, int] = {}
        for task in tasks:
            if task.assignee_id is None:
                continue
            bound = bounds.get(task.project_id)
            if bound is None:
                continue
            if bound.is_active(task.status):
                active_count[task.assignee_id] = (
                    active_count.get(task.assignee_id, 0) + 1
                )

        result = [
            {
                "user": {"id": user.id, "full_name": user.full_name},
                "active_count": active_count.get(user.id, 0),
            }
            for user, _ in members
        ]
        result.sort(key=lambda row: cast(int, row["active_count"]), reverse=True)
        return result

    def _build_projects_progress(
        self, projects, tasks, bounds
    ) -> list[dict]:
        """Per project completion metrics."""

        by_project: dict[uuid.UUID, list[Task]] = {}
        for task in tasks:
            by_project.setdefault(task.project_id, []).append(task)

        progress: list[dict] = []
        for project in projects:
            bound = bounds[project.id]
            project_tasks = by_project.get(project.id, [])
            total = len(project_tasks)
            done = sum(1 for t in project_tasks if bound.is_done(t.status))
            in_progress = sum(
                1 for t in project_tasks if bound.is_in_progress(t.status)
            )
            percent_done = round(done / total * 100) if total else 0
            progress.append(
                {
                    "project": {
                        "id": project.id,
                        "name": project.name,
                        "methodology": project.methodology.value
                        if hasattr(project.methodology, "value")
                        else project.methodology,
                    },
                    "total": total,
                    "done": done,
                    "in_progress": in_progress,
                    "percent_done": percent_done,
                }
            )
        return progress

    def _build_totals(self, projects, tasks, bounds, now) -> dict:
        """Organization-wide headline counters."""

        overdue = 0
        at_risk = 0
        for task in tasks:
            bound = bounds.get(task.project_id)
            if bound is None:
                continue
            if self._is_overdue(task, bound, now):
                overdue += 1
            if self._is_at_risk(task, bound, now):
                at_risk += 1

        return {
            "projects": len(projects),
            "tasks": len(tasks),
            "overdue": overdue,
            "at_risk": at_risk,
        }

    # -- predicates --------------------------------------------------------

    @staticmethod
    def _is_overdue(task: Task, bound: _StatusBounds, now: datetime) -> bool:
        if task.due_date is None:
            return False
        return task.due_date < now and not bound.is_done(task.status)

    def _is_at_risk(
        self, task: Task, bound: _StatusBounds, now: datetime
    ) -> bool:
        return bool(task.risk_flag) or self._is_overdue(task, bound, now)

    # -- helpers -----------------------------------------------------------

    async def _bounds_for(self, project: Project) -> _StatusBounds:
        """First/last allowed status for ``project``, from its LIVE board.

        Uses ``resolve_board_strategy`` (design.md C1) instead of the raw
        base strategy, so a reordered/reconfigured board is reflected
        immediately — the base strategy alone would keep returning the
        original ``default_columns()`` forever.
        """

        strategy = await resolve_board_strategy(project, self.db)
        allowed = strategy.allowed_statuses()
        first = allowed[0] if allowed else None
        last = allowed[-1] if allowed else None
        return _StatusBounds(first, last)

    async def _bounds_for_all(
        self, projects: list[Project]
    ) -> dict[uuid.UUID, _StatusBounds]:
        """Resolve ``_bounds_for`` for every project.

        Sequential by necessity: ``AsyncSession`` is not safe for concurrent
        use across coroutines sharing the same session, so this cannot be
        parallelized with ``asyncio.gather``. The batched, N+1-free path
        (single query for many projects) is reserved for
        ``ProjectRepository.list_boards_with_columns_for_projects``, used by
        ``ProjectService.list_projects`` (design.md C1).
        """

        return {project.id: await self._bounds_for(project) for project in projects}

    @staticmethod
    def _to_read(task: Task, name_map: dict[uuid.UUID, str]) -> TaskRead:
        task.assignee_name = (
            name_map.get(task.assignee_id) if task.assignee_id else None
        )
        return TaskRead.model_validate(task)
