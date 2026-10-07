"""Session-bound adapters for daily_sync: the real steps and the unit of work.

All steps of one organization share ONE ``AsyncSession``; after a failed
step the use case rolls it back so the next step starts clean.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.intake.service import IntakeService
from app.modules.organizations.repository import OrganizationRepository
from app.modules.task_import.checklist_apply import ChecklistTargetError
from app.modules.task_import.checklist_sync_service import (
    ChecklistMemberError,
    ChecklistOrganizationError,
    ChecklistSourceError,
    ChecklistSyncConfig,
    sync_checklist_from_config,
)
from app.shared.enums import IntakeRunStatus

from .repository import SqlScheduledSyncRunStore
from .service import ClassificationStep, NoopClassificationStep, StepFailed, StepSkipped

_CHECKLIST_ERRORS = (
    ChecklistSourceError,
    ChecklistOrganizationError,
    ChecklistMemberError,
    ChecklistTargetError,
)


class SessionSyncSteps:
    def __init__(
        self,
        session: AsyncSession,
        checklist: ChecklistSyncConfig | None,
        classifier: ClassificationStep | None = None,
    ) -> None:
        self.session = session
        self.checklist_config = checklist
        self.classifier = classifier or NoopClassificationStep()

    async def checklist(self, organization_id: uuid.UUID) -> dict[str, Any]:
        config = self.checklist_config
        if config is None:
            raise StepSkipped("La sincronización del checklist no está configurada.")
        organization = await OrganizationRepository(self.session).get_by_slug(
            config.organization_slug
        )
        if organization is None or organization.id != organization_id:
            raise StepSkipped("El checklist está configurado para otra organización.")
        try:
            result = await sync_checklist_from_config(self.session, config)
        except _CHECKLIST_ERRORS as exc:
            raise StepFailed(f"{type(exc).__name__}: {exc}") from exc
        return result.counts

    async def intake(
        self,
        organization_id: uuid.UUID,
        *,
        since: datetime | None,
        actor_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        service = IntakeService(self.session)
        if not await service.connectors.list_connectors(organization_id):
            raise StepSkipped("La organización no tiene conectores activos.")
        runs = await service.pull(organization_id, actor_id=actor_id, since=since)
        errored = sum(1 for run in runs if run.status == IntakeRunStatus.error)
        counts = {
            "accounts": len(runs),
            "errored": errored,
            "since": since.isoformat() if since else None,
            **{
                key: sum(getattr(run, key) for run in runs)
                for key in ("items_fetched", "items_new", "items_duplicated", "items_converted")
            },
        }
        if errored:
            raise StepFailed(f"{errored} de {len(runs)} cuentas terminaron con error.", counts)
        return counts

    async def classify(self, organization_id: uuid.UUID) -> dict[str, Any]:
        return await self.classifier(organization_id)


class SessionSyncUnit:
    def __init__(
        self,
        session: AsyncSession,
        steps: Any,
        checklist_slug: str | None = None,
    ) -> None:
        self.session = session
        self.steps = steps
        self.runs = SqlScheduledSyncRunStore(session)
        self._checklist_slug = checklist_slug

    async def organizations_to_sync(self) -> list[uuid.UUID]:
        return await self.runs.organizations_to_sync(checklist_slug=self._checklist_slug)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def session_unit_factory(
    session_factory: Callable[[], Any],
    checklist: ChecklistSyncConfig | None,
    classifier_factory: Callable[[AsyncSession], ClassificationStep] | None = None,
) -> Callable[[], Any]:
    """``open_unit`` for :func:`run_scheduled_sync`: one fresh session each.
    ``classifier_factory`` binds the classification step to that session."""

    @asynccontextmanager
    async def open_unit() -> AsyncIterator[SessionSyncUnit]:
        async with session_factory() as session:
            classifier = classifier_factory(session) if classifier_factory else None
            yield SessionSyncUnit(
                session,
                SessionSyncSteps(session, checklist, classifier),
                checklist.organization_slug if checklist else None,
            )

    return open_unit
