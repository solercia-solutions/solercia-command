"""Business logic for institutional plans (change 45a, design.md D-F/D-I/D-K/D-M).

Router -> service -> repository. The service owns the transaction (it is the
use case that commits, never the repository) and is the only place that
derives ``activity_key``, the double progress, ``is_confirmed`` and the domain
errors. Derived fields are set transiently on the read schemas, same pattern as
``TaskRead.task_key``.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans import vocabularies as vocab
from app.modules.plans.models import PlanActivity
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import (
    ActivityConflictCountRead,
    ActivityLinkCreate,
    ActivityTaskRead,
    PlanActivityDetailRead,
    PlanActivityGroupCount,
    PlanActivityLinkRead,
    PlanActivityRead,
    PlanActivityReportRead,
    PlanActivityReportUpsert,
    PlanDetailRead,
    PlanRead,
    TaskLinkCreate,
)
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


def _not_found(detail: str, code: str) -> AppException:
    return AppException(detail, code=code, status_code=404)


class PlansService:
    """Use cases of the plans aggregate."""

    def __init__(self, db: AsyncSession, repository: PlansRepository | None = None) -> None:
        self.db = db
        self.repo = repository if repository is not None else PlansRepository(db)

    # ------------------------------------------------------------------
    # Derivations (pure)
    # ------------------------------------------------------------------

    @staticmethod
    def link_to_read(link: Any) -> PlanActivityLinkRead:
        """``is_confirmed = resolution != "conflict"`` — the ONE place (D-I/H3)."""

        read = PlanActivityLinkRead.model_validate(link)
        read.is_confirmed = link.resolution != vocab.CONFLICT_RESOLUTION
        return read

    @staticmethod
    def activity_to_read(
        activity: Any,
        plan_code: str | None,
        *,
        rollup: tuple[int, int, int] | None,
        reported: Decimal | None,
        period: str | None,
    ) -> PlanActivityRead:
        """Build the read schema and assign the derived, never-persisted fields.

        ``calculated_progress`` has ONE null rule (D-F): ``primary_task_count
        == 0`` => ``None`` (never ``0``). ``reported_progress`` belongs to the
        queried ``period``; without ``period`` the system does not pick one.
        """

        read = PlanActivityRead.model_validate(activity)
        if plan_code is not None:
            read.activity_key = f"{plan_code}/{activity.code}"
        done, primary_total, contributing_total = rollup or (0, 0, 0)
        read.primary_task_count = primary_total
        read.contributing_task_count = contributing_total
        read.calculated_progress = None if primary_total == 0 else done / primary_total
        read.reported_progress = reported
        read.reported_period = period
        return read

    async def build_activity_reads(
        self,
        organization_id: uuid.UUID,
        activities: Sequence[PlanActivity],
        period: str | None,
    ) -> list[PlanActivityRead]:
        """Fixed query count for N activities, independent of N (R8).

        Plan codes, one roll-up for the whole batch and — only when a period
        was asked for — one lookup of the reported values.
        """

        if not activities:
            return []
        ids = [a.id for a in activities]
        plan_codes = await self.repo.plan_codes(
            organization_id, sorted({a.plan_id for a in activities}, key=str)
        )
        rollup = await self.repo.rollup_activity_progress(organization_id, ids)
        reported: dict[uuid.UUID, Decimal | None] = {}
        if period is not None:
            reported = await self.repo.list_reports_for_period(organization_id, ids, period)
        return [
            self.activity_to_read(
                a,
                plan_codes.get(a.plan_id),
                rollup=rollup.get(a.id),
                reported=reported.get(a.id),
                period=period,
            )
            for a in activities
        ]

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_plans(
        self,
        organization_id: uuid.UUID,
        *,
        plan_type: str | None = None,
        period_year: int | None = None,
        status: str | None = None,
        params: PaginationParams | None = None,
    ) -> tuple[list[PlanRead], int]:
        if plan_type is not None:
            vocab.validate_plan_type(plan_type)
        if status is not None:
            vocab.validate_plan_status(status)
        rows, total = await self.repo.list_plans(
            organization_id,
            plan_type=plan_type,
            period_year=period_year,
            status=status,
            params=params,
        )
        return [PlanRead.model_validate(r) for r in rows], total

    async def get_plan(self, organization_id: uuid.UUID, plan_id: uuid.UUID) -> PlanDetailRead:
        plan = await self.repo.get_plan(organization_id, plan_id)
        if plan is None:
            raise _not_found("El plan no existe.", "plan_not_found")
        groups = await self.repo.count_activities_by_group(organization_id, plan_id)
        detail = PlanDetailRead.model_validate(plan)
        detail.groups = [
            PlanActivityGroupCount(group_code=code, group_name=name, activity_count=count)
            for code, name, count in groups
        ]
        detail.activity_count = sum(g.activity_count for g in detail.groups)
        return detail

    async def list_activities(
        self,
        organization_id: uuid.UUID,
        *,
        plan_id: uuid.UUID | None = None,
        plan_type: str | None = None,
        is_mine: bool | None = None,
        group_code: str | None = None,
        task_id: uuid.UUID | None = None,
        period: str | None = None,
        params: PaginationParams | None = None,
    ) -> tuple[list[PlanActivityRead], int]:
        if plan_type is not None:
            vocab.validate_plan_type(plan_type)
        if period is not None:
            vocab.validate_period(period)
        rows, total = await self.repo.list_activities(
            organization_id,
            plan_id=plan_id,
            plan_type=plan_type,
            is_mine=is_mine,
            group_code=group_code,
            task_id=task_id,
            params=params,
        )
        return await self.build_activity_reads(organization_id, rows, period), total

    async def _require_activity(
        self, organization_id: uuid.UUID, activity_id: uuid.UUID
    ) -> PlanActivity:
        """Missing and foreign-tenant activities answer the SAME 404 (D-D)."""

        activity = await self.repo.get_activity(organization_id, activity_id)
        if activity is None:
            raise _not_found("La actividad no existe.", "plan_activity_not_found")
        return activity

    async def get_activity(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        period: str | None = None,
    ) -> PlanActivityDetailRead:
        if period is not None:
            vocab.validate_period(period)
        activity = await self._require_activity(organization_id, activity_id)
        (base,) = await self.build_activity_reads(organization_id, [activity], period)
        reports = await self.repo.list_reports(organization_id, activity_id)
        links = await self.repo.list_links(organization_id, activity_id)
        return PlanActivityDetailRead(
            **base.model_dump(),
            reports=[PlanActivityReportRead.model_validate(r) for r in reports],
            links_out=[
                self.link_to_read(link) for link in links if link.from_activity_id == activity_id
            ],
            links_in=[
                self.link_to_read(link) for link in links if link.to_activity_id == activity_id
            ],
        )

    async def list_activity_tasks(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        role: str | None = None,
    ) -> list[ActivityTaskRead]:
        if role is not None:
            vocab.validate_task_link_role(role)
        await self._require_activity(organization_id, activity_id)
        rows = await self.repo.list_activity_tasks(organization_id, activity_id, role)
        reads: list[ActivityTaskRead] = []
        for row in rows:
            task_key = (
                f"{row.project_code}-{row.task_number}"
                if row.project_code and row.task_number is not None
                else None
            )
            reads.append(
                ActivityTaskRead(
                    task_id=row.task_id,
                    task_key=task_key,
                    title=row.title,
                    project_code=row.project_code,
                    project_name=row.project_name,
                    status=row.status,
                    role=row.role,
                    note=row.note,
                    counts_toward_progress=bool(row.counts_toward_progress),
                )
            )
        return reads

    async def list_conflict_counts(
        self, organization_id: uuid.UUID
    ) -> list[ActivityConflictCountRead]:
        """Activities with at least one ``conflict`` link, and how many."""

        counts = await self.repo.link_counts_by_resolution(
            organization_id, vocab.CONFLICT_RESOLUTION
        )
        return [
            ActivityConflictCountRead(activity_id=activity_id, conflict_count=count)
            for activity_id, count in sorted(counts.items(), key=lambda item: str(item[0]))
        ]

    # ------------------------------------------------------------------
    # Writes (the service commits — D-M)
    # ------------------------------------------------------------------

    async def upsert_report(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        period: str,
        data: PlanActivityReportUpsert,
        actor_id: uuid.UUID | None,
    ) -> PlanActivityReportRead:
        """Idempotent ``PUT``: one row per ``(activity, period)`` (D11)."""

        vocab.validate_period(period)
        vocab.validate_reported_progress(data.reported_progress)
        await self._require_activity(organization_id, activity_id)
        report = await self.repo.upsert_report(activity_id, period, data, actor_id)
        await self.db.commit()
        # Server-side defaults (updated_at) are expired after the INSERT.
        await self.db.refresh(report)
        return PlanActivityReportRead.model_validate(report)

    async def create_task_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        body: TaskLinkCreate,
        actor_id: uuid.UUID | None,
    ) -> ActivityTaskRead:
        vocab.validate_task_link_role(body.role)
        await self._require_activity(organization_id, activity_id)
        if not await self.repo.task_exists(organization_id, body.task_id):
            raise _not_found("La tarea no existe.", "plan_task_not_found")
        duplicate = AppException(
            "La tarea ya está enlazada a esta actividad.",
            code="plan_task_link_duplicate",
            status_code=409,
        )
        if await self.repo.find_task_link(activity_id, body.task_id) is not None:
            raise duplicate
        try:
            await self.repo.upsert_task_link(
                body.task_id, activity_id, body.role, body.note, actor_id
            )
            await self.db.commit()
        except IntegrityError as exc:  # design.md D-K (H10)
            # Lost the race: another request inserted the SAME pair between our
            # lookup and our INSERT. Same business fact as the check above, so
            # it surfaces as the SAME domain error — never a 500.
            await self.db.rollback()
            raise duplicate from exc
        rows = await self.list_activity_tasks(organization_id, activity_id)
        return next(r for r in rows if r.task_id == body.task_id)

    async def delete_task_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        task_id: uuid.UUID,
    ) -> None:
        await self._require_activity(organization_id, activity_id)
        removed = await self.repo.delete_task_link(organization_id, activity_id, task_id)
        if not removed:
            raise _not_found(
                "El enlace entre la tarea y la actividad no existe.",
                "plan_task_link_not_found",
            )
        await self.db.commit()

    async def create_activity_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        body: ActivityLinkCreate,
        actor_id: uuid.UUID | None,
    ) -> PlanActivityLinkRead:
        """Create an activity<->activity link. ALWAYS ``resolution='manual'``.

        ``exact``/``by_external_code``/``conflict`` are assertions about
        reading a source; the API never accepts them from a client (D14). The
        self-link is rejected here WITHOUT reaching the engine's CHECK.
        """

        vocab.validate_activity_link_type(body.link_type)
        if body.to_activity_id == activity_id:
            raise AppException(
                "Una actividad no puede enlazarse consigo misma.",
                code="plan_activity_self_link",
                status_code=422,
            )
        await self._require_activity(organization_id, activity_id)
        # The destination goes through the SAME tenant scope as the origin
        # (H11): otherwise this would be the only path able to cross tenants.
        await self._require_activity(organization_id, body.to_activity_id)
        duplicate = AppException(
            "Las actividades ya están enlazadas con ese tipo de enlace.",
            code="plan_activity_link_duplicate",
            status_code=409,
        )
        existing = await self.repo.find_activity_link(
            activity_id, body.to_activity_id, body.link_type
        )
        if existing is not None:
            raise duplicate
        try:
            link = await self.repo.upsert_activity_link(
                from_activity_id=activity_id,
                to_activity_id=body.to_activity_id,
                link_type=body.link_type,
                resolution="manual",
                source_reference=body.source_reference,
                actor_id=actor_id,
            )
            read = self.link_to_read(link)
            await self.db.commit()
        except IntegrityError as exc:  # design.md D-K (H10)
            await self.db.rollback()
            raise duplicate from exc
        return read

    async def delete_activity_link(
        self,
        organization_id: uuid.UUID,
        activity_id: uuid.UUID,
        link_id: uuid.UUID,
    ) -> None:
        await self._require_activity(organization_id, activity_id)
        removed = await self.repo.delete_activity_link(organization_id, activity_id, link_id)
        if not removed:
            raise _not_found(
                "El enlace entre actividades no existe.",
                "plan_activity_link_not_found",
            )
        await self.db.commit()
