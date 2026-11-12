"""Tests for the intake pull's connector filter and for the external
provenance a converted insumo hands to its task (``Task.source`` /
``Task.external_key``): a second conversion of the same message is a
detectable conflict, never a duplicate task, and never aborts the run.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.dtos import MailMessage
from app.integrations.ports import Capability, CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.intake.models import IntakeItem, IntakeRule
from app.modules.intake.service import IntakeService
from app.modules.tasks.models import Task
from app.shared.enums import AccountStatus, ConnectorStatus, IntakeItemStatus, IntakeRunStatus
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_connector(
    session: AsyncSession,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    provider: str,
    credential_kind: CredentialKind = CredentialKind.oauth,
) -> Connector:
    connector = Connector(
        organization_id=organization_id,
        provider=provider,
        credential_kind=credential_kind,
        status=ConnectorStatus.active,
    )
    session.add(connector)
    await session.flush()

    account = ConnectedAccount(
        organization_id=organization_id,
        connector_id=connector.id,
        user_id=owner_id,
        external_account_id=f"{provider}-account",
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    session.add(
        ConnectionCredentials(
            organization_id=organization_id,
            connected_account_id=account.id,
            access_token_enc=crypto.encrypt(
                "fake-access-token"
                if credential_kind == CredentialKind.oauth
                else json.dumps({"api_token": "x"})
            ),
            refresh_token_enc=(
                crypto.encrypt("fake-refresh-token")
                if credential_kind == CredentialKind.oauth
                else None
            ),
            token_type="Bearer",
        )
    )
    await session.flush()
    return connector


async def _seed_rule(session: AsyncSession, organization_id: uuid.UUID, provider: str) -> None:
    session.add(
        IntakeRule(
            organization_id=organization_id,
            name=f"Convertir todo de {provider}",
            criteria=[{"field": "source_provider", "operator": "equals", "value": provider}],
            convert_to_task=True,
            rule_order=1,
        )
    )
    await session.flush()


class _StubMailPort:
    async def list_messages(self, ctx, *, since=None, limit: int = 50):
        return [
            MailMessage(
                external_id="stub-mail-1",
                subject="Mensaje del stub",
                sender="alguien@stub.test",
                recipients=("yo@stub.test",),
                received_at=datetime.now(UTC),
                snippet="Hola",
                body_text="Hola",
            )
        ][:limit]


class _StubMailAdapter:
    """A provider the task vocabulary does NOT know (`KNOWN_TASK_SOURCES`)."""

    provider = "stub-origin"
    capabilities = frozenset({Capability.mail})
    credential_kind = CredentialKind.api_token
    credential_kinds = frozenset({CredentialKind.api_token})
    oauth = None
    api_token = None

    def __init__(self) -> None:
        self._port = _StubMailPort()

    def port_for(self, capability: Capability) -> object | None:
        return self._port if capability == Capability.mail else None


@pytest.fixture
def stub_adapter(monkeypatch: pytest.MonkeyPatch) -> _StubMailAdapter:
    from app.integrations import registry as integrations_registry

    adapter = _StubMailAdapter()
    monkeypatch.setitem(integrations_registry._ADAPTERS, adapter.provider, adapter)
    return adapter


# ---------------------------------------------------------------------------
# pull(connector_id=...)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_pull_filtered_by_connector_reads_only_that_connector(
    session: AsyncSession, two_orgs: TwoOrgs, stub_adapter: _StubMailAdapter
) -> None:
    organization_id = two_orgs.a.organization.id
    fake = await _seed_connector(session, organization_id, two_orgs.a.user.id, provider="fake")
    await _seed_connector(
        session,
        organization_id,
        two_orgs.a.user.id,
        provider=stub_adapter.provider,
        credential_kind=CredentialKind.api_token,
    )
    service = IntakeService(session)

    filtered = await service.pull(organization_id, connector_id=fake.id)
    everything = await service.pull(organization_id)

    assert [run.connector_id for run in filtered] == [fake.id]
    assert filtered[0].status == IntakeRunStatus.completed
    assert filtered[0].items_fetched == 5  # fake adapter: five capabilities
    assert len(everything) == 2


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_pull_filtered_by_a_foreign_connector_reads_nothing(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    await _seed_connector(session, two_orgs.a.organization.id, two_orgs.a.user.id, provider="fake")
    foreign = await _seed_connector(
        session, two_orgs.b.organization.id, two_orgs.b.user.id, provider="fake"
    )

    runs = await IntakeService(session).pull(two_orgs.a.organization.id, connector_id=foreign.id)

    assert runs == []


# ---------------------------------------------------------------------------
# external_origin on conversion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_automatic_conversion_anchors_the_task_to_its_origin(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    organization_id = two_orgs.a.organization.id
    await _seed_connector(session, organization_id, two_orgs.a.user.id, provider="fake")
    await _seed_rule(session, organization_id, "fake")

    outcomes = await IntakeService(session).pull_outcomes(organization_id)

    assert outcomes[0].run.items_converted == 5
    assert outcomes[0].anchor_conflicts == 0
    result = await session.execute(select(Task).where(Task.source == "fake"))
    anchored = {task.external_key for task in result.scalars().all()}
    assert anchored == {
        "fake-mail-1",
        "fake-event-1",
        "fake-task-1",
        "fake-note-1",
        "fake-ticket-1",
    }


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_existing_anchor_skips_that_item_without_aborting_the_run(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    organization_id = two_orgs.a.organization.id
    await _seed_connector(session, organization_id, two_orgs.a.user.id, provider="fake")
    await _seed_rule(session, organization_id, "fake")
    session.add(
        Task(
            project_id=two_orgs.a.project.id,
            title="Ya existía",
            status="Backlog",
            source="fake",
            external_key="fake-mail-1",
        )
    )
    await session.flush()

    outcomes = await IntakeService(session).pull_outcomes(organization_id)

    outcome = outcomes[0]
    assert outcome.run.status == IntakeRunStatus.completed
    assert outcome.run.items_new == 5
    assert outcome.run.items_converted == 4
    assert outcome.anchor_conflicts == 1
    assert outcome.error_code is None

    result = await session.execute(
        select(IntakeItem).where(
            IntakeItem.organization_id == organization_id,
            IntakeItem.external_id == "fake-mail-1",
        )
    )
    skipped = result.scalar_one()
    assert skipped.status == IntakeItemStatus.pending
    assert skipped.created_task_id is None

    tasks = await session.execute(
        select(Task).where(Task.source == "fake", Task.external_key == "fake-mail-1")
    )
    assert len(tasks.scalars().all()) == 1  # still only the pre-existing one


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unknown_source_converts_without_an_anchor(
    session: AsyncSession, two_orgs: TwoOrgs, stub_adapter: _StubMailAdapter
) -> None:
    organization_id = two_orgs.a.organization.id
    await _seed_connector(
        session,
        organization_id,
        two_orgs.a.user.id,
        provider=stub_adapter.provider,
        credential_kind=CredentialKind.api_token,
    )
    await _seed_rule(session, organization_id, stub_adapter.provider)

    outcomes = await IntakeService(session).pull_outcomes(organization_id)

    assert outcomes[0].run.items_converted == 1
    result = await session.execute(
        select(IntakeItem).where(
            IntakeItem.organization_id == organization_id,
            IntakeItem.external_id == "stub-mail-1",
        )
    )
    item = result.scalar_one()
    task = await session.get(Task, item.created_task_id)
    assert task is not None
    assert task.source is None
    assert task.external_key is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manual_conversion_anchors_and_reports_a_conflict(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    organization_id = two_orgs.a.organization.id
    connector = await _seed_connector(session, organization_id, two_orgs.a.user.id, provider="fake")
    # No rule: every item lands in triage as `pending`.
    await IntakeService(session).pull(organization_id)
    result = await session.execute(
        select(IntakeItem).where(
            IntakeItem.organization_id == organization_id,
            IntakeItem.connector_id == connector.id,
            IntakeItem.item_type == "email",
        )
    )
    item = result.scalar_one()

    converted = await client.post(
        f"/intake/items/{item.id}/convert", json={}, headers=_auth(two_orgs.a.token)
    )
    assert converted.status_code == 200, converted.text
    task = await session.get(Task, uuid.UUID(converted.json()["data"]["created_task_id"]))
    assert task is not None
    assert (task.source, task.external_key) == ("fake", "fake-mail-1")

    # A second item carrying the SAME provenance (another connector row, so the
    # intake idempotency key does not collide) cannot become a second task.
    other_connector = Connector(
        organization_id=organization_id,
        provider="fake-second",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )
    session.add(other_connector)
    await session.flush()
    twin = IntakeItem(
        organization_id=organization_id,
        source_provider="fake",
        connector_id=other_connector.id,
        connected_account_id=None,
        item_type="email",
        external_id="fake-mail-1",
        title="Gemelo",
        snippet=None,
        origin_actor="alguien@fake.test",
        occurred_at=datetime.now(UTC),
        raw_payload={},
        status=IntakeItemStatus.pending,
    )
    session.add(twin)
    await session.flush()

    conflict = await client.post(
        f"/intake/items/{twin.id}/convert", json={}, headers=_auth(two_orgs.a.token)
    )

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "task_external_anchor_conflict"
    await session.refresh(twin)
    assert twin.status == IntakeItemStatus.pending
