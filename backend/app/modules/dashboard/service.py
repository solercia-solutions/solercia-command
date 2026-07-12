"""Business logic for the executive ("vista de jefe") dashboard.

Everything is derived from each project's methodology Strategy so the metrics
stay correct regardless of how many columns a board has:

* ``first`` allowed status   -> not started.
* ``last`` allowed status    -> done.
* anything in between         -> in progress.

All figures are scoped to the caller's organization.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.board_aware import resolve_board_strategy
from app.modules.activity.repository import ActivityRepository
from app.modules.projects.models import Project
from app.modules.projects.repository import ProjectRepository
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskRead
from app.modules.time_logs.repository import TimeLogRepository

# Default lookback window for "no_recent_activity" (dashboard-executive.md,
# "Colaboradores sin actividad reciente").
DEFAULT_WORK_GAP_THRESHOLD_DAYS = 3


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
        self.time_logs = TimeLogRepository(db)
        self.activity = ActivityRepository(db)

    async def executive(
        self,
        organization_id: uuid.UUID,
        threshold_days: int = DEFAULT_WORK_GAP_THRESHOLD_DAYS,
    ) -> dict:
        """Build the full executive payload for the caller's organization.

        ``threshold_days`` governs the ``work_gap.no_recent_activity`` window
        (dashboard-executive.md, "Colaboradores sin actividad reciente").
        """

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
        work_gap = await self._work_gap(
            organization_id, tasks, bounds, members, now, threshold_days
        )

        return {
            "by_assignee": by_assignee,
            "at_risk": at_risk,
            "workload": workload,
            "projects_progress": projects_progress,
            "totals": totals,
            "work_gap": work_gap,
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

    async def _work_gap(
        self,
        organization_id: uuid.UUID,
        tasks: list[Task],
        bounds: dict[uuid.UUID, "_StatusBounds"],
        members,
        now: datetime,
        threshold_days: int,
    ) -> dict:
        """Build the ``work_gap`` block: hours/tasks cruce + no-recent-activity list.

        Per collaborator with at least one active assigned task: ``hours_logged``
        (all-time sum of ``TaskTimeLog.hours``) vs. ``hours_estimated`` (sum of
        ``estimation_hours`` of their active tasks), and ``tasks_assigned`` vs.
        ``tasks_with_activity`` (tasks with a ``TaskHistory``/``TaskTimeLog``
        entry within the last ``threshold_days`` days). ``no_recent_activity``
        lists collaborators whose most recent activity (of either kind, ANY
        task) is older than ``threshold_days`` days, or who have none at all
        (dashboard-executive.md, "Colaboradores sin actividad reciente").

        Fixed number of aggregation queries regardless of team/task size: 2
        for hours/last-activity per source + 2 for "recent task ids" per
        source (design.md, "Cruce dashboard sin N+1").
        """

        cutoff_date = now.date() - timedelta(days=threshold_days)
        cutoff_datetime = now - timedelta(days=threshold_days)

        active_task_ids_by_user: dict[uuid.UUID, set[uuid.UUID]] = {}
        for task in tasks:
            if task.assignee_id is None:
                continue
            bound = bounds.get(task.project_id)
            if bound is None or not bound.is_active(task.status):
                continue
            active_task_ids_by_user.setdefault(task.assignee_id, set()).add(task.id)

        hours_logged_by_user = await self.time_logs.hours_by_user(organization_id)
        hours_estimated_by_user = self._hours_estimated_by_user(tasks, bounds)
        recent_task_ids = await self.time_logs.task_ids_with_recent_entries(
            organization_id, cutoff_date
        )
        recent_task_ids |= await self.activity.task_ids_with_recent_entries(
            organization_id, cutoff_datetime
        )
        last_log_activity = await self.time_logs.last_activity_by_user(organization_id)
        last_history_activity = await self.activity.last_activity_by_actor(
            organization_id
        )

        by_user: list[dict] = []
        no_recent_activity: list[dict] = []
        for member_user, _ in members:
            assigned_ids = active_task_ids_by_user.get(member_user.id)
            if not assigned_ids:
                continue

            tasks_with_activity = sum(
                1 for task_id in assigned_ids if task_id in recent_task_ids
            )
            by_user.append(
                {
                    "user": {"id": member_user.id, "full_name": member_user.full_name},
                    "hours_logged": hours_logged_by_user.get(
                        member_user.id, Decimal("0")
                    ),
                    "hours_estimated": hours_estimated_by_user.get(
                        member_user.id, Decimal("0")
                    ),
                    "tasks_assigned": len(assigned_ids),
                    "tasks_with_activity": tasks_with_activity,
                }
            )

            last_activity_date = last_log_activity.get(member_user.id)
            last_history_dt = last_history_activity.get(member_user.id)
            if last_history_dt is not None:
                history_date = last_history_dt.date()
                if last_activity_date is None or history_date > last_activity_date:
                    last_activity_date = history_date

            if last_activity_date is None or last_activity_date < cutoff_date:
                no_recent_activity.append(
                    {"id": member_user.id, "full_name": member_user.full_name}
                )

        return {"by_user": by_user, "no_recent_activity": no_recent_activity}

    @staticmethod
    def _hours_estimated_by_user(
        tasks: list[Task], bounds: dict[uuid.UUID, "_StatusBounds"]
    ) -> dict[uuid.UUID, Decimal]:
        """Sum ``estimation_hours`` of each user's active assigned tasks, in Python."""

        totals: dict[uuid.UUID, Decimal] = {}
        for task in tasks:
            if task.assignee_id is None:
                continue
            bound = bounds.get(task.project_id)
            if bound is None or not bound.is_active(task.status):
                continue
            hours = task.estimation_hours or Decimal("0")
            totals[task.assignee_id] = totals.get(task.assignee_id, Decimal("0")) + hours
        return totals

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
