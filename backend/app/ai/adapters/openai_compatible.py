"""`LlmPort` adapter for any OpenAI-compatible server (Ollama's `/v1` shim,
llama.cpp, LM Studio, OpenAI, OpenRouter, Groq, DeepSeek, Mistral) —
design.md "Adaptador openai_compatible". Transport/`sleep` injectable,
destination+model validated in the constructor before any request (spec
`llm-port` "Guarda de destino"), deterministic retries (D7), logs never
carry the key, the request body nor the provider's response body (spec
`llm-port` "Protección de secretos").

C04: the adapter is configured by an `OpenAiCompatibleConfig` (built from
the global `LLM_*` or from an organization's saved settings) and dispatches
ONLY when it holds an `LlmDispatchContext`; without one, `complete`,
`probe` and `embed` keep the deny-all barrier of `cf0beff`.
"""

import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.errors import (
    LlmAuthError,
    LlmAuthorizationRequired,
    LlmConfigInvalid,
    LlmContentFiltered,
    LlmEmbeddingsUnavailable,
    LlmInvalidOutput,
    LlmRateLimited,
    LlmSchemaMismatch,
    LlmTimeout,
    LlmUnavailable,
)
from app.ai.ports import (
    FinishReason,
    LlmDispatchContext,
    LlmProbe,
    LlmRequest,
    LlmResponse,
    LlmUsage,
)
from app.ai.presets import preset_base_urls
from app.config import Settings
from app.config import settings as default_settings

logger = logging.getLogger("solercia.ai.openai_compatible")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _wire_schema(model: type[BaseModel]) -> dict[str, Any]:
    """`output_schema.model_json_schema()` with `required` forced to every
    property and `additionalProperties: false` injected on each object
    node (design.md "Cuerpo por LLM_JSON_MODE")."""

    schema = model.model_json_schema()
    _tighten(schema)
    return schema


def _tighten(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" and "properties" in node:
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False
        for value in node.values():
            _tighten(value)
    elif isinstance(node, list):
        for item in node:
            _tighten(item)


def _extract_json(text: str) -> Any:
    """Tolerant, deterministic extraction (design.md D7): raw JSON, then a
    fenced ```json block, then the substring between the first `{` and the
    last `}` — no retry, no asking the model to fix itself."""

    try:
        return json.loads(text)
    except ValueError:
        pass

    fenced = _FENCE_RE.search(text)
    if fenced is not None:
        try:
            return json.loads(fenced.group(1))
        except ValueError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass

    raise LlmInvalidOutput()


def _validate_base_url(settings: Settings) -> str:
    """Global `LLM_*` path: the URL must be in `LLM_BASE_URL_ALLOWLIST` or be
    one of the fixed preset URLs (C04 extends the allowlist with them)."""

    cleaned = settings.LLM_BASE_URL.strip().rstrip("/")
    if not cleaned:
        raise LlmConfigInvalid()
    allowlist = {entry.strip().rstrip("/") for entry in settings.LLM_BASE_URL_ALLOWLIST}
    if cleaned not in allowlist | preset_base_urls():
        raise LlmConfigInvalid()
    return cleaned


@dataclass(frozen=True)
class OpenAiCompatibleConfig:
    """Everything one adapter instance needs. `base_url` must come out of a
    destination guard (`_validate_base_url` or `app.ai.url_guard`). The key
    is excluded from `repr` so it never reaches a log or a traceback."""

    base_url: str
    chat_model: str
    embedding_model: str | None = None
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 60.0
    max_tokens: int = 1024
    temperature: float = 0.0
    #: Sent as `reasoning_effort` when set ("none" disables thinking).
    reasoning_effort: str | None = None
    json_mode: str = "json_object"
    max_retries: int = 2
    max_backoff_seconds: float = 30.0
    #: Provider-specific body keys, e.g. Ollama's `{"options": {"num_ctx": N}}`.
    extra_body: Mapping[str, Any] = field(default_factory=dict)
    provider_label: str = "openai_compatible"

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAiCompatibleConfig":
        base_url = _validate_base_url(settings)
        if not settings.LLM_MODEL.strip():
            raise LlmConfigInvalid()
        return cls(
            base_url=base_url,
            chat_model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_tokens=settings.LLM_MAX_TOKENS,
            json_mode=settings.LLM_JSON_MODE,
            max_retries=settings.LLM_MAX_RETRIES,
            max_backoff_seconds=settings.LLM_MAX_BACKOFF_SECONDS,
        )


class OpenAiCompatibleAdapter:
    """Injectable, network-boundary `LlmPort` adapter. One ephemeral
    `httpx.AsyncClient` per call (D3, mirrors `solercia_connect/client.py`)."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        config: OpenAiCompatibleConfig | None = None,
        dispatch_context: LlmDispatchContext | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if config is None:
            config = OpenAiCompatibleConfig.from_settings(settings)
        elif not config.base_url.strip() or not config.chat_model.strip():
            raise LlmConfigInvalid()
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self.dispatch_context = dispatch_context
        self._transport = transport
        self._sleep = sleep

    def _authorize(self) -> None:
        """Deny-all barrier: only a server-built `LlmDispatchContext`
        authorizes a real call. Keys, allowlists, localhost and prompt
        claims cannot."""

        if self.dispatch_context is None:
            raise LlmAuthorizationRequired()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._config.api_key.strip():
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def _build_body(self, request: LlmRequest) -> dict[str, Any]:
        config = self._config
        system_content = request.system
        response_format: dict[str, Any] | None = None

        if request.output_schema is not None:
            schema = _wire_schema(request.output_schema)
            mode = config.json_mode
            if mode == "json_schema_openai":
                response_format = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": request.output_schema.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                }
            elif mode == "json_schema_llamacpp":
                response_format = {"type": "json_schema", "schema": schema}
            else:  # "json_object" (default, D6): the schema travels as a prompt hint
                response_format = {"type": "json_object"}
                system_content = (
                    f"{system_content}\n\nResponde ÚNICAMENTE con un objeto json que cumpla "
                    f"exactamente este esquema:\n{json.dumps(schema)}"
                )

        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        body: dict[str, Any] = dict(config.extra_body)
        body.update(
            {
                "model": config.chat_model,
                "messages": messages,
                "max_tokens": request.max_tokens or config.max_tokens,
                "temperature": (
                    request.temperature if request.temperature is not None else config.temperature
                ),
                "stream": False,
            }
        )
        if config.reasoning_effort:
            body["reasoning_effort"] = config.reasoning_effort
        if response_format is not None:
            body["response_format"] = response_format
        return body

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self._authorize()
        started_at = time.perf_counter()
        body = self._build_body(request)
        response = await self._post_with_retries(
            "/chat/completions", body, timeout=request.timeout_seconds
        )
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return self._to_response(response, request, latency_ms)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """`POST /embeddings` — one vector per text, reordered by `index`."""

        self._authorize()
        model = self._config.embedding_model
        if not model or not model.strip():
            raise LlmEmbeddingsUnavailable()
        inputs = list(texts)
        if not inputs:
            return []
        response = await self._post_with_retries(
            "/embeddings", {"model": model, "input": inputs}, timeout=None
        )
        return self._to_vectors(response, expected=len(inputs))

    @staticmethod
    def _to_vectors(response: httpx.Response, *, expected: int) -> list[list[float]]:
        try:
            items = response.json()["data"]
            ordered = sorted(items, key=lambda item: int(item["index"]))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmInvalidOutput() from exc
        if len(vectors) != expected or any(
            not vector or any(not math.isfinite(v) for v in vector) for vector in vectors
        ):
            raise LlmInvalidOutput()
        return vectors

    async def _post_with_retries(
        self, path: str, body: dict[str, Any], *, timeout: float | None
    ) -> httpx.Response:
        effective_timeout = timeout or self._config.timeout_seconds
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=effective_timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(path, json=body, headers=self._headers())
            except httpx.TimeoutException as exc:
                raise LlmTimeout() from exc
            except httpx.RequestError as exc:
                raise LlmUnavailable() from exc

            if response.status_code == 429:
                attempt += 1
                if attempt > self._config.max_retries:
                    self._log_error(response)
                    raise LlmRateLimited()
                await self._sleep(self._retry_after_seconds(response))
                continue

            if response.status_code >= 500:
                attempt += 1
                if attempt > self._config.max_retries:
                    self._log_error(response)
                    raise LlmUnavailable()
                await self._sleep(self._retry_after_seconds(response))
                continue

            if response.status_code in (401, 403):
                self._log_error(response)
                raise LlmAuthError()

            if response.status_code >= 400:
                self._log_error(response)
                raise LlmConfigInvalid()

            return response

    def _retry_after_seconds(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After")
        seconds = 1.0
        if header is not None:
            try:
                seconds = float(header)
            except ValueError:
                seconds = 1.0
        return min(seconds, self._config.max_backoff_seconds)

    def _log_error(self, response: httpx.Response) -> None:
        """Status and provider label only — never a header, the request
        body, the key, nor the response body (a provider may echo any of
        them back)."""

        logger.warning(
            "El proveedor LLM %s respondió %s.", self._config.provider_label, response.status_code
        )

    def _to_response(
        self, response: httpx.Response, request: LlmRequest, latency_ms: int
    ) -> LlmResponse:
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmInvalidOutput() from exc
        if not isinstance(text, str):
            raise LlmInvalidOutput()

        finish_reason_raw = choice.get("finish_reason")
        usage_raw = payload.get("usage") or {}
        usage = LlmUsage(
            input_tokens=int(usage_raw.get("prompt_tokens") or 0),
            output_tokens=int(usage_raw.get("completion_tokens") or 0),
            total_tokens=int(usage_raw.get("total_tokens") or 0),
        )

        if finish_reason_raw == "content_filter":
            raise LlmContentFiltered()

        if finish_reason_raw == "length":
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
            provider=self._config.provider_label,
            model=self._config.chat_model,
            prompt_version=request.prompt_version,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _validate_output(text: str, schema: type[BaseModel]) -> BaseModel:
        data = _extract_json(text)
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LlmSchemaMismatch() from exc

    async def probe(self) -> LlmProbe:
        """`GET /models` — never generates text (D4). Denied without context."""

        self._authorize()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get("/models", headers=self._headers())
        except httpx.HTTPError:
            return LlmProbe(
                reachability="unreachable",
                reason="No fue posible conectar con el proveedor LLM configurado.",
            )

        if response.status_code >= 400:
            return LlmProbe(
                reachability="unreachable",
                reason=f"El proveedor LLM respondió {response.status_code} en /models.",
            )

        try:
            payload = response.json()
            model_ids = {
                str(item.get("id")) for item in payload.get("data", []) if isinstance(item, dict)
            }
        except (ValueError, AttributeError):
            return LlmProbe(reachability="ok")

        if model_ids and self._config.chat_model not in model_ids:
            return LlmProbe(
                reachability="ok",
                reason="El modelo configurado no aparece en la lista de modelos del proveedor.",
            )
        return LlmProbe(reachability="ok")
