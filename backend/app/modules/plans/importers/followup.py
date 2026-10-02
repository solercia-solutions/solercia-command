"""Follow-up feed for loaded plans: period reports + task<->activity links.

Pure readers (no database) over three kinds of evidence, each one kept with a
literal quote and a coordinate so every written value can be traced back:

1. **PAI follow-up** already filled in the consolidated XLSX (45a P2). The
   period is the one marked ``x`` in the ``Ejecutado`` row of the activity —
   an explicit statement of the source, never inferred from dates. Exactly one
   executed period is required; otherwise the activity goes to review.
2. **Task links stated in the checklist itself**: ``[PSPI x.y]`` at the start
   of ``Tarea`` (role ``primary``), ``actividad x.y del Plan de Seguridad/PSPI``
   and ``control|riesgo Rnn`` in any text column (role ``contributes``).
   Unqualified mentions (bare ``Rnn``, ``actividad x.y`` without a plan,
   ``Plan de Acción``/``PTEP`` without an activity code) go to review.
3. **Cruce report** (PSPI vs checklist, 2026-08-14): the ``T-nn`` it names per
   PSPI activity become ``contributes`` links, except rows it qualifies as
   ``Sin cobertura`` (review).

Monthly ``Reporte Seguimiento Plan de Acción`` DOCX files are indicator-level
(policy), carry no activity code and, for Seguridad Digital, an empty
percentage; they produce review notes only.
"""

import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.modules.plans.importers.common import SourceFormatError, SourceInfo, clean, normalize
from app.modules.plans.importers.pai import DEFAULT_POLICIES, _locate

PSPI_PLAN = "PSPI-{year}"
PTR_PLAN = "PTR-{year}"
PAI_PLAN = "PAI-{year}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_DOCX_XML_BYTES = 20 * 1024 * 1024
QUOTE_CHARS = 240


def quote(text: str | None, limit: int = QUOTE_CHARS) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


@dataclass(frozen=True)
class ReportDraft:
    activity_key: str
    period: str
    reported_progress: Decimal | None
    raw_progress: str | None
    qualitative_summary: str | None
    evidence_refs: list[str] | None
    is_met: bool | None
    met_on_time: bool | None
    source_ref: str
    progress_basis: str


@dataclass(frozen=True)
class LinkCandidate:
    source_id: str
    #: ``PLAN/CODE`` when the source names the activity; ``None`` + ``external_code``
    #: when only an external code (``OM-05``) is stated.
    activity_key: str | None
    external_code: str | None
    role: str
    resolution: str
    source_ref: str
    quote: str


@dataclass(frozen=True)
class FollowupReview:
    origin: str
    subject: str
    reason: str
    quote: str = ""


@dataclass
class FollowupBundle:
    sources: list[SourceInfo] = field(default_factory=list)
    reports: list[ReportDraft] = field(default_factory=list)
    links: list[LinkCandidate] = field(default_factory=list)
    review: list[FollowupReview] = field(default_factory=list)


# --------------------------------------------------------------------------
# 1. PAI follow-up (XLSX)
# --------------------------------------------------------------------------

_FOLLOWUP_HEADERS = (
    ("observaciones", "observations"),
    ("% de avance", "progress"),
    ("avance cualitativo", "qualitative"),
    ("evidencia", "evidence"),
    ("se cumplio la actividad", "is_met"),
    ("se cumplio en la fecha", "met_on_time"),
)


def _followup_columns(header: tuple[Any, ...], start: int) -> dict[str, int]:
    """Locate follow-up columns to the RIGHT of the ``Programado`` column.

    ``EVIDENCIA`` also exists in the planning block (expected evidence), so the
    scan starts after the period columns.
    """

    mapping: dict[str, int] = {}
    for index in range(start, len(header)):
        cell = normalize(str(header[index])) if header[index] is not None else ""
        for prefix, key in _FOLLOWUP_HEADERS:
            if cell.startswith(prefix) and key not in mapping:
                mapping[key] = index
    return mapping


def _yes_no(value: Any) -> bool | None:
    text = normalize(clean(value))
    if text in {"si", "sí"}:
        return True
    if text == "no":
        return False
    return None


def _progress(value: Any) -> tuple[Decimal | None, str | None, str]:
    """``(progress 0-100, raw, basis)`` from the ``% de avance`` cell.

    The cell is a plain number. A value in ``[0, 1]`` is read as an Excel
    fraction of the ``%`` column (``1`` -> ``100``); a value in ``(1, 100]`` is
    already a percentage. Anything else is left empty.
    """

    if value is None or (isinstance(value, str) and not clean(value)):
        return None, None, "sin cifra"
    raw = str(value)
    try:
        number = Decimal(str(value).replace(",", ".").strip())
    except ArithmeticError:
        return None, raw, "cifra no numérica"
    if Decimal(0) <= number <= Decimal(1):
        return (number * 100).quantize(Decimal("0.01")), raw, "fracción de la columna «%» (×100)"
    if Decimal(1) < number <= Decimal(100):
        return number.quantize(Decimal("0.01")), raw, "porcentaje"
    return None, raw, "fuera de rango"


def parse_pai_followup(
    path: Path,
    *,
    period_year: int,
    policies: tuple[str, ...] = DEFAULT_POLICIES,
) -> tuple[list[ReportDraft], list[FollowupReview]]:
    rows, columns, header_index = _locate(path)
    header = rows[header_index]
    period_columns = {p: columns[p] for p in ("I", "II", "III") if p in columns}
    if not period_columns:
        raise SourceFormatError("El PAI no tiene columnas de seguimiento cuatrimestral.")
    follow = _followup_columns(header, max(period_columns.values()) + 1)
    if "progress" not in follow or "qualitative" not in follow:
        raise SourceFormatError(
            "El PAI no tiene las columnas «% de avance Cuatrimestral» y «Avance cualitativo»."
        )

    def cell(row: tuple[Any, ...], index: int | None) -> Any:
        return row[index] if index is not None and index < len(row) else None

    reports: list[ReportDraft] = []
    review: list[FollowupReview] = []
    plan_code = PAI_PLAN.format(year=period_year)
    policy = None
    pending: tuple[str, int, tuple[Any, ...]] | None = None
    for number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        policy_text = clean(cell(row, columns["policy"]))
        match = re.match(r"^\s*(\d+)\s*\.", policy_text or "")
        if match:
            policy = match.group(1)
        kind = normalize(clean(cell(row, columns["kind"])))
        if kind == "programado":
            code = clean(cell(row, columns["code"]))
            code = str(int(float(code))) if code and re.fullmatch(r"\d+(\.0)?", code) else code
            pending = (f"{policy}.{code}", number, row) if policy in policies and code else None
            continue
        if kind != "ejecutado" or pending is None:
            continue
        activity_code, programmed_row, programmed = pending
        pending = None
        key = f"{plan_code}/{activity_code}"
        progress_cell = cell(programmed, follow.get("progress"))
        qualitative = clean(cell(programmed, follow.get("qualitative")))
        if progress_cell in (None, "") and not qualitative:
            continue  # nothing reported for this activity
        executed = [
            p for p, index in period_columns.items() if normalize(clean(cell(row, index))) == "x"
        ]
        ref = f"{path.name}, filas {programmed_row}/{number}"
        if len(executed) != 1:
            review.append(
                FollowupReview(
                    "pai",
                    key,
                    "El seguimiento está diligenciado pero la fila «Ejecutado» marca "
                    f"{len(executed)} cuatrimestres; no se asigna periodo.",
                    quote(qualitative),
                )
            )
            continue
        progress, raw, basis = _progress(progress_cell)
        observations = clean(cell(programmed, follow.get("observations")))
        summary = qualitative
        if observations:
            summary = (
                f"{qualitative}\n\nObservaciones: {observations}" if qualitative else observations
            )
        evidence = clean(cell(programmed, follow.get("evidence")))
        reports.append(
            ReportDraft(
                activity_key=key,
                period=executed[0],
                reported_progress=progress,
                raw_progress=raw,
                qualitative_summary=summary,
                evidence_refs=[part.strip() for part in evidence.split("·") if part.strip()]
                if evidence
                else None,
                is_met=_yes_no(cell(programmed, follow.get("is_met"))),
                met_on_time=_yes_no(cell(programmed, follow.get("met_on_time"))),
                source_ref=ref,
                progress_basis=basis,
            )
        )
    return reports, review


# --------------------------------------------------------------------------
# 2. Links stated in the checklist rows
# --------------------------------------------------------------------------

_PSPI_TITLE = re.compile(r"^\s*\[PSPI\s+(\d+\.\d+)\]")
_PSPI_QUALIFIED = re.compile(
    r"actividad\s+(\d+\.\d+)\s+(?:del\s+)?(?:plan\s+(?:de\s+)?seguridad|pspi)\b", re.IGNORECASE
)
_ANY_ACTIVITY = re.compile(r"actividad\s+(\d+\.\d+)", re.IGNORECASE)
_RISK_QUALIFIED = re.compile(r"\b(?:control|riesgo)\s+(R\d{1,2})\b", re.IGNORECASE)
_RISK_BARE = re.compile(r"\b(R\d{1,2})\b")
_OM = re.compile(r"\bOM-\d{2}\b")
_PLAN_MENTION = re.compile(r"Plan de Acci[oó]n|\bPTEP\b", re.IGNORECASE)
TEXT_COLUMNS = ("Tarea", "Detalle", "Observaciones")


def _context(text: str, start: int, end: int, width: int = 80) -> str:
    return quote(text[max(0, start - width) : min(len(text), end + width)], 2 * width + 40)


def checklist_link_candidates(
    rows: Iterable[tuple[str, int, dict[str, str]]],
    *,
    source_name: str,
    period_year: int,
) -> tuple[list[LinkCandidate], list[FollowupReview]]:
    """``rows`` = ``(ID, record number, {column: text})`` of the checklist."""

    pspi = PSPI_PLAN.format(year=period_year)
    ptr = PTR_PLAN.format(year=period_year)
    links: list[LinkCandidate] = []
    review: list[FollowupReview] = []
    for source_id, number, values in rows:
        linked: set[str] = set()
        title = values.get("Tarea", "")
        primary = _PSPI_TITLE.match(title)
        if primary:
            code = primary.group(1)
            links.append(
                LinkCandidate(
                    source_id,
                    f"{pspi}/{code}",
                    None,
                    "primary",
                    "exact",
                    f"{source_name}, registro {number}, columna Tarea",
                    quote(title, 120),
                )
            )
            linked.add(code)
        for column in TEXT_COLUMNS:
            text = values.get(column, "")
            ref = f"{source_name}, registro {number}, columna {column}"
            for match in _PSPI_QUALIFIED.finditer(text):
                code = match.group(1)
                if code in linked:
                    continue
                linked.add(code)
                links.append(
                    LinkCandidate(
                        source_id,
                        f"{pspi}/{code}",
                        None,
                        "contributes",
                        "exact",
                        ref,
                        _context(text, match.start(), match.end()),
                    )
                )
            for match in _RISK_QUALIFIED.finditer(text):
                code = match.group(1).upper()
                if code in linked:
                    continue
                linked.add(code)
                links.append(
                    LinkCandidate(
                        source_id,
                        f"{ptr}/{code}",
                        None,
                        "contributes",
                        "by_external_code",
                        ref,
                        _context(text, match.start(), match.end()),
                    )
                )
            if not primary:
                for match in _OM.finditer(text):
                    code = match.group(0)
                    if code in linked:
                        continue
                    linked.add(code)
                    links.append(
                        LinkCandidate(
                            source_id,
                            None,
                            code,
                            "contributes",
                            "by_external_code",
                            ref,
                            _context(text, match.start(), match.end()),
                        )
                    )
        # Second pass: unqualified mentions not already covered -> review.
        for column in TEXT_COLUMNS:
            text = values.get(column, "")
            for match in _ANY_ACTIVITY.finditer(text):
                if match.group(1) not in linked:
                    review.append(
                        FollowupReview(
                            "checklist",
                            source_id,
                            f"«actividad {match.group(1)}» sin plan explícito ({column}).",
                            _context(text, match.start(), match.end()),
                        )
                    )
            bare = sorted({m.group(1) for m in _RISK_BARE.finditer(text)} - linked)
            if bare:
                review.append(
                    FollowupReview(
                        "checklist",
                        source_id,
                        f"Códigos de riesgo sin calificar ({', '.join(bare)}) en {column}; "
                        "no se enlazan al PTR.",
                        quote(text, 160),
                    )
                )
            mention = _PLAN_MENTION.search(text)
            if mention:
                review.append(
                    FollowupReview(
                        "checklist",
                        source_id,
                        f"Menciona «{mention.group(0)}» sin código de actividad ({column}).",
                        _context(text, mention.start(), mention.end()),
                    )
                )
    return links, review


# --------------------------------------------------------------------------
# 3. Cruce report (Markdown)
# --------------------------------------------------------------------------

_SECTION = re.compile(r"^##\s+(\d+)\.")
_ROW_CODE = re.compile(r"^\*{0,2}(\d+\.\d+)\*{0,2}$")
_TASK_ID = re.compile(r"\bT-\d+\b")
CRUCE_SECTIONS = ("2", "3", "4")


def parse_cruce_report(
    path: Path, *, period_year: int
) -> tuple[list[LinkCandidate], list[FollowupReview]]:
    pspi = PSPI_PLAN.format(year=period_year)
    links: list[LinkCandidate] = []
    review: list[FollowupReview] = []
    section = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        heading = _SECTION.match(line)
        if heading:
            section = heading.group(1)
            continue
        if section not in CRUCE_SECTIONS or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        code_match = _ROW_CODE.match(cells[0]) if cells else None
        if not code_match:
            continue
        code = code_match.group(1)
        rest = " | ".join(cells[1:])
        tasks = sorted(set(_TASK_ID.findall(rest)), key=lambda t: int(t[2:]))
        ref = f"{path.name}, sección {section}, línea {number}"
        if not tasks:
            continue
        if "sin cobertura" in rest.lower():
            for task in tasks:
                review.append(
                    FollowupReview(
                        "cruce",
                        f"{task} → {pspi}/{code}",
                        "El cruce menciona la tarea pero califica la actividad «Sin cobertura».",
                        quote(cells[-1], 200),
                    )
                )
            continue
        for task in tasks:
            links.append(
                LinkCandidate(
                    task, f"{pspi}/{code}", None, "contributes", "exact", ref, quote(cells[-1])
                )
            )
    return links, review


# --------------------------------------------------------------------------
# 4. Monthly indicator reports (DOCX) -> review only
# --------------------------------------------------------------------------


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCX_XML_BYTES:
                raise SourceFormatError(f"El documento {path.name} excede el tamaño permitido.")
            raw = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SourceFormatError(f"{path.name} no es un .docx válido.") from exc
    if b"<!DOCTYPE" in raw[:4096]:
        raise SourceFormatError(f"{path.name} declara un DOCTYPE no permitido.")
    root = ET.fromstring(raw)
    blocks = []
    for paragraph in root.iter(f"{_W}p"):
        text = "".join(t.text or "" for t in paragraph.iter(f"{_W}t")).strip()
        if text:
            blocks.append(text)
    return "\n".join(blocks)


_SECURITY = re.compile(r"Pol[ií]tica de Seguridad Digital", re.IGNORECASE)
_SUM = re.compile(r"PORCENTAJE DE AVANCE \(Sumatoria\):\s*([^\n%]*)%", re.IGNORECASE)


def monthly_report_review(paths: Iterable[Path]) -> list[FollowupReview]:
    review = []
    for path in paths:
        text = docx_text(path)
        found = _SECURITY.search(text)
        figure = None
        if found:
            after = _SUM.search(text, found.end())
            figure = after.group(1).strip() if after else None
        review.append(
            FollowupReview(
                "reporte_mensual",
                path.name,
                "Reporte mensual por indicador de la política (no por actividad del PSPI/PAI); "
                + (
                    f"cifra de avance de Seguridad Digital: «{figure}»."
                    if figure
                    else "la cifra de avance de Seguridad Digital está vacía."
                )
                + " No se registra como reporte de periodo.",
            )
        )
    return review


def merge_links(candidates: list[LinkCandidate]) -> list[LinkCandidate]:
    """One candidate per ``(task, activity_key|external_code)``.

    ``primary`` wins over ``contributes``; ``exact`` over ``by_external_code``;
    references and quotes are concatenated so every source stays visible.
    """

    merged: dict[tuple[str, str], LinkCandidate] = {}
    for item in candidates:
        key = (item.source_id, item.activity_key or f"#{item.external_code}")
        current = merged.get(key)
        if current is None:
            merged[key] = item
            continue
        merged[key] = LinkCandidate(
            item.source_id,
            current.activity_key,
            current.external_code,
            "primary" if "primary" in (current.role, item.role) else "contributes",
            "exact" if "exact" in (current.resolution, item.resolution) else current.resolution,
            f"{current.source_ref}; {item.source_ref}",
            f"{current.quote} || {item.quote}",
        )
    return list(merged.values())


def link_note(candidate: LinkCandidate) -> str:
    return (
        f"Resolución: {candidate.resolution}. Fuente: {candidate.source_ref}. "
        f"Texto: «{candidate.quote}»"
    )
