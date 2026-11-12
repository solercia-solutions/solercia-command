"""`LlmPort` adapter for Ollama's NATIVE API (E03).

Why not the OpenAI-compatible ``/v1`` shim: it ignores ``options`` —
``top_k``, ``num_ctx``, ``num_gpu`` and ``num_thread`` never reach the
runner (verified against Ollama 0.35: ``/v1`` with ``options.num_ctx`` 3072
loaded the model with its default context). Reproducible classification
needs them, so this adapter speaks ``/api/chat`` (``think: false``,
``format`` = JSON schema, ``options`` from ``Determinism``) and
``/api/embed``.

Same barrier as the OpenAI-compatible adapter: it dispatches ONLY with an
`LlmDispatchContext`. Logs never carry prompts, bodies nor responses.
"""

import logging
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.adapters.openai_compatible import _extract_json, _wire_schema
from app.ai.determinism import Determinism
from app.ai.errors import (
    LlmAuthorizationRequired,
    LlmConfigInvalid,
    LlmEmbeddingsUnavailable,
    LlmInvalidOutput,
    LlmSchemaMismatch,
    LlmTimeout,
    LlmUnavailable,
)
from app.ai.ports import LlmDispatchContext, LlmProbe, LlmRequest, LlmResponse, LlmUsage

logger = logging.getLogger("solercia.ai.ollama_native")


def native_base_url(base_url: str) -> str:
    """``http://host:11434/v1`` → ``http://host:11434`` (presets store ``/v1``)."""

    cleaned = base_url.strip().rstrip("/")
    return cleaned[: -len("/v1")] if cleaned.endswith("/v1") else cleaned


@dataclass(frozen=True)
class OllamaNativeConfig:
    base_url: str
    chat_model: str
    embedding_model: str | None = None
    determinism: Determinism = field(default_factory=Determinism)
    timeout_seconds: float = 300.0
    max_tokens: int = 600
    keep_alive: str = "10m"
    provider_label: str = "ollama_native"


class OllamaNativeAdapter:
    def __init__(
        self,
        *,
        config: OllamaNativeConfig,
        dispatch_context: LlmDispatchContext | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not config.base_url.strip() or not config.chat_model.strip():
            raise LlmConfigInvalid()
        self._config = config
        self._base_url = native_base_url(config.base_url)
        self.dispatch_context = dispatch_context
        self._transport = transport

    def _authorize(self) -> None:
        if self.dispatch_context is None:
            raise LlmAuthorizationRequired()

    async def _send(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._config.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, json=body)
        except httpx.TimeoutException as exc:
            raise LlmTimeout() from exc
        except httpx.RequestError as exc:
            raise LlmUnavailable() from exc
        if response.status_code >= 500:
            logger.warning("Ollama respondió %s en %s.", response.status_code, path)
            raise LlmUnavailable()
        if response.status_code >= 400:
            logger.warning("Ollama respondió %s en %s.", response.status_code, path)
            raise LlmConfigInvalid()
        return response

    def _body(self, request: LlmRequest) -> dict[str, Any]:
        determinism = self._config.determinism
        messages = [{"role": "system", "content": request.system}]
        messages += [{"role": m.role, "content": m.content} for m in request.messages]
        options = determinism.ollama_options(
            max_tokens=request.max_tokens or self._config.max_tokens
        )
        if request.temperature is not None:
            options["temperature"] = float(request.temperature)
        body: dict[str, Any] = {
            "model": self._config.chat_model,
            "messages": messages,
            "stream": False,
            "think": determinism.think,
            "keep_alive": self._config.keep_alive,
            "options": options,
        }
        if request.output_schema is not None:
            body["format"] = _wire_schema(request.output_schema)
        return body

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self._authorize()
        started_at = time.perf_counter()
        response = await self._send("POST", "/api/chat", self._body(request))
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        try:
            payload = response.json()
            text = payload["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmInvalidOutput() from exc
        if not isinstance(text, str):
            raise LlmInvalidOutput()
        prompt_tokens = int(payload.get("prompt_eval_count") or 0)
        output_tokens = int(payload.get("eval_count") or 0)
        usage = LlmUsage(prompt_tokens, output_tokens, prompt_tokens + output_tokens)
        finish = "length" if payload.get("done_reason") == "length" else "stop"
        parsed = None
        if request.output_schema is not None:
            if finish == "length":
                raise LlmInvalidOutput()
            try:
                parsed = request.output_schema.model_validate(_extract_json(text))
            except ValidationError as exc:
                raise LlmSchemaMismatch() from exc
        return LlmResponse(
            text=text,
            parsed=parsed,
            usage=usage,
            provider=self._config.provider_label,
            model=self._config.chat_model,
            prompt_version=request.prompt_version,
            latency_ms=latency_ms,
            finish_reason=finish,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self._authorize()
        model = self._config.embedding_model
        if not model or not model.strip():
            raise LlmEmbeddingsUnavailable()
        inputs = list(texts)
        if not inputs:
            return []
        response = await self._send(
            "POST", "/api/embed", {"model": model, "input": inputs, "truncate": True}
        )
        try:
            vectors = [[float(v) for v in vector] for vector in response.json()["embeddings"]]
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmInvalidOutput() from exc
        if len(vectors) != len(inputs) or any(
            not vector or any(not math.isfinite(v) for v in vector) for vector in vectors
        ):
            raise LlmInvalidOutput()
        return vectors

    async def probe(self) -> LlmProbe:
        self._authorize()
        try:
            response = await self._send("GET", "/api/tags")
        except (LlmUnavailable, LlmTimeout, LlmConfigInvalid):
            return LlmProbe(reachability="unreachable", reason="Ollama no respondió.")
        names = {m.get("name") for m in response.json().get("models", []) if isinstance(m, dict)}
        if names and self._config.chat_model not in names:
            return LlmProbe(reachability="ok", reason="El modelo no está instalado en Ollama.")
        return LlmProbe(reachability="ok")

    async def loaded_models(self) -> dict[str, dict[str, int]]:
        """``/api/ps``: bytes in memory per loaded model (RAM/VRAM estimate)."""

        self._authorize()
        response = await self._send("GET", "/api/ps")
        return {
            str(m.get("name")): {
                "size": int(m.get("size") or 0),
                "size_vram": int(m.get("size_vram") or 0),
            }
            for m in response.json().get("models", [])
            if isinstance(m, dict)
        }
