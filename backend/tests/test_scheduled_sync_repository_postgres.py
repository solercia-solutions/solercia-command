"""C02: scheduled_sync_runs adapter against real PostgreSQL (disposable)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.connectors.models import Connector
from app.modules.scheduled_sync.repository import SqlScheduledSyncRunStore
from tests.conftest import skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]

T0 = datetime(2026, 10, 6, 6, 0, tzinfo=UTC)


def _run(org, started, *, intake="ok", status="success"):
    return {
        "organization_id": org,
        "trigger": "scheduled",
        "status": status,
        "started_at": started,
        "finished_at": started + timedelta(minutes=1),
        "actor_id": None,
        "steps": [
            {"name": "checklist", "status": "ok", "counts": {}, "detail": None, "error": None},
            {"name": "intake", "status": intake, "counts": {}, "detail": None, "error": None},
        ],
    }


async def test_last_successful_intake_uses_the_intake_step_and_tenant(session, two_orgs):
    org_a, org_b = two_orgs.a.organization.id, two_orgs.b.organization.id
    store = SqlScheduledSyncRunStore(session)
    await store.add(_run(org_a, T0))
    await store.add(_run(org_a, T0 + timedelta(hours=18), intake="error", status="partial"))
    await store.add(_run(org_b, T0 + timedelta(days=1)))
    await session.flush()
    assert await store.last_successful_intake_started_at(org_a) == T0
    assert await store.last_successful_intake_started_at(uuid.uuid4()) is None


async def test_list_runs_is_paginated_newest_first_and_scoped(session, two_orgs):
    org_a, org_b = two_orgs.a.organization.id, two_orgs.b.organization.id
    store = SqlScheduledSyncRunStore(session)
    for hours in range(3):
        await store.add(_run(org_a, T0 + timedelta(hours=hours)))
    await store.add(_run(org_b, T0))
    await session.flush()
    rows, total = await store.list_runs(org_a, page=1, size=2)
    assert total == 3 and [r.started_at for r in rows] == [
        T0 + timedelta(hours=2),
        T0 + timedelta(hours=1),
    ]
    rows, total = await store.list_runs(org_a, page=2, size=2)
    assert total == 3 and len(rows) == 1
    assert all(r.organization_id == org_a for r in rows)
    assert rows[0].steps[1]["name"] == "intake"


async def test_organizations_to_sync_has_active_connectors_and_checklist_org(session, two_orgs):
    org_a, org_b = two_orgs.a.organization, two_orgs.b.organization
    session.add(Connector(organization_id=org_a.id, provider="fake"))
    session.add(Connector(organization_id=org_b.id, provider="fake", is_active=False))
    await session.flush()
    store = SqlScheduledSyncRunStore(session)
    found = await store.organizations_to_sync(checklist_slug=None)
    assert org_a.id in found and org_b.id not in found
    with_checklist = await store.organizations_to_sync(checklist_slug=org_b.slug)
    assert org_b.id in with_checklist and with_checklist.count(org_a.id) == 1
