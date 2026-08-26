"""Zero-network `LlmPort` adapter (change 48-puerto-llm, design.md
"Adaptador fake sin red") — mirrors `ConsoleEmailSender`
(`app/email/sender.py`): default backend, keeps every call in memory so a
test can inspect what it was asked.
"""

import time

from pydantic import ValidationError

from app.ai.errors import LlmSchemaMismatch
from app.ai.ports import LlmProbe, LlmRequest, LlmResponse, LlmUsage


class FakeLlmAdapter:
    """Injectable, network-free `LlmPort`. `next_text`/`next_usage` is the
    canned response `complete()` returns, validated against
    `request.output_schema` like a real adapter (B1)."""

    def __init__(self) -> None:
        self.calls: list[LlmRequest] = []
        self.probe_calls: int = 0
        self.next_text: str = "Respuesta de prueba del adaptador fake."
        self.next_usage: LlmUsage = LlmUsage(input_tokens=10, output_tokens=5, total_tokens=15)

    async def complete(self, request: LlmRequest) -> LlmResponse:
        started_at = time.perf_counter()
        self.calls.append(request)

        parsed = None
        if request.output_schema is not None:
            try:
                parsed = request.output_schema.model_validate_json(self.next_text)
            except ValidationError as exc:
                raise LlmSchemaMismatch() from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return LlmResponse(
            text=self.next_text,
            parsed=parsed,
            usage=self.next_usage,
            provider="fake",
            model="fake-model",
            prompt_version=request.prompt_version,
            latency_ms=latency_ms,
            finish_reason="stop",
        )

    async def probe(self) -> LlmProbe:
        self.probe_calls += 1
        return LlmProbe(reachability="ok")


# Module-level singleton (D3, mirrors `_console_sender`).
_fake_adapter = FakeLlmAdapter()


def get_fake_adapter() -> FakeLlmAdapter:
    """Process-wide singleton — never a fresh instance (D3)."""
    return _fake_adapter
