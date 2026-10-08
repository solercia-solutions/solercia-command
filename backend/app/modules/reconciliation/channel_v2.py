"""Channel v2 orchestration (E03): one unit → one verdict. No database.

Order (methodology): deterministic prechecks (noise, unattended events) →
explicit identifiers as forced candidates → top-k by ONE local embedding
model (independent of the chat model; vectors cached by model + text hash)
→ LLM with prompt v2, JSON schema and fixed decoding parameters →
post-rules and calibrated confidence.

The C05 service (``channel = "v2"``) and the offline evaluator
(``scripts/eval_classifier.py``) share this class, so a model is measured
exactly as it would run.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.ai.ports import LlmMessage, LlmPort, LlmRequest
from app.shared.exceptions import AppException

from .prompt_v2 import ClassificationV2, apply_post_rules, build_user_message_v2, latest_note
from .prompt_versions import DEFAULT_PROMPT_VERSION_V2, get_prompt_v2
from .rules import CompiledRules
from .stages import (
    CandidateV2,
    TaskEntry,
    Unit,
    forced_candidates,
    precheck,
    rank_candidates,
    subject_candidates,
    task_embedding_text,
    unit_identifiers,
    unit_text,
)

#: Failures of ONE answer; anything else means the provider is down.
UNIT_ERRORS = frozenset({"llm_schema_mismatch", "llm_invalid_output", "llm_content_filtered"})
_EMBED_BATCH = 32


class ProviderDown(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EmbeddingCache(Protocol):
    def get(self, model: str, digest: str) -> list[float] | None: ...

    def put(self, model: str, digest: str, vector: list[float]) -> None: ...


class MemoryEmbeddingCache:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], list[float]] = {}

    def get(self, model: str, digest: str) -> list[float] | None:
        return self.items.get((model, digest))

    def put(self, model: str, digest: str, vector: list[float]) -> None:
        self.items[(model, digest)] = list(vector)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _code(exc: AppException) -> str:
    return exc.code or type(exc).__name__


@dataclass(frozen=True)
class ChannelV2Config:
    top_k: int = 5
    max_chars: int = 6000
    embed_chars: int = 2000
    max_tokens: int = 600
    #: A registered version (``prompt_versions.PROMPTS_V2``).
    prompt_version: str = DEFAULT_PROMPT_VERSION_V2
    #: Literal subject in the task text forces a candidate (methodology b.4, step 2).
    subject_match: bool = False


@dataclass
class UnitResult:
    kind: str
    key: str
    thread_key: str | None
    state: str | None
    clase: str | None
    task_id: str | None
    task_ref: str | None
    confidence: float | None
    #: ``regla`` (deterministic) | ``llm`` | ``error_llm`` | ``sin_llm``.
    stage: str
    reason: str | None = None
    candidates: list[CandidateV2] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None
    output_hash: str | None = None
    model: str | None = None
    provider: str | None = None
    prompt_version: str | None = None


class ChannelV2:
    def __init__(
        self,
        rules: CompiledRules,
        *,
        chat: LlmPort | None,
        embedder: LlmPort | None,
        embedding_model: str | None,
        cache: EmbeddingCache,
        config: ChannelV2Config,
    ) -> None:
        self._rules = rules
        self._chat = chat
        self._embedder = embedder
        self._embedding_model = embedding_model
        self._cache = cache
        self._config = config
        self._prompt = get_prompt_v2(config.prompt_version)
        self.embedding_error: str | None = None

    @property
    def rules(self) -> CompiledRules:
        return self._rules

    # --- embeddings -------------------------------------------------------------------

    async def _embed_cached(self, texts: Sequence[str]) -> list[list[float] | None]:
        if self._embedder is None or not self._embedding_model or self.embedding_error:
            return [None] * len(texts)
        model = self._embedding_model
        digests = [text_digest(t) for t in texts]
        vectors: list[list[float] | None] = [self._cache.get(model, d) for d in digests]
        missing = [i for i, v in enumerate(vectors) if v is None]
        try:
            for start in range(0, len(missing), _EMBED_BATCH):
                batch = missing[start : start + _EMBED_BATCH]
                embedded = await self._embedder.embed([texts[i] for i in batch])
                for index, vector in zip(batch, embedded, strict=True):
                    self._cache.put(model, digests[index], list(vector))
                    vectors[index] = list(vector)
        except AppException as exc:
            self.embedding_error = _code(exc)
        return vectors

    async def task_vectors(self, tasks: Sequence[TaskEntry]) -> dict[str, list[float]]:
        vectors = await self._embed_cached([task_embedding_text(t) for t in tasks])
        return {t.id: v for t, v in zip(tasks, vectors, strict=True) if v is not None}

    # --- one unit ------------------------------------------------------------------------

    def _result(self, unit: Unit, **fields: Any) -> UnitResult:
        return UnitResult(
            kind=unit.kind,
            key=unit.key,
            thread_key=unit.thread_key,
            state=unit.state,
            **fields,
        )

    async def classify(
        self,
        unit: Unit,
        tasks: Sequence[TaskEntry],
        task_vectors: Mapping[str, Sequence[float]],
    ) -> UnitResult:
        decided = precheck(unit, self._rules)
        if decided is not None:
            clase, reason = decided
            return self._result(
                unit,
                clase=clase,
                task_id=None,
                task_ref=None,
                confidence=1.0,
                stage="regla",
                reason=reason,
                payload={"clase": clase, "motivo_regla": reason},
                output_hash=text_digest(f"{clase}|{reason}"),
            )

        text = unit_text(unit, self._rules)
        forced = forced_candidates(unit_identifiers(unit, self._rules), tasks, self._rules)
        if self._config.subject_match:
            forced += subject_candidates(
                unit,
                tasks,
                exclude={c.task_id for c in forced},
                limit=self._config.top_k - len(forced),
            )
        unit_vector = None
        if task_vectors and len(forced) < self._config.top_k:
            (unit_vector,) = await self._embed_cached(
                [f"{unit.subject}\n{text}"[: self._config.embed_chars]]
            )
        candidates = rank_candidates(forced, unit_vector, task_vectors, tasks, k=self._config.top_k)
        if self._chat is None:
            return self._result(
                unit,
                clase=None,
                task_id=None,
                task_ref=None,
                confidence=None,
                stage="sin_llm",
                candidates=candidates,
            )

        notes = None
        if self._prompt.candidate_notes:
            by_id = {t.id: t for t in tasks}
            notes = {
                c.task_id: note
                for c in candidates
                if c.task_id in by_id and (note := latest_note(by_id[c.task_id].observations))
            }
        request = LlmRequest(
            system=self._prompt.system,
            messages=(
                LlmMessage(
                    role="user",
                    content=build_user_message_v2(
                        unit,
                        candidates,
                        max_chars=self._config.max_chars,
                        rules=self._rules,
                        notes=notes,
                    ),
                ),
            ),
            output_schema=ClassificationV2,
            temperature=0.0,
            max_tokens=self._config.max_tokens,
            prompt_version=self._prompt.version,
        )
        try:
            response = await self._chat.complete(request)
        except AppException as exc:
            code = _code(exc)
            if code not in UNIT_ERRORS:
                raise ProviderDown(code) from exc
            return self._result(
                unit,
                clase="no_concluyente",
                task_id=None,
                task_ref=None,
                confidence=0.0,
                stage="error_llm",
                candidates=candidates,
                error=code,
                payload={"clase": "no_concluyente", "error": code},
                output_hash=text_digest(f"error|{code}"),
                prompt_version=self._prompt.version,
            )
        if not isinstance(response.parsed, ClassificationV2):
            raise ProviderDown("llm_invalid_output")
        verdict = apply_post_rules(response.parsed, candidates, text)
        return self._result(
            unit,
            clase=verdict.clase,
            task_id=verdict.task_id,
            task_ref=verdict.task_ref,
            confidence=verdict.confidence,
            stage="llm",
            candidates=candidates,
            payload=verdict.payload,
            latency_ms=response.latency_ms,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            output_hash=text_digest(
                json.dumps(response.parsed.model_dump(), sort_keys=True, ensure_ascii=False)
            ),
            model=response.model,
            provider=response.provider,
            prompt_version=self._prompt.version,
        )
