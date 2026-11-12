"""C02: real step adapters against disposable PostgreSQL (no provider calls)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.connectors.models import Connector
from app.modules.scheduled_sync.service import StepFailed, StepSkipped
from app.modules.scheduled_sync.unit import SessionSyncSteps
from app.modules.task_import.checklist_sync_service import ChecklistSyncConfig
from tests.conftest import skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]


async def test_checklist_is_skipped_unless_configured_for_this_organization(session, two_orgs):
    org_a, org_b = two_orgs.a.organization, two_orgs.b.organization
    with pytest.raises(StepSkipped):
        await SessionSyncSteps(session, None).checklist(org_a.id)
    config = ChecklistSyncConfig(path=Path("/no/existe.csv"), organization_slug=org_b.slug)
    with pytest.raises(StepSkipped):
        await SessionSyncSteps(session, config).checklist(org_a.id)


async def test_checklist_domain_errors_become_a_recorded_step_failure(session, two_orgs):
    org_a = two_orgs.a.organization
    config = ChecklistSyncConfig(path=Path("/no/existe.csv"), organization_slug=org_a.slug)
    with pytest.raises(StepFailed, match="ChecklistSourceError"):
        await SessionSyncSteps(session, config).checklist(org_a.id)


async def test_intake_is_skipped_without_active_connectors(session, two_orgs):
    with pytest.raises(StepSkipped):
        await SessionSyncSteps(session, None).intake(
            two_orgs.a.organization.id, since=None, actor_id=None
        )


async def test_intake_with_a_connector_and_no_accounts_reports_zero(session, two_orgs):
    org_a = two_orgs.a.organization
    session.add(Connector(organization_id=org_a.id, provider="fake"))
    await session.flush()
    since = datetime(2026, 10, 6, tzinfo=UTC)
    counts = await SessionSyncSteps(session, None).intake(org_a.id, since=since, actor_id=None)
    assert counts["accounts"] == 0 and counts["errored"] == 0
    assert counts["since"] == since.isoformat()


async def test_classification_defaults_to_the_noop_extension_point(session, two_orgs):
    with pytest.raises(StepSkipped):
        await SessionSyncSteps(session, None).classify(two_orgs.a.organization.id)
