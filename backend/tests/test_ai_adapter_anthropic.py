"""`AnthropicAdapter` over the official SDK, doubled at the transport level
via `httpx2.MockTransport(handler)` inside a `DefaultAsyncHttpxClient`
(design.md "Estrategia de pruebas" — no `skip`: the `anthropic==1.0.0` pin
is a requirement of this slice, verified live at gate 3.0). Requirement
`llm-port` R5.
"""

import json
import sys
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel

from app.ai.adapters.anthropic import AnthropicAdapter
from app.ai.errors import (
    LlmAuthError,
    LlmConfigInvalid,
    LlmContentFiltered,
    LlmInvalidOutput,
    LlmRateLimited,
    LlmTimeout,
    LlmUnavailable,
)
from app.ai.ports import LlmMessage, LlmRequest
from app.config import Settings

_BASE_URL = "https://api.anthropic.com"


@pytest.fixture(autouse=True, scope="module")
def _isolate_anthropic_import() -> Any:
    """`AnthropicAdapter.complete()` imports the real `anthropic` package
    lazily; without this teardown it would stay in `sys.modules` for the
    rest of the pytest session and break `test_ai_registry.py`'s isolation
    scenario (spec `llm-port` R5 "Aislamiento de dependencia")."""

    yield
    for name in [key for key in sys.modules if key == "anthropic" or key.startswith("anthropic.")]:
        del sys.modules[name]
    sys.modules.pop("app.ai.adapters.anthropic", None)


class TriageDecision(BaseModel):
    """Flat model used ONLY here to exercise `output_schema` validation —
    change 49 defines the real classification schema."""

    category: str
    urgent: bool


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "LLM_BASE_URL": _BASE_URL,
        "LLM_MODEL": "claude-opus-5",
        "LLM_API_KEY": "sk-test-key",
        "LLM_BASE_URL_ALLOWLIST": [_BASE_URL],
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _request(**overrides: Any) -> LlmRequest:
    defaults: dict[str, object] = {
        "system": "Eres un asistente de triage de correo.",
        "messages": (LlmMessage(role="user", content="Clasifica este correo."),),
        "max_tokens": 200,
    }
    defaults.update(overrides)
    return LlmRequest(**defaults)  # type: ignore[arg-type]


def _message_response(
    *,
    text: str = "hola",
    stop_reason: str = "end_turn",
    stop_details: dict[str, Any] | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
    if stop_details is not None:
        body["stop_details"] = stop_details
    return body


def _adapter(handler: Any, **settings_overrides: Any) -> AnthropicAdapter:
    return AnthropicAdapter(
        settings=_settings(**settings_overrides), transport=httpx2.MockTransport(handler)
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_system_is_top_level_and_temperature_is_never_sent() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_message_response())

    await _adapter(handler).complete(_request())

    body = captured["body"]
    assert body["system"] == "Eres un asistente de triage de correo."
    assert "temperature" not in body
    assert "top_p" not in body
    assert "top_k" not in body


@pytest.mark.asyncio(loop_scope="session")
async def test_always_sends_an_integer_max_tokens() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_message_response())

    await _adapter(handler).complete(_request(max_tokens=None))

    assert captured["body"]["max_tokens"] == Settings().LLM_MAX_TOKENS
    assert isinstance(captured["body"]["max_tokens"], int)


@pytest.mark.asyncio(loop_scope="session")
async def test_sends_adaptive_thinking_without_budget_tokens() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_message_response())

    await _adapter(handler).complete(_request())

    assert captured["body"]["thinking"] == {"type": "adaptive"}


@pytest.mark.asyncio(loop_scope="session")
async def test_schema_request_carries_required_and_additional_properties_false() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(
            200, json=_message_response(text='{"category": "queja", "urgent": true}')
        )

    await _adapter(handler).complete(_request(output_schema=TriageDecision))

    schema = captured["body"]["output_config"]["format"]["schema"]
    assert set(schema["required"]) == {"category", "urgent"}
    assert schema["additionalProperties"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_refusal_stop_reason_maps_to_content_filtered() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=_message_response(
                stop_reason="refusal",
                stop_details={"type": "refusal", "category": "policy", "explanation": "no"},
            ),
        )

    with pytest.raises(LlmContentFiltered) as excinfo:
        await _adapter(handler).complete(_request())
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_max_tokens_stop_reason_maps_to_invalid_output() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json=_message_response(stop_reason="max_tokens", text='{"category": "q')
        )

    with pytest.raises(LlmInvalidOutput) as excinfo:
        await _adapter(handler).complete(_request(output_schema=TriageDecision))
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio(loop_scope="session")
async def test_max_tokens_without_schema_returns_length() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json=_message_response(stop_reason="max_tokens", text="texto truncado")
        )

    response = await _adapter(handler).complete(_request())
    assert response.finish_reason == "length"
    assert response.parsed is None


def _status_handler(status: int) -> Any:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"type": "x", "message": "y"}})

    return handler


def _connect_error_handler(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("boom", request=request)


def _timeout_handler(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.TimeoutException("boom", request=request)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (_status_handler(401), LlmAuthError),
        (_status_handler(429), LlmRateLimited),
        (_status_handler(500), LlmUnavailable),
        (_status_handler(529), LlmUnavailable),
        (_connect_error_handler, LlmUnavailable),
        (_timeout_handler, LlmTimeout),
    ],
)
async def test_typed_exceptions_map_to_the_port_taxonomy(handler: Any, expected: type) -> None:
    with pytest.raises(expected):
        await _adapter(handler, LLM_MAX_RETRIES=0).complete(_request())


def test_empty_api_key_and_base_url_outside_allowlist_raise_config_invalid_before_any_request() -> (
    None
):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("the transport must never receive a request")

    with pytest.raises(LlmConfigInvalid):
        _adapter(handler, LLM_API_KEY="")

    with pytest.raises(LlmConfigInvalid):
        _adapter(
            handler, LLM_BASE_URL="https://evil.example.com", LLM_BASE_URL_ALLOWLIST=[_BASE_URL]
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_fallbacks_and_betas_are_never_requested() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_message_response())

    await _adapter(handler).complete(_request())

    assert "fallbacks" not in captured["body"]
    assert "betas" not in captured["body"]


@pytest.mark.asyncio(loop_scope="session")
async def test_usage_maps_input_and_output_tokens() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_message_response(input_tokens=7, output_tokens=3))

    response = await _adapter(handler).complete(_request())
    assert response.usage.input_tokens == 7
    assert response.usage.output_tokens == 3
    assert response.usage.total_tokens == 10


def test_timeout_and_max_retries_come_from_settings() -> None:
    adapter = AnthropicAdapter(
        settings=_settings(LLM_TIMEOUT_SECONDS=12.5, LLM_MAX_RETRIES=4),
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200)),
    )
    _, client = adapter._build_client()
    assert client.timeout == 12.5
    assert client.max_retries == 4
