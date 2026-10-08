"""`LlmPort` contract + frozen DTOs (change 48-puerto-llm, design.md
"Contrato del puerto"). Mirrors `app/email/sender.py`'s `EmailSender`
Protocol: the domain depends on this, never a provider SDK directly.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel

# `system` is NOT a message role — it travels only in `LlmRequest.system`
# (design.md "Desviación declarada (`Role`)").
Role = Literal["user", "assistant"]

# `refusal`/`tool` are reserved by contract; no adapter in change 48
# emits them (design.md, table "FinishReason, valor por valor").
FinishReason = Literal["stop", "length", "refusal", "tool"]

Reachability = Literal["ok", "unreachable", "not_probed"]


@dataclass(frozen=True)
class LlmMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class LlmUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LlmRequest:
    """`output_schema` is a Pydantic model TYPE (design.md D1).
    `max_tokens=None` resolves against the adapter configuration (D2);
    `temperature=None` too (C04: per-organization default, 0.0 otherwise)."""

    system: str
    messages: tuple[LlmMessage, ...]
    output_schema: type[BaseModel] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_seconds: float | None = None
    prompt_version: str | None = None


@dataclass(frozen=True)
class LlmResponse:
    """`parsed` exists ONLY when `output_schema` validated locally (B1);
    never returned unvalidated (D7)."""

    text: str
    parsed: BaseModel | None
    usage: LlmUsage
    provider: str
    model: str
    prompt_version: str | None
    latency_ms: int
    finish_reason: FinishReason


@dataclass(frozen=True)
class LlmProbe:
    """`probe()` result — NEVER generates text (D4)."""

    reachability: Reachability
    reason: str | None = None


DispatchSource = Literal[
    "organization_settings", "global_settings", "default_preset", "offline_evaluation"
]


@dataclass(frozen=True)
class LlmDispatchContext:
    """Trusted authorization to dispatch to a real provider (C04).

    Built ONLY by `app.modules.ai_settings.service.build_llm_port` from an
    `organization_id` resolved server-side (JWT membership or the scheduler's
    own organization loop) and a provider configuration that organization's
    admin saved (or the operator's `LLM_*`, or the local default preset).
    Never derived from request payloads or prompts. Without it, real
    adapters keep the deny-all barrier.

    E04 exception: ``offline_evaluation`` is built only by the operator-run
    evaluator (``scripts/eval_classifier.py``), which refuses non-local
    presets unless explicitly confirmed and never touches a database."""

    organization_id: uuid.UUID
    source: DispatchSource


class LlmPort(Protocol):
    async def complete(self, request: LlmRequest) -> LlmResponse: ...

    async def probe(self) -> LlmProbe: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per input text, in input order (C04)."""
        ...
