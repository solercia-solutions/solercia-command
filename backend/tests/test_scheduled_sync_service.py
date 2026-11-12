"""C02: daily_sync orchestration with fakes — order, failure isolation, since, record."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from app.modules.scheduled_sync.service import (
    NoopClassificationStep,
    StepFailed,
    StepSkipped,
    run_organization_sync,
    run_scheduled_sync,
)

ORG = uuid.uuid4()
OTHER = uuid.uuid4()
LAST_OK = datetime(2026, 10, 6, 23, 59, tzinfo=UTC)


class FakeSteps:
    def __init__(self, *, fail=(), skip=(), partial=()):
        self.calls: list[tuple] = []
        self.fail, self.skip, self.partial = set(fail), set(skip), set(partial)

    async def _step(self, name, organization_id, **kwargs):
        self.calls.append((name, organization_id, kwargs))
        if name in self.fail:
            raise RuntimeError(f"secreto://{name}")
        if name in self.skip:
            raise StepSkipped("sin configurar")
        if name in self.partial:
            raise StepFailed("1 cuenta con error", {"accounts": 2, "errored": 1})
        return {"done": 1}

    async def checklist(self, organization_id):
        return await self._step("checklist", organization_id)

    async def intake(self, organization_id, *, since, actor_id):
        return await self._step("intake", organization_id, since=since, actor_id=actor_id)

    async def classify(self, organization_id):
        return await self._step("classification", organization_id)


class FakeRuns:
    """In-memory, tenant-scoped, insert-only run store."""

    def __init__(self, last_ok=None, organizations=(ORG,)):
        self.rows: list[dict] = []
        self.pending: list[dict] = []
        self.last_ok = last_ok or {}
        self.organizations = list(organizations)
        self.commits = self.rollbacks = 0

    async def last_successful_intake_started_at(self, organization_id):
        return self.last_ok.get(organization_id)

    async def add(self, run):
        self.pending.append(run)

    async def organizations_to_sync(self):
        return self.organizations

    async def commit(self):
        self.rows += self.pending
        self.pending = []
        self.commits += 1

    async def rollback(self):
        self.pending = []
        self.rollbacks += 1


class Unit:
    """Unit of work: the steps and the run store share one transaction scope."""

    def __init__(self, steps, runs):
        self.steps, self.runs = steps, runs

    async def organizations_to_sync(self):
        return await self.runs.organizations_to_sync()

    async def commit(self):
        await self.runs.commit()

    async def rollback(self):
        await self.runs.rollback()


@pytest.mark.asyncio
async def test_steps_run_in_order_and_success_is_recorded():
    steps, runs = FakeSteps(), FakeRuns(last_ok={ORG: LAST_OK})
    record = await run_organization_sync(Unit(steps, runs), ORG, trigger="scheduled")
    assert [c[0] for c in steps.calls] == ["checklist", "intake", "classification"]
    assert steps.calls[1][2] == {"since": LAST_OK, "actor_id": None}
    assert record["status"] == "success" and record["trigger"] == "scheduled"
    assert [s["name"] for s in record["steps"]] == ["checklist", "intake", "classification"]
    assert all(s["status"] == "ok" for s in record["steps"])
    assert runs.rows == [record] and record["organization_id"] == ORG
    assert record["started_at"] <= record["finished_at"]


@pytest.mark.asyncio
async def test_a_failing_step_does_not_stop_the_others():
    steps, runs = FakeSteps(fail={"checklist"}), FakeRuns()
    record = await run_organization_sync(Unit(steps, runs), ORG, trigger="manual")
    assert [c[0] for c in steps.calls] == ["checklist", "intake", "classification"]
    checklist, intake, _ = record["steps"]
    assert checklist["status"] == "error" and intake["status"] == "ok"
    assert record["status"] == "partial"
    # Unknown errors never leak their message (may carry URLs or secrets).
    assert "secreto" not in str(record) and checklist["error"]["type"] == "RuntimeError"
    assert runs.rollbacks >= 1 and len(runs.rows) == 1


@pytest.mark.asyncio
async def test_default_window_when_there_is_no_successful_run():
    steps = FakeSteps()
    await run_organization_sync(Unit(steps, FakeRuns()), ORG, trigger="manual", actor_id=OTHER)
    assert steps.calls[1][2] == {"since": None, "actor_id": OTHER}


@pytest.mark.asyncio
async def test_skipped_and_partial_steps_are_recorded_with_counts():
    steps = FakeSteps(skip={"checklist"}, partial={"intake"})
    record = await run_organization_sync(Unit(steps, FakeRuns()), ORG, trigger="scheduled")
    checklist, intake, classification = record["steps"]
    assert checklist == {
        "name": "checklist",
        "status": "skipped",
        "counts": {},
        "detail": "sin configurar",
        "error": None,
    }
    assert intake["status"] == "error" and intake["counts"] == {"accounts": 2, "errored": 1}
    assert intake["error"]["detail"] == "1 cuenta con error"
    assert classification["status"] == "ok"
    assert record["status"] == "partial"


@pytest.mark.asyncio
async def test_every_executed_step_failing_is_failed():
    steps = FakeSteps(skip={"checklist"}, fail={"intake", "classification"})
    record = await run_organization_sync(Unit(steps, FakeRuns()), ORG, trigger="scheduled")
    assert record["status"] == "failed"


@pytest.mark.asyncio
async def test_all_skipped_is_success():
    steps = FakeSteps(skip={"checklist", "intake", "classification"})
    record = await run_organization_sync(Unit(steps, FakeRuns()), ORG, trigger="scheduled")
    assert record["status"] == "success"


@pytest.mark.asyncio
async def test_noop_classification_is_the_c05_extension_point():
    with pytest.raises(StepSkipped):
        await NoopClassificationStep()(ORG)


@pytest.mark.asyncio
async def test_scheduled_sync_isolates_each_organization():
    runs = FakeRuns(organizations=[ORG, OTHER])
    seen = []

    @asynccontextmanager
    async def open_unit():
        steps = FakeSteps()

        async def checklist(organization_id):
            seen.append(organization_id)
            if organization_id == ORG:
                raise RuntimeError("falla aislada")
            return {}

        steps.checklist = checklist
        yield Unit(steps, runs)

    records = await run_scheduled_sync(open_unit)
    assert seen == [ORG, OTHER]
    assert [r["organization_id"] for r in records] == [ORG, OTHER]
    assert [r["status"] for r in records] == ["partial", "success"]
