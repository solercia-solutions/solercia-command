"""Pure tema→respondiente classification engine (change 22-intake-classifier,
design.md "Motor de reglas": ``ClassifierPort`` Protocol/Strategy +
``RuleBasedClassifier``).

NO database access, NO HTTP — a deterministic function of
``(IntakeItem, Sequence[IntakeRule])``. This is the ONE seam a future
``LLMClassifier`` would implement without touching ``service.py`` (precedent
``app/methodology/``: behavior is read FROM the strategy, never
``if provider == ...`` scattered through the codebase).
"""

import unicodedata
from collections.abc import Sequence
from typing import Protocol

from app.modules.intake.models import IntakeItem, IntakeRule


class ClassifierPort(Protocol):
    """Strategy contract: the first active rule whose criteria match GANA."""

    def classify(
        self, item: IntakeItem, rules: Sequence[IntakeRule]
    ) -> IntakeRule | None: ...


def _fold(text: str) -> str:
    """Case-insensitive, accent-insensitive normalization (stdlib only,
    design.md "Matching de texto" — no ``unidecode`` dependency).

    ``unicodedata.NFKD`` decomposes accented characters into base + combining
    mark; encoding to ASCII with ``errors="ignore"`` drops the marks (and any
    other non-ASCII codepoint); ``casefold()`` is the Unicode-aware,
    more-aggressive sibling of ``lower()``.
    """

    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return ascii_only.casefold()


def _field_value(item: IntakeItem, field: str) -> str:
    """Resolve ``field`` (intake-rules spec, "Criterios evaluables") to the
    ``IntakeItem`` attribute it reads from."""

    if field == "origin_actor":
        return item.origin_actor or ""
    if field == "domain":
        actor = item.origin_actor or ""
        return actor.rsplit("@", 1)[-1] if "@" in actor else ""
    if field == "title":
        return item.title or ""
    if field == "snippet":
        return item.snippet or ""
    if field == "source_provider":
        return item.source_provider or ""
    if field == "connector_id":
        return str(item.connector_id)
    return ""


def _match_criterion(item: IntakeItem, criterion: dict) -> bool:
    """Evaluate ONE ``{field, operator, value}`` condition."""

    field_value = _fold(_field_value(item, criterion.get("field", "")))
    operator = criterion.get("operator", "equals")
    value = criterion.get("value")

    if operator == "equals":
        return field_value == _fold(str(value))
    if operator == "contains":
        return _fold(str(value)) in field_value
    if operator == "in":
        candidates = value if isinstance(value, list) else [value]
        return field_value in {_fold(str(candidate)) for candidate in candidates}
    return False


def _match_rule(item: IntakeItem, rule: IntakeRule) -> bool:
    """A rule matches only if EVERY criterion matches (AND, intake-rules
    spec, "Criterios evaluables combinados con AND")."""

    criteria = rule.criteria or []
    if not criteria:
        return False
    return all(_match_criterion(item, criterion) for criterion in criteria)


class RuleBasedClassifier:
    """Deterministic ``ClassifierPort`` implementation — the ONLY classifier
    this change ships (an LLM-backed one is future scope, design.md)."""

    def classify(
        self, item: IntakeItem, rules: Sequence[IntakeRule]
    ) -> IntakeRule | None:
        """Return the FIRST rule (by the caller's own ordering) that is
        active AND matches ``item``; ``None`` if none does.

        Skips ``is_active=False`` rules itself (defense-in-depth, intake-rules
        spec "Reglas inactivas excluidas de la evaluación") even though the
        repository's ``list_active_rules_ordered`` already filters them —
        this function stays correct standalone, with an unfiltered list too.
        """

        for rule in rules:
            if not rule.is_active:
                continue
            if _match_rule(item, rule):
                return rule
        return None
