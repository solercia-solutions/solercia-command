"""Tests for the `gitlab` adapter's credential handshake (S1).

`credential_kind=api_token`: `base_url` + `access_token`, validated against
`GET /api/v4/user` and `GET /api/v4/personal_access_tokens/self`. Only a
read-only token (`read_api`, no write scope) is accepted, and the host must
be `https` and listed in `GITLAB_BASE_URL_ALLOWLIST`.

Unit tests drive the handshake directly; endpoint tests go through
`POST /connectors` + `POST /connectors/{id}/credentials` with the real
registry entry swapped for an adapter bound to an `httpx.MockTransport`.
Zero real network.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.adapters.gitlab import errors
from app.integrations.adapters.gitlab.adapter import GitlabAdapter
from app.integrations.registry import get_adapter, register_adapter
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials
from tests.conftest import TwoOrgs, skip_no_db

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "gitlab"
_BASE_URL = "https://gitlab.com"
_TOKEN = "glpat-SECRETO-DE-PRUEBA"


def _fixture(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {"GITLAB_BASE_URL_ALLOWLIST": "gitlab.com"}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class _Recorder:
    """MockTransport handler that records every request it serves."""

    def __init__(self, routes: dict[str, Callable[[], httpx.Response]]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        factory = self.routes.get(request.url.path)
        if factory is None:
            return httpx.Response(404, json={"message": "404 Not Found"})
        return factory()


def _read_only_routes() -> dict[str, Callable[[], httpx.Response]]:
    return {
        "/api/v4/user": lambda: httpx.Response(200, json=_fixture("user.json")),
        "/api/v4/personal_access_tokens/self": lambda: httpx.Response(
            200, json=_fixture("token_read_api.json")
        ),
    }


def _adapter(recorder: _Recorder, **settings_overrides: object) -> GitlabAdapter:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return GitlabAdapter(
        settings=_settings(**settings_overrides),
        transport=httpx.MockTransport(recorder),
        sleep=_no_sleep,
    )


# ---------------------------------------------------------------------------
# Handshake (unit)
# ---------------------------------------------------------------------------


class TestGitlabHandshake:
    @pytest.mark.asyncio
    async def test_read_only_token_connects_and_sends_private_token_header(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        account = await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert account.external_account_id == "gitlab-4242"
        assert account.display_name == "Equipo de desarrollo (@equipo-desarrollo)"
        assert [r.url.path for r in recorder.requests] == [
            "/api/v4/user",
            "/api/v4/personal_access_tokens/self",
        ]
        assert all(r.headers["PRIVATE-TOKEN"] == _TOKEN for r in recorder.requests)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "scope",
        [
            "api",
            "write_repository",
            "write_registry",
            "write_virtual_registry",
            "sudo",
            "admin_mode",
            "create_runner",
            "manage_runner",
            "k8s_proxy",
            "self_rotate",
            "ai_features",
            "alcance_futuro_desconocido",
        ],
    )
    async def test_token_with_a_scope_outside_the_read_only_allowlist_is_rejected(
        self, scope: str
    ) -> None:
        payload = _fixture("token_read_api.json") | {"scopes": ["read_api", scope]}
        routes = _read_only_routes() | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(200, json=payload)
        }
        adapter = _adapter(_Recorder(routes))

        with pytest.raises(errors.GitlabTokenScopeNotAllowed) as exc_info:
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert scope in exc_info.value.detail
        assert "solo lectura" in exc_info.value.detail
        assert _TOKEN not in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_token_with_every_allowed_read_only_scope_connects(self) -> None:
        scopes = [
            "read_api",
            "read_user",
            "read_repository",
            "read_registry",
            "read_virtual_registry",
            "read_observability",
            "openid",
            "profile",
            "email",
        ]
        payload = _fixture("token_read_api.json") | {"scopes": scopes}
        routes = _read_only_routes() | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(200, json=payload)
        }
        adapter = _adapter(_Recorder(routes))

        account = await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert account.external_account_id == "gitlab-4242"

    @pytest.mark.asyncio
    async def test_token_that_cannot_be_inspected_gets_its_own_message(self) -> None:
        routes = _read_only_routes() | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(
                404, json={"message": "404 Not Found"}
            )
        }
        adapter = _adapter(_Recorder(routes))

        with pytest.raises(errors.GitlabTokenNotInspectable) as exc_info:
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "gitlab_token_not_inspectable"
        assert "repositorio" not in exc_info.value.detail
        assert _TOKEN not in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "base_url",
        ["https://gitl\tab.com", "https://gitlab.com/ruta con espacio", "https://gitlab\x00.com"],
    )
    async def test_base_url_with_whitespace_or_control_chars_is_rejected_before_any_call(
        self, base_url: str
    ) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        with pytest.raises(errors.GitlabConfigInvalid) as exc_info:
            await adapter.api_token.connect({"base_url": base_url, "access_token": _TOKEN})

        assert exc_info.value.status_code == 422
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_token_without_read_api_is_rejected(self) -> None:
        payload = _fixture("token_read_api.json") | {"scopes": ["read_user"]}
        routes = _read_only_routes() | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(200, json=payload)
        }
        adapter = _adapter(_Recorder(routes))

        with pytest.raises(errors.GitlabTokenScopeMissing) as exc_info:
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert "read_api" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_inactive_token_is_rejected_as_auth_error(self) -> None:
        payload = _fixture("token_read_api.json") | {"active": False}
        routes = _read_only_routes() | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(200, json=payload)
        }
        adapter = _adapter(_Recorder(routes))

        with pytest.raises(errors.GitlabAuthError):
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

    @pytest.mark.asyncio
    async def test_host_outside_allowlist_is_rejected_before_any_http_call(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        with pytest.raises(errors.GitlabConfigInvalid):
            await adapter.api_token.connect(
                {"base_url": "https://gitlab.interno.example", "access_token": _TOKEN}
            )

        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_host_suffix_trick_is_rejected(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        with pytest.raises(errors.GitlabConfigInvalid):
            await adapter.api_token.connect(
                {"base_url": "https://gitlab.com.evil.example", "access_token": _TOKEN}
            )
        with pytest.raises(errors.GitlabConfigInvalid):
            await adapter.api_token.connect(
                {"base_url": "https://user@gitlab.com", "access_token": _TOKEN}
            )

        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_http_scheme_is_rejected_before_any_http_call(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        with pytest.raises(errors.GitlabConfigInvalid) as exc_info:
            await adapter.api_token.connect(
                {"base_url": "http://gitlab.com", "access_token": _TOKEN}
            )

        assert "https" in exc_info.value.detail
        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_self_managed_host_in_allowlist_is_accepted(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder, GITLAB_BASE_URL_ALLOWLIST="gitlab.com, gitlab.entidad.gov.co")

        account = await adapter.api_token.connect(
            {"base_url": "https://gitlab.entidad.gov.co/", "access_token": _TOKEN}
        )

        assert account.external_account_id == "gitlab-4242"
        assert recorder.requests[0].url.host == "gitlab.entidad.gov.co"

    @pytest.mark.asyncio
    async def test_unauthorized_token_maps_to_controlled_error(self) -> None:
        routes = {"/api/v4/user": lambda: httpx.Response(401, json={"message": "401 Unauthorized"})}
        adapter = _adapter(_Recorder(routes))

        with pytest.raises(errors.GitlabAuthError) as exc_info:
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert exc_info.value.status_code == 422
        assert _TOKEN not in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_missing_fields_are_rejected_without_http_call(self) -> None:
        recorder = _Recorder(_read_only_routes())
        adapter = _adapter(recorder)

        with pytest.raises(errors.GitlabCredentialsIncomplete):
            await adapter.api_token.connect({"base_url": _BASE_URL})

        assert recorder.requests == []

    @pytest.mark.asyncio
    async def test_rate_limit_is_retried_then_succeeds(self) -> None:
        attempts = {"user": 0}

        def user_route() -> httpx.Response:
            attempts["user"] += 1
            if attempts["user"] == 1:
                return httpx.Response(429, headers={"Retry-After": "2"})
            return httpx.Response(200, json=_fixture("user.json"))

        routes = _read_only_routes() | {"/api/v4/user": user_route}
        adapter = _adapter(_Recorder(routes))

        account = await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})

        assert account.external_account_id == "gitlab-4242"
        assert attempts["user"] == 2

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted_maps_to_controlled_error(self) -> None:
        routes = {"/api/v4/user": lambda: httpx.Response(429)}
        adapter = _adapter(_Recorder(routes), GITLAB_MAX_RETRIES=2)

        with pytest.raises(errors.GitlabRateLimited):
            await adapter.api_token.connect({"base_url": _BASE_URL, "access_token": _TOKEN})


# ---------------------------------------------------------------------------
# Registration through the connectors HTTP flow
# ---------------------------------------------------------------------------


@pytest.fixture
def gitlab_transport() -> Iterator[Callable[[dict], _Recorder]]:
    """Swap the registered `gitlab` adapter for one bound to a MockTransport;
    restore the original afterwards."""

    original = get_adapter("gitlab")

    def _install(routes: dict) -> _Recorder:
        recorder = _Recorder(routes)
        register_adapter(_adapter(recorder))
        return recorder

    yield _install

    if original is not None:
        register_adapter(original)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_gitlab_connector(client: AsyncClient, token: str) -> str:
    response = await client.post(
        "/connectors",
        json={"provider": "gitlab", "credential_kind": "api_token"},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


async def _account_rows(session: AsyncSession, connector_id: str) -> list[ConnectedAccount]:
    result = await session.execute(
        select(ConnectedAccount).where(ConnectedAccount.connector_id == connector_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_read_only_token_registers_encrypted_and_never_echoed(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_transport
) -> None:
    gitlab_transport(_read_only_routes())
    connector_id = await _create_gitlab_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"base_url": _BASE_URL, "access_token": _TOKEN},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["external_account_id"] == "gitlab-4242"
    assert _TOKEN not in response.text

    accounts = await _account_rows(session, connector_id)
    assert len(accounts) == 1
    creds = (
        await session.execute(
            select(ConnectionCredentials).where(
                ConnectionCredentials.connected_account_id == accounts[0].id
            )
        )
    ).scalar_one()
    assert _TOKEN not in creds.access_token_enc


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_token_with_api_scope_is_rejected_and_nothing_persisted(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_transport
) -> None:
    gitlab_transport(
        _read_only_routes()
        | {
            "/api/v4/personal_access_tokens/self": lambda: httpx.Response(
                200, json=_fixture("token_api.json")
            )
        }
    )
    connector_id = await _create_gitlab_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"base_url": _BASE_URL, "access_token": _TOKEN},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "gitlab_token_scope_not_allowed"
    assert "solo lectura" in body["detail"]
    assert _TOKEN not in response.text
    assert await _account_rows(session, connector_id) == []
    creds_count = (await session.execute(select(ConnectionCredentials))).scalars().all()
    assert all(_TOKEN not in row.access_token_enc for row in creds_count)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_host_outside_allowlist_rejected_via_endpoint_with_zero_calls(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_transport
) -> None:
    recorder = gitlab_transport(_read_only_routes())
    connector_id = await _create_gitlab_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"base_url": "https://169.254.169.254", "access_token": _TOKEN},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "gitlab_config_invalid"
    assert recorder.requests == []
    assert await _account_rows(session, connector_id) == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unauthorized_token_via_endpoint_is_controlled_and_not_persisted(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, gitlab_transport
) -> None:
    gitlab_transport(
        {"/api/v4/user": lambda: httpx.Response(401, json={"message": "401 Unauthorized"})}
    )
    connector_id = await _create_gitlab_connector(client, two_orgs.a.token)

    response = await client.post(
        f"/connectors/{connector_id}/credentials",
        json={"base_url": _BASE_URL, "access_token": _TOKEN},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "gitlab_auth_error"
    assert _TOKEN not in response.text
    assert await _account_rows(session, connector_id) == []
