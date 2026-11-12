"""RED tests for MCP connector REGISTRATION (change 19-mcp-connector, Lote
6, mcp-connector/spec.md MC-R1/MC-R7/MC-R10, specs/connectors/spec.md delta
C-R1/C-R2, specs/integration-ports/spec.md delta IP-R2). Mirrors
`test_connectors_api_token.py`'s style — `client` ASGI + `two_orgs`.

Registration happens over `POST /connectors` in the SAME request as the
credential (design.md, "el token en el MISMO POST /connectors") — there is
NO separate `POST /connectors/{id}/credentials` step for `mcp` (unlike
GLPI/Jira).
"""

import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from tests.conftest import TwoOrgs, skip_no_db

_ALLOWED_BASE_URL = "https://127.0.0.1:9443/mcp"
_PRIVATE_OUTSIDE_ALLOWLIST_BASE_URL = "https://10.0.0.5/mcp"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mcp_settings(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "base_url": _ALLOWED_BASE_URL,
        "transport": "streamable_http",
        "auth_mode": "api_token",
        "tools_allowlist": [],
    }
    payload.update(overrides)
    return {"mcp": payload}


# ---------------------------------------------------------------------------
# MC-R1 / C-R2 — registro con token estático / sin autenticación
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_registers_mcp_connector_with_static_token_encrypted(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Registro con token estático."""

    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "api_token",
            "settings": _mcp_settings(auth_mode="api_token"),
            "token": "mcp-static-token-1",
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["credential_kind"] == "api_token"
    assert "mcp-static-token-1" not in response.text

    connector_id = body["id"]
    accounts_result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.connector_id == connector_id)
    )
    account = accounts_result.scalar_one()
    creds_result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = creds_result.scalar_one()
    assert "mcp-static-token-1" not in credentials.access_token_enc


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_registers_mcp_connector_without_auth_creates_no_credentials(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Registro sin autenticación."""

    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": _mcp_settings(auth_mode="none"),
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["credential_kind"] == "none"

    accounts_result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.connector_id == body["id"])
    )
    assert accounts_result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_register_mcp_connector(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: RBAC — solo admin/manager registran conectores."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": _mcp_settings(auth_mode="none"),
        },
        headers=_auth(member_token),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# MC-R7 — anti-SSRF al registrar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_registration_with_url_outside_allowlist_is_rejected_without_persisting(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: URL privada sin allowlist es rechazada — el registro NO
    persiste ningún conector."""

    before = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.organization_id == two_orgs.a.organization.id
        )
    )
    assert before.scalar_one_or_none() is None

    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": _mcp_settings(
                base_url=_PRIVATE_OUTSIDE_ALLOWLIST_BASE_URL, auth_mode="none"
            ),
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"].startswith("mcp_")

    from app.modules.connectors.models import Connector

    persisted = await session.execute(
        select(Connector).where(
            Connector.organization_id == two_orgs.a.organization.id,
            Connector.provider == "mcp",
        )
    )
    assert persisted.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_registration_with_http_scheme_rejected_when_allow_http_is_off(
    client: AsyncClient, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: `http` rechazado en producción — `MCP_ALLOW_HTTP=False`
    (el valor de producción)."""

    monkeypatch.setattr(app_settings, "MCP_ALLOW_HTTP", False)

    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": _mcp_settings(base_url="http://127.0.0.1:9443/mcp", auth_mode="none"),
        },
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "mcp_http_not_allowed"


# ---------------------------------------------------------------------------
# C-R2 — authorize no aplica a un conector de credencial directa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_authorize_on_mcp_connector_is_rejected_without_state(
    client: AsyncClient, two_orgs: TwoOrgs, patched_redis
) -> None:
    """Scenario: `authorize`/`callback` no aplica a un conector de
    credencial directa."""

    create_response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": _mcp_settings(auth_mode="none"),
        },
        headers=_auth(two_orgs.a.token),
    )
    connector_id = create_response.json()["data"]["id"]
    before = await patched_redis.dbsize()

    response = await client.get(
        f"/connectors/{connector_id}/authorize", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "credential_kind_not_oauth"
    after = await patched_redis.dbsize()
    assert after == before


# ---------------------------------------------------------------------------
# MC-R10 — el token nunca se expone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_token_never_appears_in_get_connector_response(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    """Scenario: Token del servidor MCP nunca expuesto — ni en la
    respuesta de `POST` ni en `GET /connectors/{id}`."""

    create_response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "api_token",
            "settings": _mcp_settings(auth_mode="api_token"),
            "token": "super-secret-mcp-token",
        },
        headers=_auth(two_orgs.a.token),
    )
    connector_id = create_response.json()["data"]["id"]
    assert "super-secret-mcp-token" not in create_response.text
    digest = hashlib.sha256(b"super-secret-mcp-token").hexdigest()

    get_response = await client.get(
        f"/connectors/{connector_id}", headers=_auth(two_orgs.a.token)
    )

    assert "super-secret-mcp-token" not in get_response.text
    assert digest not in get_response.text
