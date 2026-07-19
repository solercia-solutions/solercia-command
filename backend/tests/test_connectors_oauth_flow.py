"""Tests for the connectors OAuth flow — authorize/callback against the
`fake` adapter (change 14-integration-ports). C-R3 Varias cuentas del mismo
proveedor · C-R4 Inicio del flujo (authorize) · C-R5 Callback exitoso ·
C-R6 Error y expiración del state en el callback. Every test uses
`patched_redis` (fakeredis) so the OAuth `state` never touches real Redis.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _authorize(client: AsyncClient, token: str, connector_id: str):
    response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(token)
    )
    assert response.status_code == 302, response.text
    return response


# ---------------------------------------------------------------------------
# C-R4 — Inicio del flujo OAuth (authorize)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_persists_state_and_returns_provider_url(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """authorize persists a state in Redis (fakeredis) and 302s to the
    provider's authorize URL."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await _authorize(client, two_orgs.a.token, connector_id)

    location = response.headers["location"]
    assert location.startswith("https://fake.test/oauth/authorize")
    after = await patched_redis.dbsize()
    assert after == before + 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_on_foreign_or_nonexistent_connector_returns_404_without_state(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """authorize on a connector of ANOTHER org (or a nonexistent one) 404s
    WITHOUT generating any state."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.b.token)
    )

    assert response.status_code == 404
    after = await patched_redis.dbsize()
    assert after == before


# ---------------------------------------------------------------------------
# C-R5 — Callback exitoso del flujo OAuth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_successful_callback_creates_account_and_encrypted_credentials(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A valid callback creates the ConnectedAccount + encrypted
    ConnectionCredentials, and invalidates the state (single-use)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await _authorize(client, two_orgs.a.token, connector_id)
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback", params={"code": "abc123", "state": state}
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["external_account_id"] == "fake-account-abc123"
    assert body["status"] == "active"

    account_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-abc123"
        )
    )
    account = account_result.scalar_one()
    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = creds_result.scalar_one()
    assert credentials.access_token_enc != "fake-access-abc123"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reused_state_is_rejected_and_creates_nothing_twice(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Replaying the SAME state on a second callback is rejected; the
    account created by the first callback is not duplicated or altered."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await _authorize(client, two_orgs.a.token, connector_id)
    state = _state_from_location(authorize_response.headers["location"])

    first = await client.get(
        "/connectors/oauth/callback", params={"code": "replay-1", "state": state}
    )
    assert first.status_code == 200, first.text

    second = await client.get(
        "/connectors/oauth/callback", params={"code": "replay-1", "state": state}
    )
    assert second.status_code == 400
    assert second.json()["code"] == "oauth_state_invalid"

    count_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-replay-1"
        )
    )
    assert len(count_result.scalars().all()) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_second_distinct_external_account_creates_a_second_row(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Connecting a SECOND, distinct external account under the SAME
    connector creates a SECOND ConnectedAccount row, no collision with the
    first (decisión ratificada #1)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    first_auth = await _authorize(client, two_orgs.a.token, connector_id)
    first_state = _state_from_location(first_auth.headers["location"])
    first_cb = await client.get(
        "/connectors/oauth/callback", params={"code": "multi-1", "state": first_state}
    )
    assert first_cb.status_code == 200

    second_auth = await _authorize(client, two_orgs.a.token, connector_id)
    second_state = _state_from_location(second_auth.headers["location"])
    second_cb = await client.get(
        "/connectors/oauth/callback", params={"code": "multi-2", "state": second_state}
    )
    assert second_cb.status_code == 200

    assert first_cb.json()["data"]["id"] != second_cb.json()["data"]["id"]
    assert first_cb.json()["data"]["external_account_id"] == "fake-account-multi-1"
    assert second_cb.json()["data"]["external_account_id"] == "fake-account-multi-2"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reconnecting_the_same_external_account_updates_without_duplicating(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Repeating the OAuth flow for the SAME external account (same `code`,
    fresh state each time) updates credentials in place — no duplicate row."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    first_auth = await _authorize(client, two_orgs.a.token, connector_id)
    first_state = _state_from_location(first_auth.headers["location"])
    first_cb = await client.get(
        "/connectors/oauth/callback",
        params={"code": "reconnect", "state": first_state},
    )
    assert first_cb.status_code == 200
    first_account_id = first_cb.json()["data"]["id"]

    second_auth = await _authorize(client, two_orgs.a.token, connector_id)
    second_state = _state_from_location(second_auth.headers["location"])
    second_cb = await client.get(
        "/connectors/oauth/callback",
        params={"code": "reconnect", "state": second_state},
    )
    assert second_cb.status_code == 200
    assert second_cb.json()["data"]["id"] == first_account_id

    count_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-reconnect"
        )
    )
    assert len(count_result.scalars().all()) == 1


# ---------------------------------------------------------------------------
# C-R6 — Error y expiración del state en el callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_expired_state_is_rejected_without_creating_an_account(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    patched_redis,
    monkeypatch,
) -> None:
    """A state whose TTL already elapsed is rejected; no account is created."""

    import asyncio

    from app.config import settings

    monkeypatch.setattr(settings, "OAUTH_STATE_TTL_SECONDS", 1)
    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await _authorize(client, two_orgs.a.token, connector_id)
    state = _state_from_location(authorize_response.headers["location"])

    await asyncio.sleep(1.2)

    response = await client.get(
        "/connectors/oauth/callback", params={"code": "expired-code", "state": state}
    )

    assert response.status_code == 400
    assert response.json()["code"] == "oauth_state_invalid"

    count_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-expired-code"
        )
    )
    assert count_result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unknown_state_is_rejected_without_registering_anything(
    client: AsyncClient, session: AsyncSession, patched_redis
) -> None:
    """A state that was never generated (possible manipulation) is rejected."""

    response = await client.get(
        "/connectors/oauth/callback",
        params={"code": "forged-code", "state": "never-issued-state"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "oauth_state_invalid"

    count_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-forged-code"
        )
    )
    assert count_result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Atomicidad del callback — falla al guardar credenciales no deja la cuenta
# a medias (Fix CRITICAL 14-integration-ports, revisión 4R)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_callback_failure_saving_credentials_rolls_back_the_account_too(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    patched_redis,
    monkeypatch,
) -> None:
    """If persisting ``ConnectionCredentials`` fails AFTER the account was
    upserted, the WHOLE callback rolls back — no half-created account
    survives the failure (single transaction, not two independent commits).

    The client's ``ASGITransport`` re-raises unhandled exceptions instead of
    surfacing the 500 response (httpx's ``raise_app_exceptions`` default —
    see the generic ``Exception`` handler in ``app/shared/exceptions.py``,
    which DOES produce the 500 for a real server), so this asserts on the
    propagated exception directly.
    """

    from app.modules.connectors.repository import ConnectedAccountRepository

    async def _boom(self, **kwargs):
        raise RuntimeError("boom-save-credentials")

    monkeypatch.setattr(ConnectedAccountRepository, "save_credentials", _boom)

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await _authorize(client, two_orgs.a.token, connector_id)
    state = _state_from_location(authorize_response.headers["location"])

    with pytest.raises(RuntimeError, match="boom-save-credentials"):
        await client.get(
            "/connectors/oauth/callback",
            params={"code": "atomic-fail", "state": state},
        )

    result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-atomic-fail"
        )
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Reconexión tras desconectar — no debe colisionar con el UNIQUE de la fila
# soft-deleted (Fix CRITICAL 14-integration-ports, revisión 4R)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reconnecting_after_disconnect_reactivates_without_500_or_duplicates(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Disconnecting a connected account and then repeating the OAuth flow
    for the SAME external account REACTIVATES the existing (soft-deleted)
    row — 200, no duplicate, no collision against
    ``uq_connected_accounts_connector_external`` (that UNIQUE constraint does
    NOT exclude soft-deleted rows)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    first_auth = await _authorize(client, two_orgs.a.token, connector_id)
    first_state = _state_from_location(first_auth.headers["location"])
    first_cb = await client.get(
        "/connectors/oauth/callback",
        params={"code": "reconnect-after-disconnect", "state": first_state},
    )
    assert first_cb.status_code == 200, first_cb.text
    account_id = first_cb.json()["data"]["id"]

    disconnect_response = await client.delete(
        f"/connected-accounts/{account_id}", headers=_auth(two_orgs.a.token)
    )
    assert disconnect_response.status_code == 204

    second_auth = await _authorize(client, two_orgs.a.token, connector_id)
    second_state = _state_from_location(second_auth.headers["location"])
    second_cb = await client.get(
        "/connectors/oauth/callback",
        params={"code": "reconnect-after-disconnect", "state": second_state},
    )

    assert second_cb.status_code == 200, second_cb.text
    assert second_cb.json()["data"]["id"] == account_id
    assert second_cb.json()["data"]["status"] == "active"

    count_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id
            == "fake-account-reconnect-after-disconnect"
        )
    )
    rows = count_result.scalars().all()
    assert len(rows) == 1
    assert rows[0].is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_provider_error_is_rejected_without_partial_records(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """`?error=` from the provider (e.g. user cancelled) is a controlled
    error, no account/credentials are created."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await _authorize(client, two_orgs.a.token, connector_id)
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback",
        params={"error": "access_denied", "state": state},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "oauth_provider_error"

    count_result = await session.execute(select(ConnectedAccount))
    assert count_result.scalars().all() == []
