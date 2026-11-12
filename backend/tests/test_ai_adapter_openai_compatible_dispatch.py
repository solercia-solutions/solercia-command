"""C04: the OpenAI-compatible adapter dispatches ONLY with a trusted
organization dispatch context (built by `get_llm_port_for_org`). Without it
the deny-all barrier of `cf0beff` still applies. Fake transport, no network.
"""

import json
import logging
import uuid

import httpx
import pytest
from pydantic import BaseModel

from app.ai import errors
from app.ai.adapters.fake import get_fake_adapter
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter, OpenAiCompatibleConfig
from app.ai.ports import LlmDispatchContext, LlmMessage, LlmRequest
from app.config import Settings

_async = pytest.mark.asyncio(loop_scope="session")

_KEY = "sk-synthetic-key-0000-WXYZ"
_BASE = "https://api.openai.com/v1"


class _Decision(BaseModel):
    category: str
    urgent: bool


def _config(**overrides) -> OpenAiCompatibleConfig:
    values = dict(
        base_url=_BASE,
        chat_model="chat-model",
        embedding_model="embed-model",
        api_key=_KEY,
        timeout_seconds=5.0,
        max_tokens=256,
        temperature=0.0,
        reasoning_effort="none",
        json_mode="json_schema_openai",
        max_retries=1,
        provider_label="openai",
    )
    values.update(overrides)
    return OpenAiCompatibleConfig(**values)


def _context() -> LlmDispatchContext:
    return LlmDispatchContext(organization_id=uuid.uuid4(), source="organization_settings")


def _request(**overrides) -> LlmRequest:
    values = dict(
        system="Clasifica.",
        messages=(LlmMessage(role="user", content="Correo de prueba"),),
    )
    values.update(overrides)
    return LlmRequest(**values)


def _chat_ok(content: str = "hola") -> dict:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }


class _Recorder:
    def __init__(self, responder):
        self.requests: list[httpx.Request] = []
        self._responder = responder

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._responder(request)


def _adapter(recorder, **config_overrides) -> OpenAiCompatibleAdapter:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return OpenAiCompatibleAdapter(
        config=_config(**config_overrides),
        dispatch_context=_context(),
        transport=httpx.MockTransport(recorder),
        sleep=_no_sleep,
    )


@_async
async def test_without_dispatch_context_the_barrier_still_denies():
    recorder = _Recorder(lambda r: httpx.Response(200, json=_chat_ok()))
    adapter = OpenAiCompatibleAdapter(config=_config(), transport=httpx.MockTransport(recorder))
    for call in (adapter.complete(_request()), adapter.probe(), adapter.embed(["x"])):
        with pytest.raises(errors.LlmAuthorizationRequired):
            await call
    assert recorder.requests == []


@_async
async def test_chat_dispatch_sends_model_reasoning_and_bearer_key():
    recorder = _Recorder(lambda r: httpx.Response(200, json=_chat_ok("listo")))
    response = await _adapter(recorder).complete(_request())
    assert response.text == "listo"
    assert response.provider == "openai"
    assert response.model == "chat-model"
    assert response.usage.total_tokens == 5
    sent = recorder.requests[0]
    assert sent.url.path == "/v1/chat/completions"
    assert sent.headers["Authorization"] == f"Bearer {_KEY}"
    body = json.loads(sent.content)
    assert body["model"] == "chat-model"
    assert body["reasoning_effort"] == "none"
    assert body["max_tokens"] == 256
    assert body["temperature"] == 0.0


@_async
async def test_request_overrides_win_over_config_defaults():
    recorder = _Recorder(lambda r: httpx.Response(200, json=_chat_ok()))
    await _adapter(recorder, temperature=0.7).complete(_request(max_tokens=32))
    body = json.loads(recorder.requests[0].content)
    assert body["max_tokens"] == 32
    assert body["temperature"] == 0.7
    await _adapter(recorder, temperature=0.7).complete(_request(temperature=0.1))
    assert json.loads(recorder.requests[1].content)["temperature"] == 0.1


@_async
async def test_reasoning_effort_is_omitted_when_not_configured():
    recorder = _Recorder(lambda r: httpx.Response(200, json=_chat_ok()))
    await _adapter(recorder, reasoning_effort=None).complete(_request())
    assert "reasoning_effort" not in json.loads(recorder.requests[0].content)


@_async
async def test_no_authorization_header_without_key_and_extra_body_is_merged():
    recorder = _Recorder(lambda r: httpx.Response(200, json=_chat_ok()))
    await _adapter(recorder, api_key="", extra_body={"options": {"num_ctx": 8192}}).complete(
        _request()
    )
    sent = recorder.requests[0]
    assert "Authorization" not in sent.headers
    assert json.loads(sent.content)["options"] == {"num_ctx": 8192}


@_async
async def test_json_schema_response_format_and_parsed_output():
    recorder = _Recorder(
        lambda r: httpx.Response(200, json=_chat_ok('{"category": "queja", "urgent": true}'))
    )
    response = await _adapter(recorder).complete(_request(output_schema=_Decision))
    assert isinstance(response.parsed, _Decision) and response.parsed.urgent is True
    envelope = json.loads(recorder.requests[0].content)["response_format"]
    assert envelope["type"] == "json_schema"
    assert envelope["json_schema"]["strict"] is True


@_async
async def test_embeddings_are_returned_in_input_order():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "model": "embed-model",
            },
        )

    recorder = _Recorder(respond)
    vectors = await _adapter(recorder).embed(["uno", "dos"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    sent = recorder.requests[0]
    assert sent.url.path == "/v1/embeddings"
    assert json.loads(sent.content) == {"model": "embed-model", "input": ["uno", "dos"]}


@_async
async def test_embed_of_nothing_makes_no_request():
    recorder = _Recorder(lambda r: httpx.Response(500))
    assert await _adapter(recorder).embed([]) == []
    assert recorder.requests == []


@_async
async def test_embed_without_embedding_model_is_a_clear_error():
    recorder = _Recorder(lambda r: httpx.Response(200))
    with pytest.raises(errors.LlmEmbeddingsUnavailable) as caught:
        await _adapter(recorder, embedding_model=None).embed(["x"])
    assert caught.value.code == "llm_embeddings_unavailable"
    assert recorder.requests == []


@_async
@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [0.1]}]},
        {"data": [{"index": 0, "embedding": "nope"}, {"index": 1, "embedding": [1]}]},
        {"nothing": True},
    ],
)
async def test_malformed_embeddings_raise_invalid_output(payload):
    recorder = _Recorder(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(errors.LlmInvalidOutput):
        await _adapter(recorder).embed(["a", "b"])


@_async
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, errors.LlmAuthError),
        (403, errors.LlmAuthError),
        (404, errors.LlmConfigInvalid),
        (429, errors.LlmRateLimited),
        (503, errors.LlmUnavailable),
    ],
)
async def test_http_errors_map_to_the_taxonomy_and_never_log_key_or_body(status, error, caplog):
    caplog.set_level(logging.DEBUG)
    recorder = _Recorder(
        lambda r: httpx.Response(status, text=f"provider echoed {_KEY} and secret-body")
    )
    with pytest.raises(error) as caught:
        await _adapter(recorder).complete(_request())
    diagnostic = f"{caught.value!r} {caught.value.detail} {caplog.text}"
    assert _KEY not in diagnostic
    assert "secret-body" not in diagnostic


@_async
async def test_timeout_and_connection_errors():
    def boom(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(errors.LlmUnavailable):
        await _adapter(_Recorder(boom)).embed(["x"])

    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(errors.LlmTimeout):
        await _adapter(_Recorder(slow)).complete(_request())


@_async
async def test_probe_with_context_lists_models():
    recorder = _Recorder(lambda r: httpx.Response(200, json={"data": [{"id": "chat-model"}]}))
    probe = await _adapter(recorder).probe()
    assert probe.reachability == "ok" and probe.reason is None
    assert recorder.requests[0].url.path == "/v1/models"


def test_config_repr_never_shows_the_key():
    assert _KEY not in repr(_config())


def test_global_settings_allowlist_now_admits_preset_urls():
    settings = Settings(
        _env_file=None,
        LLM_BASE_URL="https://api.groq.com/openai/v1",
        LLM_BASE_URL_ALLOWLIST=[],
        LLM_MODEL="m",
    )
    OpenAiCompatibleAdapter(settings=settings)  # no LlmConfigInvalid


def test_global_settings_still_reject_unknown_urls():
    settings = Settings(
        _env_file=None,
        LLM_BASE_URL="https://unknown.example/v1",
        LLM_BASE_URL_ALLOWLIST=[],
        LLM_MODEL="m",
    )
    with pytest.raises(errors.LlmConfigInvalid):
        OpenAiCompatibleAdapter(settings=settings)


@_async
async def test_fake_adapter_embeds_deterministically():
    fake = get_fake_adapter()
    fake.embed_calls.clear()
    first = await fake.embed(["hola", "chao"])
    second = await fake.embed(["hola"])
    assert len(first) == 2 and first[0] == second[0]
    assert all(isinstance(value, float) for value in first[0])
    assert fake.embed_calls == [("hola", "chao"), ("hola",)]
