"""Tests for the OAuth authorize/callback browser-return flow (Conexiones
page): ``redirect_to`` on ``GET /connectors/{id}/authorize`` (validated
against ``OAUTH_REDIRECT_ALLOWLIST``, 422 otherwise), a friendly ``302``
back to that destination from the GLOBAL callback (``?connected=1`` on
success, ``?error=<code>`` on failure), and the single-use, short-TTL
authorize TICKET (``POST /connectors/{id}/authorize-ticket`` +
``GET .../authorize?ticket=``) that lets a full-page browser navigation
authenticate the authorize step WITHOUT ever placing the JWT in a URL
(CWE-598: query strings land in server logs, proxies and browser history).

Backwards compatibility is asserted explicitly: a callback whose state has
NO stored destination keeps answering the original JSON envelope, and an
invalid/expired state keeps its 400 ``oauth_state_invalid`` JSON error.
An unexpected (non-AppException) failure AFTER the state was consumed also
redirects back (``?error=oauth_unexpected_error``) when a destination is
known, instead of stranding the user on a raw 500.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.connectors.models import ConnectedAccount
from tests.conftest import TwoOrgs, skip_no_db

ALLOWED_RETURN = "http://localhost:4242/connections"


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


def test_default_allowlist_includes_connections_page_urls() -> None:
    """The default allowlist covers the Conexiones page on every local
    frontend port (4200 prod-like, 4242/4243 dev servers)."""

    for url in (
        "http://localhost:4200/connections",
        "http://localhost:4242/connections",
        "http://localhost:4243/connections",
    ):
        assert url in settings.OAUTH_REDIRECT_ALLOWLIST


# ---------------------------------------------------------------------------
# authorize + redirect_to
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_with_allowed_redirect_to_302s_to_provider(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """authorize with an allowlisted ``redirect_to`` still 302s to the IdP
    and persists ONE state."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_to": ALLOWED_RETURN},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"].startswith("https://fake.test/oauth/authorize")
    assert await patched_redis.dbsize() == before + 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_with_disallowed_redirect_to_is_rejected_without_state(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A ``redirect_to`` outside the allowlist is rejected with 422 BEFORE
    any state is generated (anti open-redirect)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_to": "https://evil.example/phish"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "oauth_redirect_to_not_allowed"
    assert await patched_redis.dbsize() == before


# ---------------------------------------------------------------------------
# callback with a stored destination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_callback_with_destination_302s_back_with_connected_flag(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A successful callback whose state stored a destination 302s back to
    it with ``?connected=1`` — and the account IS created."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_to": ALLOWED_RETURN},
        headers=_auth(two_orgs.a.token),
    )
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback",
        params={"code": "redir-ok", "state": state},
    )

    assert response.status_code == 302, response.text
    location = response.headers["location"]
    parsed = urlparse(location)
    assert location.startswith(ALLOWED_RETURN)
    assert parse_qs(parsed.query)["connected"] == ["1"]

    account_result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.external_account_id == "fake-account-redir-ok"
        )
    )
    assert account_result.scalar_one() is not None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_callback_provider_error_with_destination_302s_back_with_error_code(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A provider ``?error=`` on a state that stored a destination 302s back
    with ``?error=oauth_provider_error`` — nothing is persisted."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_to": ALLOWED_RETURN},
        headers=_auth(two_orgs.a.token),
    )
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback",
        params={"error": "access_denied", "state": state},
    )

    assert response.status_code == 302, response.text
    parsed = urlparse(response.headers["location"])
    assert response.headers["location"].startswith(ALLOWED_RETURN)
    assert parse_qs(parsed.query)["error"] == ["oauth_provider_error"]

    count_result = await session.execute(select(ConnectedAccount))
    assert count_result.scalars().all() == []


# ---------------------------------------------------------------------------
# callback WITHOUT destination — original behavior preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_callback_without_destination_keeps_json_envelope(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A callback whose state has NO stored destination keeps answering the
    original JSON envelope (compatibility with pre-existing flows)."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.a.token)
    )
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback",
        params={"code": "json-compat", "state": state},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Cuenta conectada."
    assert body["data"]["external_account_id"] == "fake-account-json-compat"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_callback_with_invalid_state_keeps_current_400_json(
    client: AsyncClient, patched_redis
) -> None:
    """An unknown/expired state keeps the current 400 JSON error — there is
    no destination to redirect to."""

    response = await client.get(
        "/connectors/oauth/callback",
        params={"code": "whatever", "state": "never-issued"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "oauth_state_invalid"


# ---------------------------------------------------------------------------
# authorize ticket (browser navigation cannot attach a Bearer header; the
# JWT must NEVER travel in a URL — CWE-598)
# ---------------------------------------------------------------------------


async def _create_ticket(client: AsyncClient, token: str, connector_id: str) -> str:
    response = await client.post(
        f"/connectors/{connector_id}/authorize-ticket", headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    ticket = response.json()["data"]["ticket"]
    assert isinstance(ticket, str) and len(ticket) >= 32
    return ticket


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_with_ticket_302s_to_provider(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """``GET .../authorize?ticket=`` authenticates the navigation with the
    single-use ticket minted by ``POST .../authorize-ticket`` — no JWT
    ever appears in the URL."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    ticket = await _create_ticket(client, two_orgs.a.token, connector_id)

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"ticket": ticket, "redirect_to": ALLOWED_RETURN},
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"].startswith("https://fake.test/oauth/authorize")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reused_or_unknown_ticket_is_401(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A ticket is single-use: replaying it (or presenting one that was
    never issued) is rejected with 401."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    ticket = await _create_ticket(client, two_orgs.a.token, connector_id)

    first = await client.get(
        f"/connectors/{connector_id}/authorize", params={"ticket": ticket}
    )
    assert first.status_code == 302, first.text

    replay = await client.get(
        f"/connectors/{connector_id}/authorize", params={"ticket": ticket}
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "oauth_ticket_invalid"

    forged = await client.get(
        f"/connectors/{connector_id}/authorize", params={"ticket": "never-issued"}
    )
    assert forged.status_code == 401
    assert forged.json()["code"] == "oauth_ticket_invalid"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_expired_ticket_is_401(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis, monkeypatch
) -> None:
    """A ticket whose short TTL already elapsed is rejected with 401."""

    import asyncio

    monkeypatch.setattr(settings, "OAUTH_AUTHORIZE_TICKET_TTL_SECONDS", 1)
    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    ticket = await _create_ticket(client, two_orgs.a.token, connector_id)

    await asyncio.sleep(1.2)

    response = await client.get(
        f"/connectors/{connector_id}/authorize", params={"ticket": ticket}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "oauth_ticket_invalid"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ticket_bound_to_another_connector_is_401(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A ticket minted for connector A cannot start the flow on connector
    B — and the failed attempt CONSUMES it (single-use). Connector B lives
    in the OTHER org because ``uq_connectors_organization_provider`` allows
    only one ``fake`` connector per organization."""

    connector_a = await _create_fake_connector(client, two_orgs.a.token)
    connector_b = await _create_fake_connector(client, two_orgs.b.token)
    ticket = await _create_ticket(client, two_orgs.a.token, connector_a)

    response = await client.get(
        f"/connectors/{connector_b}/authorize", params={"ticket": ticket}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "oauth_ticket_invalid"

    retry_on_a = await client.get(
        f"/connectors/{connector_a}/authorize", params={"ticket": ticket}
    )
    assert retry_on_a.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_no_longer_accepts_access_token_in_query(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """The old ``?access_token=`` fallback is GONE (CWE-598): a valid JWT
    in the query is ignored and the navigation is rejected with 401."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"access_token": two_orgs.a.token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_ticket_requires_authentication(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Minting a ticket requires the normal Bearer header."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    response = await client.post(f"/connectors/{connector_id}/authorize-ticket")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# unexpected failure AFTER the state was consumed (W2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unexpected_exchange_failure_redirects_with_generic_error_code(
    client: AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    patched_redis,
    monkeypatch,
) -> None:
    """A NON-AppException raised by ``exchange_code`` (e.g. a transport
    error the adapter did not map) with a stored destination 302s back
    with the generic ``?error=oauth_unexpected_error`` instead of leaving
    the user on a raw 500 — nothing is persisted."""

    from app.integrations.adapters.fake import FakeAdapter

    async def _boom(self, code: str, redirect_uri: str):
        raise RuntimeError("boom-exchange")

    monkeypatch.setattr(FakeAdapter, "exchange_code", _boom)

    connector_id = await _create_fake_connector(client, two_orgs.a.token)
    authorize_response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"redirect_to": ALLOWED_RETURN},
        headers=_auth(two_orgs.a.token),
    )
    state = _state_from_location(authorize_response.headers["location"])

    response = await client.get(
        "/connectors/oauth/callback",
        params={"code": "boom-code", "state": state},
    )

    assert response.status_code == 302, response.text
    parsed = urlparse(response.headers["location"])
    assert response.headers["location"].startswith(ALLOWED_RETURN)
    assert parse_qs(parsed.query)["error"] == ["oauth_unexpected_error"]

    count_result = await session.execute(select(ConnectedAccount))
    assert count_result.scalars().all() == []
