"""Contract every `LlmPort` adapter must satisfy (design.md "Estrategia de
pruebas"). Slice 1 exercised only `fake`; as of slice 2, this SAME `fake`
fixture also parametrizes over `openai_compatible` through a hermetic
`httpx.MockTransport` double exposing the identical `next_text`/`calls`/
`probe_calls` surface as `FakeLlmAdapter` — the test bodies below never
change per provider. Requirement `llm-port` R1/R3.
"""

from dataclasses import FrozenInstanceError
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.ai.adapters.fake import get_fake_adapter
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
from app.ai.errors import LlmSchemaMismatch
from app.ai.ports import LlmMessage, LlmProbe, LlmRequest, LlmResponse
from app.config import Settings

_OPENAI_COMPATIBLE_BASE_URL = "http://localhost:11434/v1"


class TriageDecision(BaseModel):
    """Flat model used ONLY here to exercise `output_schema` validation —
    change 49 defines the real classification schema."""

    category: str
    urgent: bool


class _OpenAiCompatibleDouble:
    """Same call-log surface as `FakeLlmAdapter` (`next_text`/`calls`/
    `probe_calls`), backed by a real `OpenAiCompatibleAdapter` behind a
    hermetic `httpx.MockTransport`."""

    def __init__(self) -> None:
        self.calls: list[LlmRequest] = []
        self.probe_calls = 0
        self.next_text = "Respuesta de prueba del adaptador openai_compatible."
        settings = Settings(
            LLM_BASE_URL=_OPENAI_COMPATIBLE_BASE_URL,
            LLM_MODEL="qwen-test",
            LLM_BASE_URL_ALLOWLIST=[_OPENAI_COMPATIBLE_BASE_URL],
        )
        self._adapter = OpenAiCompatibleAdapter(
            settings=settings, transport=httpx.MockTransport(self._handle)
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            self.probe_calls += 1
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": self.next_text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self.calls.append(request)
        return await self._adapter.complete(request)

    async def probe(self) -> LlmProbe:
        return await self._adapter.probe()


@pytest.fixture(params=["fake", "openai_compatible"])
def fake(request: pytest.FixtureRequest) -> Any:
    """Fresh call history per test (D3); `openai_compatible` gets a fresh
    double per test since it is not a process singleton."""
    if request.param == "openai_compatible":
        return _OpenAiCompatibleDouble()
    adapter = get_fake_adapter()
    adapter.calls.clear()
    adapter.probe_calls = 0
    adapter.next_text = "Respuesta de prueba del adaptador fake."
    return adapter


def _request(**overrides: object) -> LlmRequest:
    defaults: dict[str, object] = {
        "system": "Eres un asistente de triage de correo.",
        "messages": (LlmMessage(role="user", content="Clasifica este correo."),),
        "max_tokens": 200,
    }
    defaults.update(overrides)
    return LlmRequest(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio(loop_scope="session")
async def test_complete_returns_text_and_provider_metadata(fake: Any) -> None:
    response = await fake.complete(_request(prompt_version="v1"))
    assert response.text
    assert response.usage.total_tokens == response.usage.input_tokens + response.usage.output_tokens
    assert response.provider
    assert response.model
    assert response.prompt_version == "v1"
    assert response.latency_ms >= 0
    assert response.finish_reason == "stop"


def test_dtos_are_frozen() -> None:
    request = _request()
    with pytest.raises(FrozenInstanceError):
        request.system = "otro sistema"  # type: ignore[misc]


@pytest.mark.asyncio(loop_scope="session")
async def test_parsed_is_none_when_no_schema_requested(fake: Any) -> None:
    response = await fake.complete(_request())
    assert response.parsed is None


@pytest.mark.asyncio(loop_scope="session")
async def test_parsed_is_a_validated_model_when_schema_requested(fake: Any) -> None:
    fake.next_text = '{"category": "queja", "urgent": true}'
    response = await fake.complete(_request(output_schema=TriageDecision))
    assert isinstance(response.parsed, TriageDecision)
    assert response.parsed.category == "queja"
    assert response.parsed.urgent is True


@pytest.mark.asyncio(loop_scope="session")
async def test_schema_mismatch_never_returns_unvalidated_parsed(fake: Any) -> None:
    fake.next_text = '{"category": "queja"}'  # falta "urgent"
    with pytest.raises(LlmSchemaMismatch) as excinfo:
        await fake.complete(_request(output_schema=TriageDecision))
    assert excinfo.value.code == "llm_schema_mismatch"
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio(loop_scope="session")
async def test_probe_never_generates_text(fake: Any) -> None:
    await fake.probe()
    assert fake.probe_calls == 1
    assert len(fake.calls) == 0
