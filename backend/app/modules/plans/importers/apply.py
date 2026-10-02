"""Import use case: parsed plans -> 45a write seam, in ONE transaction (D10).

The repository never commits (agents/rules/solercia-persistence.md); this use
case owns completion: either every plan, activity and link of the bundle is
written or none is. Idempotent because every write is an upsert by natural
key — ``(organization, plan.code)``, ``(plan, activity.code)`` and
``(from, to, link_type)`` — so a rerun creates no rows.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plans.importers.common import ParsedPlan
from app.modules.plans.importers.linker import (
    LINK_TYPE,
    LinkDraft,
    ReviewItem,
    resolve_cross_references,
)
from app.modules.plans.models import Plan, PlanActivity, PlanActivityLink
from app.modules.plans.repository import PlansRepository
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert
from app.modules.plans.vocabularies import validate_plan_type, validate_resolution


@dataclass
class ImportBundle:
    plans: list[ParsedPlan]
    links: list[LinkDraft] = field(default_factory=list)
    review: list[ReviewItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_bundle(plans: list[ParsedPlan]) -> ImportBundle:
    """Validate the set of plans and resolve the links the sources state."""

    kinds = [parsed.kind for parsed in plans]
    if len(set(kinds)) != len(kinds):
        raise ValueError("Cada tipo de plan se importa desde una sola fuente por corrida.")
    for parsed in plans:
        validate_plan_type(parsed.plan.plan_type)
    bundle = ImportBundle(plans=plans)
    by_kind = {parsed.kind: parsed for parsed in plans}
    ptr, pspi = by_kind.get("ptr"), by_kind.get("pspi")
    if ptr is not None and ptr.cross_refs:
        if pspi is None:
            bundle.warnings.append(
                "El PTR cita actividades del PSPI, pero el PSPI no está en esta corrida: "
                "los enlaces PTR → PSPI no se resuelven."
            )
        else:
            bundle.links, bundle.review = resolve_cross_references(ptr, pspi)
    if "pai" in by_kind:
        bundle.warnings.append(
            "El PAI no declara referencias a actividades de otros planes: no genera enlaces."
        )
    for link in bundle.links:
        validate_resolution(link.resolution)
    return bundle


class PlanImportPort(Protocol):
    async def upsert_plan(
        self, organization_id: uuid.UUID, data: PlanUpsert, actor_id: uuid.UUID | None = None
    ) -> Plan: ...

    async def upsert_activity(
        self, plan_id: uuid.UUID, data: PlanActivityUpsert, actor_id: uuid.UUID | None = None
    ) -> PlanActivity: ...

    async def upsert_activity_link(
        self,
        from_activity_id: uuid.UUID,
        to_activity_id: uuid.UUID,
        link_type: str,
        resolution: str,
        source_reference: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> PlanActivityLink: ...


class PlanImportUow(Protocol):
    plans: PlanImportPort

    async def flush(self) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SessionPlanImportUow:
    """Binds the plans repository and the completion to one caller session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plans: PlanImportPort = PlansRepository(session)

    async def flush(self) -> None:
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def apply_bundle(
    uow: PlanImportUow,
    organization_id: uuid.UUID,
    bundle: ImportBundle,
    *,
    actor_id: uuid.UUID | None = None,
) -> int:
    """Write the bundle atomically; return the number of upserted activities."""

    try:
        activity_ids: dict[str, uuid.UUID] = {}
        for parsed in bundle.plans:
            plan = await uow.plans.upsert_plan(organization_id, parsed.plan, actor_id)
            for data in parsed.activities:
                activity = await uow.plans.upsert_activity(plan.id, data, actor_id)
                activity_ids[f"{parsed.plan.code}/{data.code}"] = activity.id
        # Activities must exist before their links reference them; the
        # sessions of this app run with autoflush disabled.
        await uow.flush()
        for link in bundle.links:
            await uow.plans.upsert_activity_link(
                activity_ids[link.from_key],
                activity_ids[link.to_key],
                LINK_TYPE,
                link.resolution,
                link.source_reference,
                actor_id,
            )
        await uow.commit()
        return len(activity_ids)
    except BaseException:
        await uow.rollback()
        raise
