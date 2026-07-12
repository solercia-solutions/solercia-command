"""Pydantic schemas and query-string helpers for the global search module.

Concentrates the two pure, side-effect-free building blocks the search
pipeline needs before touching the database: escaping user input for a safe
``ILIKE`` pattern and parsing/validating the ``types`` filter (design.md,
Interfaces/Contracts).
"""

import re
import uuid

from pydantic import BaseModel

#: Catalog of entity types accepted by ``?types=`` (global-search.md, R3).
ENTITY_TYPES: frozenset[str] = frozenset({"task", "project", "comment"})

# Matches the three LIKE/ILIKE metacharacters that must be escaped before a
# user-supplied string is wrapped as a `%...%` pattern.
_LIKE_ESCAPE_RE = re.compile(r"([%_\\])")


def escape_like(value: str) -> str:
    r"""Escape ``%``, ``_`` and ``\\`` so ``value`` is a literal ILIKE substring.

    Postgres' default ``LIKE``/``ILIKE`` escape character is ``\\``; prefixing
    every metacharacter with it neutralizes ``%``/``_`` as wildcards and
    ``\\`` itself as an escape introducer (design.md, "Seguridad").
    """

    return _LIKE_ESCAPE_RE.sub(r"\\\1", value)


def parse_types(types: str | None) -> set[str]:
    """Parse the ``types`` query param (CSV) into a validated set.

    ``None`` (the param was omitted) returns the full catalog — the
    documented default. Any other value is split on commas, trimmed, and
    validated: an empty result (empty string, or only commas/whitespace) or
    any token outside :data:`ENTITY_TYPES` raises ``ValueError`` so the
    caller (the service layer) can translate it into a ``422``.
    """

    if types is None:
        return set(ENTITY_TYPES)

    tokens = [token.strip() for token in types.split(",")]
    tokens = [token for token in tokens if token]
    if not tokens:
        raise ValueError("El filtro 'types' no puede estar vacío.")

    invalid = set(tokens) - ENTITY_TYPES
    if invalid:
        raise ValueError(
            f"Tipo(s) inválido(s) en 'types': {', '.join(sorted(invalid))}. "
            f"Valores permitidos: {', '.join(sorted(ENTITY_TYPES))}."
        )
    return set(tokens)


class SearchResult(BaseModel):
    """A single row of the global search result list.

    ``task_key``/``task_id`` are only populated for the entity types where
    they make sense: ``task_key`` (e.g. ``"SDM-7"``) for ``entity_type ==
    "task"``; ``task_id`` — the parent task's id, required as extra context
    by global-search.md R1 — for ``entity_type == "comment"``.
    """

    entity_type: str
    id: uuid.UUID
    title: str
    snippet: str
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    task_key: str | None = None
    task_id: uuid.UUID | None = None
