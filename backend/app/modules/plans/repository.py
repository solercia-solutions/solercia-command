"""Data-access layer for institutional plans (change 45a, design.md D-D/D-G/D-M).

Only this layer talks to SQLAlchemy. Rules that shape it:

* ``plan_activities`` has NO ``organization_id`` (P7): the tenant is reached
  transitively through ``plans``. EVERY read and delete composes
  :meth:`_activity_scope` / :meth:`_require_activity` instead of writing its own
  ``JOIN plans`` — forgetting the JOIN in one query would leak rows across
  organizations (design.md D-D).
* NEVER commits, rolls back or flushes on its own
  (agents/rules/solercia-persistence.md): the service owns the transaction,
  which is what lets an importer write a whole plan atomically (D-M). Primary
  keys are assigned when the object is created, so no flush is needed to
  chain ``upsert_plan`` -> ``upsert_activity``; SQLAlchemy autoflush covers the
  reads that follow.
* The upsert methods are the write SEAM consumed by a later importer; there is
  no HTTP route that creates plans or activities (D10).
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Row, and_, delete, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql import Select

from app.modules.boards.models import Board, BoardColumn
from app.modules.plans.models import (
    Plan,
    PlanActivity,
    PlanActivityLink,
    PlanActivityReport,
    TaskPlanActivity,
)
from app.modules.plans.progress import progress_denominator
from app.modules.plans.schemas import (
    PlanActivityReportUpsert,
    PlanActivityUpsert,
    PlanUpsert,
)
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.pagination import PaginationParams, paginate

# First entry of each mapping is the default order when pagination is requested
# without an explicit ``sort``.
PLAN_SORTABLE_FIELDS: dict[str, InstrumentedAttribute[Any]] = {
    "period_year": Plan.period_year,
    "code": Plan.code,
    "name": Plan.name,
    "created_at": Plan.created_at,
}
ACTIVITY_SORTABLE_FIELDS: dict[str, InstrumentedAttribute[Any]] = {
    "sort_order": PlanActivity.sort_order,
    "code": PlanActivity.code,
    "due_date": PlanActivity.due_date,
    "created_at": PlanActivity.created_at,
}


class PlansRepository:
    """Async repository encapsulating plans persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Tenant scope (design.md D-D)
    # ------------------------------------------------------------------

    def _activity_scope(self, organization_id: uuid.UUID, *columns: Any) -> Select[Any]:
        """The ONLY way this module reaches a ``plan_activities`` row.

        ``plan_activities`` has NO ``organization_id`` (P7): the tenant arrives
        transitively through ``plan_id -> plans.organization_id``. Forgetting
        this JOIN in ONE read leaks rows across organizations (R5), so it is
        not a convention every query remembers — it is a single composable
        point. Pass ``columns`` to select something other than the entity.
        """

        stmt = select(*(columns or (PlanActivity,)))
        return (
            stmt.select_from(PlanActivity)
            .join(Plan, Plan.id == PlanActivity.plan_id)
            .where(
                Plan.organization_id == organization_id,
                Plan.is_active.is_(True),
                PlanActivity.is_active.is_(True),
            )
        )

    async def _require_activity(
        self, organization_id: uuid.UUID, activity_id: uuid.UUID
    ) -> PlanActivity | None:
        """Punctual twin of :meth:`_activity_scope`.

        ``None`` both when the activity does not exist and when it belongs to
        another organization: the service maps both to the same 404.
        """

        result = await self.db.execute(
            self._activity_scope(organization_id).where(PlanActivity.id == activity_id)
        )
        return result.scalars().first()

    async def get_activity(
        self, organization_id: uuid.UUID, activity_id: uuid.UUID
    ) -> PlanActivity | None:
        return await self._require_activity(organization_id, activity_id)

    async def plan_codes(
        self, organization_id: uuid.UUID, plan_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """``{plan_id: plan.code}`` for the derived ``activity_key``."""

        if not plan_ids:
            return {}
        result = await self.db.execute(
            select(Plan.id, Plan.code).where(
                Plan.id.in_(plan_ids),
                Plan.organization_id == organization_id,
                Plan.is_active.is_(True),
            )
        )
        return {row.id: row.code for row in result.all()}

    async def task_exists(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> bool:
        """Whether an active task of an active project of this tenant exists."""

        result = await self.db.execute(
            select(Task.id)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id == task_id,
                Task.is_active.is_(True),
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
            )
        )
        return result.first() is not None

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def _fetch(
        self,
        stmt: Select[Any],
        natural_order: Sequence[ColumnElement[Any]],
        params: PaginationParams | None,
        sortable: dict[str, InstrumentedAttribute[Any]],
    ) -> tuple[Sequence[Any], int]:
        """Opt-in pagination. ``stmt`` arrives WITHOUT ``order_by``.

        ``order_by`` APPENDS clauses instead of replacing them, so chaining the
        natural order and ``paginate``'s own would produce a contradictory
        ``ORDER BY``: the order is decided here, after the path is known
        (design.md D-L / R12).
        """

        if params is not None and params.requested:
            return await paginate(self.db, stmt, params, sortable)
        result = await self.db.execute(stmt.order_by(*natural_order))
        rows = result.scalars().all()
        return rows, len(rows)

    async def list_plans(
        self,
        organization_id: uuid.UUID,
        *,
        plan_type: str | None = None,
        period_year: int | None = None,
        status: str | None = None,
        params: PaginationParams | None = None,
    ) -> tuple[Sequence[Plan], int]:
        stmt = select(Plan).where(Plan.organization_id == organization_id, Plan.is_active.is_(True))
        if plan_type is not None:
            stmt = stmt.where(Plan.plan_type == plan_type)
        if period_year is not None:
            stmt = stmt.where(Plan.period_year == period_year)
        if status is not None:
            stmt = stmt.where(Plan.status == status)
        return await self._fetch(
            stmt,
            (Plan.period_year.desc(), Plan.code.asc()),
            params,
            PLAN_SORTABLE_FIELDS,
        )

    async def get_plan(self, organization_id: uuid.UUID, plan_id: uuid.UUID) -> Plan | None:
        result = await self.db.execute(
            select(Plan).where(
                Plan.id == plan_id,
                Plan.organization_id == organization_id,
                Plan.is_active.is_(True),
            )
        )
        return result.scalars().first()

    async def count_activities_by_group(
        self, organization_id: uuid.UUID, plan_id: uuid.UUID
    ) -> list[tuple[str | None, str | None, int]]:
        """``[(group_code, group_name, count)]`` via ``GROUP BY`` (D-I/H13)."""

        stmt = (
            self._activity_scope(
                organization_id,
                PlanActivity.group_code,
                PlanActivity.group_name,
                func.count().label("activity_count"),
            )
            .where(PlanActivity.plan_id == plan_id)
            .group_by(PlanActivity.group_code, PlanActivity.group_name)
            .order_by(
                func.min(PlanActivity.sort_order),
                PlanActivity.group_code,
            )
        )
        result = await self.db.execute(stmt)
        return [(r.group_code, r.group_name, r.activity_count) for r in result.all()]

    async def list_activities(
        self,
        organization_id: uuid.UUID,
        *,
        plan_id: uuid.UUID | None = None,
        plan_type: str | None = None,
        is_mine: bool | None = None,
        group_code: str | None = None,
        task_id: uuid.UUID | None = None,
        params: PaginationParams | None = None,
    ) -> tuple[Sequence[PlanActivity], int]:
        stmt = self._activity_scope(organization_id)
        if plan_id is not None:
            stmt = stmt.where(PlanActivity.plan_id == plan_id)
        if plan_type is not None:
            stmt = stmt.where(Plan.plan_type == plan_type)
        if is_mine is not None:
            stmt = stmt.where(PlanActivity.is_mine.is_(is_mine))
        if group_code is not None:
            stmt = stmt.where(PlanActivity.group_code == group_code)
        if task_id is not None:
            stmt = stmt.where(
                PlanActivity.id.in_(
                    select(TaskPlanActivity.plan_activity_id).where(
                        TaskPlanActivity.task_id == task_id
                    )
                )
            )
        return await self._fetch(
            stmt,
            (PlanActivity.sort_order.asc(), PlanActivity.code.asc()),
            params,
            ACTIVITY_SORTABLE_FIELDS,
        )

    @staticmethod
    def _last_column_subquery() -> Any:
        """Last active column of each project's board, one row per project.

        ``DISTINCT ON (board.project_id) ... ORDER BY column_order DESC,
        created_at DESC`` — the rule of ``projects/repository.py`` — but
        joined later by ``project_id`` per task instead of filtered to a single
        project subtree (R3): each task is judged against ITS OWN board.
        """

        return (
            select(
                Board.project_id.label("project_id"),
                BoardColumn.status_key.label("status_key"),
            )
            .distinct(Board.project_id)
            .select_from(Board)
            .join(BoardColumn, BoardColumn.board_id == Board.id)
            .where(Board.is_active.is_(True), BoardColumn.is_active.is_(True))
            .order_by(
                Board.project_id,
                BoardColumn.order.desc(),
                BoardColumn.created_at.desc(),
            )
            .subquery("last_column")
        )

    async def rollup_activity_progress(
        self,
        organization_id: uuid.UUID,
        activity_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, tuple[int, int, int]]:
        """Return ``{activity_id: (done, primary_total, contributing_total)}``.

        ONE query for the WHOLE batch (R8). Activities with no linked task do
        not appear: the SERVICE turns absence into ``calculated_progress =
        None``, never ``0`` (D-F). Does NOT read ``plan_activity_links``, which
        is the structural reason a ``conflict`` link can never alter a progress
        figure (D-G/H3). Tenant is checked twice: through ``plans`` for the
        activity side and through ``projects`` for the task side. Does NOT
        commit.
        """

        if not activity_ids:
            return {}

        last_column = self._last_column_subquery()
        denominator = progress_denominator()
        countable = and_(TaskPlanActivity.role == "primary", denominator.predicate)

        stmt = (
            select(
                TaskPlanActivity.plan_activity_id.label("activity_id"),
                func.count(Task.id)
                .filter(countable, Task.status == last_column.c.status_key)
                .label("done"),
                func.count(Task.id).filter(countable).label("primary_total"),
                func.count(Task.id)
                .filter(TaskPlanActivity.role == "contributes")
                .label("contributing_total"),
            )
            .select_from(TaskPlanActivity)
            .join(PlanActivity, PlanActivity.id == TaskPlanActivity.plan_activity_id)
            .join(Plan, Plan.id == PlanActivity.plan_id)
            .join(Task, Task.id == TaskPlanActivity.task_id)
            .join(Project, Project.id == Task.project_id)
            .outerjoin(last_column, last_column.c.project_id == Task.project_id)
        )
        for target, onclause in denominator.extra_joins:
            stmt = stmt.outerjoin(target, onclause)
        stmt = stmt.where(
            TaskPlanActivity.plan_activity_id.in_(activity_ids),
            Plan.organization_id == organization_id,
            Plan.is_active.is_(True),
            PlanActivity.is_active.is_(True),
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
            Task.is_active.is_(True),
        ).group_by(TaskPlanActivity.plan_activity_id)

        result = await self.db.execute(stmt)
        return {
            row.activity_id: (row.done, row.primary_total, row.contributing_total)
            for row in result.all()
        }

    async def list_activity_tasks(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        role: str | None = None,
    ) -> list[Row[Any]]:
        """Tasks linked to ONE activity, in a SINGLE query (design.md D-I/H4).

        ``counts_toward_progress`` is computed in SQL with the very same
        predicate (``progress_denominator()``) and per-project last column the
        roll-up uses, so both figures move together if change 44 moves the
        criterion.
        """

        last_column = self._last_column_subquery()
        denominator = progress_denominator()
        stmt = (
            select(
                TaskPlanActivity.task_id.label("task_id"),
                Task.title.label("title"),
                Task.task_number.label("task_number"),
                Project.code.label("project_code"),
                Project.name.label("project_name"),
                Task.status.label("status"),
                TaskPlanActivity.role.label("role"),
                TaskPlanActivity.note.label("note"),
                and_(TaskPlanActivity.role == "primary", denominator.predicate).label(
                    "counts_toward_progress"
                ),
            )
            .select_from(TaskPlanActivity)
            .join(Task, Task.id == TaskPlanActivity.task_id)
            .join(Project, Project.id == Task.project_id)
            .outerjoin(last_column, last_column.c.project_id == Task.project_id)
        )
        for target, onclause in denominator.extra_joins:
            stmt = stmt.outerjoin(target, onclause)
        stmt = stmt.where(
            TaskPlanActivity.plan_activity_id == activity_id,
            TaskPlanActivity.plan_activity_id.in_(
                self._activity_scope(organization_id, PlanActivity.id)
            ),
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
            Task.is_active.is_(True),
        )
        if role is not None:
            stmt = stmt.where(TaskPlanActivity.role == role)
        stmt = stmt.order_by(TaskPlanActivity.role.asc(), TaskPlanActivity.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.all())

    async def list_links(
        self, organization_id: uuid.UUID, activity_id: uuid.UUID
    ) -> Sequence[PlanActivityLink]:
        """Every link touching ``activity_id``, both directions.

        Both ends must belong to the tenant: a link whose other end is outside
        the scope is invisible.
        """

        scope_ids = self._activity_scope(organization_id, PlanActivity.id)
        result = await self.db.execute(
            select(PlanActivityLink)
            .where(
                or_(
                    PlanActivityLink.from_activity_id == activity_id,
                    PlanActivityLink.to_activity_id == activity_id,
                ),
                PlanActivityLink.from_activity_id.in_(scope_ids),
                PlanActivityLink.to_activity_id.in_(scope_ids),
            )
            .order_by(PlanActivityLink.created_at.asc(), PlanActivityLink.id.asc())
        )
        return result.scalars().all()

    async def get_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        link_id: uuid.UUID,
    ) -> PlanActivityLink | None:
        """An outgoing link of ``activity_id`` by id (tenant-scoped)."""

        result = await self.db.execute(
            select(PlanActivityLink).where(
                PlanActivityLink.id == link_id,
                PlanActivityLink.from_activity_id == activity_id,
                PlanActivityLink.from_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            )
        )
        return result.scalars().first()

    async def list_reports(
        self, organization_id: uuid.UUID, activity_id: uuid.UUID
    ) -> Sequence[PlanActivityReport]:
        """Every registered report of one activity (a missing period has no row)."""

        result = await self.db.execute(
            select(PlanActivityReport)
            .where(
                PlanActivityReport.plan_activity_id == activity_id,
                PlanActivityReport.plan_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            )
            .order_by(PlanActivityReport.period.asc())
        )
        return result.scalars().all()

    async def list_reports_for_period(
        self,
        organization_id: uuid.UUID,
        activity_ids: Sequence[uuid.UUID],
        period: str,
    ) -> dict[uuid.UUID, Decimal | None]:
        """``{activity_id: reported_progress}`` of the queried period only."""

        if not activity_ids:
            return {}
        result = await self.db.execute(
            select(
                PlanActivityReport.plan_activity_id,
                PlanActivityReport.reported_progress,
            ).where(
                PlanActivityReport.plan_activity_id.in_(activity_ids),
                PlanActivityReport.period == period,
                PlanActivityReport.plan_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def link_counts_by_resolution(
        self, organization_id: uuid.UUID, resolution: str
    ) -> dict[uuid.UUID, int]:
        """``{activity_id: n}`` of links with ``resolution`` touching each activity.

        Counts BOTH ends (outgoing and incoming): a conflict needs review from
        either side. Each end is scoped through :meth:`_activity_scope`, so an
        activity of another tenant never appears. One query, read-only.
        """

        conflict = PlanActivityLink.resolution == resolution
        ends = union_all(
            select(PlanActivityLink.from_activity_id.label("activity_id")).where(
                conflict,
                PlanActivityLink.from_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            ),
            select(PlanActivityLink.to_activity_id.label("activity_id")).where(
                conflict,
                PlanActivityLink.to_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            ),
        ).subquery()
        result = await self.db.execute(
            select(ends.c.activity_id, func.count()).group_by(ends.c.activity_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def find_task_link(
        self, activity_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskPlanActivity | None:
        return await self._find_task_link(activity_id, task_id)

    async def _find_task_link(
        self, activity_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskPlanActivity | None:
        result = await self.db.execute(
            select(TaskPlanActivity).where(
                TaskPlanActivity.plan_activity_id == activity_id,
                TaskPlanActivity.task_id == task_id,
            )
        )
        return result.scalars().first()

    async def find_activity_link(
        self,
        from_activity_id: uuid.UUID,
        to_activity_id: uuid.UUID,
        link_type: str,
    ) -> PlanActivityLink | None:
        return await self._find_activity_link(from_activity_id, to_activity_id, link_type)

    async def _find_activity_link(
        self,
        from_activity_id: uuid.UUID,
        to_activity_id: uuid.UUID,
        link_type: str,
    ) -> PlanActivityLink | None:
        result = await self.db.execute(
            select(PlanActivityLink).where(
                PlanActivityLink.from_activity_id == from_activity_id,
                PlanActivityLink.to_activity_id == to_activity_id,
                PlanActivityLink.link_type == link_type,
            )
        )
        return result.scalars().first()

    async def activity_index(
        self, organization_id: uuid.UUID, plan_codes: Sequence[str]
    ) -> list[tuple[str, str, uuid.UUID, list[Any] | None]]:
        """``(plan_code, activity_code, activity_id, external_codes)`` of active
        activities of ``plan_codes`` in the tenant (follow-up feed). Read-only.
        """

        if not plan_codes:
            return []
        result = await self.db.execute(
            self._activity_scope(
                organization_id,
                Plan.code,
                PlanActivity.code,
                PlanActivity.id,
                PlanActivity.external_codes,
            ).where(Plan.code.in_(plan_codes))
        )
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def find_report(
        self, activity_id: uuid.UUID, period: str
    ) -> PlanActivityReport | None:
        """The report of ``(activity_id, period)``; the caller already scoped
        ``activity_id`` to its tenant (it comes from :meth:`activity_index`)."""

        result = await self.db.execute(
            select(PlanActivityReport).where(
                PlanActivityReport.plan_activity_id == activity_id,
                PlanActivityReport.period == period,
            )
        )
        return result.scalars().first()

    async def import_snapshot(
        self, organization_id: uuid.UUID, plan_codes: Sequence[str]
    ) -> tuple[dict[str, set[str]], set[tuple[str, str, str, str]]]:
        """What the importer (45b) would find for ``plan_codes`` of the tenant.

        Returns ``({plan_code: {activity_code}}, {(from_key, to_key,
        link_type, resolution)})`` with keys in ``activity_key`` form. Includes
        soft-deleted rows on purpose: the upsert seam reactivates them, so for
        the import they already exist. Read-only; safe in a READ ONLY
        transaction.
        """

        if not plan_codes:
            return {}, set()
        result = await self.db.execute(
            select(Plan.code, PlanActivity.code)
            .select_from(Plan)
            .outerjoin(PlanActivity, PlanActivity.plan_id == Plan.id)
            .where(Plan.organization_id == organization_id, Plan.code.in_(plan_codes))
        )
        activities: dict[str, set[str]] = {}
        for plan_code, activity_code in result.all():
            codes = activities.setdefault(plan_code, set())
            if activity_code is not None:
                codes.add(activity_code)

        source, target = aliased(PlanActivity), aliased(PlanActivity)
        source_plan, target_plan = aliased(Plan), aliased(Plan)
        links = await self.db.execute(
            select(
                source_plan.code,
                source.code,
                target_plan.code,
                target.code,
                PlanActivityLink.link_type,
                PlanActivityLink.resolution,
            )
            .select_from(PlanActivityLink)
            .join(source, source.id == PlanActivityLink.from_activity_id)
            .join(source_plan, source_plan.id == source.plan_id)
            .join(target, target.id == PlanActivityLink.to_activity_id)
            .join(target_plan, target_plan.id == target.plan_id)
            .where(
                source_plan.organization_id == organization_id,
                target_plan.organization_id == organization_id,
                source_plan.code.in_(plan_codes),
            )
        )
        return activities, {
            (f"{fp}/{fa}", f"{tp}/{ta}", link_type, resolution)
            for fp, fa, tp, ta, link_type, resolution in links.all()
        }

    # ------------------------------------------------------------------
    # Write seam (design.md D10/D-M): idempotent, NEVER commits
    # ------------------------------------------------------------------

    async def upsert_plan(
        self,
        organization_id: uuid.UUID,
        data: PlanUpsert,
        actor_id: uuid.UUID | None = None,
    ) -> Plan:
        """Create or update the plan identified by ``(organization_id, code)``.

        Idempotent by ``uq_plans_org_code``. A soft-deleted plan with the same
        code is reactivated instead of colliding with the unique. NEVER
        commits: the caller owns the transaction.
        """

        result = await self.db.execute(
            select(Plan).where(Plan.organization_id == organization_id, Plan.code == data.code)
        )
        plan = result.scalars().first()
        if plan is None:
            plan = Plan(
                id=uuid.uuid4(),
                organization_id=organization_id,
                code=data.code,
                created_by=actor_id,
            )
            self.db.add(plan)
        plan.name = data.name
        plan.plan_type = data.plan_type
        plan.period_year = data.period_year
        plan.version = data.version
        plan.source_document = data.source_document
        plan.status = data.status
        plan.is_active = True
        plan.deleted_at = None
        plan.updated_by = actor_id
        return plan

    async def upsert_activity(
        self,
        plan_id: uuid.UUID,
        data: PlanActivityUpsert,
        actor_id: uuid.UUID | None = None,
    ) -> PlanActivity:
        """Create or update the activity identified by ``(plan_id, code)``.

        THE write seam of the aggregate (design.md D10): there is no HTTP
        route that creates a plan or an activity, because the authority of a
        Decreto 612 plan is its source document, not a form. Idempotent by
        ``uq_plan_activities_plan_code``. NEVER commits: the caller owns the
        transaction, which lets an importer write a whole plan atomically.
        """

        result = await self.db.execute(
            select(PlanActivity).where(
                PlanActivity.plan_id == plan_id, PlanActivity.code == data.code
            )
        )
        activity = result.scalars().first()
        if activity is None:
            activity = PlanActivity(
                id=uuid.uuid4(),
                plan_id=plan_id,
                code=data.code,
                created_by=actor_id,
            )
            self.db.add(activity)
        activity.name = data.name
        activity.group_code = data.group_code
        activity.group_name = data.group_name
        activity.deliverable = data.deliverable
        activity.evidence_expected = data.evidence_expected
        activity.responsible = data.responsible
        activity.is_mine = data.is_mine
        activity.due_date = data.due_date
        activity.target_from = data.target_from
        activity.target_to = data.target_to
        activity.iso_controls = data.iso_controls
        activity.external_codes = data.external_codes
        activity.scheduled_periods = data.scheduled_periods
        activity.sort_order = data.sort_order
        activity.is_active = True
        activity.deleted_at = None
        activity.updated_by = actor_id
        return activity

    async def upsert_report(
        self,
        activity_id: uuid.UUID,
        period: str,
        data: PlanActivityReportUpsert,
        actor_id: uuid.UUID | None = None,
    ) -> PlanActivityReport:
        """Create or replace the report of ``(activity_id, period)`` (D11).

        The second write for the same period replaces the values IN THE SAME
        ROW (``uq_plan_activity_reports_activity_period``). NEVER commits.
        """

        result = await self.db.execute(
            select(PlanActivityReport).where(
                PlanActivityReport.plan_activity_id == activity_id,
                PlanActivityReport.period == period,
            )
        )
        report = result.scalars().first()
        if report is None:
            report = PlanActivityReport(
                id=uuid.uuid4(),
                plan_activity_id=activity_id,
                period=period,
                created_by=actor_id,
            )
            self.db.add(report)
        report.reported_progress = data.reported_progress
        report.qualitative_summary = data.qualitative_summary
        report.evidence_refs = data.evidence_refs
        report.is_met = data.is_met
        report.met_on_time = data.met_on_time
        report.updated_by = actor_id
        return report

    async def upsert_activity_link(
        self,
        from_activity_id: uuid.UUID,
        to_activity_id: uuid.UUID,
        link_type: str,
        resolution: str,
        source_reference: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> PlanActivityLink:
        """Create or update the link ``(from, to, link_type)``. NEVER commits."""

        link = await self._find_activity_link(from_activity_id, to_activity_id, link_type)
        if link is None:
            link = PlanActivityLink(
                id=uuid.uuid4(),
                from_activity_id=from_activity_id,
                to_activity_id=to_activity_id,
                link_type=link_type,
                created_by=actor_id,
            )
            self.db.add(link)
        link.resolution = resolution
        link.source_reference = source_reference
        link.updated_by = actor_id
        return link

    async def upsert_task_link(
        self,
        task_id: uuid.UUID,
        plan_activity_id: uuid.UUID,
        role: str,
        note: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> TaskPlanActivity:
        """Create or update the link ``(task, activity)``. NEVER commits."""

        link = await self._find_task_link(plan_activity_id, task_id)
        if link is None:
            link = TaskPlanActivity(
                id=uuid.uuid4(),
                task_id=task_id,
                plan_activity_id=plan_activity_id,
                created_by=actor_id,
            )
            self.db.add(link)
        link.role = role
        link.note = note
        link.updated_by = actor_id
        return link

    # ------------------------------------------------------------------
    # Deletes (physical, design.md D-C). NEVER commit.
    # ------------------------------------------------------------------

    async def delete_task_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> bool:
        """Remove the (task, activity) link. ``False`` when it does not exist."""

        result = await self.db.execute(
            delete(TaskPlanActivity).where(
                TaskPlanActivity.plan_activity_id == activity_id,
                TaskPlanActivity.task_id == task_id,
                TaskPlanActivity.plan_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            )
        )
        return bool(result.rowcount)

    async def delete_activity_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        link_id: uuid.UUID,
    ) -> bool:
        """Remove an outgoing activity link. ``False`` when it does not exist."""

        result = await self.db.execute(
            delete(PlanActivityLink).where(
                PlanActivityLink.id == link_id,
                PlanActivityLink.from_activity_id == activity_id,
                PlanActivityLink.from_activity_id.in_(
                    self._activity_scope(organization_id, PlanActivity.id)
                ),
            )
        )
        return bool(result.rowcount)
