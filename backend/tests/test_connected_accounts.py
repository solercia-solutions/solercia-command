"""Tests for connected accounts — list/disconnect (change 14-integration-ports).

C-R7 Cifrado de tokens en reposo y no exposición · C-R8 Listado y
desconexión de cuentas conectadas. Every test uses `patched_redis`
(fakeredis) since it drives accounts through the real authorize/callback
flow against the `fake` adapter.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _state_from_location(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


async def _create_fake_connector(client: AsyncClient, admin_token: str) -> str:
    response = await client.post(
        "/connectors", json={"provider": "fake"}, headers=_auth(admin_token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _connect_account(
    client: AsyncClient, member_token: str, connector_id: str, code: str
) -> dict:
    auth_response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(member_token)
    )
    state = _state_from_location(auth_response.headers["location"])
    callback = await client.get(
        "/connectors/oauth/callback", params={"code": code, "state": state}
    )
    assert callback.status_code == 200, callback.text
    return callback.json()["data"]


# ---------------------------------------------------------------------------
# C-R8 — Listado por rol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_sees_only_own_accounts_admin_sees_all(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, patched_redis
) -> None:
    """A `member` only sees THEIR OWN connected accounts; admin/manager see
    every account of the connector."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    member_a, member_a_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    member_b, member_b_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    await _connect_account(client, member_a_token, connector_id, "member-a-code")
    await _connect_account(client, member_b_token, connector_id, "member-b-code")

    member_a_view = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(member_a_token)
    )
    assert member_a_view.status_code == 200, member_a_view.text
    assert member_a_view.json()["meta"]["total"] == 1
    assert (
        member_a_view.json()["data"][0]["external_account_id"]
        == "fake-account-member-a-code"
    )

    admin_view = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(two_orgs.a.token)
    )
    assert admin_view.status_code == 200, admin_view.text
    assert admin_view.json()["meta"]["total"] == 2


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_also_sees_all_accounts(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, patched_redis
) -> None:
    """A `manager` (not just `admin`) also sees every account of the connector."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    _, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    await _connect_account(client, member_token, connector_id, "manager-view-code")

    manager_view = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(manager_token)
    )
    assert manager_view.status_code == 200, manager_view.text
    assert manager_view.json()["meta"]["total"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_accounts_response_never_includes_token_fields(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """GET /connectors/{id}/accounts never includes access/refresh tokens,
    encrypted or plain (specs/connectors/spec.md)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    await _connect_account(client, two_orgs.a.token, connector_id, "no-leak-code")

    response = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    account = response.json()["data"][0]
    assert "access_token" not in account
    assert "refresh_token" not in account
    assert "access_token_enc" not in account
    assert "fake-access-no-leak-code" not in response.text


# ---------------------------------------------------------------------------
# C-R8 — Desconexión
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_owner_disconnects_own_account_soft_deletes_account_and_credentials(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """The account owner disconnects (DELETE /connected-accounts/{id}); both
    the account AND its credentials are removed (soft-delete account,
    purge credentials)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    account = await _connect_account(client, two_orgs.a.token, connector_id, "disconnect-me")
    account_id = account["id"]

    response = await client.delete(
        f"/connected-accounts/{account_id}", headers=_auth(two_orgs.a.token)
    )
    assert response.status_code == 204, response.text

    account_result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.id == account_id)
    )
    persisted_account = account_result.scalar_one()
    assert persisted_account.is_active is False
    assert persisted_account.deleted_at is not None

    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account_id
        )
    )
    assert creds_result.scalar_one_or_none() is None

    listing = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(two_orgs.a.token)
    )
    assert listing.json()["meta"]["total"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_disconnects_another_members_account(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, patched_redis
) -> None:
    """An admin can disconnect a connected account owned by another member
    of the SAME organization."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    account = await _connect_account(client, member_token, connector_id, "admin-disconnects")

    response = await client.delete(
        f"/connected-accounts/{account['id']}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 204, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_different_member_cannot_disconnect_someone_elses_account(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, patched_redis
) -> None:
    """A `member` who does NOT own the account, and is not admin/manager,
    gets 403 trying to disconnect it."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    _, owner_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    _, other_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    account = await _connect_account(client, owner_token, connector_id, "not-yours")

    response = await client.delete(
        f"/connected-accounts/{account['id']}", headers=_auth(other_token)
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# C-R1 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connected_account_of_another_org_returns_404_on_get_and_delete(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A connected account under org A is invisible (404) to org B on the
    accounts listing route and on DELETE /connected-accounts/{id}."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    account = await _connect_account(client, two_orgs.a.token, connector_id, "cross-org")

    accounts_view = await client.get(
        f"/connectors/{connector_id}/accounts", headers=_auth(two_orgs.b.token)
    )
    assert accounts_view.status_code == 404

    delete_response = await client.delete(
        f"/connected-accounts/{account['id']}", headers=_auth(two_orgs.b.token)
    )
    assert delete_response.status_code == 404
