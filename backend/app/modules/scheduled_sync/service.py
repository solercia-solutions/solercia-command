"""daily_sync use case (C02): isolated steps, one recorded run per organization.

Order per organization: (1) checklist sync (C01) when configured for it,
(2) intake pull since the start of the last run whose intake step was ``ok``
(``None`` = each port's default window), (3) classification — a no-op
extension point that C05 implements. A failing step never stops the next
ones: its session work is rolled back and the failure is recorded. Unknown
exceptions are recorded by TYPE only (their text may carry URLs or secrets);
the full traceback goes to the server log.

Transaction ownership: each step completes its own work (the checklist
service and the intake repositories commit); the run row is inserted once
at the end and committed by this use case through the unit of work.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

logger = logging.getLogger("solercia.scheduled_sync")

Trigger = Literal["scheduled", "manual"]

#: One run at a time per process (scheduled or manual). The scheduler adds
#: ``max_instances=1``; a manual request while this is held gets a 409.
SYNC_LOCK = asyncio.Lock()


class StepSkipped(Exception):
    """The step does not apply (not configured, no connectors, pending C05)."""


class StepFailed(Exception):
    """The step ran but failed partially; ``counts`` keeps what it did."""

    def __init__(self, detail: str, counts: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.counts = counts or {}


class SyncSteps(Protocol):
    async def checklist(self, organization_id: uuid.UUID) -> dict[str, Any]: ...

    async def intake(
        self,
        organization_id: uuid.UUID,
        *,
        since: datetime | None,
        actor_id: uuid.UUID | None,
    ) -> dict[str, Any]: ...

    async def classify(self, organization_id: uuid.UUID) -> dict[str, Any]: ...


class ClassificationStep(Protocol):
    """C05 extension point: classify the organization's pending threads."""

    async def __call__(self, organization_id: uuid.UUID) -> dict[str, Any]: ...


class NoopClassificationStep:
    async def __call__(self, organization_id: uuid.UUID) -> dict[str, Any]:
        raise StepSkipped("La clasificación con IA aún no está habilitada.")


class SyncRunStore(Protocol):
    async def last_successful_intake_started_at(
        self, organization_id: uuid.UUID
    ) -> datetime | None: ...

    async def add(self, run: dict[str, Any]) -> None: ...


class SyncUnit(Protocol):
    @property
    def steps(self) -> SyncSteps: ...

    @property
    def runs(self) -> SyncRunStore: ...

    async def organizations_to_sync(self) -> list[uuid.UUID]: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


def _error(exc: Exception) -> dict[str, str]:
    # Only StepFailed carries a message written by us; adapters translate
    # their known domain errors into it.
    if isinstance(exc, StepFailed):
        detail = str(exc)[:500]
    else:
        detail = "Error inesperado; revisa el registro del servidor."
    return {"type": type(exc).__name__, "detail": detail}


def _status(steps: list[dict[str, Any]]) -> str:
    executed = [step for step in steps if step["status"] != "skipped"]
    errors = [step for step in executed if step["status"] == "error"]
    if not errors:
        return "success"
    return "failed" if len(errors) == len(executed) else "partial"


async def run_organization_sync(
    unit: SyncUnit,
    organization_id: uuid.UUID,
    *,
    trigger: Trigger,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Run the three steps for ONE organization and record the run."""

    started_at = datetime.now(UTC)
    since = await unit.runs.last_successful_intake_started_at(organization_id)
    calls: list[tuple[str, Callable[[], Any]]] = [
        ("checklist", lambda: unit.steps.checklist(organization_id)),
        (
            "intake",
            lambda: unit.steps.intake(organization_id, since=since, actor_id=actor_id),
        ),
        ("classification", lambda: unit.steps.classify(organization_id)),
    ]
    steps: list[dict[str, Any]] = []
    for name, call in calls:
        step: dict[str, Any] = {
            "name": name,
            "status": "ok",
            "counts": {},
            "detail": None,
            "error": None,
        }
        try:
            step["counts"] = dict(await call() or {})
        except StepSkipped as exc:
            step.update(status="skipped", detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - isolate the step, record, continue
            logger.exception("Paso %s de la sincronización falló (%s).", name, organization_id)
            await unit.rollback()
            step.update(status="error", error=_error(exc))
            if isinstance(exc, StepFailed):
                step["counts"] = dict(exc.counts)
        steps.append(step)
    record = {
        "organization_id": organization_id,
        "trigger": trigger,
        "status": _status(steps),
        "started_at": started_at,
        "finished_at": datetime.now(UTC),
        "actor_id": actor_id,
        "steps": steps,
    }
    try:
        await unit.runs.add(record)
        await unit.commit()
    except BaseException:
        await unit.rollback()
        raise
    return record


UnitFactory = Callable[[], AbstractAsyncContextManager[SyncUnit]]


async def run_scheduled_sync(open_unit: UnitFactory) -> list[dict[str, Any]]:
    """daily_sync job body: every organization in its own unit, isolated."""

    async with SYNC_LOCK:
        async with open_unit() as unit:
            organizations = await unit.organizations_to_sync()
        records = []
        for organization_id in organizations:
            try:
                async with open_unit() as unit:
                    records.append(
                        await run_organization_sync(unit, organization_id, trigger="scheduled")
                    )
            except Exception:  # noqa: BLE001 - one organization never blocks the others
                logger.exception("La sincronización de %s no se pudo registrar.", organization_id)
        logger.info("Sincronización programada: %d organizaciones.", len(records))
        return records
