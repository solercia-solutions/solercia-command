"""APScheduler jobs for the email engine — mirrors app/reminders/scheduler.py.

Registers its own job(s) onto the SAME ``AsyncIOScheduler`` instance returned
by ``app.alerts.scheduler.start_scheduler()``: one scheduler loop, isolated
jobs. Each job opens its own DB session and swallows its own exceptions — an
email failure never takes down the alert/reminder jobs or vice-versa.
Dependency direction is ``main -> email``, NEVER ``alerts -> email`` (D3, gate
correction — ``email_dispatch`` is the ONLY outbox dispatcher in the system).
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.email.outbox import dispatch_outbox

logger = logging.getLogger("solercia.email.scheduler")


async def _run_dispatch() -> None:
    """Scheduler job wrapper: opens its own DB session and drains the outbox."""
    async with AsyncSessionLocal() as db:
        try:
            total = await dispatch_outbox(db)
            logger.info("Scheduled email dispatch complete: %d row(s) processed.", total)
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled email dispatch failed.")


def register_email_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register the ``email_dispatch`` job onto an already-running scheduler."""
    interval_minutes: int = getattr(settings, "EMAIL_DISPATCH_INTERVAL_MINUTES", 5)
    scheduler.add_job(
        _run_dispatch,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="email_dispatch",
        name="Email Outbox Dispatch",
        replace_existing=True,
    )
    logger.info("Email dispatch job registered (interval: %smin).", interval_minutes)
