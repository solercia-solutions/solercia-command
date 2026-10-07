"""Pure thread building for the classification channel (C05).

No database, no clock, no LLM. Groups mail ``IntakeItem`` projections into
threads and derives their deterministic state:

- **Key**: ``conv:<conversation_id>`` when the provider observed one.
  Otherwise ``subj:<hash>`` over the normalized subject (``RE/RV/FW/Fwd/TR``
  stripped, accents folded) and the counterparts: two messages with the same
  subject join when they share a counterpart (participants other than the
  ingesting mailbox and the senders of outbound mail). The hash material is
  the earliest message's sender and recipients, so the key stays stable
  while the thread grows.
- **State**: ``respondido`` when an outbound message is later than the last
  inbound one; ``pendiente_respuesta`` when the last inbound is unanswered;
  ``solo_saliente`` when there is no inbound (own follow-up). A message with
  unknown direction counts as inbound (conservative: it shows as pending).

Text helpers cut quoted history (same delimiters the manual TAREAS cut
uses) and extract task keys such as ``T-205``, ``SGSI-12`` or ``CP-13``.
"""

import hashlib
import html
import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ThreadState = Literal["respondido", "pendiente_respuesta", "solo_saliente"]
THREAD_STATES: tuple[ThreadState, ...] = ("respondido", "pendiente_respuesta", "solo_saliente")

_SUBJECT_PREFIX = re.compile(r"^\s*(?:re|rv|fw|fwd|tr)\s*(?:\[\d+\])?\s*:\s*", re.IGNORECASE)
_QUOTE_START = re.compile(
    r"^(?:De:|From:|-{3,}\s*(?:Original Message|Mensaje original)|_{10,}\s*$"
    r"|El .{5,120} escribió:|On .{5,120} wrote:)",
    re.MULTILINE | re.IGNORECASE,
)
_HTML_BLOCK = re.compile(r"(?is)<(script|style|head).*?</\1>")
_HTML_BREAK = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>")
_HTML_TAG = re.compile(r"<[^>]+>")
_TASK_KEY = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{0,9})-(\d{1,5})(?![A-Za-z0-9])")


@dataclass(frozen=True)
class MailItem:
    """Projection of a mail ``IntakeItem`` (the adapter builds it)."""

    id: uuid.UUID
    conversation_id: str | None
    subject: str
    sender: str
    recipients: tuple[str, ...]
    cc: tuple[str, ...]
    direction: str | None
    occurred_at: datetime
    body: str
    #: Canonical address of the account that ingested the item, if known.
    mailbox: str | None = None

    @property
    def is_outbound(self) -> bool:
        return self.direction == "outbound"


@dataclass(frozen=True)
class MailThread:
    key: str
    conversation_id: str | None
    messages: tuple[MailItem, ...]
    state: ThreadState

    @property
    def subject(self) -> str:
        return self.messages[-1].subject

    @property
    def item_ids(self) -> list[str]:
        return sorted(str(message.id) for message in self.messages)

    @property
    def last_message_at(self) -> datetime:
        return self.messages[-1].occurred_at


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def normalize_subject(subject: str) -> str:
    text = subject or ""
    while True:
        stripped = _SUBJECT_PREFIX.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return " ".join(_fold(text).split())


def _address(value: str) -> str:
    return (value or "").strip().lower()


def html_to_text(text: str) -> str:
    if "<" not in text or ">" not in text:
        return text
    text = _HTML_BLOCK.sub("", text)
    text = _HTML_BREAK.sub("\n", text)
    return html.unescape(_HTML_TAG.sub("", text))


def new_content(body: str) -> str:
    """Body without HTML, blank lines nor quoted history."""

    text = html_to_text(body or "").replace("\xa0", " ").replace("​", "")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    match = _QUOTE_START.search(text)
    if match and match.start() > 0:
        text = text[: match.start()]
    return text.strip()


def extract_task_keys(text: str) -> set[str]:
    """Normalized ``PREFIX-N`` tokens (``t-07`` → ``T-7``)."""

    return {f"{prefix.upper()}-{int(number)}" for prefix, number in _TASK_KEY.findall(text or "")}


def normalize_task_key(key: str) -> str | None:
    found = extract_task_keys(key)
    return next(iter(found)) if len(found) == 1 else None


def thread_state(messages: list[MailItem] | tuple[MailItem, ...]) -> ThreadState:
    inbound = [m.occurred_at for m in messages if not m.is_outbound]
    if not inbound:
        return "solo_saliente"
    last_inbound = max(inbound)
    if any(m.is_outbound and m.occurred_at > last_inbound for m in messages):
        return "respondido"
    return "pendiente_respuesta"


def _ordered(messages: list[MailItem]) -> tuple[MailItem, ...]:
    return tuple(sorted(messages, key=lambda m: (m.occurred_at, str(m.id))))


def _fallback_groups(items: list[MailItem], owners: set[str]) -> list[list[MailItem]]:
    """Union-find over same-subject items that share a counterpart."""

    def counterparts(item: MailItem) -> set[str]:
        people = {_address(item.sender), *map(_address, item.recipients), *map(_address, item.cc)}
        mine = owners | ({_address(item.mailbox)} if item.mailbox else set())
        return {p for p in people if p and p not in mine}

    by_subject: dict[str, list[MailItem]] = defaultdict(list)
    for item in items:
        by_subject[normalize_subject(item.subject)].append(item)

    groups: list[list[MailItem]] = []
    for same_subject in by_subject.values():
        parent = list(range(len(same_subject)))
        seen: dict[str, int] = {}
        for index, item in enumerate(same_subject):
            for person in counterparts(item):
                if person in seen:
                    parent[_find(parent, index)] = _find(parent, seen[person])
                else:
                    seen[person] = index
        components: dict[int, list[MailItem]] = defaultdict(list)
        for index, item in enumerate(same_subject):
            components[_find(parent, index)].append(item)
        groups.extend(components.values())
    return groups


def _find(parent: list[int], i: int) -> int:
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _fallback_key(messages: tuple[MailItem, ...]) -> str:
    first = messages[0]
    material = "|".join(
        [
            normalize_subject(first.subject),
            _address(first.sender),
            ",".join(sorted(_address(r) for r in first.recipients)),
        ]
    )
    return "subj:" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def group_threads(items: list[MailItem]) -> list[MailThread]:
    """Threads, most recent last message first."""

    by_conversation: dict[str, list[MailItem]] = defaultdict(list)
    loose: list[MailItem] = []
    for item in items:
        if item.conversation_id:
            by_conversation[item.conversation_id].append(item)
        else:
            loose.append(item)

    threads = []
    for conversation_id, messages in by_conversation.items():
        ordered = _ordered(messages)
        threads.append(
            MailThread(f"conv:{conversation_id}", conversation_id, ordered, thread_state(ordered))
        )
    owners = {_address(item.sender) for item in items if item.is_outbound}
    for group in _fallback_groups(loose, owners):
        ordered = _ordered(group)
        threads.append(MailThread(_fallback_key(ordered), None, ordered, thread_state(ordered)))
    threads.sort(key=lambda t: (t.last_message_at, t.key), reverse=True)
    return threads
