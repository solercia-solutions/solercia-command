"""Tests for the OAuth authorize/callback browser-return flow (Conexiones
page): ``redirect_to`` on ``GET /connectors/{id}/authorize`` (validated
against ``OAUTH_REDIRECT_ALLOWLIST``, 422 otherwise), a friendly ``302``
back to that destination from the GLOBAL callback (``?connected=1`` on
success, ``?error=<code>`` on failure), and the ``?access_token=`` query
fallback that lets a full-page browser navigation authenticate the
authorize step (no ``Authorization`` header travels on a navigation).

Backwards compatibility is asserted explicitly: a callback whose state has
NO stored destination keeps answering the original JSON envelope, and an
invalid/expired state keeps its 400 ``oauth_state_invalid`` JSON error.
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
# access_token via query (browser navigation cannot attach a Bearer header)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_accepts_access_token_via_query_param(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """``GET .../authorize?access_token=`` authenticates the navigation —
    ONLY this endpoint accepts the query fallback."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"access_token": two_orgs.a.token, "redirect_to": ALLOWED_RETURN},
    )

    assert response.status_code == 302, response.text
    assert response.headers["location"].startswith("https://fake.test/oauth/authorize")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_with_invalid_query_token_is_401(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """A malformed ``access_token`` query value is rejected with 401."""

    connector_id = await _create_fake_connector(client, two_orgs.a.token)

    response = await client.get(
        f"/connectors/{connector_id}/authorize",
        params={"access_token": "not-a-jwt"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_other_endpoints_do_not_accept_query_token(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """The query-token fallback is scoped to authorize: a regular endpoint
    (list connectors) still requires the Authorization header."""

    response = await client.get(
        "/connectors", params={"access_token": two_orgs.a.token}
    )

    assert response.status_code == 401
