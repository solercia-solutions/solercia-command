"""E03: Ollama native adapter (``/api/chat``) with full determinism options.

Ollama's OpenAI-compatible ``/v1`` endpoint ignores ``options`` (``top_k``,
``num_ctx``, ``num_gpu``, ``num_thread``); the native API honors them and
``think: false``. Zero network: ``httpx.MockTransport``.
"""

import json
import uuid

import httpx
import pytest
from pydantic import BaseModel

from app.ai.adapters.ollama_native import OllamaNativeAdapter, OllamaNativeConfig
from app.ai.determinism import determinism_profile
from app.ai.errors import (
    LlmAuthorizationRequired,
    LlmInvalidOutput,
    LlmSchemaMismatch,
    LlmUnavailable,
)
from app.ai.ports import LlmDispatchContext, LlmMessage, LlmRequest

pytestmark = pytest.mark.asyncio

CONTEXT = LlmDispatchContext(organization_id=uuid.uuid4(), source="offline_evaluation")


class Out(BaseModel):
    clase: str


def _request(**overrides):
    base = dict(
        system="sistema",
        messages=(LlmMessage(role="user", content="hola"),),
        output_schema=Out,
        max_tokens=200,
        prompt_version="p-v2",
    )
    base.update(overrides)
    return LlmRequest(**base)


def _adapter(handler, *, context=CONTEXT, profile="server"):
    return OllamaNativeAdapter(
        config=OllamaNativeConfig(
            base_url="http://127.0.0.1:11434/v1",
            chat_model="modelo:9b",
            embedding_model="emb:0.6b",
            determinism=determinism_profile(profile, num_thread=6),
        ),
        dispatch_context=context,
        transport=httpx.MockTransport(handler),
    )


def _chat_reply(content, *, done_reason="stop"):
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": content},
            "done_reason": done_reason,
            "prompt_eval_count": 120,
            "eval_count": 30,
        },
    )


async def test_denied_without_dispatch_context():
    adapter = _adapter(lambda r: _chat_reply("{}"), context=None)
    with pytest.raises(LlmAuthorizationRequired):
        await adapter.complete(_request())
    with pytest.raises(LlmAuthorizationRequired):
        await adapter.embed(["x"])


async def test_chat_sends_native_body_with_determinism_options():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return _chat_reply('{"clase": "avanza"}')

    response = await _adapter(handler).complete(_request())
    body = seen["body"]
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert body["model"] == "modelo:9b" and body["stream"] is False and body["think"] is False
    assert body["messages"][0] == {"role": "system", "content": "sistema"}
    assert body["format"]["properties"]["clase"]["type"] == "string"
    assert body["format"]["additionalProperties"] is False
    assert body["options"] == {
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "seed": 42,
        "num_ctx": 8192,
        "num_predict": 200,
        "num_gpu": 0,
        "num_thread": 6,
    }
    assert response.parsed == Out(clase="avanza")
    assert (response.usage.input_tokens, response.usage.output_tokens) == (120, 30)
    assert response.provider == "ollama_native" and response.prompt_version == "p-v2"


async def test_invalid_outputs_are_typed_errors():
    with pytest.raises(LlmInvalidOutput):
        await _adapter(lambda r: _chat_reply("no es json")).complete(_request())
    with pytest.raises(LlmSchemaMismatch):
        await _adapter(lambda r: _chat_reply('{"otra": 1}')).complete(_request())
    with pytest.raises(LlmInvalidOutput):
        await _adapter(lambda r: _chat_reply('{"clase"', done_reason="length")).complete(_request())


async def test_server_errors_and_connection_failures_are_unavailable():
    with pytest.raises(LlmUnavailable):
        await _adapter(lambda r: httpx.Response(500)).complete(_request())

    def boom(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(LlmUnavailable):
        await _adapter(boom).complete(_request())


async def test_embed_uses_native_endpoint_in_order():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    vectors = await _adapter(handler).embed(["a", "b"])
    assert seen["url"] == "http://127.0.0.1:11434/api/embed"
    assert seen["body"] == {"model": "emb:0.6b", "input": ["a", "b"], "truncate": True}
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_loaded_models_reports_memory():
    def handler(request: httpx.Request):
        assert request.url.path == "/api/ps"
        return httpx.Response(
            200, json={"models": [{"name": "modelo:9b", "size": 7_000, "size_vram": 6_000}]}
        )

    assert await _adapter(handler).loaded_models() == {
        "modelo:9b": {"size": 7_000, "size_vram": 6_000}
    }
