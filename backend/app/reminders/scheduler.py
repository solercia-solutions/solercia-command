"""APScheduler job for periodic reminder dispatch — mirrors app/alerts/scheduler.py.

Registers its own job onto the SAME ``AsyncIOScheduler`` instance returned by
``app.alerts.scheduler.start_scheduler()`` (design.md, "segundo job propio en
el MISMO AsyncIOScheduler"): one scheduler loop, isolated jobs. ``_run_reminders``
opens its own DB session and swallows its own exceptions — a reminders failure
never takes down the alert evaluation job or vice-versa. Dependency direction
is ``main -> reminders``, NEVER ``alerts -> reminders``.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.reminders.dispatcher import dispatch_reminders

logger = logging.getLogger("solercia.reminders.scheduler")


async def _run_reminders() -> None:
    """Scheduler job wrapper: opens its own DB session and runs the dispatcher."""
    async with AsyncSessionLocal() as db:
        try:
            total = await dispatch_reminders(db)
            logger.info(
                "Scheduled reminder dispatch complete: %d new notifications.", total
            )
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled reminder dispatch failed.")


def register_reminders_job(scheduler: AsyncIOScheduler) -> None:
    """Register the ``reminders_dispatch`` job onto an already-running scheduler."""
    interval_minutes: int = getattr(settings, "REMINDER_SCHEDULER_INTERVAL_MINUTES", 5)
    scheduler.add_job(
        _run_reminders,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="reminders_dispatch",
        name="Reminder Dispatch",
        replace_existing=True,
    )
    logger.info("Reminders job registered (interval: %smin).", interval_minutes)
