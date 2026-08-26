"""`LlmPort` adapter over Anthropic's official SDK (change 48-puerto-llm,
design.md "Adaptador anthropic"). `anthropic` is imported LAZILY inside
`_build_client()` — the package must never land in `sys.modules` while
`LLM_PROVIDER` is something else (spec `llm-port` R5 "Aislamiento de
dependencia"). `system` travels top-level, `max_tokens` is always an
integer on the wire, `temperature`/`top_p`/`top_k` are NEVER sent (the SDK
does not even expose them as `messages.create()` kwargs in 1.x — passing
them raises `TypeError`). Retries and timeout are delegated to the SDK
(`LLM_MAX_RETRIES`, `LLM_TIMEOUT_SECONDS`); no backoff of our own (D7).
"""

import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    LlmAuthError,
    LlmConfigInvalid,
    LlmContentFiltered,
    LlmInvalidOutput,
    LlmRateLimited,
    LlmSchemaMismatch,
    LlmTimeout,
    LlmUnavailable,
)
from app.ai.ports import FinishReason, LlmProbe, LlmRequest, LlmResponse, LlmUsage
from app.config import Settings
from app.config import settings as default_settings

_NOT_PROBED_REASON = "Sólo se valida la configuración; sondear consumiría cuota."


def _wire_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Top-level `required` + `additionalProperties: false` (design.md
    "Adaptador anthropic"). Nested `$defs`/`$ref` stay as Pydantic emits
    them — this port documents schemas as flat by convention (D1 gotcha),
    it does not force-tighten nested nodes."""

    schema = model.model_json_schema()
    if schema.get("type") == "object" and "properties" in schema:
        schema["required"] = list(schema["properties"].keys())
        schema["additionalProperties"] = False
    return schema


def _validate_settings(settings: Settings) -> str:
    """Allowlist (spec `llm-port` "Guarda de destino") and API key (spec
    `llm-port` R5 "Falta de API key con anthropic activo") — checked BEFORE
    the SDK is even imported, let alone a client built."""

    cleaned = settings.LLM_BASE_URL.strip().rstrip("/")
    if not cleaned:
        raise LlmConfigInvalid()
    allowlist = {entry.strip().rstrip("/") for entry in settings.LLM_BASE_URL_ALLOWLIST}
    if cleaned not in allowlist:
        raise LlmConfigInvalid()
    if not settings.LLM_API_KEY.strip():
        raise LlmConfigInvalid()
    return cleaned


class AnthropicAdapter:
    """`LlmPort` over `AsyncAnthropic`. One ephemeral client per call (D3);
    the `anthropic` import itself is deferred to `_build_client()`, never
    to module import time or to `__init__`."""

    def __init__(self, *, settings: Settings = default_settings, transport: Any = None) -> None:
        self._base_url = _validate_settings(settings)
        self._settings = settings
        self._transport = transport

    def _build_client(self) -> tuple[Any, Any]:
        try:
            import anthropic
        except ImportError as exc:
            raise LlmConfigInvalid() from exc

        http_client = (
            anthropic.DefaultAsyncHttpxClient(transport=self._transport)
            if self._transport is not None
            else None
        )
        client = anthropic.AsyncAnthropic(
            api_key=self._settings.LLM_API_KEY,
            base_url=self._base_url,
            timeout=self._settings.LLM_TIMEOUT_SECONDS,
            max_retries=self._settings.LLM_MAX_RETRIES,
            http_client=http_client,
        )
        return anthropic, client

    def _build_kwargs(self, request: LlmRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._settings.LLM_MODEL,
            "max_tokens": request.max_tokens or self._settings.LLM_MAX_TOKENS,
            "system": request.system,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            # Never `budget_tokens` (design.md "Adaptador anthropic").
            "thinking": {"type": "adaptive"},
        }
        if request.output_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": _wire_schema(request.output_schema)}
            }
        return kwargs

    async def complete(self, request: LlmRequest) -> LlmResponse:
        started_at = time.perf_counter()
        anthropic_module, client = self._build_client()
        try:
            async with client:
                response = await client.messages.create(**self._build_kwargs(request))
        except (
            anthropic_module.AuthenticationError,
            anthropic_module.PermissionDeniedError,
        ) as exc:
            raise LlmAuthError() from exc
        except (anthropic_module.NotFoundError, anthropic_module.BadRequestError) as exc:
            raise LlmConfigInvalid() from exc
        except anthropic_module.RateLimitError as exc:
            raise LlmRateLimited() from exc
        except anthropic_module.APITimeoutError as exc:
            # MUST be caught before `APIConnectionError` — it is a subclass.
            raise LlmTimeout() from exc
        except anthropic_module.APIConnectionError as exc:
            raise LlmUnavailable() from exc
        except anthropic_module.APIStatusError as exc:
            # Remaining status errors: 5xx and 529 overloaded.
            raise LlmUnavailable() from exc

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return self._to_response(response, request, latency_ms)

    def _to_response(self, response: Any, request: LlmRequest, latency_ms: int) -> LlmResponse:
        usage = LlmUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

        if response.stop_reason == "refusal":
            details = response.stop_details
            reason = (details.explanation or details.category) if details else None
            if reason:
                raise LlmContentFiltered(reason)
            raise LlmContentFiltered()

        text = "".join(block.text for block in response.content if block.type == "text")

        if response.stop_reason == "max_tokens":
            if request.output_schema is not None:
                raise LlmInvalidOutput()
            return self._response(text, None, usage, request, latency_ms, "length")

        parsed = None
        if request.output_schema is not None:
            parsed = self._validate_output(text, request.output_schema)
        return self._response(text, parsed, usage, request, latency_ms, "stop")

    def _response(
        self,
        text: str,
        parsed: BaseModel | None,
        usage: LlmUsage,
        request: LlmRequest,
        latency_ms: int,
        finish_reason: FinishReason,
    ) -> LlmResponse:
        return LlmResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            provider="anthropic",
            model=self._settings.LLM_MODEL,
            prompt_version=request.prompt_version,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _validate_output(text: str, schema: type[BaseModel]) -> BaseModel:
        try:
            return schema.model_validate_json(text)
        except ValidationError as exc:
            raise LlmSchemaMismatch() from exc

    async def probe(self) -> LlmProbe:
        """NEVER touches the network — probing would spend quota (D4)."""
        return LlmProbe(reachability="not_probed", reason=_NOT_PROBED_REASON)
