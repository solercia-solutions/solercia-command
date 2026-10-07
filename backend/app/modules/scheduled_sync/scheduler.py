"""Scheduler of the daily_sync job (C02).

A dedicated ``AsyncIOScheduler``, separate from the alerts scheduler, so it
can run under ``STARTUP_PROFILE=local_restricted`` without registering
alerts, reminders nor mail. One ``CronTrigger`` per ``SCHEDULED_SYNC_TIMES``
entry with the explicit zone ``SCHEDULED_SYNC_TZ``; ``max_instances=1`` and
``coalesce=True`` so a slow run or a wake-up after sleep never stacks runs.

Multi-worker note (same as ``app/alerts/scheduler.py``): every uvicorn
worker would start its own scheduler. The host runs a single worker.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("solercia.scheduled_sync")

_scheduler: AsyncIOScheduler | None = None


def parse_sync_times(raw: str) -> list[tuple[int, int]]:
    times = []
    for part in raw.split(","):
        hour_text, _, minute_text = part.strip().partition(":")
        hour, minute = int(hour_text), int(minute_text)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Hora no válida: «{part.strip()}».")
        times.append((hour, minute))
    return times


def build_sync_scheduler(settings: Any, job: Callable[[], Awaitable[Any]]) -> AsyncIOScheduler:
    """Return a NOT started scheduler with one daily_sync job per time."""

    zone = settings.SCHEDULED_SYNC_TZ
    scheduler = AsyncIOScheduler(timezone=zone)
    for hour, minute in parse_sync_times(settings.SCHEDULED_SYNC_TIMES):
        scheduler.add_job(
            job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=zone),
            id=f"daily_sync_{hour:02d}{minute:02d}",
            name=f"Sincronización diaria {hour:02d}:{minute:02d} ({zone})",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=settings.SCHEDULED_SYNC_MISFIRE_GRACE_SECONDS,
            replace_existing=True,
        )
    return scheduler


async def _daily_sync() -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.modules.reconciliation.step import session_classification_step
    from app.modules.task_import.checklist_sync_service import ChecklistSyncConfig

    from .service import run_scheduled_sync
    from .unit import session_unit_factory

    try:
        await run_scheduled_sync(
            session_unit_factory(
                AsyncSessionLocal,
                ChecklistSyncConfig.from_settings(settings),
                lambda session: session_classification_step(session, settings),
            )
        )
    except Exception:  # noqa: BLE001 - a job failure must never kill the scheduler
        logger.exception("La sincronización programada falló.")


def start_sync_scheduler() -> AsyncIOScheduler:
    """Create and start the daily_sync scheduler. Call once from lifespan."""

    global _scheduler
    from app.config import settings

    _scheduler = build_sync_scheduler(settings, _daily_sync)
    _scheduler.start()
    logger.info(
        "Sincronización programada activa: %s (%s).",
        settings.SCHEDULED_SYNC_TIMES,
        settings.SCHEDULED_SYNC_TZ,
    )
    return _scheduler


def stop_sync_scheduler() -> None:
    """Shut the scheduler down without waiting for a running job."""

    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Sincronización programada detenida.")
    _scheduler = None
