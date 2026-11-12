"""RED tests for the intake REST surface — storage + pull ingestion (change
22-intake-classifier, tasks.md T2.7): admin pull exitoso, RBAC de member,
aislamiento de cuenta con token irrecuperable, filtros y aislamiento
multi-tenant.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.ports import CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.shared.enums import AccountStatus, ConnectorStatus, MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_fake_connector(
    session: AsyncSession, organization_id: uuid.UUID
) -> Connector:
    connector = Connector(
        organization_id=organization_id,
        provider="fake",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )
    session.add(connector)
    await session.flush()
    return connector


async def _add_fake_account(
    session: AsyncSession,
    connector: Connector,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    external_account_id: str = "fake-account-endpoints",
    access_token_enc: str | None = None,
) -> ConnectedAccount:
    account = ConnectedAccount(
        organization_id=organization_id,
        connector_id=connector.id,
        user_id=owner_id,
        external_account_id=external_account_id,
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    credentials = ConnectionCredentials(
        organization_id=organization_id,
        connected_account_id=account.id,
        access_token_enc=access_token_enc or crypto.encrypt("fake-access-token"),
        refresh_token_enc=crypto.encrypt("fake-refresh-token"),
        token_type="Bearer",
        scopes=["mail"],
    )
    session.add(credentials)
    await session.flush()
    return account


async def _create_fake_connector_with_account(
    session: AsyncSession,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    external_account_id: str = "fake-account-endpoints",
    access_token_enc: str | None = None,
) -> Connector:
    """Convenience one-connector-one-account seed for the common case."""

    connector = await _create_fake_connector(session, organization_id)
    await _add_fake_account(
        session,
        connector,
        organization_id,
        owner_id,
        external_account_id=external_account_id,
        access_token_enc=access_token_enc,
    )
    return connector


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_pull_succeeds_with_correct_counts(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Admin dispara un pull exitoso — un IntakeRun por cuenta con
    conteos correctos (fake adapter: 5 capacidades -> 5 items nuevos)."""

    await _create_fake_connector_with_account(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert len(body) == 1
    assert body[0]["status"] == "completed"
    assert body[0]["items_fetched"] == 5
    assert body[0]["items_new"] == 5
    assert body[0]["items_duplicated"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_trigger_pull_and_no_run_is_created(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Member no puede disparar el pull — 403, sin IntakeRun."""

    await _create_fake_connector_with_account(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    _member, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post("/intake/pull", headers=_auth(member_token))
    assert response.status_code == 403, response.text

    runs_response = await client.get("/intake/runs", headers=_auth(two_orgs.a.token))
    assert runs_response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_account_with_undecryptable_token_errors_without_blocking_healthy_account(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Error en una cuenta no bloquea las demás — la cuenta con
    token irrecuperable cierra su IntakeRun en `error`, la cuenta sana cierra
    el suyo en `completed` con ítems almacenados."""

    connector = await _create_fake_connector(session, two_orgs.a.organization.id)
    await _add_fake_account(
        session,
        connector,
        two_orgs.a.organization.id,
        two_orgs.a.user.id,
        external_account_id="fake-account-broken",
        access_token_enc="not-a-valid-fernet-token",
    )
    await _add_fake_account(
        session,
        connector,
        two_orgs.a.organization.id,
        two_orgs.a.user.id,
        external_account_id="fake-account-healthy",
    )

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    runs = response.json()["data"]
    assert len(runs) == 2
    statuses = {run["status"] for run in runs}
    assert statuses == {"error", "completed"}

    completed_run = next(run for run in runs if run["status"] == "completed")
    assert completed_run["items_new"] == 5


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_filter_items_by_pending_status(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Filtrar la cola de triage (`?status=pending`)."""

    await _create_fake_connector_with_account(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    pull_response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    assert pull_response.status_code == 200, pull_response.text

    response = await client.get(
        "/intake/items", params={"status": "pending"}, headers=_auth(two_orgs.a.token)
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    assert len(items) == 5
    assert all(item["status"] == "pending" for item in items)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_intake_item_from_other_organization_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Insumo de otra organización no es visible — 404."""

    await _create_fake_connector_with_account(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    pull_response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    assert pull_response.status_code == 200, pull_response.text

    items_response = await client.get("/intake/items", headers=_auth(two_orgs.a.token))
    item_id = items_response.json()["data"][0]["id"]

    response = await client.get(f"/intake/items/{item_id}", headers=_auth(two_orgs.b.token))
    assert response.status_code == 404, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_org_b_never_sees_org_a_items(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Aislamiento multi-tenant sobre el listado — org B no ve ítems de A."""

    await _create_fake_connector_with_account(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    pull_response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))
    assert pull_response.status_code == 200, pull_response.text

    response = await client.get("/intake/items", headers=_auth(two_orgs.b.token))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == []
