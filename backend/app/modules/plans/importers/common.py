"""Shared value objects and deterministic cell parsers for the plan importers."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert


class SourceFormatError(ValueError):
    """The source does not have the structure the parser expects."""


@dataclass(frozen=True)
class SourceInfo:
    name: str
    sha256: str
    size_bytes: int

    @classmethod
    def of(cls, path: Path) -> "SourceInfo":
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return cls(name=path.name, sha256=digest.hexdigest(), size_bytes=path.stat().st_size)


@dataclass
class ParsedPlan:
    """One plan read from its source, ready for the 45a write seam."""

    kind: str
    source: SourceInfo
    plan: PlanUpsert
    activities: list[PlanActivityUpsert]
    warnings: list[str] = field(default_factory=list)
    #: ``{activity code: literal cross-reference text}`` (PTR -> PSPI column).
    cross_refs: dict[str, str] = field(default_factory=dict)
    #: Source facts worth reporting that are not persisted.
    facts: dict[str, Any] = field(default_factory=dict)


_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}
_ES_DATE = re.compile(r"^\s*(\d{1,2})-([a-záéíóú]{3})[a-z]*-(\d{4})\s*$", re.IGNORECASE)
_TARGET = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:→|->)\s*(\d+(?:[.,]\d+)?)\s*%")
_ISO_CONTROL = re.compile(r"\b(\d{1,2}\.\d{1,2})\b")
_OM_CODE = re.compile(r"\bOM-\d{2}\b")
_VERSION = re.compile(r"_(v\d+_\d{8})", re.IGNORECASE)


def normalize(text: str | None) -> str:
    """Lowercase, accent-free, single-spaced (for tolerant comparisons)."""

    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.lower().split())


def clean(text: Any) -> str | None:
    """Trimmed single-spaced string; ``None`` for empty cells and ``-``."""

    if text is None:
        return None
    value = " ".join(str(text).split())
    return value if value and value != "-" else None


def parse_es_date(text: str | None) -> date | None:
    """``15-dic-2026`` -> ``date(2026, 12, 15)``; prose (``Continuo``) -> ``None``."""

    match = _ES_DATE.match(text or "")
    if not match:
        return None
    month = _MONTHS.get(normalize(match.group(2))[:3])
    if month is None:
        return None
    return date(int(match.group(3)), month, int(match.group(1)))


def parse_target(text: str | None) -> tuple[Decimal | None, Decimal | None]:
    """``0% → 100%`` -> ``(Decimal(0), Decimal(100))``."""

    match = _TARGET.search(text or "")
    if not match:
        return None, None
    return tuple(Decimal(group.replace(",", ".")) for group in match.groups())  # type: ignore[return-value]


def parse_iso_controls(text: str | None) -> list[str] | None:
    controls = list(dict.fromkeys(_ISO_CONTROL.findall(text or "")))
    return controls or None


def parse_om_codes(text: str | None) -> list[str] | None:
    codes = list(dict.fromkeys(_OM_CODE.findall(text or "")))
    return codes or None


def version_from_filename(name: str) -> str | None:
    """``..._v2_20260120.docx`` -> ``v2_20260120``."""

    match = _VERSION.search(name)
    return match.group(1).lower() if match else None


def require_unique_codes(activities: list[PlanActivityUpsert], label: str) -> None:
    """A repeated code would make the idempotent upsert overwrite silently."""

    seen: set[str] = set()
    repeated: set[str] = set()
    for activity in activities:
        (repeated if activity.code in seen else seen).add(activity.code)
    if repeated:
        raise SourceFormatError(
            f"El {label} repite códigos de actividad: {', '.join(sorted(repeated))}. "
            "Corrige la fuente antes de importar."
        )


def is_mine(responsible: str | None, markers: tuple[str, ...]) -> bool:
    """Whole-word, accent-insensitive match of any marker in ``responsible``."""

    haystack = normalize(responsible)
    return any(re.search(rf"\b{re.escape(normalize(m))}\b", haystack) for m in markers)
