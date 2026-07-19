"""Business logic for GLPI assignee homologation (change 17-adapter-glpi).

This module currently holds the MATCHING CASCADE only (Lote 7, UH-R2) —
PURE functions, no DB session, no HTTP: ``org_users``/``existing_link`` are
plain in-memory instances the caller (Lote 8's sync orchestration) resolves
beforehand. The queue/link persistence orchestration (``run_sync``,
``resolve_unmatched_entry``, ...) is added in Lote 8.

Cascada determinística (design.md "Algoritmo de homologación"): correo
exacto normalizado -> documento exacto normalizado -> nombre normalizado
(``difflib.SequenceMatcher``, NUNCA auto-confirma, solo sugiere). Un link
``(connector_id, glpi_user_id)`` ya existente salta la cascada completa.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING
from uuid import UUID

from app.integrations.dtos import ExternalPerson
from app.shared.enums import MatchMethod

if TYPE_CHECKING:
    from app.modules.glpi_sync.models import GlpiUserLink
    from app.modules.users.models import User

# Below this `difflib` similarity ratio, a name is NOT similar enough to
# suggest as a candidate at all (design.md doesn't fix an exact number —
# 0.75 is a deliberately conservative threshold: high enough to exclude
# unrelated names, low enough to still catch minor spelling variance
# between GLPI's `firstname realname` and the platform's four-part name).
_NAME_MATCH_THRESHOLD = 0.75


def norm_email(email: str) -> str:
    """Case-insensitive, whitespace-trimmed email normalization."""

    return email.strip().lower()


def norm_doc(document: str) -> str:
    """Keep only digits — strips dots/dashes/spaces/prefixes (e.g. "CC")
    from a Colombian identity document."""

    return "".join(char for char in document if char.isdigit())


def norm_name(name: str) -> str:
    """Lowercase, accent-stripped (Unicode NFKD), whitespace-collapsed
    normalization — "José  MARÍA" and "jose maria" normalize identically.
    """

    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def _platform_full_name(user: "User") -> str:
    """GLPI's name is ``firstname realname``; the platform's is the four
    Colombian name parts (design.md "Algoritmo de homologación")."""

    parts = (
        user.primer_nombre,
        user.segundo_nombre,
        user.primer_apellido,
        user.segundo_apellido,
    )
    return " ".join(part for part in parts if part)


@dataclass(frozen=True)
class MatchCandidate:
    """A SUGGESTED (never auto-confirmed) name-match candidate."""

    user_id: UUID
    score: float
    reason: str = "name"


@dataclass(frozen=True)
class MatchResult:
    """Outcome of running :func:`match_assignee` for one GLPI person.

    ``matched_user_id``/``match_method`` are BOTH set together (an
    auto-confirmed match: ``email``/``document``, or ``skipped=True``
    reusing an existing link's ``match_method=None`` since the cascade
    never actually ran). ``candidates`` is populated ONLY by the name
    level — never alongside a confirmed match.
    """

    matched_user_id: UUID | None
    match_method: MatchMethod | None
    candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)
    skipped: bool = False


def match_assignee(
    person: ExternalPerson,
    org_users: Sequence["User"],
    existing_link: "GlpiUserLink | None",
) -> MatchResult:
    """Run the determinstic cascade (correo -> documento -> nombre) for one
    GLPI-assigned ``person`` against the organization's ``org_users``.

    An ``existing_link`` for this exact ``(connector_id, glpi_user_id)``
    short-circuits EVERYTHING — the cascade never runs (user-homologation
    spec, "link ya existente ... se salta la cascada completa").
    """

    if existing_link is not None:
        return MatchResult(
            matched_user_id=existing_link.user_id, match_method=None, skipped=True
        )

    if person.email:
        target_email = norm_email(person.email)
        for user in org_users:
            if user.email and norm_email(user.email) == target_email:
                return MatchResult(matched_user_id=user.id, match_method=MatchMethod.email)

    if person.document:
        target_doc = norm_doc(person.document)
        if target_doc:
            for user in org_users:
                if user.numero_documento and norm_doc(user.numero_documento) == target_doc:
                    return MatchResult(
                        matched_user_id=user.id, match_method=MatchMethod.document
                    )

    candidates = _name_candidates(person, org_users)
    return MatchResult(matched_user_id=None, match_method=None, candidates=candidates)


def _name_candidates(
    person: ExternalPerson, org_users: Sequence["User"]
) -> tuple[MatchCandidate, ...]:
    """Level 3 of the cascade — NEVER auto-confirms, only suggests
    candidates ordered by descending similarity score."""

    if not person.display_name:
        return ()

    target_name = norm_name(person.display_name)
    if not target_name:
        return ()

    scored: list[MatchCandidate] = []
    for user in org_users:
        candidate_name = norm_name(_platform_full_name(user))
        if not candidate_name:
            continue
        ratio = SequenceMatcher(None, target_name, candidate_name).ratio()
        if ratio >= _NAME_MATCH_THRESHOLD:
            scored.append(MatchCandidate(user_id=user.id, score=ratio, reason="name"))

    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return tuple(scored)
