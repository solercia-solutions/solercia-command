"""Tests for the Solercia Connect facade (`/connectors/solercia-connect*`).

Connect is faked at the HTTP boundary with ``httpx.MockTransport`` — no
runtime, no network. Each endpoint gets its happy path, its error mapping and
its permission check; the request Command sends (path, header, body) is
asserted so the contract with Connect is pinned on this side too.
"""

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.integrations import crypto
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.intake.models import IntakeRule
from app.modules.tasks.models import Task
from app.shared.enums import AccountStatus, MemberRole
from tests.conftest import TwoOrgs, skip_no_db

_BASE_URL = "http://127.0.0.1:8765"
_API_KEY = "runtime-key-that-must-never-leak"
_ACCOUNT = "persona@entidad.example.gov.co"
_SCHEMA = "solercia.connect/v1"

Responder = Callable[[httpx.Request], httpx.Response]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _health(*, interactive_login: bool = True, version: str = "0.4.0") -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": True,
        "operation": "health",
        "status": "ok",
        "data": {"version": version, "interactive_login": interactive_login},
        "error": None,
    }


def _connected(operation: str = "connections.test") -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": True,
        "operation": operation,
        "status": "connected_browser",
        "provider": "outlook",
        "account": _ACCOUNT,
        "route": "browser",
        "data": {},
        "error": None,
    }


def _failure(
    status: str,
    code: str,
    *,
    message: str = "Connect says no",
    remediation: list[str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": False,
        "operation": "connections.test",
        "status": status,
        "provider": "outlook",
        "account": _ACCOUNT,
        "route": None,
        "data": data or {},
        "error": {"code": code, "message": message, "remediation": remediation or []},
    }


_REMEDIATION = [
    "solercia-connect connect --type outlook --account persona@entidad.example.gov.co",
    "Set SOLERCIA_CONNECT_HTTP_INTERACTIVE_LOGIN=true (...) to allow the loopback service "
    "to start the supervised browser.",
]


def _run_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": True,
        "status": "success",
        "operation": "run",
        "account": _ACCOUNT,
        "route": "browser",
        "data": {"records": records},
        "error": None,
    }


def _mail(record_id: str, sent_at: str) -> dict[str, Any]:
    return {
        "id": record_id,
        "subject": f"Asunto {record_id}",
        "sent_at": sent_at,
        "sender": {"address": "remitente@entidad.example.gov.co"},
        "to": [{"address": _ACCOUNT}],
        "body": "Cuerpo del mensaje",
        "body_format": "text",
    }


class ConnectFake:
    """Routes ``(METHOD, path)`` to a responder and records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._routes: dict[tuple[str, str], Responder] = {}

    def on(self, method: str, path: str, responder: Responder | httpx.Response) -> None:
        self._routes[(method, path)] = (
            responder if callable(responder) else (lambda request, r=responder: r)
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        responder = self._routes.get((request.method, request.url.path))
        if responder is None:
            return httpx.Response(500, json={"detail": f"unrouted {request.url.path}"})
        return responder(request)

    def paths(self) -> list[str]:
        return [f"{request.method} {request.url.path}" for request in self.requests]

    def bodies(self, path: str) -> list[dict[str, Any]]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path == path and request.content
        ]


def _refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.fixture
def connect(monkeypatch: pytest.MonkeyPatch) -> ConnectFake:
    """Fake Connect wired into BOTH places that build a client (the adapter's
    handshake and the facade), plus the server-side settings the facade reads."""

    from app.integrations.adapters.solercia_connect import adapter as adapter_module
    from app.modules.connectors import solercia_connect_service as facade_module

    fake = ConnectFake()
    transport = httpx.MockTransport(fake.handler)
    original = adapter_module.SolerciaConnectClient

    def factory(**kwargs: Any) -> Any:
        return original(**kwargs, transport=transport)

    monkeypatch.setattr(adapter_module, "SolerciaConnectClient", factory)
    monkeypatch.setattr(facade_module, "SolerciaConnectClient", factory)
    monkeypatch.setattr(app_settings, "SOLERCIA_CONNECT_API_KEY", SecretStr(_API_KEY))
    monkeypatch.setattr(app_settings, "SOLERCIA_CONNECT_BASE_URL", _BASE_URL)
    fake.on("GET", "/v1/health", httpx.Response(200, json=_health()))
    return fake


async def _register(client: httpx.AsyncClient, token: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"account": _ACCOUNT, "target": "outlook"}
    payload.update(overrides)
    response = await client.post("/connectors/solercia-connect", json=payload, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _account_row(session: AsyncSession, connector_id: str) -> ConnectedAccount:
    result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.connector_id == uuid.UUID(connector_id),
            ConnectedAccount.is_active.is_(True),
        )
    )
    return result.scalar_one()


async def _set_account_status(
    session: AsyncSession, connector_id: str, status: AccountStatus
) -> None:
    account = await _account_row(session, connector_id)
    account.status = status
    await session.flush()


# ---------------------------------------------------------------------------
# 1. POST /connectors/solercia-connect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_creates_connector_account_and_encrypted_key(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token, account=_ACCOUNT.upper())

    assert data["connector"]["provider"] == "solercia_connect"
    assert data["connector"]["credential_kind"] == "api_token"
    assert data["connector"]["settings"]["solercia_connect"] == {
        "account": _ACCOUNT,
        "target": "outlook",
        "allow_browser_fallback": True,
    }
    assert data["settings"] == {
        "account": _ACCOUNT,
        "target": "outlook",
        "allow_browser_fallback": True,
    }
    assert data["account"]["external_account_id"] == _ACCOUNT
    assert data["account"]["status"] == "active"
    assert data["runtime"] == {"reachable": True, "version": "0.4.0", "interactive_login": True}
    # Probe first, then the adapter's own handshake — nothing else.
    assert connect.paths() == ["GET /v1/health", "GET /v1/health"]

    account = await _account_row(session, data["connector"]["id"])
    result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = result.scalar_one()
    assert _API_KEY not in credentials.access_token_enc
    blob = json.loads(crypto.decrypt(credentials.access_token_enc))
    assert blob["api_key"] == _API_KEY
    assert blob["base_url"] == _BASE_URL
    assert blob["allow_browser_fallback"] == "true"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_never_returns_the_api_key(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    response = await client.post(
        "/connectors/solercia-connect",
        json={"account": _ACCOUNT},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201
    assert _API_KEY not in response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_twice_reuses_the_single_connector(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    first = await _register(client, two_orgs.a.token)
    second = await _register(client, two_orgs.a.token, allow_browser_fallback=False)

    assert second["connector"]["id"] == first["connector"]["id"]
    assert second["settings"]["allow_browser_fallback"] is False
    result = await session.execute(
        select(Connector).where(
            Connector.organization_id == two_orgs.a.organization.id,
            Connector.provider == "solercia_connect",
        )
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_with_another_account_retires_the_previous_one(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    first = await _register(client, two_orgs.a.token)
    second = await _register(client, two_orgs.a.token, account="otra@entidad.example.gov.co")

    assert second["connector"]["id"] == first["connector"]["id"]
    result = await session.execute(
        select(ConnectedAccount).where(
            ConnectedAccount.connector_id == uuid.UUID(first["connector"]["id"])
        )
    )
    rows = {row.external_account_id: row for row in result.scalars().all()}
    assert rows[_ACCOUNT].is_active is False
    assert rows["otra@entidad.example.gov.co"].is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_when_runtime_is_down_is_503_and_writes_nothing(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    connect.on("GET", "/v1/health", _refused)

    response = await client.post(
        "/connectors/solercia-connect", json={"account": _ACCOUNT}, headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "solercia_connect_unavailable"
    result = await session.execute(
        select(Connector).where(
            Connector.organization_id == two_orgs.a.organization.id,
            Connector.provider == "solercia_connect",
        )
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_without_server_key_is_422_not_configured(
    client: httpx.AsyncClient,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "SOLERCIA_CONNECT_API_KEY", None)

    response = await client.post(
        "/connectors/solercia-connect", json={"account": _ACCOUNT}, headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "solercia_connect_not_configured"
    assert connect.requests == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_with_base_url_outside_allowlist_is_422(
    client: httpx.AsyncClient,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_settings, "SOLERCIA_CONNECT_BASE_URL", "http://evil.example.com")

    response = await client.post(
        "/connectors/solercia-connect", json={"account": _ACCOUNT}, headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "solercia_connect_not_configured"
    assert connect.requests == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_rejects_an_unknown_target_and_a_bad_email(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    bad_target = await client.post(
        "/connectors/solercia-connect",
        json={"account": _ACCOUNT, "target": "gmail"},
        headers=_auth(two_orgs.a.token),
    )
    bad_email = await client.post(
        "/connectors/solercia-connect",
        json={"account": "no-es-un-correo"},
        headers=_auth(two_orgs.a.token),
    )

    assert bad_target.status_code == 422
    assert bad_email.status_code == 422
    assert connect.requests == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_register(
    client: httpx.AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    make_member,
) -> None:
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post(
        "/connectors/solercia-connect", json={"account": _ACCOUNT}, headers=_auth(member_token)
    )

    assert response.status_code == 403
    assert connect.requests == []


# ---------------------------------------------------------------------------
# 2. GET /connectors/{id}/solercia-connect/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_connected_reactivates_the_account(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    await _set_account_status(session, connector_id, AccountStatus.expired)
    connect.on("POST", "/v1/connections/test", httpx.Response(200, json=_connected()))

    response = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["state"] == "connected"
    assert body["route"] == "browser"
    assert body["account"] == _ACCOUNT
    assert body["runtime"] == {"reachable": True, "version": "0.4.0", "interactive_login": True}
    assert body["checked_at"]
    assert connect.bodies("/v1/connections/test") == [
        {"type": "outlook", "account": _ACCOUNT, "allow_browser_fallback": True}
    ]
    assert connect.requests[-1].headers["X-Solercia-Connect-Key"] == _API_KEY
    account = await _account_row(session, connector_id)
    assert account.status == AccountStatus.active


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_action_required_with_gate_open_is_needs_login(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on(
        "POST",
        "/v1/connections/test",
        httpx.Response(
            409, json=_failure("action_required", "action_required", remediation=_REMEDIATION)
        ),
    )

    response = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    body = response.json()["data"]
    assert body["state"] == "needs_login"
    assert body["remediation"] == _REMEDIATION
    account = await _account_row(session, connector_id)
    assert account.status == AccountStatus.expired


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_action_required_with_gate_closed_is_interactive_disabled(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on("GET", "/v1/health", httpx.Response(200, json=_health(interactive_login=False)))
    connect.on(
        "POST",
        "/v1/connections/test",
        httpx.Response(409, json=_failure("action_required", "action_required")),
    )

    response = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    body = response.json()["data"]
    assert body["state"] == "interactive_disabled"
    assert body["runtime"]["interactive_login"] is False
    # Not a verdict on the session: the account is left as it was.
    account = await _account_row(session, connector_id)
    assert account.status == AccountStatus.active


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_runtime_down_is_a_state_not_an_error(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on("GET", "/v1/health", _refused)

    response = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["state"] == "runtime_unavailable"
    assert body["runtime"]["reachable"] is False
    account = await _account_row(session, connector_id)
    assert account.status == AccountStatus.active


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_rejected_key_is_runtime_unauthorized(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on("POST", "/v1/connections/test", httpx.Response(401, json={"detail": "nope"}))

    response = await client.get(
        f"/connectors/{data['connector']['id']}/solercia-connect/status",
        headers=_auth(two_orgs.a.token),
    )

    assert response.json()["data"]["state"] == "runtime_unauthorized"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_503_or_configuration_error_is_misconfigured(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on("POST", "/v1/connections/test", httpx.Response(503, json={"detail": "off"}))

    first = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )
    connect.on(
        "POST",
        "/v1/connections/test",
        httpx.Response(200, json=_failure("configuration_error", "configuration_error")),
    )
    second = await client.get(
        f"/connectors/{connector_id}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    assert first.json()["data"]["state"] == "misconfigured"
    assert first.json()["data"]["runtime"]["reachable"] is True
    assert second.json()["data"]["state"] == "misconfigured"
    account = await _account_row(session, connector_id)
    assert account.status == AccountStatus.error


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_unknown_failure_is_error_with_connect_message(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on(
        "POST",
        "/v1/connections/test",
        httpx.Response(200, json=_failure("failed", "unknown_error", message="Perfil dañado")),
    )

    response = await client.get(
        f"/connectors/{data['connector']['id']}/solercia-connect/status",
        headers=_auth(two_orgs.a.token),
    )

    body = response.json()["data"]
    assert body["state"] == "error"
    assert body["detail"] == "Perfil dañado"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_is_readable_by_a_plain_member(
    client: httpx.AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    make_member,
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on("POST", "/v1/connections/test", httpx.Response(200, json=_connected()))
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.get(
        f"/connectors/{data['connector']['id']}/solercia-connect/status",
        headers=_auth(member_token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["state"] == "connected"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_status_of_foreign_or_non_connect_connector_is_404(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    other = await client.post(
        "/connectors", json={"provider": "microsoft365"}, headers=_auth(two_orgs.a.token)
    )

    foreign = await client.get(
        f"/connectors/{data['connector']['id']}/solercia-connect/status",
        headers=_auth(two_orgs.b.token),
    )
    wrong_provider = await client.get(
        f"/connectors/{other.json()['data']['id']}/solercia-connect/status",
        headers=_auth(two_orgs.a.token),
    )
    missing = await client.get(
        f"/connectors/{uuid.uuid4()}/solercia-connect/status", headers=_auth(two_orgs.a.token)
    )

    assert foreign.status_code == 404
    assert wrong_provider.status_code == 404
    assert missing.status_code == 404
    assert connect.paths().count("POST /v1/connections/test") == 0


# ---------------------------------------------------------------------------
# 3. POST /connectors/{id}/solercia-connect/connect
# ---------------------------------------------------------------------------


def _started(session_id: str = "5f6a0b1e-1111-4222-8333-444455556666") -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": True,
        "operation": "connections.connect",
        "status": "started",
        "provider": "outlook",
        "account": _ACCOUNT,
        "route": "browser",
        "data": {
            "session_id": session_id,
            "interactive_flow_started": True,
            "expires_in_seconds": 600,
        },
        "receipt": None,
        "error": None,
    }


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connect_starts_a_session_and_returns_202(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on("POST", "/v1/connections/connect", httpx.Response(202, json=_started()))

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/connect",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 202, response.text
    assert response.json()["data"] == {
        "session_id": "5f6a0b1e-1111-4222-8333-444455556666",
        "started": True,
        "expires_in_seconds": 600,
    }
    assert connect.bodies("/v1/connections/connect") == [
        {"type": "outlook", "account": _ACCOUNT, "allow_browser_fallback": True}
    ]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connect_busy_is_409_with_the_running_session_in_meta(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on(
        "POST",
        "/v1/connections/connect",
        httpx.Response(
            409,
            json=_failure("busy", "interactive_session_busy", data={"session_id": "running-7"}),
        ),
    )

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/connect",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "solercia_connect_busy"
    assert body["meta"] == {"session_id": "running-7"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connect_with_gate_closed_is_409_with_remediation_in_detail(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on(
        "POST",
        "/v1/connections/connect",
        httpx.Response(
            409, json=_failure("action_required", "action_required", remediation=_REMEDIATION)
        ),
    )

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/connect",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "solercia_connect_interactive_disabled"
    assert body["detail"] == " ".join(_REMEDIATION)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connect_invalid_request_and_runtime_failures_are_mapped(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    url = f"/connectors/{data['connector']['id']}/solercia-connect/connect"

    connect.on(
        "POST",
        "/v1/connections/connect",
        httpx.Response(422, json=_failure("invalid_input", "invalid_input", message="tipo")),
    )
    invalid = await client.post(url, headers=_auth(two_orgs.a.token))
    connect.on("POST", "/v1/connections/connect", _refused)
    down = await client.post(url, headers=_auth(two_orgs.a.token))
    connect.on("POST", "/v1/connections/connect", httpx.Response(403, json={}))
    unauthorized = await client.post(url, headers=_auth(two_orgs.a.token))

    assert (invalid.status_code, invalid.json()["code"]) == (
        422,
        "solercia_connect_invalid_request",
    )
    assert invalid.json()["detail"] == "tipo"
    assert (down.status_code, down.json()["code"]) == (503, "solercia_connect_unavailable")
    assert (unauthorized.status_code, unauthorized.json()["code"]) == (
        502,
        "solercia_connect_unauthorized",
    )


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_connect_without_browser_fallback_is_refused_before_calling_connect(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token, allow_browser_fallback=False)
    before = len(connect.requests)

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/connect",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "solercia_connect_fallback_not_allowed"
    assert len(connect.requests) == before


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_start_a_login(
    client: httpx.AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    make_member,
) -> None:
    data = await _register(client, two_orgs.a.token)
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/connect",
        headers=_auth(member_token),
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 4. GET /connectors/{id}/solercia-connect/sessions/{session_id}
# ---------------------------------------------------------------------------


def _session_running(session_id: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA,
        "ok": True,
        "operation": "connections.session",
        "status": "running",
        "provider": "outlook",
        "account": _ACCOUNT,
        "route": "browser",
        "data": {
            "session_id": session_id,
            "started_at": "2026-09-04T10:00:00+00:00",
            "interactive_flow_started": True,
        },
        "error": None,
    }


def _session_finished(session_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    body = dict(envelope)
    body["operation"] = "connections.session"
    body["data"] = {
        **body.get("data", {}),
        "session_id": session_id,
        "started_at": "2026-09-04T10:00:00+00:00",
        "finished_at": "2026-09-04T10:02:00+00:00",
    }
    return body


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_running_and_connected_states(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    await _set_account_status(session, connector_id, AccountStatus.expired)
    url = f"/connectors/{connector_id}/solercia-connect/sessions/sess-1"
    connect.on(
        "GET",
        "/v1/connections/sessions/sess-1",
        httpx.Response(200, json=_session_running("sess-1")),
    )

    running = await client.get(url, headers=_auth(two_orgs.a.token))
    assert running.status_code == 200, running.text
    assert running.json()["data"]["state"] == "running"
    assert running.json()["data"]["started_at"] == "2026-09-04T10:00:00Z"
    assert (await _account_row(session, connector_id)).status == AccountStatus.expired

    connect.on(
        "GET",
        "/v1/connections/sessions/sess-1",
        httpx.Response(200, json=_session_finished("sess-1", _connected("connections.connect"))),
    )
    connected = await client.get(url, headers=_auth(two_orgs.a.token))
    body = connected.json()["data"]
    assert body["state"] == "connected"
    assert body["route"] == "browser"
    assert body["finished_at"] == "2026-09-04T10:02:00Z"
    assert (await _account_row(session, connector_id)).status == AccountStatus.active


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_failures_set_expired_or_error_on_the_account(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    url = f"/connectors/{connector_id}/solercia-connect/sessions/sess-2"

    connect.on(
        "GET",
        "/v1/connections/sessions/sess-2",
        httpx.Response(
            200,
            json=_session_finished(
                "sess-2",
                _failure("failed", "browser_mfa_required", remediation=["Completa el MFA."]),
            ),
        ),
    )
    login = await client.get(url, headers=_auth(two_orgs.a.token))
    body = login.json()["data"]
    assert body["state"] == "failed"
    assert body["error_code"] == "browser_mfa_required"
    assert body["remediation"] == ["Completa el MFA."]
    assert (await _account_row(session, connector_id)).status == AccountStatus.expired

    connect.on(
        "GET",
        "/v1/connections/sessions/sess-2",
        httpx.Response(200, json=_session_finished("sess-2", _failure("failed", "unknown_error"))),
    )
    other = await client.get(url, headers=_auth(two_orgs.a.token))
    assert other.json()["data"]["state"] == "failed"
    assert other.json()["data"]["error_code"] == "unknown_error"
    assert (await _account_row(session, connector_id)).status == AccountStatus.error


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_unknown_id_is_not_found_and_malformed_id_is_422(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on(
        "GET",
        "/v1/connections/sessions/ghost",
        httpx.Response(404, json=_failure("not_found", "session_not_found")),
    )

    missing = await client.get(
        f"/connectors/{connector_id}/solercia-connect/sessions/ghost",
        headers=_auth(two_orgs.a.token),
    )
    malformed = await client.get(
        f"/connectors/{connector_id}/solercia-connect/sessions/bad%20id%21",
        headers=_auth(two_orgs.a.token),
    )

    assert missing.status_code == 200
    assert missing.json()["data"]["state"] == "not_found"
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "solercia_connect_invalid_request"
    assert not any("bad" in path for path in connect.paths())


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_session_is_readable_by_a_member_and_404_for_foreign_org(
    client: httpx.AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    make_member,
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on(
        "GET",
        "/v1/connections/sessions/sess-3",
        httpx.Response(200, json=_session_running("sess-3")),
    )
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    url = f"/connectors/{connector_id}/solercia-connect/sessions/sess-3"

    member = await client.get(url, headers=_auth(member_token))
    foreign = await client.get(url, headers=_auth(two_orgs.b.token))

    assert member.status_code == 200
    assert foreign.status_code == 404


# ---------------------------------------------------------------------------
# 5. POST /connectors/{id}/solercia-connect/sync
# ---------------------------------------------------------------------------


def _run_by_capability(records_by_capability: dict[str, list[dict[str, Any]]]) -> Responder:
    def responder(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200, json=_run_records(records_by_capability.get(body["capability"], []))
        )

    return responder


async def _seed_convert_all_rule(session: AsyncSession, organization_id: uuid.UUID) -> None:
    session.add(
        IntakeRule(
            organization_id=organization_id,
            name="Todo lo de Connect a tarea",
            criteria=[
                {"field": "source_provider", "operator": "equals", "value": "solercia_connect"}
            ],
            convert_to_task=True,
            rule_order=1,
        )
    )
    await session.flush()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sync_pulls_both_folders_and_creates_anchored_tasks(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    await _seed_convert_all_rule(session, two_orgs.a.organization.id)
    connect.on(
        "POST",
        "/v1/run",
        _run_by_capability(
            {
                "mail.inbox.list": [_mail("in-1", "2026-09-03T09:00:00+00:00")],
                "mail.sent.list": [_mail("out-1", "2026-09-02T09:00:00+00:00")],
            }
        ),
    )

    response = await client.post(
        f"/connectors/{connector_id}/solercia-connect/sync",
        json={"since_days": 3},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "completed"
    assert body["run_id"] == body["runs"][0]["id"]
    assert body["runs"][0]["connector_id"] == connector_id
    assert body["items_fetched"] == 2
    assert body["items_new"] == 2
    assert body["items_duplicated"] == 0
    assert body["tasks_created"] == 2
    assert body["errors"] == []

    capabilities = [entry["capability"] for entry in connect.bodies("/v1/run")]
    assert capabilities[:2] == ["mail.inbox.list", "mail.sent.list"]
    # `since_days` becomes Connect's exact window (both bounds travel together).
    assert all("start" in entry and "end" in entry for entry in connect.bodies("/v1/run"))

    result = await session.execute(select(Task).where(Task.source == "solercia_connect"))
    tasks = result.scalars().all()
    assert sorted(task.external_key for task in tasks) == ["in-1", "out-1"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sync_repeated_reports_duplicates_and_no_new_tasks(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    await _seed_convert_all_rule(session, two_orgs.a.organization.id)
    connect.on(
        "POST",
        "/v1/run",
        _run_by_capability({"mail.inbox.list": [_mail("in-1", "2026-09-03T09:00:00+00:00")]}),
    )
    url = f"/connectors/{connector_id}/solercia-connect/sync"

    await client.post(url, json={}, headers=_auth(two_orgs.a.token))
    second = await client.post(url, headers=_auth(two_orgs.a.token))

    body = second.json()["data"]
    assert body["items_new"] == 0
    assert body["items_duplicated"] == 1
    assert body["tasks_created"] == 0
    result = await session.execute(select(Task).where(Task.source == "solercia_connect"))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sync_when_login_is_required_is_409_and_expires_the_account(
    client: httpx.AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connector_id = data["connector"]["id"]
    connect.on(
        "POST",
        "/v1/run",
        httpx.Response(
            409, json=_failure("action_required", "action_required", remediation=_REMEDIATION)
        ),
    )

    response = await client.post(
        f"/connectors/{connector_id}/solercia-connect/sync", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "solercia_connect_needs_login"
    assert body["meta"]["errors"][0]["code"] == "action_required"
    assert (await _account_row(session, connector_id)).status == AccountStatus.expired


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sync_other_failures_are_200_with_errors_listed(
    client: httpx.AsyncClient, two_orgs: TwoOrgs, connect: ConnectFake
) -> None:
    data = await _register(client, two_orgs.a.token)
    connect.on("POST", "/v1/run", _refused)

    response = await client.post(
        f"/connectors/{data['connector']['id']}/solercia-connect/sync",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["status"] == "error"
    assert body["runs"][0]["status"] == "error"
    assert body["errors"][0]["code"] == "solercia_connect_unavailable"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_sync_validates_since_days_and_roles(
    client: httpx.AsyncClient,
    session: AsyncSession,
    two_orgs: TwoOrgs,
    connect: ConnectFake,
    make_member,
) -> None:
    data = await _register(client, two_orgs.a.token)
    url = f"/connectors/{data['connector']['id']}/solercia-connect/sync"
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    out_of_range = await client.post(url, json={"since_days": 0}, headers=_auth(two_orgs.a.token))
    member = await client.post(url, headers=_auth(member_token))
    foreign = await client.post(url, headers=_auth(two_orgs.b.token))

    assert out_of_range.status_code == 422
    assert out_of_range.json()["code"] == "validation_error"
    assert member.status_code == 403
    assert foreign.status_code == 404
    assert "POST /v1/run" not in connect.paths()
