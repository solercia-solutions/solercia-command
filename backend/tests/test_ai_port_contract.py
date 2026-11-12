"""Local fake retains completion semantics; real adapter denial is tested directly.

There is no trusted tenant/purpose/authorization in LlmRequest yet. A fake
success must not imply that a real provider is authorized to receive data.
"""

from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from pydantic import BaseModel

from app.ai.adapters.fake import get_fake_adapter
from app.ai.errors import LlmSchemaMismatch
from app.ai.ports import LlmMessage, LlmRequest


class TriageDecision(BaseModel):
    category: str
    urgent: bool


@pytest.fixture
def fake() -> Any:
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
    assert response.provider == "fake"
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
    fake.next_text = '{"category": "queja"}'
    with pytest.raises(LlmSchemaMismatch) as excinfo:
        await fake.complete(_request(output_schema=TriageDecision))
    assert excinfo.value.code == "llm_schema_mismatch"
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio(loop_scope="session")
async def test_probe_never_generates_text(fake: Any) -> None:
    probe = await fake.probe()
    assert probe.reachability == "ok"
    assert fake.probe_calls == 1
    assert len(fake.calls) == 0
