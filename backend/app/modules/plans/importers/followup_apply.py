"""Resolve and apply a follow-up bundle in ONE transaction (repositories never commit).

Resolution is read-only and produces the exact writes plus the review list:
an activity key that does not exist in the tenant, an external code that maps
to zero or several activities, or a task that was not imported yet are NEVER
guessed — they go to review. Writes go through the 45a seam
(``upsert_report`` / ``upsert_task_link``), which is idempotent by natural key
``(activity, period)`` and ``(task, activity)``.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans.importers.followup import (
    FollowupBundle,
    FollowupReview,
    LinkCandidate,
    ReportDraft,
    link_note,
    merge_links,
)
from app.modules.plans.models import PlanActivityReport, TaskPlanActivity
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import PlanActivityReportUpsert
from app.modules.plans.vocabularies import (
    validate_period,
    validate_reported_progress,
    validate_resolution,
    validate_task_link_role,
)
from app.modules.task_import.checklist_apply import SqlChecklistImportStore
from app.modules.task_import.checklist_import import CHECKLIST_SOURCE, external_key


class FollowupPlansPort(Protocol):
    async def activity_index(
        self, organization_id: uuid.UUID, plan_codes: list[str]
    ) -> list[tuple[str, str, uuid.UUID, list[Any] | None]]: ...

    async def find_report(
        self, activity_id: uuid.UUID, period: str
    ) -> PlanActivityReport | None: ...

    async def find_task_link(
        self, activity_id: uuid.UUID, task_id: uuid.UUID
    ) -> TaskPlanActivity | None: ...

    async def upsert_report(
        self,
        activity_id: uuid.UUID,
        period: str,
        data: PlanActivityReportUpsert,
        actor_id: uuid.UUID | None = None,
    ) -> PlanActivityReport: ...

    async def upsert_task_link(
        self,
        task_id: uuid.UUID,
        plan_activity_id: uuid.UUID,
        role: str,
        note: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> TaskPlanActivity: ...


class TaskAnchorPort(Protocol):
    async def find_anchors(
        self, organization_id: uuid.UUID, source: str, keys: list[str]
    ) -> dict[str, Any]: ...


class FollowupUow(Protocol):
    plans: FollowupPlansPort
    tasks: TaskAnchorPort

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SessionFollowupUow:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans: FollowupPlansPort = PlansRepository(session)
        self.tasks: TaskAnchorPort = SqlChecklistImportStore(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


@dataclass(frozen=True)
class ResolvedReport:
    draft: ReportDraft
    activity_id: uuid.UUID
    status: str  # nuevo | sin cambios | actualiza


@dataclass(frozen=True)
class ResolvedLink:
    candidate: LinkCandidate
    activity_key: str
    task_id: uuid.UUID
    activity_id: uuid.UUID
    note: str
    status: str


@dataclass
class ResolvedFollowup:
    reports: list[ResolvedReport] = field(default_factory=list)
    links: list[ResolvedLink] = field(default_factory=list)
    review: list[FollowupReview] = field(default_factory=list)


def _report_payload(draft: ReportDraft) -> PlanActivityReportUpsert:
    validate_period(draft.period)
    validate_reported_progress(draft.reported_progress)
    return PlanActivityReportUpsert(
        reported_progress=draft.reported_progress,
        qualitative_summary=draft.qualitative_summary,
        evidence_refs=draft.evidence_refs,
        is_met=draft.is_met,
        met_on_time=draft.met_on_time,
    )


def _same_report(existing: PlanActivityReport, payload: PlanActivityReportUpsert) -> bool:
    progress = existing.reported_progress
    return (
        (None if progress is None else Decimal(progress)) == payload.reported_progress
        and existing.qualitative_summary == payload.qualitative_summary
        and existing.evidence_refs == payload.evidence_refs
        and existing.is_met == payload.is_met
        and existing.met_on_time == payload.met_on_time
    )


async def resolve_followup(
    uow: FollowupUow,
    organization_id: uuid.UUID,
    bundle: FollowupBundle,
    *,
    plan_codes: list[str],
    namespace: str,
) -> ResolvedFollowup:
    resolved = ResolvedFollowup(review=list(bundle.review))
    index = await uow.plans.activity_index(organization_id, plan_codes)
    by_key = {f"{plan}/{code}": activity_id for plan, code, activity_id, _ in index}
    by_external: dict[str, list[str]] = {}
    for plan, code, _, externals in index:
        for external in externals or []:
            by_external.setdefault(str(external), []).append(f"{plan}/{code}")

    for draft in bundle.reports:
        activity_id = by_key.get(draft.activity_key)
        if activity_id is None:
            resolved.review.append(
                FollowupReview(
                    "pai", draft.activity_key, "La actividad no existe en la organización."
                )
            )
            continue
        payload = _report_payload(draft)
        existing = await uow.plans.find_report(activity_id, draft.period)
        status = (
            "nuevo"
            if existing is None
            else "sin cambios"
            if _same_report(existing, payload)
            else "actualiza"
        )
        resolved.reports.append(ResolvedReport(draft, activity_id, status))

    candidates = merge_links(bundle.links)
    keys = sorted({external_key(namespace, c.source_id) for c in candidates})
    anchors = await uow.tasks.find_anchors(organization_id, CHECKLIST_SOURCE, keys)
    seen: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for candidate in candidates:
        activity_key = candidate.activity_key
        if activity_key is None:
            matches = by_external.get(candidate.external_code or "", [])
            if len(matches) != 1:
                resolved.review.append(
                    FollowupReview(
                        "enlace",
                        f"{candidate.source_id} → {candidate.external_code}",
                        f"El código externo corresponde a {len(matches)} actividades; "
                        "no se enlaza.",
                        candidate.quote,
                    )
                )
                continue
            activity_key = matches[0]
        activity_id = by_key.get(activity_key)
        if activity_id is None:
            resolved.review.append(
                FollowupReview(
                    "enlace",
                    f"{candidate.source_id} → {activity_key}",
                    "La actividad citada no existe en los planes cargados.",
                    candidate.quote,
                )
            )
            continue
        anchor = anchors.get(external_key(namespace, candidate.source_id))
        if anchor is None or not anchor.is_active:
            resolved.review.append(
                FollowupReview(
                    "enlace",
                    f"{candidate.source_id} → {activity_key}",
                    "La tarea no está importada (o está eliminada) en la organización.",
                    candidate.quote,
                )
            )
            continue
        validate_task_link_role(candidate.role)
        validate_resolution(candidate.resolution)
        pair = (anchor.task_id, activity_id)
        if pair in seen:
            # Same (task, activity) reached through a code AND an external code.
            previous = resolved.links[seen[pair]].candidate
            candidate = merge_links(
                [
                    previous,
                    LinkCandidate(
                        previous.source_id,
                        previous.activity_key,
                        previous.external_code,
                        candidate.role,
                        candidate.resolution,
                        candidate.source_ref,
                        candidate.quote,
                    ),
                ]
            )[0]
            resolved.links.pop(seen.pop(pair))
            seen = {
                key: i
                for i, key in enumerate((item.task_id, item.activity_id) for item in resolved.links)
            }
        note = link_note(candidate)
        existing = await uow.plans.find_task_link(activity_id, anchor.task_id)
        status = (
            "nuevo"
            if existing is None
            else "sin cambios"
            if (existing.role, existing.note) == (candidate.role, note)
            else "actualiza"
        )
        seen[pair] = len(resolved.links)
        resolved.links.append(
            ResolvedLink(candidate, activity_key, anchor.task_id, activity_id, note, status)
        )
    return resolved


async def apply_followup(
    uow: FollowupUow,
    resolved: ResolvedFollowup,
    *,
    actor_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Write every resolved report and link atomically; returns write counts."""

    try:
        for report in resolved.reports:
            if report.status != "sin cambios":
                await uow.plans.upsert_report(
                    report.activity_id, report.draft.period, _report_payload(report.draft), actor_id
                )
        for link in resolved.links:
            if link.status != "sin cambios":
                await uow.plans.upsert_task_link(
                    link.task_id, link.activity_id, link.candidate.role, link.note, actor_id
                )
        await uow.commit()
    except BaseException:
        await uow.rollback()
        raise
    return {
        "reports_written": sum(r.status != "sin cambios" for r in resolved.reports),
        "links_written": sum(link.status != "sin cambios" for link in resolved.links),
    }
