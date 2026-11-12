"""SQLAlchemy adapter for ``scheduled_sync_runs``. Never commits: the use case
(:mod:`app.modules.scheduled_sync.service`) owns completion through the
unit of work (:class:`app.modules.scheduled_sync.unit.SessionSyncUnit`).

Every read is scoped by ``organization_id`` except
:meth:`organizations_to_sync`, the system job's deliberate cross-tenant
discovery (it returns ids only, never data).
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import Connector
from app.modules.organizations.models import Organization

from .models import ScheduledSyncRun


class SqlScheduledSyncRunStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, run: dict[str, Any]) -> None:
        self.session.add(ScheduledSyncRun(**run))
        await self.session.flush()

    async def last_successful_intake_started_at(
        self, organization_id: uuid.UUID
    ) -> datetime | None:
        """Start of the newest run whose intake step finished ``ok``."""

        return await self.session.scalar(
            select(func.max(ScheduledSyncRun.started_at)).where(
                ScheduledSyncRun.organization_id == organization_id,
                # JSONB containment (@>): the intake step of this run is ok.
                ScheduledSyncRun.steps.contains([{"name": "intake", "status": "ok"}]),
            )
        )

    async def list_runs(
        self, organization_id: uuid.UUID, *, page: int, size: int
    ) -> tuple[Sequence[ScheduledSyncRun], int]:
        scope = ScheduledSyncRun.organization_id == organization_id
        total = await self.session.scalar(
            select(func.count()).select_from(ScheduledSyncRun).where(scope)
        )
        rows = await self.session.scalars(
            select(ScheduledSyncRun)
            .where(scope)
            .order_by(ScheduledSyncRun.started_at.desc(), ScheduledSyncRun.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return rows.all(), int(total or 0)

    async def organizations_to_sync(self, *, checklist_slug: str | None) -> list[uuid.UUID]:
        """Active organizations with an active connector, plus the checklist's."""

        with_connectors = (
            select(Connector.organization_id).where(Connector.is_active.is_(True)).distinct()
        )
        condition: ColumnElement[bool] = Organization.id.in_(with_connectors)
        if checklist_slug:
            condition = condition | (Organization.slug == checklist_slug)
        rows = await self.session.scalars(
            select(Organization.id)
            .where(Organization.is_active.is_(True), condition)
            .order_by(Organization.created_at, Organization.id)
        )
        return list(rows.all())
