"""Executive dashboard routes.

Requires authentication; all metrics are scoped to the caller's current
organization and wrapped in a ``{data}`` envelope.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_membership
from app.modules.dashboard.service import (
    DEFAULT_WORK_GAP_THRESHOLD_DAYS,
    DashboardService,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.dashboard.daily_contracts import (
    DailyAccessPort, DailyClock, DailyContext as TrustedDailyContext,
)
from app.modules.dashboard.daily_repository import DailyRepository
from app.modules.dashboard.daily_schemas import DailyResponse, project_daily
from app.modules.dashboard.daily_service import DailySummaryError, DailySummaryService
from app.shared.exceptions import AppException
from app.shared.no_store_route import NoStoreRoute

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Deadline covers both the local organization gate and the facts query.
DAILY_QUERY_SECONDS = 5.0
_daily_router = APIRouter(route_class=NoStoreRoute)


class _DailyClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def get_daily_clock() -> DailyClock:
    return _DailyClock()


def get_daily_repository(db: AsyncSession = Depends(get_db)) -> DailyAccessPort:
    return DailyRepository(db)


def _daily_error(status: int, code: str) -> AppException:
    return AppException('No se pudo consultar el resumen diario.', code, status,
                        headers={'Cache-Control': 'no-store'})


@lru_cache(maxsize=1)
def _iana_timezones() -> frozenset[str]:
    return frozenset(available_timezones()) - {'localtime', 'posixrules'}


def _daily_options(request: Request) -> tuple[str, str]:
    params = request.query_params
    if (set(params) != {'timezone', 'date_policy'}
            or any(len(params.getlist(key)) != 1 for key in params)
            or params['timezone'] not in _iana_timezones()
            or params['date_policy'] not in ('stored_calendar_date', 'instant')):
        raise _daily_error(422, 'invalid_daily_parameters')
    return params['timezone'], params['date_policy']


async def _daily_disconnect(request: Request) -> None:
    while True:
        if (await request.receive())['type'] == 'http.disconnect':
            return
        await asyncio.sleep(0)


async def _join_daily(tasks) -> None:
    """Cancel once and join even under repeated cancellation before DB release.

    The deadline bounds admission/waiting, not driver cleanup. Never detach an
    in-flight query just to return a timely error while its session is closing.
    """
    for task in tasks:
        if not task.done():
            task.cancel()
    joined = asyncio.gather(*tasks, return_exceptions=True)
    interrupted = False
    while not joined.done():
        try:
            await asyncio.shield(joined)
        except asyncio.CancelledError:
            interrupted = True
    joined.result()
    if interrupted:
        raise asyncio.CancelledError


@_daily_router.get('/daily', response_model=DailyResponse)
async def daily_dashboard(
    request: Request,
    membership: OrganizationMember = Depends(get_current_membership),
    repository: DailyAccessPort = Depends(get_daily_repository),
    clock: DailyClock = Depends(get_daily_clock),
) -> DailyResponse:
    """Consulta tus tareas con timezone IANA y date_policy explícitos.

    Los grupos pueden superponerse; las advertencias indican cobertura parcial.
    No representa sincronización con proveedores ni infiere cancelaciones.
    """
    if not settings.DAILY_DASHBOARD_ENABLED:
        raise _daily_error(404, 'daily_disabled')
    timezone, date_policy = _daily_options(request)
    context = TrustedDailyContext(membership.organization_id, membership.user_id)

    async def load():
        if not await repository.organization_available(context):
            raise _daily_error(403, 'organization_unavailable')
        try:
            summary = await DailySummaryService(repository, clock).summarize(
                context, timezone=timezone, date_policy=date_policy,
            )
        except DailySummaryError as error:
            if str(error) == 'input_limit':
                raise _daily_error(413, 'input_limit') from None
            raise _daily_error(503, 'daily_unavailable') from None
        return project_daily(summary)

    work = asyncio.create_task(load())
    disconnect = asyncio.create_task(_daily_disconnect(request))
    try:
        done, _ = await asyncio.wait((work, disconnect), timeout=DAILY_QUERY_SECONDS,
                                     return_when=asyncio.FIRST_COMPLETED)
        if disconnect in done:
            raise _daily_error(499, 'client_disconnected')
        if work not in done:
            raise _daily_error(504, 'timeout')
        return work.result()
    finally:
        await _join_daily((work, disconnect))


router.include_router(_daily_router)


@router.get("/executive")
async def executive_dashboard(
    threshold_days: int = Query(default=DEFAULT_WORK_GAP_THRESHOLD_DAYS, ge=1),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the executive ("vista de jefe") summary for the organization.

    ``threshold_days`` (default 3) sets the lookback window for the
    ``work_gap.no_recent_activity`` list (dashboard-executive.md).
    """

    service = DashboardService(db)
    data = await service.executive(membership.organization_id, threshold_days)
    return {"data": data}


@router.get("/performance")
async def performance_dashboard(
    sprint_id: uuid.UUID | None = None,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return per-collaborator performance metrics for the organization.

    Pass ``sprint_id`` to restrict the figures to a single sprint's tasks.
    """

    service = DashboardService(db)
    data = await service.performance(membership.organization_id, sprint_id)
    return {"data": data}
