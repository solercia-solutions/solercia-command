"""`GET /assistant/health` (change 48-puerto-llm, design.md "Endpoint de
salud"). Spec `assistant-health` R1-R4: RBAC (`admin`/`manager` only),
configuration envelope, opt-in `?probe=true` reachability and secret
redaction. `LlmPort` configuration is global per process (design.md
"Aislamiento por organización") — every test monkeypatches the shared
``app.config.settings`` singleton, same pattern as
``tests/test_ai_registry.py``.
"""

import sys
from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.assistant.service as assistant_service
from app.ai.adapters.fake import get_fake_adapter
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
from app.config import settings
from app.shared.enums import MemberRole
from tests.conftest import skip_no_db


@pytest.fixture(autouse=True, scope="module")
def _isolate_anthropic_import() -> Iterator[None]:
    """`LLM_PROVIDER="anthropic"` makes `registry._build_anthropic()` lazy
    `importlib.import_module` the real adapter module; without this
    teardown it stays in `sys.modules` for the rest of the pytest session
    and breaks `test_ai_registry.py`'s isolation scenario (same fixture as
    `test_ai_adapter_anthropic.py`, tasks.md 3.13)."""

    yield
    for name in [key for key in sys.modules if key == "anthropic" or key.startswith("anthropic.")]:
        del sys.modules[name]
    sys.modules.pop("app.ai.adapters.anthropic", None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _install_openai_probe(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Injects a `MockTransport`-backed `openai_compatible` adapter as the
    port `describe()` resolves for `probe=True` — the module-level
    attribute, so it takes effect (design.md "Inyección para pruebas")."""

    def _factory() -> OpenAiCompatibleAdapter:
        return OpenAiCompatibleAdapter(settings=settings, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(assistant_service, "get_llm_port", _factory)


# Isolated service tests below use no session/client/tenant fixtures.
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("stage", ["construction", "probe"])
async def test_isolated_authorization_denial_is_not_probed(stage):
    from app.ai.errors import LlmAuthorizationRequired

    class DeniedPort:
        async def probe(self):
            raise LlmAuthorizationRequired()

    def factory():
        if stage == "construction":
            raise LlmAuthorizationRequired()
        return DeniedPort()

    data = await assistant_service.AssistantHealthService(port_factory=factory).describe(probe=True)
    assert data.reachability == "not_probed"
    assert data.reachability_reason == LlmAuthorizationRequired().detail


@pytest.mark.asyncio(loop_scope="session")
async def test_isolated_passive_health_never_builds_provider():
    from unittest.mock import Mock

    factory = Mock(side_effect=AssertionError("passive inspection must not build a provider"))
    data = await assistant_service.AssistantHealthService(port_factory=factory).describe(probe=False)
    assert data.reachability == "not_probed"
    assert data.reachability_reason is None
    factory.assert_not_called()


@pytest.mark.asyncio(loop_scope="session")
async def test_isolated_real_probe_denied_without_http(monkeypatch, caplog):
    from app.ai.errors import LlmAuthorizationRequired

    base_url = "https://user:synthetic-password@approved.invalid/synthetic-path"
    monkeypatch.setattr(settings, "LLM_BASE_URL", base_url)
    monkeypatch.setattr(settings, "LLM_BASE_URL_ALLOWLIST", [base_url])
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_API_KEY", "synthetic-key")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text="synthetic-provider-secret")

    _install_openai_probe(monkeypatch, handler)
    data = await assistant_service.AssistantHealthService().describe(probe=True)
    assert data.reachability == "not_probed"
    assert data.reachability_reason == LlmAuthorizationRequired().detail
    assert calls == []
    assert "synthetic-" not in data.model_dump_json() + caplog.text


@pytest.mark.asyncio(loop_scope="session")
async def test_isolated_fake_probe_and_config_validation_unchanged():
    from app.ai.errors import LlmConfigInvalid

    fake = get_fake_adapter()
    before = len(fake.calls)
    data = await assistant_service.AssistantHealthService(port_factory=lambda: fake).describe(
        probe=True
    )
    assert data.reachability == "ok"
    assert len(fake.calls) == before

    def invalid_factory():
        raise LlmConfigInvalid()

    data = await assistant_service.AssistantHealthService(
        port_factory=invalid_factory
    ).describe(probe=True)
    assert data.reachability == "unreachable"
    assert data.reachability_reason == LlmConfigInvalid().detail


# ---------------------------------------------------------------------------
# assistant-health R1 — RBAC
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize("role", [MemberRole.admin, MemberRole.manager])
async def test_admin_and_manager_get_200(
    client: AsyncClient, session: AsyncSession, tenant, make_member, role: MemberRole
) -> None:
    _, token = await make_member(session, tenant, role)
    response = await client.get("/assistant/health", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert body["message"] == "Estado del proveedor de IA."


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize("role", [MemberRole.member, MemberRole.viewer])
async def test_member_and_viewer_get_403(
    client: AsyncClient, session: AsyncSession, tenant, make_member, role: MemberRole
) -> None:
    _, token = await make_member(session, tenant, role)
    response = await client.get("/assistant/health", headers=_auth(token))
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    assert "data" not in body


# ---------------------------------------------------------------------------
# assistant-health R2 — sobre de respuesta y campos de configuración
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_default_response_is_not_probed(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-secreta")

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", headers=_auth(token))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["base_url_host"] == "localhost:11434"
    assert isinstance(data["api_key_configured"], bool)
    assert data["api_key_configured"] is True
    assert data["reachability"] == "not_probed"


# ---------------------------------------------------------------------------
# Frontera de secretos — ningún secreto ni URL completa
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
@pytest.mark.parametrize("probe", ["false", "true"])
async def test_body_never_contains_the_api_key_or_the_full_base_url(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
    probe: str,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-secreta")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen-test")
    if probe == "true":
        _install_openai_probe(
            monkeypatch, lambda request: httpx.Response(200, json={"data": [{"id": "qwen-test"}]})
        )

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": probe}, headers=_auth(token))

    assert response.status_code == 200
    assert "sk-secreta" not in response.text
    assert "/v1" not in response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_base_url_userinfo_is_never_echoed(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://usuario:secreto@localhost:11434/v1")

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["base_url_host"] == "localhost:11434"
    assert "secreto" not in response.text
    assert "usuario" not in response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_base_url_host_without_port_has_no_none_suffix(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.anthropic.com")

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["base_url_host"] == "api.anthropic.com"
    assert "api.anthropic.com:None" not in response.text


# ---------------------------------------------------------------------------
# assistant-health R3 — sonda opt-in sin gasto de tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_probe_true_reports_authorization_not_probed(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen-test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": [{"id": "qwen-test"}]})

    _install_openai_probe(monkeypatch, handler)

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": "true"}, headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["reachability"] == "not_probed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_probe_true_denies_before_connection_with_a_readable_reason(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "qwen-test")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    _install_openai_probe(monkeypatch, handler)

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": "true"}, headers=_auth(token))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachability"] == "not_probed"
    assert isinstance(data["reachability_reason"], str)
    assert data["reachability_reason"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_probe_true_anthropic_never_probes(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.adapters import anthropic as anthropic_adapter_module

    def _guard(self: object) -> None:
        raise AssertionError("probe() must never build a network client for anthropic")

    monkeypatch.setattr(anthropic_adapter_module.AnthropicAdapter, "_build_client", _guard)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-ant-test")

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": "true"}, headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["reachability"] == "not_probed"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_probe_true_fake_reports_ok_and_never_generates_text(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    fake_adapter = get_fake_adapter()
    calls_before = len(fake_adapter.calls)

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": "true"}, headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["data"]["reachability"] == "ok"
    # The probe generates ZERO text (design.md D4): `.calls` only grows on
    # `complete()`, never on `probe()`.
    assert len(fake_adapter.calls) == calls_before


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_invalid_configuration_is_a_reason_not_a_500(
    client: AsyncClient,
    session: AsyncSession,
    tenant,
    make_member,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`openai_compatible` with an empty `LLM_MODEL` fails the adapter's
    constructor (`LlmConfigInvalid`) BEFORE any request — the endpoint
    still answers 200 with a readable reason, never a 500."""

    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai_compatible")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "")

    _, token = await make_member(session, tenant, MemberRole.admin)
    response = await client.get("/assistant/health", params={"probe": "true"}, headers=_auth(token))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["reachability"] == "unreachable"
    assert isinstance(data["reachability_reason"], str)
    assert data["reachability_reason"]
