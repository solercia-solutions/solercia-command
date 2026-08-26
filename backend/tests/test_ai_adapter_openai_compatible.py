"""`OpenAiCompatibleAdapter` (design.md "Adaptador openai_compatible").
`httpx.MockTransport` + injected `sleep` — no real network, no real
waiting. Requirement `llm-port` R4 (adapter), R6 (allowlist), R7 (secrets)."""

import json
import logging
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
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

_BASE_URL = "http://localhost:11434/v1"
_MODEL = "qwen-test"


class _Decision(BaseModel):
    """Flat model used only here to exercise `output_schema` wiring."""

    category: str
    urgent: bool


class _SleepSpy:
    """Injected `sleep` that records requested seconds instead of waiting."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "LLM_BASE_URL": _BASE_URL,
        "LLM_MODEL": _MODEL,
        "LLM_BASE_URL_ALLOWLIST": [_BASE_URL],
        "LLM_MAX_RETRIES": 2,
        "LLM_MAX_BACKOFF_SECONDS": 5.0,
    }
    values.update(overrides)
    return Settings(**values)


async def _no_wait(_seconds: float) -> None:
    return None


def _adapter(handler: Any, *, sleep: Any = _no_wait, **settings_overrides: Any) -> Any:
    return OpenAiCompatibleAdapter(
        settings=_settings(**settings_overrides),
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )


def _request(**overrides: Any) -> LlmRequest:
    defaults: dict[str, Any] = {
        "system": "Eres un asistente de triage de correo.",
        "messages": (LlmMessage(role="user", content="Clasifica este correo."),),
        "max_tokens": 200,
    }
    defaults.update(overrides)
    return LlmRequest(**defaults)  # type: ignore[arg-type]


def _completion_payload(content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_rejects_a_base_url_outside_the_allowlist_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the transport must never be called")

    with pytest.raises(LlmConfigInvalid):
        _adapter(handler, LLM_BASE_URL="http://evil.example.com/v1")


@pytest.mark.asyncio(loop_scope="session")
async def test_base_url_within_the_allowlist_reaches_the_injected_transport() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_completion_payload("respuesta ok"))

    response = await _adapter(handler).complete(_request())
    assert len(calls) == 1
    assert response.finish_reason == "stop"


def test_rejects_an_empty_model_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the transport must never be called")

    with pytest.raises(LlmConfigInvalid):
        _adapter(handler, LLM_MODEL="")


@pytest.mark.asyncio(loop_scope="session")
async def test_system_travels_as_the_first_message_and_stream_is_false() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_completion_payload("respuesta ok"))

    await _adapter(handler).complete(_request())

    body = captured["body"]
    assert body["messages"][0] == {
        "role": "system",
        "content": "Eres un asistente de triage de correo.",
    }
    assert body["stream"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_json_mode_openai_sends_the_nested_envelope() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_completion_payload('{"category": "queja", "urgent": true}')
        )

    adapter = _adapter(handler, LLM_JSON_MODE="json_schema_openai")
    await adapter.complete(_request(output_schema=_Decision))

    envelope = captured["body"]["response_format"]
    assert envelope["type"] == "json_schema"
    assert envelope["json_schema"]["strict"] is True
    schema = envelope["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"category", "urgent"}


@pytest.mark.asyncio(loop_scope="session")
async def test_json_mode_llamacpp_sends_the_schema_at_top_level() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_completion_payload('{"category": "queja", "urgent": true}')
        )

    adapter = _adapter(handler, LLM_JSON_MODE="json_schema_llamacpp")
    await adapter.complete(_request(output_schema=_Decision))

    response_format = captured["body"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert "json_schema" not in response_format
    assert response_format["schema"]["additionalProperties"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_json_mode_json_object_sends_the_schema_as_a_prompt_hint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_completion_payload('{"category": "queja", "urgent": true}')
        )

    adapter = _adapter(handler, LLM_JSON_MODE="json_object")
    await adapter.complete(_request(output_schema=_Decision))

    body = captured["body"]
    assert body["response_format"] == {"type": "json_object"}
    system_content = body["messages"][0]["content"]
    assert "json" in system_content.lower()
    assert "category" in system_content


@pytest.mark.asyncio(loop_scope="session")
async def test_parses_a_fenced_json_body() -> None:
    fenced = '```json\n{"category": "queja", "urgent": true}\n```'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_payload(fenced))

    response = await _adapter(handler).complete(_request(output_schema=_Decision))
    assert isinstance(response.parsed, _Decision)
    assert response.parsed.category == "queja"


@pytest.mark.asyncio(loop_scope="session")
async def test_429_retries_then_raises_rate_limited() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "limited"})

    spy = _SleepSpy()
    with pytest.raises(LlmRateLimited):
        await _adapter(handler, sleep=spy, LLM_MAX_RETRIES=2).complete(_request())

    assert attempts["count"] == 3
    assert len(spy.calls) == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_clamps_retry_after_to_max_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999"}, json={"error": "limited"})

    spy = _SleepSpy()
    with pytest.raises(LlmRateLimited):
        await _adapter(handler, sleep=spy, LLM_MAX_RETRIES=1, LLM_MAX_BACKOFF_SECONDS=5.0).complete(
            _request()
        )

    assert spy.calls == [5.0]


@pytest.mark.asyncio(loop_scope="session")
async def test_maps_500_401_404_timeout_connect_error() -> None:
    def _status_handler(status: int) -> Any:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": "boom"})

        return handler

    with pytest.raises(LlmUnavailable):
        await _adapter(_status_handler(500), LLM_MAX_RETRIES=0).complete(_request())

    with pytest.raises(LlmAuthError):
        await _adapter(_status_handler(401)).complete(_request())

    with pytest.raises(LlmConfigInvalid):
        await _adapter(_status_handler(404)).complete(_request())

    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LlmTimeout):
        await _adapter(_timeout).complete(_request())

    def _connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LlmUnavailable):
        await _adapter(_connect_error).complete(_request())


@pytest.mark.asyncio(loop_scope="session")
async def test_finish_reason_length_maps_to_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_completion_payload('{"category": "queja"', finish_reason="length")
        )

    with pytest.raises(LlmInvalidOutput):
        await _adapter(handler).complete(_request(output_schema=_Decision))


@pytest.mark.asyncio(loop_scope="session")
async def test_max_tokens_without_schema_returns_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_completion_payload("texto truncado", finish_reason="length")
        )

    response = await _adapter(handler).complete(_request())
    assert response.finish_reason == "length"
    assert response.parsed is None


@pytest.mark.asyncio(loop_scope="session")
async def test_finish_reason_content_filter_maps_to_content_filtered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_payload("", finish_reason="content_filter"))

    with pytest.raises(LlmContentFiltered):
        await _adapter(handler).complete(_request())


@pytest.mark.asyncio(loop_scope="session")
async def test_error_log_contains_status_and_200_chars_but_never_the_key_or_the_prompt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_key = "sk-super-secreta-no-debe-aparecer-jamas"
    secret_prompt = "contenido sensible del correo del usuario"
    long_body = "x" * 300 + secret_key  # the key sits past the 200-char cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=long_body)

    adapter = _adapter(handler, LLM_API_KEY=secret_key)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(LlmAuthError):
            await adapter.complete(
                _request(messages=(LlmMessage(role="user", content=secret_prompt),))
            )

    log_text = "\n".join(record.message for record in caplog.records)
    assert "401" in log_text
    assert secret_key not in log_text
    assert secret_prompt not in log_text
    assert len(log_text) < 500


@pytest.mark.asyncio(loop_scope="session")
async def test_probe_hits_models_and_reports_ok() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"data": [{"id": _MODEL}]})

    probe = await _adapter(handler).probe()
    assert probe.reachability == "ok"
    assert len(calls) == 1
    assert calls[0].url.path.endswith("/models")


@pytest.mark.asyncio(loop_scope="session")
async def test_probe_reports_unreachable_with_reason() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    probe = await _adapter(handler).probe()
    assert probe.reachability == "unreachable"
    assert probe.reason
