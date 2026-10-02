"""Pure confirm plan for the personal checklist (T05f): rows -> task drafts.

No I/O, settings or persistence. Consumes the preview produced by
``parse_checklist`` and decides, deterministically and only from explicit
source fields:

* **Identity.** Business key = ``(organization, source, external_key)`` with
  ``source = "checklist_xlsx"`` (the checklist family registered by change 43;
  the CSV and XLSX exports of the same checklist are ONE source, so a format
  change never creates a second task) and ``external_key =
  "<namespace>:<ID>"`` (``CHECKLIST_TAREAS:T-01``). The ``ID`` column is the
  checklist's own stable identifier (T-numbers are never reused across file
  versions); the namespace keeps two different checklists of the same
  organization apart. Never title or file hash: the hash identifies a byte
  version, not a task.
* **Project.** From the ``Categoría`` column only (see :func:`map_project`).
  Anything without an explicit rule goes to ``GENERALES`` and is listed.
* **Status.** ``Estado`` mapped onto the target project's board columns. A
  state the target board cannot represent is never approximated: the row is
  placed in ``GENERALES`` (which has the seven checklist states) and listed.
* **Dates.** Only explicit ``YYYY-MM-DD`` values. Sentinels (``Sin fecha
  (...)``, ``Recurrente``, ``-``) and bare prose (``Sin fecha``) stay ``None``
  and are listed; the prose ones go to review.
* **Provenance.** Source file, ID and record/line coordinates are written in a
  delimited footer of the description, so a re-run compares the business body
  without the footer.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from .contracts import ChecklistPreview, ChecklistRow

CHECKLIST_SOURCE = "checklist_xlsx"
DEFAULT_NAMESPACE = "CHECKLIST_TAREAS"
PROVENANCE_MARKER = "\n\n---\nProcedencia del checklist"
#: A calendar date is stored at 12:00 Bogotá (17:00 UTC) so that both the
#: browser-local rendering and the UTC ``slice(0, 10)`` of the task modal show
#: the same calendar day as the source.
DUE_TIME = time(12, 0, tzinfo=ZoneInfo("America/Bogota"))

GENERALES = "GENERALES"
SGSI = "SGSI"
PANDORA = "PAN"

#: First segment of ``Categoría`` (before ``/``) that places a row in SGSI.
SGSI_FIRST_SEGMENTS: frozenset[str] = frozenset(
    {
        "plan seguridad d612",
        "sgsi",
        "seguridad",
        "vulnerabilidades",
        "dlp",
        "gobierno de seguridad",
        "mspi",
        "proteccion de datos",
        "riesgos",
        "activos",
        "continuidad",
    }
)

CHECKLIST_STATES = (
    "PENDIENTE",
    "EN CURSO",
    "DIFERIDA",
    "RECURRENTE",
    "GESTIONADA APARTE",
    "REMOVIDA",
    "COMPLETADA",
)

#: Checklist ``Estado`` -> board ``status_key`` per target project. Verified
#: against the board columns of the SDMujer projects (clone of 2026-10-01).
STATUS_MAP: dict[str, dict[str, str]] = {
    GENERALES: {state: state for state in CHECKLIST_STATES},
    SGSI: {
        "PENDIENTE": "Sin iniciar",
        "EN CURSO": "En curso",
        "DIFERIDA": "Diferida",
        "RECURRENTE": "Recurrente",
        "GESTIONADA APARTE": "Gestionada aparte",
        "REMOVIDA": "Removida",
        "COMPLETADA": "Completada",
    },
    PANDORA: {"PENDIENTE": "Backlog", "EN CURSO": "Doing", "COMPLETADA": "Done"},
}

PRIORITY_MAP: dict[str, str] = {
    "CRÍTICA": "critical",
    "ALTA": "high",
    "MEDIA": "medium",
    "BAJA": "low",
}
#: ``tasks.priority`` is NOT NULL; an empty urgency takes the model default and
#: the row is listed so nobody reads it as a decision of the source.
DEFAULT_PRIORITY = "medium"

_SENTINEL_DATE = re.compile(r"^(Sin fecha \([^\r\n]+\)|Recurrente|-)$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ReviewKind = Literal[
    "fecha_en_prosa",
    "categoria_sin_regla",
    "estado_sin_columna",
    "urgencia_vacia",
    "fila_rechazada",
]


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


@dataclass(frozen=True)
class ProjectDecision:
    code: str
    #: ``rule`` = explicit category rule; ``default`` = no rule matched.
    basis: Literal["rule", "default", "state_fallback"]
    reason: str


def map_project(category: str | None) -> ProjectDecision:
    """Place a row by its ``Categoría`` only.

    1. Any ``/`` segment equal to ``Pandora`` -> ``PAN`` (``Pandora / SIG``,
       ``Gestión Documental / Pandora``).
    2. First segment in :data:`SGSI_FIRST_SEGMENTS` -> ``SGSI``.
    3. Otherwise ``GENERALES`` (listed as ``categoria_sin_regla``).
    """

    raw = (category or "").strip()
    segments = [_plain(part) for part in raw.split("/") if part.strip()]
    if any(segment == "pandora" for segment in segments):
        return ProjectDecision(PANDORA, "rule", f"Categoría «{raw}» contiene «Pandora».")
    if segments and segments[0] in SGSI_FIRST_SEGMENTS:
        return ProjectDecision(
            SGSI, "rule", f"Categoría «{raw}» es de seguridad de la información."
        )
    return ProjectDecision(GENERALES, "default", f"Categoría «{raw or '—'}» sin regla explícita.")


@dataclass(frozen=True)
class ReviewNote:
    kind: ReviewKind
    source_id: str | None
    row: int
    detail: str


@dataclass(frozen=True)
class TaskDraft:
    external_key: str
    source_id: str
    row: int
    line_start: int | None
    line_end: int | None
    project_code: str
    project_basis: str
    project_reason: str
    source_status: str
    status_key: str
    priority: str
    title: str
    body: str
    provenance: str
    due_date: datetime | None
    due_raw: str
    category: str
    work_folder: str | None

    @property
    def description(self) -> str:
        return self.body + self.provenance


@dataclass
class ChecklistPlan:
    source_name: str
    sha256: str
    namespace: str
    drafts: list[TaskDraft] = field(default_factory=list)
    review: list[ReviewNote] = field(default_factory=list)
    skipped: list[ReviewNote] = field(default_factory=list)
    rows_read: int = 0


def external_key(namespace: str, source_id: str) -> str:
    return f"{namespace}:{source_id}"


def due_datetime(value: date | None) -> datetime | None:
    return None if value is None else datetime.combine(value, DUE_TIME)


def _cells(preview: ChecklistPreview, row: ChecklistRow) -> dict[str, str]:
    headings = [str(cell.value) for cell in preview.headers]
    values: dict[str, str] = {}
    for heading, cell in zip(headings, row.cells, strict=False):
        value = cell.value
        values[heading] = "" if value is None else str(value).strip()
    return values


def _body(values: dict[str, str]) -> str:
    parts = []
    if values.get("Detalle"):
        parts.append(values["Detalle"])
    if values.get("Observaciones"):
        parts.append("**Observaciones**\n\n" + values["Observaciones"])
    return "\n\n".join(parts)


def _provenance(
    source_name: str,
    row: ChecklistRow,
    values: dict[str, str],
    work_folder: str | None,
) -> str:
    lines = [
        f"{PROVENANCE_MARKER}: {source_name} · ID {values.get('ID', '')} · registro {row.number}"
        + (
            f" (líneas {row.line_start}–{row.line_end})"
            if row.line_start is not None and row.line_end is not None
            else ""
        ),
        f"- Estado en la fuente: {values.get('Estado') or '—'}",
        f"- Categoría: {values.get('Categoría') or '—'}",
        f"- Solicitante: {values.get('Solicitante') or '—'}",
        f"- Urgencia: {values.get('Urgencia') or '—'}",
        f"- Fecha límite (texto de la fuente): {values.get('Fecha Límite') or '—'}",
        f"- Vencido (al corte del archivo): {values.get('Vencido') or '—'}",
        f"- Apoyo IA: {values.get('Apoyo IA') or '—'}",
    ]
    if work_folder:
        lines.append(f"- Carpeta de trabajo (relativa a TAREAS): {work_folder}/")
    return "\n".join(lines)


def _due(row: ChecklistRow, raw: str) -> tuple[datetime | None, bool]:
    """Return ``(due, is_prose)``; never guesses a date from prose."""

    if row.due_date is not None:
        return due_datetime(row.due_date), False
    if raw and _ISO_DATE.match(raw):
        return due_datetime(date.fromisoformat(raw)), False
    if not raw or _SENTINEL_DATE.match(raw):
        return None, False
    return None, True


def build_checklist_plan(
    preview: ChecklistPreview,
    *,
    source_name: str,
    namespace: str = DEFAULT_NAMESPACE,
    work_folders: dict[str, str] | None = None,
) -> ChecklistPlan:
    """Turn a complete preview into drafts. Raises if the preview is not complete."""

    if not preview.complete:
        raise ValueError("La vista previa del checklist no está completa; no se planifica nada.")
    plan = ChecklistPlan(source_name=source_name, sha256=preview.sha256, namespace=namespace)
    folders = work_folders or {}
    for row in preview.rows:
        if row.disposition == "blank_skipped":
            continue
        plan.rows_read += 1
        values = _cells(preview, row)
        source_id = values.get("ID") or None
        issue_codes = {issue.code for issue in row.issues}
        # A bare prose date ("Sin fecha") is the ONLY rejection we absorb: the
        # row is otherwise valid and its date simply stays empty.
        if row.disposition == "rejected" and (issue_codes != {"invalid_date"} or not source_id):
            plan.skipped.append(
                ReviewNote(
                    "fila_rechazada",
                    source_id,
                    row.number,
                    "Rechazada por el analizador: " + ", ".join(sorted(issue_codes)) + ".",
                )
            )
            continue
        assert source_id is not None
        raw_due = values.get("Fecha Límite", "")
        due, is_prose = _due(row, raw_due)
        if is_prose or row.disposition == "rejected":
            plan.review.append(
                ReviewNote(
                    "fecha_en_prosa",
                    source_id,
                    row.number,
                    f"Fecha límite en texto libre «{raw_due}»; queda sin fecha.",
                )
            )
        decision = map_project(values.get("Categoría"))
        if decision.basis == "default":
            plan.review.append(
                ReviewNote("categoria_sin_regla", source_id, row.number, decision.reason)
            )
        state = values.get("Estado", "").upper()
        if state not in CHECKLIST_STATES:
            plan.skipped.append(
                ReviewNote(
                    "fila_rechazada", source_id, row.number, f"Estado desconocido «{state}»."
                )
            )
            continue
        status_key = STATUS_MAP[decision.code].get(state)
        if status_key is None:
            plan.review.append(
                ReviewNote(
                    "estado_sin_columna",
                    source_id,
                    row.number,
                    f"El tablero de {decision.code} no tiene columna para «{state}»; "
                    f"se ubica en {GENERALES}.",
                )
            )
            decision = ProjectDecision(
                GENERALES,
                "state_fallback",
                f"{decision.reason} Estado «{state}» sin columna en {decision.code}.",
            )
            status_key = STATUS_MAP[GENERALES][state]
        urgency = values.get("Urgencia", "")
        priority = PRIORITY_MAP.get(urgency)
        if priority is None:
            plan.review.append(
                ReviewNote(
                    "urgencia_vacia",
                    source_id,
                    row.number,
                    f"Urgencia «{urgency or '—'}»; se usa la prioridad por defecto (media).",
                )
            )
            priority = DEFAULT_PRIORITY
        folder = folders.get(source_id)
        plan.drafts.append(
            TaskDraft(
                external_key=external_key(namespace, source_id),
                source_id=source_id,
                row=row.number,
                line_start=row.line_start,
                line_end=row.line_end,
                project_code=decision.code,
                project_basis=decision.basis,
                project_reason=decision.reason,
                source_status=state,
                status_key=status_key,
                priority=priority,
                title=values.get("Tarea") or source_id,
                body=_body(values),
                provenance=_provenance(source_name, row, values, folder),
                due_date=due,
                due_raw=raw_due,
                category=values.get("Categoría", ""),
                work_folder=folder,
            )
        )
    return plan


_FOLDER = re.compile(r"^(T-\d+)(?:_.*)?$")


def work_folders_from_names(names: list[str]) -> dict[str, str]:
    """``{"T-157": "T-157_GLPI_..."}`` from directory NAMES (no I/O here).

    An ID with more than one folder keeps none: ambiguity is never resolved by
    picking one.
    """

    found: dict[str, list[str]] = {}
    for name in names:
        match = _FOLDER.match(name)
        if match:
            found.setdefault(match.group(1), []).append(name)
    return {key: values[0] for key, values in found.items() if len(values) == 1}


def body_of(description: str | None) -> str:
    """Business body of a stored description, without the provenance footer."""

    if not description:
        return ""
    index = description.find(PROVENANCE_MARKER)
    return description if index < 0 else description[:index]
