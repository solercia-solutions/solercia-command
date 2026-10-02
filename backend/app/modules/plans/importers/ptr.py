"""PTR reader: Plan de Tratamiento de Riesgos de Seguridad de la Información (DOCX).

Activities are the treatment ACTIONS, one per risk, spread over the tables
whose header has ``Riesgo | Acción | … | Actividad Plan Seguridad`` (one table
per residual level, named by its caption ``Tabla 9. Riesgos Altos``). The
risk matrix and the accepted-risks table are read only to report the source's
internal gaps as warnings (45a D6.6), never as hard errors.
"""

import re
from pathlib import Path

from app.modules.plans.importers.common import (
    ParsedPlan,
    SourceFormatError,
    SourceInfo,
    clean,
    is_mine,
    normalize,
    parse_es_date,
    parse_iso_controls,
    parse_target,
    require_unique_codes,
    version_from_filename,
)
from app.modules.plans.importers.docx_reader import DocxTable, read_tables
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert

DEFAULT_MINE_MARKERS: tuple[str, ...] = ("OAP",)
_RISK = re.compile(r"^R\d+$")
_CAPTION = re.compile(r"^\s*tabla\s+\d+\.\s*", re.IGNORECASE)
_LEVELS = ("extremo", "alto", "moderado", "bajo")
_COLUMNS = {
    "riesgo": "risk",
    "accion": "action",
    "responsable": "responsible",
    "fecha": "due",
    "meta 2026": "target",
    "producto": "product",
    "control iso 27001:2022": "iso",
    "actividad plan seguridad": "pspi_ref",
}


def _column_map(table: DocxTable) -> dict[str, int] | None:
    header = [normalize(cell) for cell in table.header]
    mapping = {}
    for index, cell in enumerate(header):
        key = _COLUMNS.get(cell) or ("target" if cell.startswith("meta") else None)
        if key:
            mapping[key] = index
    required = {"risk", "action", "pspi_ref"}
    return mapping if required <= mapping.keys() else None


def _cell(cells: list[str], index: int) -> str | None:
    return clean(cells[index]) if index < len(cells) else None


def _group(caption: str) -> tuple[str | None, str | None]:
    name = _CAPTION.sub("", caption).strip() or None
    lowered = normalize(name)
    level = next((lvl.upper() for lvl in _LEVELS if lvl in lowered), None)
    return level, name


def _matrix(tables: list[DocxTable]) -> list[list[str]]:
    for table in tables:
        header = [normalize(cell) for cell in table.header]
        if header[:1] == ["id"] and any("descripcion del riesgo" in c for c in header):
            return [row.cells for row in table.rows[1:] if row.cells]
    return []


def _accepted(tables: list[DocxTable]) -> set[str]:
    for table in tables:
        if any("aceptacion" in normalize(cell) for cell in table.header):
            return {clean(row.cells[0]) or "" for row in table.rows[1:] if row.cells}
    return set()


def _declared_total(tables: list[DocxTable]) -> int | None:
    for table in tables:
        for row in table.rows:
            if row.cells and normalize(row.cells[0]) == "total" and len(row.cells) > 1:
                digits = re.sub(r"\D", "", row.cells[1])
                return int(digits) if digits else None
    return None


def parse_ptr(
    path: Path,
    *,
    period_year: int,
    mine_markers: tuple[str, ...] = DEFAULT_MINE_MARKERS,
) -> ParsedPlan:
    tables = read_tables(path)
    activities: list[PlanActivityUpsert] = []
    cross_refs: dict[str, str] = {}
    warnings: list[str] = []
    for table in tables:
        columns = _column_map(table)
        if columns is None:
            continue
        group_code, group_name = _group(table.caption)
        for row in table.rows[1:]:
            values = {key: _cell(row.cells, index) for key, index in columns.items()}
            code = values.get("risk")
            if not code or not _RISK.match(code):
                warnings.append(f"Fila ignorada en «{table.caption}»: «{code}».")
                continue
            responsible = values.get("responsible")
            target_from, target_to = parse_target(values.get("target"))
            activities.append(
                PlanActivityUpsert(
                    code=code,
                    name=values.get("action") or code,
                    group_code=group_code,
                    group_name=group_name,
                    deliverable=values.get("product"),
                    responsible=responsible,
                    is_mine=is_mine(responsible, mine_markers),
                    due_date=parse_es_date(values.get("due")),
                    target_from=target_from,
                    target_to=target_to,
                    iso_controls=parse_iso_controls(values.get("iso")),
                    sort_order=len(activities),
                )
            )
            reference = values.get("pspi_ref")
            if reference:
                cross_refs[code] = reference
    if not activities:
        raise SourceFormatError(
            "No se encontraron tablas de acciones del PTR "
            "(encabezado «Riesgo | Acción | … | Actividad Plan Seguridad»)."
        )
    require_unique_codes(activities, "PTR")

    matrix = _matrix(tables)
    accepted = _accepted(tables)
    matrix_ids = {code for code in (clean(row[0]) for row in matrix) if code and _RISK.match(code)}
    action_ids = {activity.code for activity in activities}
    for code in sorted(action_ids - matrix_ids, key=lambda c: int(c[1:])):
        warnings.append(
            f"El riesgo {code} tiene acción de tratamiento pero no figura en la matriz."
        )
    for code in sorted(matrix_ids - action_ids - accepted, key=lambda c: int(c[1:])):
        warnings.append(
            f"El riesgo {code} figura en la matriz sin acción de tratamiento ni aceptación."
        )
    declared = _declared_total(tables)
    if declared is not None and matrix and declared != len(matrix):
        warnings.append(
            f"La distribución de riesgos declara {declared} riesgos "
            f"y la matriz tiene {len(matrix)} filas."
        )
    return ParsedPlan(
        kind="ptr",
        source=SourceInfo.of(path),
        plan=PlanUpsert(
            code=f"PTR-{period_year}",
            name=f"Plan de Tratamiento de Riesgos de Seguridad de la Información {period_year}",
            plan_type="ptr",
            period_year=period_year,
            version=version_from_filename(path.name),
            source_document=path.name,
        ),
        activities=activities,
        warnings=warnings,
        cross_refs=cross_refs,
        facts={
            "matrix_risks": len(matrix),
            "declared_total": declared,
            "accepted_risks": sorted(accepted),
        },
    )
