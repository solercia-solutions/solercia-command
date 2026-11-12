"""Tests for the connectors `api_token` direct-registration flow (change
17-adapter-glpi, delta specs/connectors/spec.md, C17-R1/C17-R2/C17-R3).

Registers a tiny in-memory `fake-api-token` adapter at import time (same
precedent as `app/integrations/adapters/fake.py`, but LOCAL to this test
module — GLPI's real adapter does not exist until Lote 6) so the
`credential_kind=api_token` path is exercised end-to-end through
`POST /connectors/{id}/credentials` without any real HTTP/GLPI dependency.
"""

import hashlib
from collections.abc import Mapping

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.dtos import AccountRef
from app.integrations.ports import ApiTokenHandshake, CredentialKind
from app.integrations.registry import register_adapter
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from tests.conftest import TwoOrgs, skip_no_db


class _FakeApiTokenHandshake:
    """Validates without any real HTTP call — mirrors GLPI's
    `initSession`+`killSession` validation shape (change 17, Lote 6)."""

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        # `external_account_id` is a PUBLIC identifier (the API returns it,
        # tests assert on it) — derived via a one-way hash, never the raw
        # secret itself, mirroring how a real adapter (GLPI) would never
        # expose the raw app_token/user_token as an identifier.
        digest = hashlib.sha256(raw.get("app_token", "unknown").encode()).hexdigest()[:12]
        return AccountRef(
            external_account_id=f"svc-{digest}",
            display_name="Cuenta de servicio api_token",
        )


class _FakeApiTokenAdapter:
    provider = "fake-api-token"
    capabilities: frozenset = frozenset()
    credential_kind = CredentialKind.api_token
    oauth = None

    def __init__(self) -> None:
        self.api_token: ApiTokenHandshake | None = _FakeApiTokenHandshake()

    def port_for(self, capability: object) -> object | None:
        return None


register_adapter(_FakeApiTokenAdapter())


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_api_token_connector(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/connectors",
        json={"provider": "fake-api-token", "credential_kind": "api_token"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


# ---------------------------------------------------------------------------
# C17-R1 — credential_kind por defecto/explícito
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connector_created_without_credential_kind_defaults_to_oauth(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Scenario: Conector oauth por defecto."""

    response = await client.post(
        "/connectors", json={"provider": "microsoft365"}, headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["credential_kind"] == "oauth"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connector_created_with_explicit_api_token_kind_persists_it(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Scenario: Conector api_token explícito."""

    response = await client.post(
        "/connectors",
        json={"provider": "fake-api-token", "credential_kind": "api_token"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["credential_kind"] == "api_token"


# ---------------------------------------------------------------------------
# C17-R2 — registro directo de credenciales api_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_registers_api_token_credentials_encrypted_and_hidden(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Admin registra credenciales api_token — se cifran y
    persisten en ConnectionCredentials sin exponerse en la respuesta."""

    connector_id = await _create_api_token_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"app_token": "APP-SECRET-1", "user_token": "USER-SECRET-1"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    expected_digest = hashlib.sha256(b"APP-SECRET-1").hexdigest()[:12]
    assert body["external_account_id"] == f"svc-{expected_digest}"
    # Never leaked in the response, in any form.
    assert "APP-SECRET-1" not in response.text
    assert "USER-SECRET-1" not in response.text

    # Persisted encrypted — the ciphertext is never the raw secret.
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
    assert "APP-SECRET-1" not in credentials.access_token_enc
    assert "USER-SECRET-1" not in credentials.access_token_enc


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_register_api_token_credentials(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Member no puede registrar credenciales api_token."""

    from app.shared.enums import MemberRole

    connector_id = await _create_api_token_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"app_token": "APP-SECRET-2", "user_token": "USER-SECRET-2"},
        headers=_auth(member_token),
    )

    assert response.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_credentials_against_nonexistent_connector_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    import uuid

    response = await client.post(
        f"/connectors/{uuid.uuid4()}/credentials",
        json={"app_token": "x", "user_token": "y"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_credentials_against_foreign_org_connector_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    connector_id = await _create_api_token_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"app_token": "x", "user_token": "y"},
        headers=_auth(two_orgs.b.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_credentials_against_oauth_connector_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """A connector whose `credential_kind` is `oauth` has no direct
    credential-registration operation — 404, same as a foreign/nonexistent
    connector (tasks.md T3.2, "404 si ... credential_kind != api_token")."""

    response = await client.post(
        "/connectors", json={"provider": "microsoft365"}, headers=_auth(two_orgs.a.token)
    )
    connector_id = response.json()["data"]["id"]

    credentials_response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"app_token": "x", "user_token": "y"},
        headers=_auth(two_orgs.a.token),
    )

    assert credentials_response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_credentials_with_base_url_outside_allowlist_returns_structured_error(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """CRITICAL/WARNING (revisión 4R del cambio 17-adapter-glpi, fix 6): un
    `base_url` fuera de `GLPI_BASE_URL_ALLOWLIST` hace que `GlpiClient`
    lance `GlpiConfigError` en su constructor — debe surgir como un error
    de dominio estructurado (422), nunca como un 500 sin controlar."""

    import app.integrations.adapters.glpi  # noqa: F401 - registra el adaptador real

    connector_response = await client.post(
        "/connectors",
        json={"provider": "glpi", "credential_kind": "api_token"},
        headers=_auth(two_orgs.a.token),
    )
    assert connector_response.status_code == 201, connector_response.text
    connector_id = connector_response.json()["data"]["id"]

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={
            "base_url": "http://169.254.169.254/apirest.php",
            "app_token": "app-token-x",
            "user_token": "user-token-y",
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "glpi_config_invalid"


# ---------------------------------------------------------------------------
# C17-R3 — authorize distingue oauth/api_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_on_api_token_connector_is_rejected_without_state(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Scenario: Authorize sobre conector api_token — error controlado, sin
    `state` ni URL."""

    connector_id = await _create_api_token_connector(client, two_orgs.a.token)
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "credential_kind_not_oauth"
    after = await patched_redis.dbsize()
    assert after == before
