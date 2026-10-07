"""Classification channel (C05): mail threads → proposals. PROPOSES only.

``ReconciliationService.classify_window(org, since)``:

1. **Deterministic** — threads and their state (``threads.py``). No LLM.
2. **Candidates** — tasks the thread mentions by key, then top-k cosine over
   cached task embeddings (``task_embeddings``; recomputed only when the
   task text hash changes).
3. **LLM** — ``complete`` with a Pydantic ``output_schema`` at temperature 0;
   the answer is validated against the candidates (``prompt.py``).
4. **Persistence** — one open ``intake_proposals`` row per thread: unchanged
   threads are skipped without calling the LLM, new messages update the
   open proposal, a decided thread is re-proposed only when it grows, and
   an open proposal the LLM never classified is retried.

When the provider is unreachable the deterministic state and the key
candidates are still saved, the remaining threads stop calling it, and the
counts carry ``llm_error`` so the scheduled step fails ISOLATED. Logs carry
ids and counts only, never mail content. One commit per thread: a long run
that dies keeps what it finished.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.ai.ports import LlmMessage, LlmPort, LlmRequest
from app.shared.exceptions import AppException

from .candidates import (
    Candidate,
    TaskSnapshot,
    build_key_index,
    select_candidates,
    task_embedding_text,
    text_hash,
)
from .models import IntakeProposal
from .prompt import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    Decision,
    ThreadClassification,
    build_user_message,
    thread_embedding_text,
    validate_classification,
)
from .repository import ReconciliationRepository
from .threads import MailThread, extract_task_keys, group_threads, new_content

logger = logging.getLogger("solercia.reconciliation")

#: Failures of ONE answer; anything else means the provider is down.
_PER_THREAD_ERRORS = frozenset(
    {"llm_schema_mismatch", "llm_invalid_output", "llm_content_filtered"}
)
_EMBED_BATCH = 32


@dataclass(frozen=True)
class ReconciliationConfig:
    max_threads: int = 40
    max_thread_chars: int = 6000
    top_k: int = 5
    llm_max_tokens: int = 600

    @classmethod
    def from_settings(cls, settings: Any) -> "ReconciliationConfig":
        return cls(
            max_threads=settings.RECONCILIATION_MAX_THREADS_PER_RUN,
            max_thread_chars=settings.RECONCILIATION_MAX_THREAD_CHARS,
            top_k=settings.RECONCILIATION_TOP_K,
            llm_max_tokens=settings.RECONCILIATION_LLM_MAX_TOKENS,
        )


@dataclass(frozen=True)
class ClassifierBackend:
    port: LlmPort
    #: ``None`` when the provider has no embedding model (keys only).
    embedding_model: str | None
    provider: str


BackendFactory = Callable[[uuid.UUID], Awaitable[ClassifierBackend]]


def _code(exc: AppException) -> str:
    return exc.code or type(exc).__name__


class ReconciliationService:
    def __init__(
        self,
        repository: ReconciliationRepository,
        *,
        backend_factory: BackendFactory,
        commit: Callable[[], Awaitable[None]],
        config: ReconciliationConfig | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repository
        self._backend_factory = backend_factory
        self._commit = commit
        self._config = config or ReconciliationConfig()
        self._clock = clock

    async def classify_window(self, organization_id: uuid.UUID, since: datetime) -> dict[str, Any]:
        threads = group_threads(await self._repo.list_mail_items(organization_id, since))
        counts: dict[str, Any] = {
            "threads": len(threads),
            "processed": 0,
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "classified": 0,
            "key_candidates": 0,
            "thread_errors": 0,
            "llm_error": None,
            "embedding_error": None,
        }
        selected = threads[: self._config.max_threads]
        counts["processed"] = len(selected)
        if not selected:
            return counts

        tasks = await self._repo.list_active_tasks(organization_id)
        by_id = {task.id: task for task in tasks}
        key_index = build_key_index(tasks)

        backend: ClassifierBackend | None = None
        try:
            backend = await self._backend_factory(organization_id)
        except AppException as exc:
            counts["llm_error"] = _code(exc)

        task_vectors: dict[uuid.UUID, list[float]] = {}
        if backend is not None and backend.embedding_model:
            try:
                task_vectors = await self._task_vectors(organization_id, backend, tasks)
            except AppException as exc:
                counts["embedding_error"] = _code(exc)
                await self._commit()  # keep the vectors already cached

        for thread in selected:
            outcome = await self._process_thread(
                organization_id, thread, backend, task_vectors, by_id, key_index, counts
            )
            counts[outcome] += 1
            await self._commit()
        logger.info(
            "Clasificación %s: %d hilos, %d creadas, %d actualizadas, %d sin cambios, error=%s.",
            organization_id,
            counts["processed"],
            counts["created"],
            counts["updated"],
            counts["unchanged"],
            counts["llm_error"],
        )
        return counts

    # --- embeddings -------------------------------------------------------------

    async def _task_vectors(
        self, organization_id: uuid.UUID, backend: ClassifierBackend, tasks: Sequence[TaskSnapshot]
    ) -> dict[uuid.UUID, list[float]]:
        model = backend.embedding_model or ""
        cached = await self._repo.find_embeddings(organization_id, model, [t.id for t in tasks])
        vectors: dict[uuid.UUID, list[float]] = {}
        stale: list[tuple[TaskSnapshot, str, str]] = []
        for task in tasks:
            text = task_embedding_text(task)
            digest = text_hash(text)
            hit = cached.get(task.id)
            if hit and hit[0] == digest:
                vectors[task.id] = hit[1]
            else:
                stale.append((task, text, digest))
        for start in range(0, len(stale), _EMBED_BATCH):
            batch = stale[start : start + _EMBED_BATCH]
            embedded = await backend.port.embed([text for _, text, _ in batch])
            for (task, _, digest), vector in zip(batch, embedded, strict=True):
                await self._repo.save_embedding(organization_id, task.id, model, digest, vector)
                vectors[task.id] = list(vector)
        return vectors

    # --- one thread ---------------------------------------------------------------

    async def _process_thread(
        self,
        organization_id: uuid.UUID,
        thread: MailThread,
        backend: ClassifierBackend | None,
        task_vectors: dict[uuid.UUID, list[float]],
        tasks: dict[uuid.UUID, TaskSnapshot],
        key_index: dict[str, TaskSnapshot],
        counts: dict[str, Any],
    ) -> str:
        item_ids = thread.item_ids
        proposal = await self._repo.find_open_proposal(organization_id, thread.key)
        if proposal is not None:
            classified = proposal.relation is not None and proposal.classification_error is None
            if classified and sorted(proposal.item_ids) == item_ids:
                return "unchanged"
        else:
            decided = await self._repo.find_latest_decided(organization_id, thread.key)
            if decided is not None and set(item_ids) <= set(decided.item_ids):
                return "unchanged"

        mentioned = extract_task_keys(
            " ".join(
                [m.subject for m in thread.messages]
                + [new_content(m.body) for m in thread.messages]
            )
        )
        thread_vector = await self._thread_vector(thread, backend, task_vectors, counts)
        candidates = select_candidates(
            mentioned_keys=mentioned,
            key_index=key_index,
            thread_vector=thread_vector,
            task_vectors=task_vectors,
            tasks=tasks,
            k=self._config.top_k,
        )
        if any(c.via == "clave" for c in candidates):
            counts["key_candidates"] += 1

        decision, response_meta, error = await self._classify(thread, candidates, backend, counts)

        is_new = proposal is None
        if is_new:
            proposal = IntakeProposal(
                organization_id=organization_id,
                conversation_key=thread.key,
                status="propuesta",
            )
        self._fill(proposal, thread, candidates, decision, response_meta, error)
        if is_new:
            await self._repo.add_proposal(proposal)
        else:
            await self._repo.flush()
        return "created" if is_new else "updated"

    async def _thread_vector(
        self,
        thread: MailThread,
        backend: ClassifierBackend | None,
        task_vectors: dict[uuid.UUID, list[float]],
        counts: dict[str, Any],
    ) -> list[float] | None:
        if backend is None or not task_vectors or counts["embedding_error"]:
            return None
        try:
            (vector,) = await backend.port.embed(
                [thread_embedding_text(thread, min(self._config.max_thread_chars, 2000))]
            )
        except AppException as exc:
            counts["embedding_error"] = _code(exc)
            return None
        return list(vector)

    async def _classify(
        self,
        thread: MailThread,
        candidates: list[Candidate],
        backend: ClassifierBackend | None,
        counts: dict[str, Any],
    ) -> tuple[Decision | None, dict[str, str | None], str | None]:
        if backend is None or counts["llm_error"]:
            return None, {}, counts["llm_error"]
        request = LlmRequest(
            system=SYSTEM_PROMPT,
            messages=(
                LlmMessage(
                    role="user",
                    content=build_user_message(thread, candidates, self._config.max_thread_chars),
                ),
            ),
            output_schema=ThreadClassification,
            temperature=0.0,
            max_tokens=self._config.llm_max_tokens,
            prompt_version=PROMPT_VERSION,
        )
        try:
            response = await backend.port.complete(request)
        except AppException as exc:
            code = _code(exc)
            if code in _PER_THREAD_ERRORS:
                counts["thread_errors"] += 1
            else:
                counts["llm_error"] = code
            logger.warning("Clasificación del hilo falló (%s).", code)
            return None, {}, code
        if not isinstance(response.parsed, ThreadClassification):
            counts["thread_errors"] += 1
            return None, {}, "llm_invalid_output"
        counts["classified"] += 1
        meta = {
            "provider": response.provider,
            "model": response.model,
            "prompt_version": response.prompt_version,
        }
        return validate_classification(response.parsed, candidates), meta, None

    def _fill(
        self,
        proposal: IntakeProposal,
        thread: MailThread,
        candidates: list[Candidate],
        decision: Decision | None,
        meta: dict[str, str | None],
        error: str | None,
    ) -> None:
        proposal.conversation_id = thread.conversation_id
        proposal.subject = (thread.subject or "(sin asunto)")[:500]
        proposal.item_ids = thread.item_ids
        proposal.message_count = len(thread.messages)
        proposal.last_message_at = thread.last_message_at
        proposal.thread_state = thread.state
        proposal.candidates = [c.as_dict() for c in candidates]
        proposal.classification_error = error
        if decision is not None:
            proposal.relation = decision.relation
            proposal.task_id = decision.task_id  # type: ignore[assignment]
            proposal.confidence = decision.confidence
            proposal.result = decision.payload
            proposal.provider = meta.get("provider")
            proposal.model = meta.get("model")
            proposal.prompt_version = meta.get("prompt_version")
            return
        # Without the LLM: keep a previous classification if there is one;
        # otherwise point at the task the thread names by key.
        if proposal.relation is None:
            keyed = next((c for c in candidates if c.via == "clave"), None)
            proposal.task_id = keyed.task_id if keyed else None
