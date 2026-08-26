"""`LlmPort` contract + frozen DTOs (change 48-puerto-llm, design.md
"Contrato del puerto"). Mirrors `app/email/sender.py`'s `EmailSender`
Protocol: the domain depends on this, never a provider SDK directly.
"""

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
    `max_tokens=None` resolves against `settings.LLM_MAX_TOKENS` (D2)."""

    system: str
    messages: tuple[LlmMessage, ...]
    output_schema: type[BaseModel] | None = None
    temperature: float = 0.0
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


class LlmPort(Protocol):
    async def complete(self, request: LlmRequest) -> LlmResponse: ...

    async def probe(self) -> LlmProbe: ...
