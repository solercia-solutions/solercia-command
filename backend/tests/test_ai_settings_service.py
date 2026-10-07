"""C04: `AiSettingsService` with an in-memory repository — no database, no
network. Covers precedence (organization row > global `LLM_*` > local
preset), Fernet at rest, key keep/clear semantics, and the connection test.
"""

import json
import uuid

import httpx
import pytest

from app.ai import errors
from app.ai.adapters.fake import FakeLlmAdapter
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
from app.config import Settings
from app.integrations import crypto
from app.modules.ai_settings.models import AiProviderSettings
from app.modules.ai_settings.schemas import AiSettingsUpdate
from app.modules.ai_settings.service import (
    AiSettingsError,
    AiSettingsService,
    build_llm_port,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

_KEY = "sk-live-synthetic-1234-ABCD"
_PUBLIC = {"llm.example.com": ["93.184.216.34"]}


def _resolver(host: str) -> list[str]:
    if host not in _PUBLIC:
        raise OSError("unknown")
    return _PUBLIC[host]


class FakeRepository:
    """Tenant-scoped store: one row per organization, like the UNIQUE."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, AiProviderSettings] = {}

    async def find_for_organization(self, organization_id):
        return self.rows.get(organization_id)

    async def add(self, row):
        if row.organization_id in self.rows:
            raise AssertionError("duplicate organization row")
        self.rows[row.organization_id] = row


class Commit:
    def __init__(self) -> None:
        self.count = 0

    async def __call__(self) -> None:
        self.count += 1


def _global(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _service(repo=None, *, global_settings=None, commit=None):
    return AiSettingsService(
        repo or FakeRepository(),
        commit=commit or Commit(),
        global_settings=global_settings or _global(),
        resolver=_resolver,
    )


def _update(**values) -> AiSettingsUpdate:
    return AiSettingsUpdate.model_validate(values)


# --- precedence ---------------------------------------------------------------


async def test_without_row_nor_global_the_default_is_local_ollama():
    resolved = await _service().resolve(uuid.uuid4())
    assert resolved.source == "default"
    assert resolved.enabled is True
    assert resolved.config.base_url == "http://127.0.0.1:11434/v1"
    assert resolved.config.chat_model == "qwen3.5:9b-q4_K_M"
    assert resolved.config.embedding_model == "qwen3-embedding:0.6b"
    assert resolved.config.reasoning_effort == "none"
    assert resolved.config.api_key == ""


async def test_global_openai_compatible_env_wins_over_the_default_preset():
    global_settings = _global(
        LLM_PROVIDER="openai_compatible",
        LLM_BASE_URL="http://localhost:11434/v1",
        LLM_MODEL="global-model",
        LLM_API_KEY="global-key",
    )
    resolved = await _service(global_settings=global_settings).resolve(uuid.uuid4())
    assert resolved.source == "global"
    assert resolved.config.chat_model == "global-model"
    assert resolved.config.api_key == "global-key"


async def test_organization_row_wins_over_global_env():
    repo = FakeRepository()
    org = uuid.uuid4()
    global_settings = _global(
        LLM_PROVIDER="openai_compatible",
        LLM_BASE_URL="http://localhost:11434/v1",
        LLM_MODEL="global-model",
    )
    service = _service(repo, global_settings=global_settings)
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    resolved = await service.resolve(org)
    assert resolved.source == "organization"
    assert resolved.config.base_url == "https://api.openai.com/v1"
    assert resolved.config.api_key == _KEY
    assert resolved.config.provider_label == "openai"


async def test_settings_of_one_organization_never_leak_to_another():
    repo = FakeRepository()
    service = _service(repo)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await service.update_settings(org_a, None, _update(preset="openai", api_key=_KEY))
    assert (await service.resolve(org_b)).source == "default"
    assert (await service.get_settings(org_b)).has_api_key is False


async def test_disabled_organization_stops_without_falling_back():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="ollama_local", enabled=False))
    resolved = await service.resolve(org)
    assert resolved.enabled is False and resolved.source == "organization"
    with pytest.raises(errors.LlmProviderDisabled):
        build_llm_port(resolved, org)


async def test_build_llm_port_carries_a_trusted_dispatch_context():
    org = uuid.uuid4()
    resolved = await _service().resolve(org)
    port = build_llm_port(resolved, org)
    assert isinstance(port, OpenAiCompatibleAdapter)
    assert port.dispatch_context.organization_id == org
    assert port.dispatch_context.source == "default_preset"


async def test_global_fake_provider_counts_as_not_configured():
    resolved = await _service(global_settings=_global(LLM_PROVIDER="fake")).resolve(uuid.uuid4())
    assert resolved.source == "default"


async def test_global_anthropic_is_delegated_to_the_process_registry(monkeypatch):
    fake = FakeLlmAdapter()
    from app.modules.ai_settings import service as module

    monkeypatch.setattr(module, "get_llm_port", lambda settings=None: fake)
    resolved = await _service(global_settings=_global(LLM_PROVIDER="anthropic")).resolve(
        uuid.uuid4()
    )
    assert resolved.source == "global" and resolved.config is None
    assert build_llm_port(resolved, uuid.uuid4()) is fake


# --- persistence semantics ---------------------------------------------------------


async def test_api_key_is_encrypted_at_rest_and_only_last4_is_exposed():
    repo = FakeRepository()
    commit = Commit()
    service = _service(repo, commit=commit)
    org, actor = uuid.uuid4(), uuid.uuid4()
    view = await service.update_settings(org, actor, _update(preset="openai", api_key=_KEY))
    row = repo.rows[org]
    assert row.api_key_ciphertext and _KEY not in row.api_key_ciphertext
    assert crypto.decrypt(row.api_key_ciphertext) == _KEY
    assert row.api_key_last4 == "ABCD"
    assert row.updated_by == actor and row.created_by == actor
    assert commit.count == 1
    dumped = view.model_dump_json()
    assert _KEY not in dumped and "ciphertext" not in dumped
    assert view.has_api_key is True and view.api_key_last4 == "ABCD"
    assert view.locality == "external" and view.source == "organization"


async def test_empty_or_omitted_key_keeps_it_and_null_clears_it():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    await service.update_settings(org, None, _update(preset="openai", chat_model="gpt-x"))
    assert crypto.decrypt(repo.rows[org].api_key_ciphertext) == _KEY
    await service.update_settings(org, None, _update(preset="openai", api_key="  "))
    assert crypto.decrypt(repo.rows[org].api_key_ciphertext) == _KEY
    view = await service.update_settings(org, None, _update(preset="ollama_local", api_key=None))
    assert repo.rows[org].api_key_ciphertext is None and repo.rows[org].api_key_last4 is None
    assert view.has_api_key is False


async def test_a_kept_key_is_never_carried_to_a_different_destination():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    view = await service.update_settings(org, None, _update(preset="ollama_local"))
    assert view.has_api_key is False
    assert repo.rows[org].api_key_ciphertext is None


async def test_external_preset_without_key_is_rejected():
    with pytest.raises(AiSettingsError) as caught:
        await _service().update_settings(uuid.uuid4(), None, _update(preset="groq"))
    assert caught.value.code == "AI_API_KEY_REQUIRED"
    assert caught.value.status_code == 422


async def test_ssrf_custom_url_is_rejected_before_persisting():
    repo = FakeRepository()
    with pytest.raises(errors.LlmBaseUrlRejected):
        await _service(repo).update_settings(
            uuid.uuid4(),
            None,
            _update(preset="custom", base_url="https://169.254.169.254/v1", chat_model="m"),
        )
    assert repo.rows == {}


async def test_custom_requires_a_chat_model():
    with pytest.raises(AiSettingsError) as caught:
        await _service().update_settings(
            uuid.uuid4(), None, _update(preset="custom", base_url="https://llm.example.com/v1")
        )
    assert caught.value.code == "AI_CHAT_MODEL_REQUIRED"


async def test_unknown_preset_is_rejected():
    with pytest.raises(errors.LlmPresetUnknown):
        await _service().update_settings(uuid.uuid4(), None, _update(preset="nope"))


async def test_preset_defaults_fill_models_and_num_ctx_travels_as_ollama_option():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    view = await service.update_settings(org, None, _update(preset="ollama_local", num_ctx=8192))
    assert view.chat_model == "qwen3.5:9b-q4_K_M"
    assert view.num_ctx == 8192
    resolved = await service.resolve(org)
    assert resolved.config.extra_body == {"options": {"num_ctx": 8192}}


async def test_get_settings_reports_the_effective_default_without_a_row():
    view = await _service().get_settings(uuid.uuid4())
    assert view.source == "default" and view.preset == "ollama_local"
    assert view.locality == "local" and view.has_api_key is False


async def test_get_settings_for_global_source_hides_userinfo_and_key():
    global_settings = _global(
        LLM_PROVIDER="openai_compatible",
        LLM_BASE_URL="http://localhost:11434/v1",
        LLM_MODEL="global-model",
        LLM_API_KEY="global-secret-key",
    )
    view = await _service(global_settings=global_settings).get_settings(uuid.uuid4())
    assert view.source == "global" and view.preset == "global"
    assert view.has_api_key is True and view.api_key_last4 is None
    assert "global-secret-key" not in view.model_dump_json()


# --- connection test -----------------------------------------------------------


def _provider(chat_status=200, embed_status=200):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/chat/completions"):
            if chat_status != 200:
                return httpx.Response(chat_status, text=f"bad {_KEY}")
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )
        if embed_status != 200:
            return httpx.Response(embed_status, text="bad")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]})

    return calls, httpx.MockTransport(handler)


async def test_connection_test_with_saved_config_reports_latency_and_models():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    calls, transport = _provider()
    result = await service.test_connection(org, None, transport=transport)
    assert result.ok is True and result.error is None
    assert result.chat_model == "gpt-5-mini" and result.chat_latency_ms >= 0
    assert result.embedding_dimensions == 3
    assert [c.url.path for c in calls] == ["/v1/chat/completions", "/v1/embeddings"]
    assert calls[0].headers["Authorization"] == f"Bearer {_KEY}"
    assert _KEY not in result.model_dump_json()


async def test_connection_test_with_a_proposal_does_not_persist_and_reuses_key_same_host():
    repo = FakeRepository()
    commit = Commit()
    service = _service(repo, commit=commit)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    calls, transport = _provider()
    result = await service.test_connection(
        org, _update(preset="openai", chat_model="gpt-other"), transport=transport
    )
    assert result.ok is True and result.chat_model == "gpt-other"
    assert calls[0].headers["Authorization"] == f"Bearer {_KEY}"
    assert json.loads(calls[0].content)["model"] == "gpt-other"
    assert repo.rows[org].chat_model == "gpt-5-mini" and commit.count == 1


async def test_connection_test_never_sends_a_stored_key_to_another_host():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="openai", api_key=_KEY))
    calls, transport = _provider()
    await service.test_connection(
        org,
        _update(preset="custom", base_url="https://llm.example.com/v1", chat_model="m"),
        transport=transport,
    )
    assert "Authorization" not in calls[0].headers


async def test_connection_test_reports_a_clear_code_on_provider_failure():
    service = _service()
    _calls, transport = _provider(chat_status=401)
    result = await service.test_connection(uuid.uuid4(), None, transport=transport)
    assert result.ok is False
    assert result.error.stage == "chat" and result.error.code == "llm_auth_error"
    assert _KEY not in result.model_dump_json()


async def test_connection_test_flags_embedding_failure_separately():
    _calls, transport = _provider(embed_status=404)
    result = await _service().test_connection(uuid.uuid4(), None, transport=transport)
    assert result.ok is False and result.chat_latency_ms is not None
    assert result.error.stage == "embeddings" and result.error.code == "llm_config_invalid"


async def test_connection_test_skips_embeddings_when_no_model():
    repo = FakeRepository()
    service = _service(repo)
    org = uuid.uuid4()
    await service.update_settings(org, None, _update(preset="deepseek", api_key=_KEY))
    calls, transport = _provider()
    result = await service.test_connection(org, None, transport=transport)
    assert result.ok is True and result.embedding_model is None
    assert result.embedding_dimensions is None and len(calls) == 1
