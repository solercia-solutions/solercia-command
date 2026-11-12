"""The 8 result classes of channel v2 (user decision, 2026-10-08).

Tokens are what the LLM returns and what metrics compare; labels are the
methodology's names (``Solo bitácora`` → ``solo_bitacora``). The mapping to
the C05 ``intake_proposals.relation`` keeps the table unchanged (no
migration): the full class travels in ``result["clase"]``.
"""

import unicodedata
from typing import Literal

ResultClass = Literal[
    "cierra",
    "avanza",
    "confirma",
    "tarea_nueva",
    "solo_bitacora",
    "informativo",
    "descartado",
    "no_concluyente",
]
CLASSES: tuple[ResultClass, ...] = (
    "cierra",
    "avanza",
    "confirma",
    "tarea_nueva",
    "solo_bitacora",
    "informativo",
    "descartado",
    "no_concluyente",
)
#: Classes that only make sense with an existing task.
TASK_CLASSES: frozenset[str] = frozenset({"cierra", "avanza", "confirma"})


def class_token(label: str | None) -> ResultClass | None:
    """``"Solo bitácora"`` → ``"solo_bitacora"``; unknown labels → ``None``."""

    if not label:
        return None
    folded = unicodedata.normalize("NFKD", label)
    plain = "".join(c for c in folded if not unicodedata.combining(c)).casefold()
    token = "_".join(plain.replace("-", " ").split())
    return token if token in CLASSES else None  # type: ignore[return-value]


def relation_for(clase: str, task_id: object | None) -> str:
    """C05 relation for a v2 class (``intake_proposals`` CHECK unchanged).

    ``no_concluyente`` keeps the task it points at (forced by key) so a person
    sees it next to that task; without one it is not actionable.
    """

    if clase == "tarea_nueva":
        return "tarea_nueva"
    if task_id is not None and (clase in TASK_CLASSES or clase == "no_concluyente"):
        return "tarea_existente"
    return "irrelevante"
