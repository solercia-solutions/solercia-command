"""Versioned classification rules per organization (E03, channel v2).

The file follows the schema of the methodology's ``reglas.json``: noise
sender lists, subject regexes, the mass-mail list, exceptions, identifier
regexes, matching order and taxonomy. It is validated with Pydantic and
compiled once into ``CompiledRules``; unknown keys are kept, so a newer
version with the same schema loads without code changes.

Where the file lives (``RECONCILIATION_RULES_PATH``):

- a JSON file → the same rules for every organization;
- a directory → ``<directory>/<organization slug>.json``;
- empty → the bundled SYNTHETIC example (``rules_example.json``).

Real rules contain institutional addresses: they stay outside the repo.
"""

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .classes import class_token

EXAMPLE_RULES_PATH = Path(__file__).with_name("rules_example.json")
DEFAULT_EVENT_EVIDENCE = ("Accepted", "Organizer")
_TASK_IDENTIFIER = "tarea"
_FLAGS = re.IGNORECASE


class RulesError(ValueError):
    """The rules file is missing, unreadable or invalid (message has no content)."""


class IdentifierSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    regex: str
    requiere_contexto: str | None = None


class RulesFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = Field(pattern=r"^\d+\.\d+(\.\d+)?$")
    buzon: str | None = None
    resultados: dict[str, Any] = Field(default_factory=dict)
    ruido: dict[str, Any] = Field(default_factory=dict)
    identificadores: dict[str, IdentifierSpec] = Field(default_factory=dict)
    orden_de_cruce: list[Any] = Field(default_factory=list)
    corte_de_citas_regex: list[str] = Field(default_factory=list)
    reuniones: dict[str, Any] = Field(default_factory=dict)

    @field_validator("identificadores")
    @classmethod
    def _has_task_identifier(cls, value: dict[str, IdentifierSpec]) -> dict:
        if _TASK_IDENTIFIER not in value:
            raise ValueError("identificadores.tarea es obligatorio")
        return value


@dataclass(frozen=True)
class CompiledIdentifier:
    name: str
    pattern: re.Pattern[str]
    context: re.Pattern[str] | None = None

    def tokens(self, text: str) -> set[str]:
        """Normalized matches; empty when the required context is absent."""

        if not text or (self.context is not None and not self.context.search(text)):
            return set()
        found: set[str] = set()
        for match in self.pattern.finditer(text):
            groups = [g for g in match.groups() if g]
            raw = "-".join(groups) if groups else match.group(0)
            found.add(re.sub(r"\s+", "", raw).upper())
        return found


@dataclass(frozen=True)
class CompiledRules:
    version: str
    digest: str
    owner: str | None
    sender_noise: tuple[str, ...]
    never_discard_senders: tuple[str, ...]
    mass_lists: tuple[str, ...]
    subject_noise: re.Pattern[str] | None
    security_subject: re.Pattern[str] | None
    subject_filter_mass_only: bool
    identifiers: tuple[CompiledIdentifier, ...]
    quote_markers: tuple[re.Pattern[str], ...]
    event_evidence_statuses: frozenset[str]
    taxonomy: tuple[str, ...]
    matching_order: tuple[str, ...]

    @property
    def task_identifier(self) -> CompiledIdentifier:
        return next(i for i in self.identifiers if i.name == _TASK_IDENTIFIER)

    def task_keys(self, text: str) -> set[str]:
        """``T-007`` → ``T-7`` (same normalization as the checklist IDs)."""

        return {normalize_task_ref(token) for token in self.task_identifier.tokens(text)}

    def object_identifiers(self) -> tuple[CompiledIdentifier, ...]:
        return tuple(i for i in self.identifiers if i.name != _TASK_IDENTIFIER)


def normalize_task_ref(value: str) -> str:
    match = re.fullmatch(r"\s*([A-Za-z][A-Za-z0-9]{0,9})-0*(\d+)\s*", value or "")
    if not match:
        return (value or "").strip().upper()
    return f"{match.group(1).upper()}-{int(match.group(2))}"


def _compile(pattern: str, where: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, _FLAGS)
    except re.error as exc:
        raise RulesError(f"Expresión regular inválida en {where}.") from exc


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _first_token(value: str) -> str:
    return re.split(r"[\s(]", value.strip(), maxsplit=1)[0].lower()


def _sender_noise(noise: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key, group in noise.items():
        if not key.startswith("remitentes"):
            continue
        items = group.get("valores") if isinstance(group, dict) else group
        values += [v.strip().lower() for v in _strings(items) if v.strip()]
    return tuple(dict.fromkeys(values))


def _subject_noise(noise: dict[str, Any]) -> re.Pattern[str] | None:
    parts = [
        value
        for key, value in noise.items()
        if key.startswith("asunto_regex") and not key.endswith("_fuente") and isinstance(value, str)
    ]
    if not parts:
        return None
    for part in parts:
        _compile(part, "ruido.asunto_regex")
    return _compile("|".join(f"(?:{p})" for p in parts), "ruido.asunto_regex")


def _mass_lists(noise: dict[str, Any]) -> tuple[str, ...]:
    raw = noise.get("lista_masiva")
    values = _strings(raw.get("valor") if isinstance(raw, dict) else raw)
    return tuple(v.strip().lower() for v in values if v.strip())


def _never_discard(exceptions: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key, items in exceptions.items():
        if "no_descartar_remitentes" in key:
            values += [_first_token(v) for v in _strings(items) if v.strip()]
    return tuple(dict.fromkeys(values))


def _taxonomy(results: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(token for r in results if (token := class_token(r))))


def _digest(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def compile_rules(raw: dict[str, Any]) -> CompiledRules:
    try:
        parsed = RulesFile.model_validate(raw)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise RulesError(f"Reglas inválidas: {', '.join(fields)}.") from exc

    noise = parsed.ruido
    exceptions = noise.get("excepciones") if isinstance(noise.get("excepciones"), dict) else {}
    security = exceptions.get("asunto_seguridad_regex")
    identifiers = tuple(
        CompiledIdentifier(
            name=name,
            pattern=_compile(spec.regex, f"identificadores.{name}"),
            context=(
                _compile(spec.requiere_contexto, f"identificadores.{name}")
                if spec.requiere_contexto
                else None
            ),
        )
        for name, spec in parsed.identificadores.items()
    )
    meetings = parsed.reuniones
    statuses = _strings(meetings.get("estados_con_asistencia")) or list(DEFAULT_EVENT_EVIDENCE)
    return CompiledRules(
        version=parsed.version,
        digest=_digest(raw),
        owner=(parsed.buzon or "").strip().lower() or None,
        sender_noise=_sender_noise(noise),
        never_discard_senders=_never_discard(exceptions),
        mass_lists=_mass_lists(noise),
        subject_noise=_subject_noise(noise),
        security_subject=(
            _compile(security, "ruido.excepciones") if isinstance(security, str) else None
        ),
        subject_filter_mass_only=bool(noise.get("asunto_solo_masivos", True)),
        identifiers=identifiers,
        quote_markers=tuple(
            _compile(p, "corte_de_citas_regex") for p in parsed.corte_de_citas_regex
        ),
        event_evidence_statuses=frozenset(statuses),
        taxonomy=_taxonomy(parsed.resultados),
        matching_order=tuple(
            str(step.get("criterio", step)) if isinstance(step, dict) else str(step)
            for step in parsed.orden_de_cruce
        ),
    )


def load_rules_file(path: Path) -> CompiledRules:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RulesError("No fue posible leer el archivo de reglas.") from exc
    if not isinstance(raw, dict):
        raise RulesError("El archivo de reglas debe ser un objeto JSON.")
    return compile_rules(raw)


def resolve_rules_path(base: str, organization_slug: str) -> Path:
    if not (base or "").strip():
        return EXAMPLE_RULES_PATH
    path = Path(base).expanduser()
    return path / f"{organization_slug}.json" if path.is_dir() else path


def load_rules_for_org(base: str, organization_slug: str) -> CompiledRules:
    return load_rules_file(resolve_rules_path(base, organization_slug))
