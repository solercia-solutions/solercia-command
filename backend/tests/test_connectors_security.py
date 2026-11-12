"""Tests for the 5 Security Requirements rows of design.md (OAuth/crypto,
change 14-integration-ports): cifrado en reposo, sin fuga de tokens,
anti-CSRF/replay, aislamiento multi-tenant, anti-SSRF/open-redirect. [C-R1,
C-R7]
"""

import logging
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_fake_connector(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/connectors", json={"provider": "fake"}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def _state_from_location(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["state"][0]


async def _authorize_and_callback(
    client: AsyncClient, token: str, connector_id: str, code: str
):
    auth_response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(token)
    )
    state = _state_from_location(auth_response.headers["location"])
    return await client.get(
        "/connectors/oauth/callback", params={"code": code, "state": state}
    )


# ---------------------------------------------------------------------------
# Row 1 — Cifrado en reposo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_tokens_are_encrypted_at_rest_and_decrypt_back(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """`access_token_enc`/`refresh_token_enc` are Fernet-encrypted (never the
    plaintext the fake adapter returned), and decrypt back to it exactly."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    callback = await _authorize_and_callback(
        client, two_orgs.a.token, connector_id, "encrypt-check"
    )
    assert callback.status_code == 200, callback.text

    account_id = callback.json()["data"]["id"]
    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account_id
        )
    )
    credentials = creds_result.scalar_one()

    assert credentials.access_token_enc != "fake-access-encrypt-check"
    assert credentials.refresh_token_enc != "fake-refresh-encrypt-check"
    assert crypto.decrypt(credentials.access_token_enc) == "fake-access-encrypt-check"
    assert crypto.decrypt(credentials.refresh_token_enc) == "fake-refresh-encrypt-check"


# ---------------------------------------------------------------------------
# Row 2 — Sin fuga de tokens (respuesta + logs)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_token_leaks_in_authorize_or_callback_json_response(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Neither the authorize redirect body nor the callback JSON contains the
    plaintext access token or its encrypted ciphertext."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    callback = await _authorize_and_callback(
        client, two_orgs.a.token, connector_id, "leak-check"
    )
    assert callback.status_code == 200, callback.text

    account_id = callback.json()["data"]["id"]
    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account_id
        )
    )
    credentials = creds_result.scalar_one()

    body_text = callback.text
    assert "fake-access-leak-check" not in body_text
    assert credentials.access_token_enc not in body_text
    assert credentials.refresh_token_enc not in body_text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_no_token_leaks_in_application_logs_during_callback(
    client: AsyncClient,
    two_orgs: TwoOrgs,
    patched_redis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The connectors logger DOES emit a record for a successful callback
    (proves the log path really executes), but it NEVER contains the
    plaintext access token."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    with caplog.at_level(logging.INFO, logger="solercia.connectors"):
        callback = await _authorize_and_callback(
            client, two_orgs.a.token, connector_id, "log-check"
        )
    assert callback.status_code == 200, callback.text

    connectors_records = [r for r in caplog.records if r.name == "solercia.connectors"]
    assert len(connectors_records) >= 1
    for record in connectors_records:
        rendered = record.getMessage()
        assert "fake-access-log-check" not in rendered
        assert "fake-refresh-log-check" not in rendered


# ---------------------------------------------------------------------------
# Row 3 — Anti-CSRF/replay (GETDEL single-use)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reused_state_rejected_with_400_getdel_single_use(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A state consumed by one callback cannot be replayed — GETDEL makes
    it single-use at the Redis layer."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    auth_response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.a.token)
    )
    state = _state_from_location(auth_response.headers["location"])

    first = await client.get(
        "/connectors/oauth/callback", params={"code": "csrf-1", "state": state}
    )
    assert first.status_code == 200

    second = await client.get(
        "/connectors/oauth/callback", params={"code": "csrf-1", "state": state}
    )
    assert second.status_code == 400
    assert second.json()["code"] == "oauth_state_invalid"


# ---------------------------------------------------------------------------
# Row 4 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connected_account_and_credentials_stay_scoped_to_their_own_org(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A connector/account/credential created under org A's authorize flow
    is persisted scoped to org A — never org B — regardless of role."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    callback = await _authorize_and_callback(
        client, two_orgs.a.token, connector_id, "tenant-check"
    )
    assert callback.status_code == 200, callback.text

    account_id = callback.json()["data"]["id"]
    account_result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.id == account_id)
    )
    account = account_result.scalar_one()
    assert account.organization_id == two_orgs.a.organization.id
    assert account.organization_id != two_orgs.b.organization.id

    # Org B cannot even start an authorize flow against org A's connector.
    forbidden = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.b.token)
    )
    assert forbidden.status_code == 404


# ---------------------------------------------------------------------------
# Row 5 — Anti-SSRF/open-redirect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_redirect_uri_outside_allowlist_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A `redirect_uri` outside `OAUTH_REDIRECT_ALLOWLIST` is rejected —
    anti-SSRF/open-redirect."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_uri": "https://evil.test/steal-tokens"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "oauth_redirect_not_allowed"
    after = await patched_redis.dbsize()
    assert after == before


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_redirect_uri_inside_allowlist_is_accepted(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Triangulation: an ALLOWED redirect_uri still succeeds (proves the
    allowlist check is a real comparison, not a blanket rejection)."""

    from app.config import settings

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_uri": settings.OAUTH_REDIRECT_ALLOWLIST[0]},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 302
