"""RED tests for the MCP connector's REST READ layer (change
19-mcp-connector, Lote 6, mcp-connector/spec.md MC-R1/MC-R5/MC-R9/MC-R10).

Swaps the registered `mcp` adapter for one bound to the in-memory fake
server's `transport_factory` (`mcp_fake_transport` fixture below) — the
router/service code under test is EXACTLY what a real deployment runs, only
the transport is fake (MC-R11).
"""

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.integrations.adapters.mcp.adapter import McpAdapter
from app.integrations.registry import get_adapter, register_adapter
from tests.conftest import TwoOrgs, skip_no_db
from tests.fixtures.mcp import make_fake_transport_factory
from tests.fixtures.mcp.fake_server import READ_ONLY_TOOL_ECHO_PREFIX, SMALL_RESOURCE_TEXT

_ALLOWED_BASE_URL = "https://127.0.0.1:9443/mcp"


@pytest_asyncio.fixture
async def mcp_fake_transport() -> AsyncGenerator[None, None]:
    """Register a `McpAdapter` bound to the fake in-memory transport for the
    duration of ONE test, then restore the real one — the registry
    (`app/integrations/registry.py`) is module-level global state."""

    original = get_adapter("mcp")
    register_adapter(McpAdapter(transport_factory=make_fake_transport_factory()))
    yield
    if original is not None:
        register_adapter(original)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_mcp_connector(
    client: AsyncClient, token: str, *, tools_allowlist: list[str] | None = None
) -> str:
    response = await client.post(
        "/connectors",
        json={
            "provider": "mcp",
            "credential_kind": "none",
            "settings": {
                "mcp": {
                    "base_url": _ALLOWED_BASE_URL,
                    "transport": "streamable_http",
                    "auth_mode": "none",
                    "tools_allowlist": tools_allowlist or [],
                }
            },
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


# ---------------------------------------------------------------------------
# MC-R1 — lectura accesible por cualquier miembro
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_any_member_can_list_mcp_resources(
    client: AsyncClient, two_orgs: TwoOrgs, make_member, session, mcp_fake_transport
) -> None:
    from app.shared.enums import MemberRole

    connector_id = await _create_mcp_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get(
        f"/connectors/{connector_id}/mcp/resources", headers=_auth(member_token)
    )

    assert response.status_code == 200, response.text
    uris = [r["uri"] for r in response.json()["data"]]
    assert "fake://notes/small" in uris


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_any_member_can_read_a_resource(
    client: AsyncClient, two_orgs: TwoOrgs, make_member, session, mcp_fake_transport
) -> None:
    from app.shared.enums import MemberRole

    connector_id = await _create_mcp_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get(
        f"/connectors/{connector_id}/mcp/resources/read",
        params={"uri": "fake://notes/small"},
        headers=_auth(member_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["text"] == SMALL_RESOURCE_TEXT


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_any_member_can_list_mcp_tools(
    client: AsyncClient, two_orgs: TwoOrgs, make_member, session, mcp_fake_transport
) -> None:
    from app.shared.enums import MemberRole

    connector_id = await _create_mcp_connector(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get(
        f"/connectors/{connector_id}/mcp/tools", headers=_auth(member_token)
    )

    assert response.status_code == 200, response.text
    tools = {t["name"]: t["read_only"] for t in response.json()["data"]}
    assert tools["read_only_echo"] is True
    assert tools["dangerous_write"] is False


# ---------------------------------------------------------------------------
# MC-R5 — invocación controlada de tools vía REST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_call_tool_allowlisted_and_read_only_succeeds(
    client: AsyncClient, two_orgs: TwoOrgs, mcp_fake_transport
) -> None:
    connector_id = await _create_mcp_connector(
        client, two_orgs.a.token, tools_allowlist=["read_only_echo"]
    )

    response = await client.post(
        f"/connectors/{connector_id}/mcp/tools/read_only_echo/call",
        json={"arguments": {"message": "hola"}},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["text"] == f"{READ_ONLY_TOOL_ECHO_PREFIX}: hola"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_call_tool_write_tool_is_rejected(
    client: AsyncClient, two_orgs: TwoOrgs, mcp_fake_transport
) -> None:
    connector_id = await _create_mcp_connector(
        client, two_orgs.a.token, tools_allowlist=["dangerous_write"]
    )

    response = await client.post(
        f"/connectors/{connector_id}/mcp/tools/dangerous_write/call",
        json={"arguments": {"payload": "boom"}},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "mcp_tool_not_allowed"


# ---------------------------------------------------------------------------
# MC-R9 / MC-R10 — aislamiento multi-tenant, ninguna ruta muta el servidor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_mcp_connector_of_org_a_is_not_accessible_from_org_b(
    client: AsyncClient, two_orgs: TwoOrgs, mcp_fake_transport
) -> None:
    connector_id = await _create_mcp_connector(client, two_orgs.a.token)

    response = await client.get(
        f"/connectors/{connector_id}/mcp/resources", headers=_auth(two_orgs.b.token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_nonexistent_connector_returns_404_on_every_mcp_route(
    client: AsyncClient, two_orgs: TwoOrgs, mcp_fake_transport
) -> None:
    missing_id = uuid.uuid4()

    resources = await client.get(
        f"/connectors/{missing_id}/mcp/resources", headers=_auth(two_orgs.a.token)
    )
    tools = await client.get(
        f"/connectors/{missing_id}/mcp/tools", headers=_auth(two_orgs.a.token)
    )

    assert resources.status_code == 404
    assert tools.status_code == 404


def test_no_mcp_route_declares_a_mutating_http_method() -> None:
    """Scenario: Ninguna operación del conector MCP DEBE mutar el servicio
    externo — every `/mcp/` route is `GET`, except the ONE gated `POST
    .../tools/{tool_name}/call`; no `PUT`/`PATCH`/`DELETE` exists."""

    from app.modules.connectors.router import router

    mcp_routes = [route for route in router.routes if "/mcp/" in getattr(route, "path", "")]
    assert mcp_routes, "no se registraron rutas /mcp/"
    for route in mcp_routes:
        methods = getattr(route, "methods", set())
        assert methods <= {"GET", "POST", "HEAD"}
        if "POST" in methods:
            assert route.path.endswith("/call")
