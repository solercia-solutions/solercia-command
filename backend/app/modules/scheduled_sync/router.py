"""``/sync`` routes (C02) — admin only, scoped to the caller's organization.

``POST /sync/run`` runs daily_sync NOW for the caller's organization only
(``trigger=manual``); it never touches another tenant. ``GET /sync/runs``
lists that organization's runs, newest first, paginated. Scheduled runs of
other organizations are never visible here.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_actor_id, require_role
from app.modules.organizations.models import OrganizationMember
from app.modules.reconciliation.step import session_classification_step
from app.modules.task_import.checklist_sync_service import ChecklistSyncConfig
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException

from .repository import SqlScheduledSyncRunStore
from .schemas import ScheduledSyncRunRead
from .service import SYNC_LOCK, SyncSteps, run_organization_sync
from .unit import SessionSyncSteps, SessionSyncUnit

router = APIRouter(prefix="/sync", tags=["scheduled-sync"])

require_sync_admin = require_role(MemberRole.admin)


def get_sync_steps(db: AsyncSession = Depends(get_db)) -> SyncSteps:
    """Real steps bound to the request session (overridable in tests)."""

    return SessionSyncSteps(
        db,
        ChecklistSyncConfig.from_settings(settings),
        session_classification_step(db, settings),
    )


@router.post("/run")
async def run_sync_now(
    membership: OrganizationMember = Depends(require_sync_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
    steps: SyncSteps = Depends(get_sync_steps),
) -> dict:
    """Run checklist → intake → classification now for the caller's
    organization (admin only). 409 ``SYNC_ALREADY_RUNNING`` while another
    run is in progress in this process."""

    if SYNC_LOCK.locked():
        raise AppException(
            "Ya hay una sincronización en curso; intenta de nuevo en unos minutos.",
            code="SYNC_ALREADY_RUNNING",
            status_code=status.HTTP_409_CONFLICT,
        )
    async with SYNC_LOCK:
        record = await run_organization_sync(
            SessionSyncUnit(db, steps),
            membership.organization_id,
            trigger="manual",
            actor_id=actor_id,
        )
    return {
        "data": ScheduledSyncRunRead.model_validate(record),
        "message": "Sincronización ejecutada.",
    }


@router.get("/runs")
async def list_sync_runs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    membership: OrganizationMember = Depends(require_sync_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The caller organization's sync runs, newest first (admin only)."""

    rows, total = await SqlScheduledSyncRunStore(db).list_runs(
        membership.organization_id, page=page, size=size
    )
    return {
        "data": [ScheduledSyncRunRead.model_validate(row) for row in rows],
        "meta": {"page": page, "size": size, "total": total},
    }
