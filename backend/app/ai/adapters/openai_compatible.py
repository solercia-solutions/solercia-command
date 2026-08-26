"""`LlmPort` adapter for any OpenAI-compatible `/chat/completions` server
(Ollama's `/v1` shim, llama.cpp, LM Studio) — design.md "Adaptador
openai_compatible". Transport/`sleep` injectable, allowlist+model
validated in the constructor before any request (spec `llm-port` "Guarda
de destino"), deterministic retries (D7), logs never carry the key or the
request body (spec `llm-port` "Protección de secretos")."""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
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

logger = logging.getLogger("solercia.ai.openai_compatible")

_LOGGED_BODY_PREVIEW_CHARS = 200
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
    cleaned = settings.LLM_BASE_URL.strip().rstrip("/")
    if not cleaned:
        raise LlmConfigInvalid()
    allowlist = {entry.strip().rstrip("/") for entry in settings.LLM_BASE_URL_ALLOWLIST}
    if cleaned not in allowlist:
        raise LlmConfigInvalid()
    return cleaned


class OpenAiCompatibleAdapter:
    """Injectable, network-boundary `LlmPort` adapter. One ephemeral
    `httpx.AsyncClient` per call (D3, mirrors `solercia_connect/client.py`)."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = _validate_base_url(settings)
        if not settings.LLM_MODEL.strip():
            raise LlmConfigInvalid()
        self._settings = settings
        self._transport = transport
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._settings.LLM_API_KEY.strip():
            headers["Authorization"] = f"Bearer {self._settings.LLM_API_KEY}"
        return headers

    def _build_body(self, request: LlmRequest) -> dict[str, Any]:
        system_content = request.system
        response_format: dict[str, Any] | None = None

        if request.output_schema is not None:
            schema = _wire_schema(request.output_schema)
            mode = self._settings.LLM_JSON_MODE
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

        body: dict[str, Any] = {
            "model": self._settings.LLM_MODEL,
            "messages": messages,
            "max_tokens": request.max_tokens or self._settings.LLM_MAX_TOKENS,
            "temperature": request.temperature,
            "stream": False,
        }
        if response_format is not None:
            body["response_format"] = response_format
        return body

    async def complete(self, request: LlmRequest) -> LlmResponse:
        started_at = time.perf_counter()
        body = self._build_body(request)
        response = await self._post_with_retries(body, timeout=request.timeout_seconds)
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return self._to_response(response, request, latency_ms)

    async def _post_with_retries(
        self, body: dict[str, Any], *, timeout: float | None
    ) -> httpx.Response:
        effective_timeout = timeout or self._settings.LLM_TIMEOUT_SECONDS
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=effective_timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        "/chat/completions", json=body, headers=self._headers()
                    )
            except httpx.TimeoutException as exc:
                raise LlmTimeout() from exc
            except httpx.RequestError as exc:
                raise LlmUnavailable() from exc

            if response.status_code == 429:
                attempt += 1
                if attempt > self._settings.LLM_MAX_RETRIES:
                    self._log_error(response)
                    raise LlmRateLimited()
                await self._sleep(self._retry_after_seconds(response))
                continue

            if response.status_code >= 500:
                attempt += 1
                if attempt > self._settings.LLM_MAX_RETRIES:
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
        return min(seconds, self._settings.LLM_MAX_BACKOFF_SECONDS)

    @staticmethod
    def _log_error(response: httpx.Response) -> None:
        """Status + up to 200 chars of the RESPONSE body only — never a
        header, never the request body, never the key."""

        body_preview = response.text[:_LOGGED_BODY_PREVIEW_CHARS]
        logger.warning("El proveedor LLM respondió %s: %s", response.status_code, body_preview)

    def _to_response(
        self, response: httpx.Response, request: LlmRequest, latency_ms: int
    ) -> LlmResponse:
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmInvalidOutput() from exc

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
            provider="openai_compatible",
            model=self._settings.LLM_MODEL,
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
        """`GET {base_url}/models` — NEVER generates text (D4)."""

        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._settings.LLM_TIMEOUT_SECONDS,
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

        if model_ids and self._settings.LLM_MODEL not in model_ids:
            return LlmProbe(
                reachability="ok",
                reason="LLM_MODEL no aparece en la lista de modelos del proveedor.",
            )
        return LlmProbe(reachability="ok")
