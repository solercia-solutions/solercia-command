"""PSPI reader: Plan de Seguridad y Privacidad de la Información (DOCX).

The activities live in the table whose header carries ``No.``, ``ACTIVIDAD``
and ``META``. Group rows are a single cell spanning the grid
(``1. DATOS PERSONALES``); activity rows have seven cells:
``No. | ACTIVIDAD | PRODUCTO | FECHA FIN | RESPONSABLE | META | CONTROL ISO``.
``OM-xx`` codes inside the activity text become ``external_codes`` (2.4 has
two), which is what lets the PTR linker resolve by code (45a D6).
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
    parse_om_codes,
    parse_target,
    require_unique_codes,
    version_from_filename,
)
from app.modules.plans.importers.docx_reader import DocxTable, read_tables
from app.modules.plans.schemas import PlanActivityUpsert, PlanUpsert

DEFAULT_MINE_MARKERS: tuple[str, ...] = ("OAP",)
_GROUP = re.compile(r"^\s*(\d+)\.\s*(.+)$")
_CODE = re.compile(r"^\d+\.\d+$")


def _activity_table(tables: list[DocxTable]) -> DocxTable:
    for table in tables:
        header = [normalize(cell) for cell in table.header]
        if header[:2] == ["no.", "actividad"] and any("meta" in cell for cell in header):
            return table
    raise SourceFormatError(
        "No se encontró la tabla de actividades del PSPI (encabezado «No. | ACTIVIDAD | … | META»)."
    )


def parse_pspi(
    path: Path,
    *,
    period_year: int,
    mine_markers: tuple[str, ...] = DEFAULT_MINE_MARKERS,
) -> ParsedPlan:
    table = _activity_table(read_tables(path))
    activities: list[PlanActivityUpsert] = []
    warnings: list[str] = []
    group_code = group_name = None
    for index, row in enumerate(table.rows[1:], start=2):
        first = clean(row.cells[0]) if row.cells else None
        if row.is_spanned or len(set(row.cells)) == 1:
            match = _GROUP.match(first or "")
            if match:
                group_code, group_name = match.group(1), match.group(2).strip()
            continue
        if not first or not _CODE.match(first) or len(row.cells) < 7:
            warnings.append(f"Fila {index} de la tabla de actividades ignorada: «{first}».")
            continue
        name, product, due, responsible, target, iso = (clean(c) for c in row.cells[1:7])
        target_from, target_to = parse_target(target)
        activities.append(
            PlanActivityUpsert(
                code=first,
                name=name or first,
                group_code=group_code,
                group_name=group_name,
                deliverable=product,
                responsible=responsible,
                is_mine=is_mine(responsible, mine_markers),
                due_date=parse_es_date(due),
                target_from=target_from,
                target_to=target_to,
                iso_controls=parse_iso_controls(iso),
                external_codes=parse_om_codes(name),
                sort_order=len(activities),
            )
        )
        if due and parse_es_date(due) is None:
            warnings.append(f"Actividad {first}: fecha fin no reconocida «{due}».")
    if not activities:
        raise SourceFormatError("La tabla de actividades del PSPI no tiene actividades.")
    require_unique_codes(activities, "PSPI")
    return ParsedPlan(
        kind="pspi",
        source=SourceInfo.of(path),
        plan=PlanUpsert(
            code=f"PSPI-{period_year}",
            name=f"Plan de Seguridad y Privacidad de la Información {period_year}",
            plan_type="pspi",
            period_year=period_year,
            version=version_from_filename(path.name),
            source_document=path.name,
        ),
        activities=activities,
        warnings=warnings,
    )
