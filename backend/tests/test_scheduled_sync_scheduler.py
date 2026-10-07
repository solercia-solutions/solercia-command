"""C02: cron registration of daily_sync — hours, explicit zone and run guards."""

from types import SimpleNamespace

import pytest
from apscheduler.triggers.cron import CronTrigger
from pydantic import ValidationError

from app.config import Settings
from app.modules.scheduled_sync.scheduler import (
    build_sync_scheduler,
    parse_sync_times,
)


def _settings(**overrides):
    base = {
        "SCHEDULED_SYNC_ENABLED": True,
        "SCHEDULED_SYNC_TIMES": "06:00,23:59",
        "SCHEDULED_SYNC_TZ": "America/Bogota",
        "SCHEDULED_SYNC_MISFIRE_GRACE_SECONDS": 3600,
    }
    return SimpleNamespace(**{**base, **overrides})


async def _job():
    return None


def _fields(trigger: CronTrigger) -> dict[str, str]:
    return {f.name: str(f) for f in trigger.fields}


def test_settings_defaults_keep_the_sync_disabled():
    current = Settings(_env_file=None)
    assert current.SCHEDULED_SYNC_ENABLED is False
    assert current.SCHEDULED_SYNC_TIMES == "06:00,23:59"
    assert current.SCHEDULED_SYNC_TZ == "America/Bogota"


@pytest.mark.parametrize("raw", ["25:00", "6", "06:60", "", "06:00,,23:59"])
def test_invalid_times_are_rejected_by_settings(raw):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SCHEDULED_SYNC_TIMES=raw)


def test_invalid_zone_is_rejected_by_settings():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SCHEDULED_SYNC_TZ="Marte/Olympus")


def test_parse_sync_times():
    assert parse_sync_times("06:00, 23:59") == [(6, 0), (23, 59)]
    with pytest.raises(ValueError):
        parse_sync_times("24:00")


def test_one_cron_job_per_time_with_explicit_zone_and_guards():
    scheduler = build_sync_scheduler(_settings(), _job)
    jobs = sorted(scheduler.get_jobs(), key=lambda j: j.id)
    assert [j.id for j in jobs] == ["daily_sync_0600", "daily_sync_2359"]
    for job, (hour, minute) in zip(jobs, [("6", "0"), ("23", "59")], strict=True):
        assert isinstance(job.trigger, CronTrigger)
        assert str(job.trigger.timezone) == "America/Bogota"
        fields = _fields(job.trigger)
        assert (fields["hour"], fields["minute"]) == (hour, minute)
        assert job.max_instances == 1 and job.coalesce is True
        assert job.misfire_grace_time == 3600
        assert job.func is _job
    assert not scheduler.running


def test_custom_times_and_zone():
    scheduler = build_sync_scheduler(
        _settings(SCHEDULED_SYNC_TIMES="07:30", SCHEDULED_SYNC_TZ="UTC"), _job
    )
    (job,) = scheduler.get_jobs()
    assert job.id == "daily_sync_0730" and str(job.trigger.timezone) == "UTC"


def test_only_sync_jobs_are_registered():
    scheduler = build_sync_scheduler(_settings(), _job)
    assert all(j.id.startswith("daily_sync_") for j in scheduler.get_jobs())
