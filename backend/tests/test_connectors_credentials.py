"""Tests for the connectors `api_token` direct-registration flow — scoped
ONLY to the Jira-specific gap NOT already covered by change 17-adapter-glpi's
generic suite (`tests/test_connectors_api_token.py`): the REAL
`_JiraApiTokenHandshake.connect()` validating against Jira's own `GET
/rest/api/3/myself`, and the "reenvío del mismo token no duplica la cuenta"
scenario (change 18-adapter-jira, delta specs/connectors/spec.md CR1) —
nowhere else exercises `register_api_token_credentials` TWICE for the SAME
`api_token` connector. The generic admin/member/foreign-org/oauth-connector
scenarios (already exercised end-to-end against a local fake adapter in
`test_connectors_api_token.py`) are DELIBERATELY NOT duplicated here — the
route `POST /connectors/{id}/credentials` itself is change 17's, this
change only consumes it (design.md Architecture Decisions, "Regla cerrada
(ratificada)").
"""

import json

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.registry import register_adapter
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from tests.conftest import TwoOrgs, skip_no_db

_MYSELF_PAYLOAD = {
    "accountId": "5b10a2844c20165700ede21g",
    "displayName": "Mia Krystof",
    "emailAddress": "mia@acme.com",
    "active": True,
}


def _register_mock_jira_adapter(handler) -> None:
    """Override the registry's `jira` entry with an instance bound to an
    `httpx.MockTransport` for THIS test — the package-level
    `register_adapter(JiraAdapter())` (real network, no transport) stays
    the default otherwise. Same override pattern
    `test_connectors_api_token.py`'s local `fake-api-token` adapter uses,
    applied here to the REAL Jira adapter instead of a stand-in."""

    register_adapter(JiraAdapter(transport=httpx.MockTransport(handler)))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_jira_connector(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/connectors",
        json={"provider": "jira", "credential_kind": "api_token"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_registers_jira_api_token_credentials_validated_via_myself(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Admin provee un API token (delta specs/connectors/spec.md
    CR1) — the REAL `_JiraApiTokenHandshake.connect()` validates the
    email/api_token pair against `GET /rest/api/3/myself` BEFORE anything
    is persisted, and the response never echoes the token."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/api/3/myself"
        return httpx.Response(200, json=_MYSELF_PAYLOAD)

    _register_mock_jira_adapter(handler)
    connector_id = await _create_jira_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={
            "base_url": "https://acme.atlassian.net",
            "email": "mia@acme.com",
            "api_token": "JIRA-TOKEN-1",
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["external_account_id"] == "jira-5b10a2844c20165700ede21g"
    assert "JIRA-TOKEN-1" not in response.text

    result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.connector_id == connector_id)
    )
    account = result.scalar_one()
    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = creds_result.scalar_one()
    assert "JIRA-TOKEN-1" not in credentials.access_token_enc


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resending_the_same_jira_account_updates_credentials_without_duplicating(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Reenvío del mismo token no duplica la cuenta (delta
    specs/connectors/spec.md CR1) — repeating the registration for the SAME
    external account (Jira's `accountId`, stable across calls) updates the
    existing `ConnectedAccount`/`ConnectionCredentials` row in place
    instead of creating a duplicate."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_MYSELF_PAYLOAD)

    _register_mock_jira_adapter(handler)
    connector_id = await _create_jira_connector(client, two_orgs.a.token)

    first = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={
            "base_url": "https://acme.atlassian.net",
            "email": "mia@acme.com",
            "api_token": "JIRA-TOKEN-OLD",
        },
        headers=_auth(two_orgs.a.token),
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={
            "base_url": "https://acme.atlassian.net",
            "email": "mia@acme.com",
            "api_token": "JIRA-TOKEN-NEW",
        },
        headers=_auth(two_orgs.a.token),
    )
    assert second.status_code == 201, second.text
    assert first.json()["data"]["id"] == second.json()["data"]["id"]

    accounts_result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.connector_id == connector_id)
    )
    accounts = accounts_result.scalars().all()
    assert len(accounts) == 1

    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == accounts[0].id
        )
    )
    credentials = creds_result.scalar_one()
    stored_raw = json.loads(crypto.decrypt(credentials.access_token_enc))
    assert stored_raw["api_token"] == "JIRA-TOKEN-NEW"
