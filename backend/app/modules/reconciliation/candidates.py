"""Pure candidate selection (C05): which active tasks a thread may be about.

Tasks a thread mentions by key (``T-205``, ``SGSI-12``…) come first with
``via="clave"``; the rest of the ``k`` slots are filled by cosine similarity
between the thread and task embeddings (``via="similitud"``). Cosine runs in
Python: a few hundred tasks per organization do not justify pgvector.
"""

import hashlib
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

_DESCRIPTION_CHARS = 280
_EMBEDDING_TEXT_CHARS = 400


@dataclass(frozen=True)
class TaskSnapshot:
    id: uuid.UUID
    #: Label shown to people and to the LLM (external key or CODE-N).
    ref: str | None
    title: str
    description: str
    #: Normalized keys a thread may mention (``T-7``, ``SGSI-12``).
    keys: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    task_id: uuid.UUID
    ref: str
    title: str
    score: float
    via: Literal["clave", "similitud"]

    def as_dict(self) -> dict:
        return {
            "task_id": str(self.task_id),
            "ref": self.ref,
            "title": self.title,
            "score": round(self.score, 4),
            "via": self.via,
        }


def task_embedding_text(task: TaskSnapshot) -> str:
    description = " ".join((task.description or "").split())[:_DESCRIPTION_CHARS]
    head = f"{task.ref} {task.title}" if task.ref else task.title
    text = f"{head}. {description}" if description else head
    return text[:_EMBEDDING_TEXT_CHARS]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


def build_key_index(tasks: Sequence[TaskSnapshot]) -> dict[str, TaskSnapshot]:
    index: dict[str, TaskSnapshot] = {}
    for task in tasks:
        for key in task.keys:
            index.setdefault(key, task)
    return index


def select_candidates(
    *,
    mentioned_keys: set[str],
    key_index: Mapping[str, TaskSnapshot],
    thread_vector: Sequence[float] | None,
    task_vectors: Mapping[uuid.UUID, Sequence[float]],
    tasks: Mapping[uuid.UUID, TaskSnapshot],
    k: int,
) -> list[Candidate]:
    picked: list[tuple[TaskSnapshot, float, Literal["clave", "similitud"]]] = []
    seen: set[uuid.UUID] = set()
    for key in sorted(mentioned_keys):
        task = key_index.get(key)
        if task is not None and task.id not in seen and len(picked) < k:
            picked.append((task, 1.0, "clave"))
            seen.add(task.id)

    if thread_vector is not None:
        ranked = sorted(
            (
                (cosine(thread_vector, vector), str(task_id), task_id)
                for task_id, vector in task_vectors.items()
                if task_id not in seen and task_id in tasks
            ),
            reverse=True,
        )
        for score, _, task_id in ranked[: max(k - len(picked), 0)]:
            picked.append((tasks[task_id], score, "similitud"))

    labels: set[str] = set()
    candidates = []
    for position, (task, score, via) in enumerate(picked, start=1):
        label = task.ref if task.ref and task.ref.upper() not in labels else f"C{position}"
        labels.add(label.upper())
        candidates.append(Candidate(task.id, label, task.title, score, via))
    return candidates
