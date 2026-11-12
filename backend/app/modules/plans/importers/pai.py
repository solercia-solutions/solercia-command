"""PAI reader: Plan de Acción Institucional (XLSX, openpyxl read-only).

Each activity spans two rows, ``Programado`` and ``Ejecutado``; the MIPG
policy (``11.Gobierno digital``) is a merged cell, so it is carried forward.
The activity code inside a policy is an integer, hence the composite code
``{policy}.{code}`` (``12.4``). Columns are located by header text, not by
letter, because the dependency extracts move them.

Only the selected policies are imported (default ``11`` and ``12``, the ones
of the Equipo de Tecnología/Arquitectura): the importer never decides the
selection by itself. The follow-up already filled in the sheet (45a P2) is
reported, never persisted.
"""

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.modules.plans.importers.common import (
    ParsedPlan,
    SourceFormatError,
    SourceInfo,
    clean,
    is_mine,
    normalize,
    require_unique_codes,
)
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert

DEFAULT_POLICIES: tuple[str, ...] = ("11", "12")
DEFAULT_MINE_MARKERS: tuple[str, ...] = (
    "Equipo Arquitectura Empresarial",
    "Equipo Tecnología de Información",
)
#: Anti-bomb guards (the real sheet is ~420 x 160).
MAX_ROWS = 5_000
MAX_COLUMNS = 400
_HEADER_SCAN_ROWS = 40
_PERIODS = (
    ("seguimiento iii cuatrimestre", "III"),
    ("seguimiento ii cuatrimestre", "II"),
    ("seguimiento i cuatrimestre", "I"),
)
_POLICY = re.compile(r"^\s*(\d+)\s*\.\s*([^(\n]+)")
_VERSION = re.compile(r"versi[oó]n:\s*(\d+)", re.IGNORECASE)
_DATE = re.compile(r"fecha:\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.IGNORECASE)


def _header_map(row: tuple[Any, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, raw in enumerate(row):
        cell = normalize(str(raw)) if raw is not None else ""
        key = None
        if cell.startswith("politicas modelo integrado"):
            key = "policy"
        elif cell == "responsable":
            key = "responsible"
        elif cell.startswith("codigo actividad"):
            key = "code"
        elif cell.startswith("actividad de gestion"):
            key = "name"
        elif cell == "producto":
            key = "product"
        elif cell == "evidencia":
            key = "evidence"
        elif cell.startswith("programado / ejecutado"):
            key = "kind"
        elif cell.startswith("% de avance"):
            key = "reported_progress"
        elif cell.startswith("avance cualitativo"):
            key = "qualitative"
        else:
            key = next((period for prefix, period in _PERIODS if cell.startswith(prefix)), None)
        if key and key not in mapping:
            mapping[key] = index
    return mapping


def _version(rows: list[tuple[Any, ...]]) -> str | None:
    text = " ".join(str(v) for row in rows for v in row if v is not None)
    version, when = _VERSION.search(text), _DATE.search(text)
    if not version:
        return None
    suffix = f"_{when.group(3)}{int(when.group(2)):02d}{int(when.group(1)):02d}" if when else ""
    return f"v{version.group(1)}{suffix}"


def _code_number(value: Any) -> str | None:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = clean(value)
    return text if text and text.isdigit() else None


def _locate(path: Path) -> tuple[list[tuple[Any, ...]], dict[str, int], int]:
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several unrelated types
        raise SourceFormatError(
            f"El archivo {path.name} no es un libro Excel (.xlsx) válido."
        ) from exc
    try:
        for sheet in workbook.worksheets:
            if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
                raise SourceFormatError(
                    f"La hoja «{sheet.title}» excede el tamaño máximo permitido para un plan."
                )
            rows = [tuple(row) for row in sheet.iter_rows(values_only=True, max_col=MAX_COLUMNS)]
            for index, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
                columns = _header_map(row)
                if {"policy", "code", "name", "kind"} <= columns.keys():
                    return rows, columns, index
    finally:
        workbook.close()
    raise SourceFormatError(
        "No se encontró la hoja del PAI (encabezados «POLÍTICAS … MIPG», "
        "«CÓDIGO ACTIVIDAD No.», «ACTIVIDAD DE GESTIÓN», «PROGRAMADO / EJECUTADO»)."
    )


def parse_pai(
    path: Path,
    *,
    period_year: int,
    policies: tuple[str, ...] = DEFAULT_POLICIES,
    mine_markers: tuple[str, ...] = DEFAULT_MINE_MARKERS,
) -> ParsedPlan:
    rows, columns, header_index = _locate(path)

    def value(row: tuple[Any, ...], key: str) -> Any:
        index = columns.get(key)
        return row[index] if index is not None and index < len(row) else None

    activities: list[PlanActivityUpsert] = []
    warnings: list[str] = []
    per_policy: dict[str, int] = {}
    prefilled: list[str] = []
    policy_code = policy_name = None
    last: PlanActivityUpsert | None = None
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        match = _POLICY.match(str(value(row, "policy") or ""))
        if match:
            policy_code, policy_name = match.group(1), f"{match.group(1)}. {match.group(2).strip()}"
        kind = normalize(clean(value(row, "kind")))
        if kind == "ejecutado" and last is not None:
            executed = [p for p in ("I", "II", "III") if normalize(clean(value(row, p))) == "x"]
            if executed:
                prefilled.append(f"{last.code} ejecutado en {', '.join(executed)}")
            continue
        if kind != "programado":
            continue
        number = _code_number(value(row, "code"))
        if policy_code is None or number is None:
            warnings.append(
                f"Fila {offset}: actividad sin política o código reconocible; ignorada."
            )
            last = None
            continue
        per_policy[policy_code] = per_policy.get(policy_code, 0) + 1
        code = f"{policy_code}.{number}"
        responsible = clean(value(row, "responsible"))
        mine = is_mine(responsible, mine_markers)
        if policy_code not in policies:
            if mine:
                warnings.append(
                    f"La actividad {code} es del equipo pero su política no está seleccionada."
                )
            last = None
            continue
        last = PlanActivityUpsert(
            code=code,
            name=clean(value(row, "name")) or code,
            group_code=policy_code,
            group_name=policy_name,
            deliverable=clean(value(row, "product")),
            evidence_expected=clean(value(row, "evidence")),
            responsible=responsible,
            is_mine=mine,
            scheduled_periods=[
                p for p in ("I", "II", "III") if normalize(clean(value(row, p))) == "x"
            ]
            or None,
            sort_order=len(activities),
        )
        activities.append(last)
        if clean(value(row, "reported_progress")) or clean(value(row, "qualitative")):
            prefilled.append(f"{code} con avance reportado en la hoja")
    if not activities:
        raise SourceFormatError(
            f"El PAI no tiene actividades en las políticas seleccionadas ({', '.join(policies)})."
        )
    require_unique_codes(activities, "PAI")
    if prefilled:
        warnings.append(
            "La hoja trae seguimiento diligenciado (no se importa; 45a P2 pendiente de confirmar): "
            + "; ".join(prefilled)
            + "."
        )
    return ParsedPlan(
        kind="pai",
        source=SourceInfo.of(path),
        plan=PlanUpsert(
            code=f"PAI-{period_year}",
            name=f"Plan de Acción Institucional {period_year}",
            plan_type="pai",
            period_year=period_year,
            version=_version(rows[:header_index]),
            source_document=path.name,
        ),
        activities=activities,
        warnings=warnings,
        facts={
            "selected_policies": list(policies),
            "activities_in_source": sum(per_policy.values()),
            "activities_per_policy": dict(sorted(per_policy.items(), key=lambda kv: int(kv[0]))),
        },
    )
