"""C05: the classification step of daily_sync (C02) runs the reconciliation
channel, records its counts, and fails ISOLATED when the LLM is down."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.reconciliation.step import ReconciliationClassificationStep
from app.modules.scheduled_sync.service import (
    StepFailed,
    StepSkipped,
    run_organization_sync,
)

pytestmark = pytest.mark.asyncio

ORG = uuid.uuid4()
NOW = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)


class FakeService:
    def __init__(self, counts):
        self.counts = counts
        self.calls = []

    async def classify_window(self, organization_id, since):
        self.calls.append((organization_id, since))
        return dict(self.counts)


def _step(service, *, enabled=True, window_days=7):
    return ReconciliationClassificationStep(
        lambda: service, enabled=enabled, window_days=window_days, clock=lambda: NOW
    )


async def test_runs_the_window_and_returns_counts():
    service = FakeService({"threads": 2, "created": 2, "llm_error": None})
    counts = await _step(service)(ORG)
    assert counts["created"] == 2
    assert service.calls == [(ORG, NOW - timedelta(days=7))]


async def test_disabled_is_skipped():
    with pytest.raises(StepSkipped):
        await _step(FakeService({}), enabled=False)(ORG)


async def test_llm_down_fails_the_step_keeping_counts():
    service = FakeService({"threads": 3, "created": 3, "llm_error": "llm_unavailable"})
    with pytest.raises(StepFailed) as failure:
        await _step(service)(ORG)
    assert failure.value.counts["created"] == 3
    assert "llm_unavailable" in str(failure.value)


class _Runs:
    def __init__(self):
        self.added = []

    async def last_successful_intake_started_at(self, organization_id):
        return None

    async def add(self, run):
        self.added.append(run)


class _Steps:
    def __init__(self, classifier):
        self.classifier = classifier

    async def checklist(self, organization_id):
        return {"created": 0}

    async def intake(self, organization_id, *, since, actor_id):
        return {"items_new": 1}

    async def classify(self, organization_id):
        return await self.classifier(organization_id)


class _Unit:
    def __init__(self, classifier):
        self.steps = _Steps(classifier)
        self.runs = _Runs()
        self.rollbacks = 0

    async def commit(self):
        return None

    async def rollback(self):
        self.rollbacks += 1


async def test_failure_is_isolated_and_recorded_in_the_run():
    service = FakeService({"threads": 1, "created": 1, "llm_error": "llm_timeout"})
    unit = _Unit(_step(service))
    record = await run_organization_sync(unit, ORG, trigger="scheduled")
    steps = {s["name"]: s for s in record["steps"]}
    assert steps["checklist"]["status"] == steps["intake"]["status"] == "ok"
    assert steps["classification"]["status"] == "error"
    assert steps["classification"]["counts"]["created"] == 1
    assert record["status"] == "partial"


async def test_real_steps_wire_the_reconciliation_step():
    from app.modules.scheduled_sync.router import get_sync_steps

    steps = get_sync_steps(db=object())
    assert isinstance(steps.classifier, ReconciliationClassificationStep)
