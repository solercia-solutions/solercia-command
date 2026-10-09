"""Deterministic stages of channel v2 (E03), in the methodology's order.

1. **Units** — front B: threads (``conversation_id`` or ``subj:`` + the
   normalized subject, the methodology's key); front A: every sent message
   and every calendar event is its own record. Stable order.
2. **Noise** — per inbound message: outbound and security subjects are never
   noise; mail to a mass list (``todos@``) is; never-discard senders are kept;
   a noise sender is noise only when the mailbox owner is not in to/cc; the
   subject filter applies only to mass mail (not addressed to the owner).
   A thread is discarded only when every inbound message is noise and it has
   no outbound message.
3. **Identifiers** — explicit task IDs (``T-xx``) and object identifiers
   (case, filing, contract…) in subject, body and attachment names become
   FORCED candidates.
4. **Thread state** — ``respondido`` / ``pendiente_respuesta`` /
   ``solo_saliente``; a sent record carries the state of its thread.
5. **Events** — cancelled, or without attendance evidence (status not in the
   rules' list) → ``no_concluyente`` without the LLM.

No database, clock nor LLM: the same input always gives the same output.
"""

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .rules import CompiledRules, normalize_task_ref
from .threads import ThreadState, html_to_text

RecordKind = Literal["in", "out", "event"]
UnitKind = Literal["thread", "sent", "event"]
Via = str  # "id_explicito" | "identificador:<name>" | "similitud"

_SUBJECT_PREFIX = re.compile(r"^\s*((re|rv|fw|fwd|tr)\s*:\s*)+", re.IGNORECASE)
_QUOTE_MIN_OFFSET = 40
_DESCRIPTION_CHARS = 280
#: A literal subject shorter than this («Informe», «Solicitud») says nothing.
_SUBJECT_MATCH_MIN_CHARS = 12


@dataclass(frozen=True)
class MailRecord:
    """One message or calendar event (the adapter or the golden loader builds it)."""

    id: str
    kind: RecordKind
    conversation_id: str | None
    subject: str
    sender: str
    to: tuple[str, ...]
    cc: tuple[str, ...]
    occurred_at: datetime
    body: str = ""
    attachments: tuple[str, ...] = ()
    response_status: str | None = None
    is_cancelled: bool = False


@dataclass(frozen=True)
class Unit:
    kind: UnitKind
    key: str
    records: tuple[MailRecord, ...]
    state: ThreadState | None
    #: Thread of a sent record (equals ``key`` for threads).
    thread_key: str | None = None

    @property
    def subject(self) -> str:
        return self.records[-1].subject

    @property
    def last_at(self) -> datetime:
        return self.records[-1].occurred_at

    @property
    def conversation_id(self) -> str | None:
        return next((r.conversation_id for r in self.records if r.conversation_id), None)


@dataclass(frozen=True)
class TaskEntry:
    """A checklist task as the classifier sees it (open or closed)."""

    id: str
    ref: str
    title: str
    detail: str = ""
    status: str = ""
    observations: str = ""

    @property
    def matching_text(self) -> str:
        return f"{self.title}\n{self.detail}\n{self.observations}"


@dataclass(frozen=True)
class CandidateV2:
    task_id: str
    ref: str
    title: str
    status: str
    score: float
    via: Via

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "ref": self.ref,
            "title": self.title,
            "status": self.status,
            "score": round(self.score, 4),
            "via": self.via,
        }


@dataclass(frozen=True)
class Identifiers:
    task_keys: set[str]
    objects: dict[str, set[str]] = field(default_factory=dict)


# --- text ---------------------------------------------------------------------------------


def normalize_subject(subject: str) -> str:
    return _SUBJECT_PREFIX.sub("", subject or "").strip().lower()


def thread_key(record: MailRecord) -> str:
    return record.conversation_id or "subj:" + normalize_subject(record.subject)


def clean_body(body: str, rules: CompiledRules | None = None) -> str:
    """HTML to text, blank lines out, quoted history cut (marker after char 40)."""

    text = html_to_text(body or "").replace("\xa0", " ")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    for marker in rules.quote_markers if rules else ():
        match = marker.search(text, _QUOTE_MIN_OFFSET)
        if match:
            text = text[: match.start()]
    return text.strip()


def _address(value: str) -> str:
    return (value or "").strip().lower()


def unit_text(unit: Unit, rules: CompiledRules | None = None) -> str:
    parts: list[str] = []
    for record in unit.records:
        parts += [record.subject, clean_body(record.body, rules), " ".join(record.attachments)]
    return "\n".join(p for p in parts if p)


def ref_sort_key(ref: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z]+)-(\d+)", ref or "")
    return (match.group(1).upper(), int(match.group(2)), ref) if match else (ref, 0, ref)


# --- units and thread state ---------------------------------------------------------------


def _ordered(records: Sequence[MailRecord]) -> tuple[MailRecord, ...]:
    return tuple(sorted(records, key=lambda r: (r.occurred_at, r.id)))


def thread_state(records: Sequence[MailRecord]) -> ThreadState:
    inbound = [r.occurred_at for r in records if r.kind != "out"]
    if not inbound:
        return "solo_saliente"
    last_inbound = max(inbound)
    if any(r.kind == "out" and r.occurred_at > last_inbound for r in records):
        return "respondido"
    return "pendiente_respuesta"


def build_units(records: Sequence[MailRecord]) -> list[Unit]:
    """Threads (newest first), then sent records, then events; ties by key."""

    by_thread: dict[str, list[MailRecord]] = defaultdict(list)
    for record in records:
        if record.kind != "event":
            by_thread[thread_key(record)].append(record)

    threads = []
    state_of: dict[str, ThreadState] = {}
    for key, members in by_thread.items():
        ordered = _ordered(members)
        state_of[key] = thread_state(ordered)
        threads.append(Unit("thread", key, ordered, state_of[key], key))
    threads.sort(key=lambda u: (u.last_at, u.key), reverse=True)

    sent = [
        Unit("sent", r.id, (r,), state_of[thread_key(r)], thread_key(r))
        for r in records
        if r.kind == "out"
    ]
    events = [Unit("event", r.id, (r,), None) for r in records if r.kind == "event"]
    sent.sort(key=lambda u: (u.last_at, u.key), reverse=True)
    events.sort(key=lambda u: (u.last_at, u.key), reverse=True)
    return threads + sent + events


# --- noise and prechecks --------------------------------------------------------------------


def message_noise(record: MailRecord, rules: CompiledRules) -> str | None:
    """Reason why ONE inbound message is noise, or ``None`` (rules v2 order)."""

    if record.kind != "in":
        return None
    subject = record.subject or ""
    if rules.security_subject and rules.security_subject.search(subject):
        return None
    to = [_address(a) for a in record.to]
    cc = [_address(a) for a in record.cc]
    fields = {"to": to, "cc": cc}
    mass_targets = [a for name in rules.mass_fields for a in fields.get(name, [])]
    if any(mass in address for address in mass_targets for mass in rules.mass_lists):
        return "lista_masiva"
    sender = _address(record.sender)
    if any(exception.matches(sender, subject) for exception in rules.exceptions):
        return None
    if any(pattern in sender for pattern in rules.sender_noise_always):
        return "remitente_automatico"
    directed = bool(rules.owner) and rules.owner in {*to, *cc}
    if not directed and any(pattern in sender for pattern in rules.sender_noise):
        return "remitente"
    mass_only = rules.subject_filter_mass_only
    subject_hit = bool(rules.subject_noise and rules.subject_noise.search(subject))
    return "asunto" if subject_hit and (not directed or not mass_only) else None


def precheck(unit: Unit, rules: CompiledRules) -> tuple[str, str] | None:
    """``(class, reason)`` decided without the LLM, or ``None``."""

    if unit.kind == "event":
        (event,) = unit.records
        if event.is_cancelled:
            return "no_concluyente", "evento_cancelado"
        if (event.response_status or "") not in rules.event_evidence_statuses:
            return "no_concluyente", "evento_sin_asistencia"
        return None
    if unit.kind != "thread" or any(r.kind == "out" for r in unit.records):
        return None
    reasons = [message_noise(r, rules) for r in unit.records]
    if reasons and all(reasons):
        return "descartado", f"ruido:{reasons[0]}"
    return None


# --- identifiers and candidates ----------------------------------------------------------------


def unit_identifiers(unit: Unit, rules: CompiledRules) -> Identifiers:
    text = unit_text(unit, rules)
    objects = {
        identifier.name: tokens
        for identifier in rules.object_identifiers()
        if (tokens := identifier.tokens(text))
    }
    return Identifiers(task_keys=rules.task_keys(text), objects=objects)


def _candidate(task: TaskEntry, score: float, via: Via) -> CandidateV2:
    return CandidateV2(task.id, task.ref, task.title, task.status, score, via)


#: E07b: an object token shared by more tasks than this is generic (a procedure code cited by
#: many tasks) and does not force a candidate in the ``specific`` mode.
OBJECT_MAX_SPREAD = 2


@dataclass(frozen=True)
class ObjectMatch:
    task: TaskEntry
    #: Fewest tasks sharing one of the matched tokens (1 = unique to this task).
    spread: int
    name: str


def object_matches(
    found: Identifiers, tasks: Sequence[TaskEntry], rules: CompiledRules
) -> list[ObjectMatch]:
    """Tasks sharing an object token with the unit, most specific first, ties by ref."""

    if not found.objects:
        return []
    identifiers = {i.name: i for i in rules.object_identifiers()}
    shared: dict[str, set[tuple[str, str]]] = {}
    for task in tasks:
        keys = {
            (name, token)
            for name in found.objects
            for token in found.objects[name] & identifiers[name].tokens(task.matching_text)
        }
        if keys:
            shared[task.id] = keys
    spread: dict[tuple[str, str], int] = defaultdict(int)
    for keys in shared.values():
        for key in keys:
            spread[key] += 1
    by_id = {t.id: t for t in tasks}
    matches = []
    for task_id, keys in shared.items():
        best = min(keys, key=lambda key: (spread[key], key))
        matches.append(ObjectMatch(by_id[task_id], spread[best], best[0]))
    matches.sort(key=lambda m: (m.spread, ref_sort_key(m.task.ref)))
    return matches


def forced_candidates(
    found: Identifiers,
    tasks: Sequence[TaskEntry],
    rules: CompiledRules,
    *,
    objects: Literal["forced", "specific"] = "forced",
    max_spread: int = OBJECT_MAX_SPREAD,
) -> list[CandidateV2]:
    """Explicit IDs first (by ref), then tasks sharing an object identifier.

    ``specific`` (E07b) forces only tokens shared by at most ``max_spread``
    tasks, most specific first: a code cited by many tasks says nothing.
    """

    by_ref = {normalize_task_ref(t.ref): t for t in tasks}
    picked: list[CandidateV2] = []
    seen: set[str] = set()
    for key in sorted(found.task_keys, key=ref_sort_key):
        task = by_ref.get(key)
        if task is not None and task.id not in seen:
            picked.append(_candidate(task, 1.0, "id_explicito"))
            seen.add(task.id)
    if objects == "specific":
        for match in object_matches(found, tasks, rules):
            if match.spread <= max_spread and match.task.id not in seen:
                picked.append(_candidate(match.task, 1.0, f"identificador:{match.name}"))
                seen.add(match.task.id)
        return picked
    if found.objects:
        identifiers = {i.name: i for i in rules.object_identifiers()}
        for task in sorted(tasks, key=lambda t: ref_sort_key(t.ref)):
            if task.id in seen:
                continue
            for name in sorted(found.objects):
                if found.objects[name] & identifiers[name].tokens(task.matching_text):
                    picked.append(_candidate(task, 1.0, f"identificador:{name}"))
                    seen.add(task.id)
                    break
    return picked


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return " ".join(plain.split())


def subject_candidates(
    unit: Unit, tasks: Sequence[TaskEntry], *, exclude: set[str], limit: int
) -> list[CandidateV2]:
    """Tasks whose title, detail or observations quote the thread subject literally.

    Methodology b.4, step 2: observations cite the subjects of earlier cuts
    between «», so a thread that continues reaches its task even when the
    embedding does not. Case and accents are ignored; a short subject forces
    nothing. Ordered by task ref.
    """

    subject = _fold(normalize_subject(unit.subject))
    if len(subject) < _SUBJECT_MATCH_MIN_CHARS or limit <= 0:
        return []
    picked = [
        _candidate(task, 1.0, "asunto")
        for task in sorted(tasks, key=lambda t: ref_sort_key(t.ref))
        if task.id not in exclude and subject in _fold(task.matching_text)
    ]
    return picked[:limit]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def rank_candidates(
    forced: Sequence[CandidateV2],
    unit_vector: Sequence[float] | None,
    task_vectors: Mapping[str, Sequence[float]],
    tasks: Sequence[TaskEntry],
    *,
    k: int,
) -> list[CandidateV2]:
    """Forced first, then cosine top-k; ties broken by task ref (stable)."""

    picked = list(forced[:k])
    seen = {c.task_id for c in picked}
    if unit_vector is not None and len(picked) < k:
        scored = sorted(
            (
                (-round(cosine(unit_vector, task_vectors[t.id]), 6), ref_sort_key(t.ref), t)
                for t in tasks
                if t.id not in seen and t.id in task_vectors
            ),
            key=lambda item: (item[0], item[1]),
        )
        picked += [_candidate(t, -score, "similitud") for score, _, t in scored[: k - len(picked)]]
    return picked


def task_embedding_text(task: TaskEntry, *, full: bool = False, max_chars: int = 2000) -> str:
    """Task text for retrieval: ref, title and a slice of the detail.

    ``full`` (E07b) adds the whole detail and the observations, where the
    methodology cites earlier subjects and objects, capped at ``max_chars``.
    """

    head = f"{task.ref} {task.title}".strip()
    if not full:
        detail = " ".join((task.detail or "").split())[:_DESCRIPTION_CHARS]
        return f"{head}. {detail}" if detail else head
    body = " ".join(f"{task.detail or ''} {task.observations or ''}".split())
    return (f"{head}. {body}" if body else head)[:max_chars]


# --- E07b: lexical ranking and rank fusion --------------------------------------------------

_TOKEN = re.compile(r"\w+")
#: Frequent Spanish function words; they carry no task signal.
_STOPWORDS_TEXT = (
    "a al ante con contra de del desde el en entre es esta este esto hacia hasta la las le "
    "les lo los mas me mi no nos o para pero por que se si sin sobre su sus te tu un una uno "
    "unos unas y ya ha he han fue ser son como cual cuando donde muy le favor buen buenos "
    "buenas dias tardes cordial saludo saludos gracias"
)
_STOPWORDS = frozenset(_STOPWORDS_TEXT.split())
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60


def lexical_tokens(text: str) -> list[str]:
    """Accent- and case-folded words; stopwords and single characters out."""

    return [
        token for token in _TOKEN.findall(_fold(text)) if len(token) > 1 and token not in _STOPWORDS
    ]


class LexicalIndex:
    """BM25 over the task text (``full`` adds detail and observations).

    Query terms count once (a long mail does not outweigh a short one); the
    ranking keeps only tasks sharing at least one term, ties by task ref.
    """

    def __init__(self, tasks: Sequence[TaskEntry], *, full: bool = False) -> None:
        self._tasks = sorted(tasks, key=lambda t: ref_sort_key(t.ref))
        self._docs: list[dict[str, int]] = []
        frequency: dict[str, int] = defaultdict(int)
        for task in self._tasks:
            counts: dict[str, int] = defaultdict(int)
            for token in lexical_tokens(task_embedding_text(task, full=full, max_chars=1 << 20)):
                counts[token] += 1
            self._docs.append(counts)
            for token in counts:
                frequency[token] += 1
        total = len(self._docs)
        self._lengths = [sum(d.values()) for d in self._docs]
        self._average = (sum(self._lengths) / total) if total else 0.0
        self._idf = {
            token: math.log(1 + (total - n + 0.5) / (n + 0.5)) for token, n in frequency.items()
        }

    def rank(self, query: str) -> list[tuple[TaskEntry, float]]:
        terms = sorted(set(lexical_tokens(query)) & self._idf.keys())
        scored = []
        for task, counts, length in zip(self._tasks, self._docs, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    norm = 1 - BM25_B + BM25_B * length / (self._average or 1.0)
                    score += self._idf[term] * tf * (BM25_K1 + 1) / (tf + BM25_K1 * norm)
            if score > 0:
                scored.append((round(score, 6), task))
        scored.sort(key=lambda item: (-item[0], ref_sort_key(item[1].ref)))
        return [(task, score) for score, task in scored]


def embedding_order(
    unit_vector: Sequence[float] | None,
    task_vectors: Mapping[str, Sequence[float]],
    tasks: Sequence[TaskEntry],
) -> list[tuple[TaskEntry, float]]:
    """Every task with a vector, by cosine (desc), ties by task ref."""

    if unit_vector is None:
        return []
    scored = [
        (round(cosine(unit_vector, task_vectors[t.id]), 6), t)
        for t in tasks
        if t.id in task_vectors
    ]
    scored.sort(key=lambda item: (-item[0], ref_sort_key(item[1].ref)))
    return [(task, score) for score, task in scored]


def ordered_candidates(
    forced: Sequence[CandidateV2],
    order: Sequence[tuple[TaskEntry, float]],
    *,
    k: int,
    via: Via,
) -> list[CandidateV2]:
    """Forced first, then ``order`` without repeats, up to ``k``."""

    picked = list(forced[:k])
    seen = {c.task_id for c in picked}
    for task, score in order:
        if len(picked) >= k:
            break
        if task.id not in seen:
            picked.append(_candidate(task, score, via))
            seen.add(task.id)
    return picked


def fused_candidates(
    forced: Sequence[CandidateV2],
    rankings: Sequence[Sequence[TaskEntry]],
    *,
    k: int,
    rrf_k: int = RRF_K,
) -> list[CandidateV2]:
    """Reciprocal rank fusion: score = Σ 1 / (rrf_k + rank); ties by task ref."""

    scores: dict[str, float] = defaultdict(float)
    by_id: dict[str, TaskEntry] = {}
    for ranking in rankings:
        for position, task in enumerate(ranking, start=1):
            scores[task.id] += 1.0 / (rrf_k + position)
            by_id[task.id] = task
    order = sorted(
        ((by_id[i], round(score, 9)) for i, score in scores.items()),
        key=lambda item: (-item[1], ref_sort_key(item[0].ref)),
    )
    return ordered_candidates(forced, order, k=k, via="rrf")
