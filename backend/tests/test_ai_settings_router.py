"""C04: `/ai/settings`, `/ai/presets`, `/ai/settings/test` — admin writes,
manager reads, member/viewer 403, anonymous 401, tenant isolation, the key
never leaves the server. Provider calls go to a fake transport.
"""

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai_settings.models import AiProviderSettings
from app.modules.ai_settings.router import get_ai_resolver, get_ai_transport
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]

_KEY = "sk-router-synthetic-9876-QRST"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def provider():
    from app.main import app

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5, 0.5]}]})

    app.dependency_overrides[get_ai_transport] = lambda: httpx.MockTransport(handler)
    app.dependency_overrides[get_ai_resolver] = lambda: lambda host: ["93.184.216.34"]
    yield calls
    app.dependency_overrides.pop(get_ai_transport, None)
    app.dependency_overrides.pop(get_ai_resolver, None)


async def test_anonymous_gets_401(client: AsyncClient):
    for method, path in (
        ("GET", "/ai/settings"),
        ("PUT", "/ai/settings"),
        ("GET", "/ai/presets"),
        ("POST", "/ai/settings/test"),
    ):
        response = await client.request(method, path, json={})
        assert response.status_code == 401, (method, path)


async def test_admin_reads_the_local_default_when_nothing_is_configured(
    client: AsyncClient, two_orgs: TwoOrgs
):
    response = await client.get("/ai/settings", headers=_auth(two_orgs.a.token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"] == "default" and data["preset"] == "ollama_local"
    assert data["locality"] == "local" and data["has_api_key"] is False


async def test_presets_list_marks_local_and_external(client: AsyncClient, two_orgs: TwoOrgs):
    response = await client.get("/ai/presets", headers=_auth(two_orgs.a.token))
    assert response.status_code == 200, response.text
    presets = {p["key"]: p for p in response.json()["data"]}
    assert presets["ollama_local"]["locality"] == "local"
    assert presets["openai"]["locality"] == "external"
    assert presets["openai"]["requires_api_key"] is True
    assert set(presets) >= {
        "ollama_local",
        "llamacpp_local",
        "openai",
        "openrouter",
        "groq",
        "deepseek",
        "mistral",
        "custom",
    }


async def test_admin_saves_byok_and_the_key_never_comes_back(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    response = await client.put(
        "/ai/settings",
        headers=_auth(two_orgs.a.token),
        json={"preset": "openai", "api_key": _KEY, "chat_model": "gpt-5-mini"},
    )
    assert response.status_code == 200, response.text
    assert _KEY not in response.text
    data = response.json()["data"]
    assert data["has_api_key"] is True and data["api_key_last4"] == "QRST"
    assert data["source"] == "organization" and data["locality"] == "external"
    assert data["updated_by"] == str(two_orgs.a.user.id)

    again = await client.get("/ai/settings", headers=_auth(two_orgs.a.token))
    assert _KEY not in again.text and again.json()["data"]["has_api_key"] is True

    row = await session.scalar(
        select(AiProviderSettings).where(
            AiProviderSettings.organization_id == two_orgs.a.organization.id
        )
    )
    assert row is not None and _KEY not in (row.api_key_ciphertext or "")


async def test_settings_are_isolated_between_organizations(client: AsyncClient, two_orgs: TwoOrgs):
    await client.put(
        "/ai/settings", headers=_auth(two_orgs.a.token), json={"preset": "openai", "api_key": _KEY}
    )
    other = await client.get("/ai/settings", headers=_auth(two_orgs.b.token))
    assert other.status_code == 200
    assert other.json()["data"]["source"] == "default"
    assert other.json()["data"]["has_api_key"] is False


async def test_manager_reads_but_cannot_write_nor_test(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, provider
):
    _manager, token = await make_member(session, two_orgs.a.organization, MemberRole.manager)
    assert (await client.get("/ai/settings", headers=_auth(token))).status_code == 200
    assert (await client.get("/ai/presets", headers=_auth(token))).status_code == 200
    put = await client.put("/ai/settings", headers=_auth(token), json={"preset": "ollama_local"})
    assert put.status_code == 403
    assert (await client.post("/ai/settings/test", headers=_auth(token))).status_code == 403


@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.viewer])
async def test_member_and_viewer_get_403(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, role
):
    _user, token = await make_member(session, two_orgs.a.organization, role)
    assert (await client.get("/ai/settings", headers=_auth(token))).status_code == 403
    assert (await client.get("/ai/presets", headers=_auth(token))).status_code == 403


async def test_ssrf_url_is_rejected_with_a_clear_code(
    client: AsyncClient, two_orgs: TwoOrgs, provider
):
    response = await client.put(
        "/ai/settings",
        headers=_auth(two_orgs.a.token),
        json={"preset": "custom", "base_url": "https://10.0.0.8/v1", "chat_model": "m"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "llm_base_url_rejected"
    assert "10.0.0.8" not in response.text


async def test_invalid_body_is_422(client: AsyncClient, two_orgs: TwoOrgs):
    response = await client.put(
        "/ai/settings",
        headers=_auth(two_orgs.a.token),
        json={"preset": "ollama_local", "temperature": 9},
    )
    assert response.status_code == 422


async def test_connection_test_with_saved_config(client: AsyncClient, two_orgs: TwoOrgs, provider):
    await client.put(
        "/ai/settings", headers=_auth(two_orgs.a.token), json={"preset": "openai", "api_key": _KEY}
    )
    response = await client.post("/ai/settings/test", headers=_auth(two_orgs.a.token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ok"] is True and data["chat_model"] == "gpt-5-mini"
    assert data["embedding_dimensions"] == 2
    assert _KEY not in response.text
    assert provider[0].headers["Authorization"] == f"Bearer {_KEY}"


async def test_connection_test_with_a_proposal(client: AsyncClient, two_orgs: TwoOrgs, provider):
    response = await client.post(
        "/ai/settings/test",
        headers=_auth(two_orgs.a.token),
        json={"preset": "custom", "base_url": "https://llm.example.com/v1", "chat_model": "m"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["ok"] is True
    assert str(provider[0].url).startswith("https://llm.example.com/v1/")
    stored = await client.get("/ai/settings", headers=_auth(two_orgs.a.token))
    assert stored.json()["data"]["source"] == "default"
