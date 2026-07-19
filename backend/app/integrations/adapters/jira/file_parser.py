"""CSV/XLSX file parsing for the Jira file-import vía (change
18-adapter-jira, design.md "Parser de archivo + guarda antibomba XLSX").

Produces a plain ``list[dict]`` of ROWS — the SAME shape
``normalizer.normalize_file_row`` expects — never a ``NormalizedJiraIssue``
itself: this module owns file mechanics only, homologation lives in
``normalizer.py`` (design.md "un único normalizador").

Tolerates a UTF-8 BOM (``utf-8-sig``) and REPEATED column headers (e.g. two
"Labels" columns) by merging them into a list under that column's key —
real Jira CSV exports repeat a multivalue column once per value instead of
joining them into one cell (specs/jira-import/spec.md "Parseo de CSV con
BOM y columnas repetidas").
"""

import csv
import io
from typing import Any

import openpyxl

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.jira import errors

_REQUIRED_COLUMNS = ("Issue key",)
# Columns Jira repeats once per value instead of joining into one cell —
# every OTHER column keeps its single (first non-empty) value.
_MULTIVALUE_COLUMNS = frozenset({"Labels", "Sprint"})


def _validate_header(header: list[str]) -> None:
    missing = tuple(column for column in _REQUIRED_COLUMNS if column not in header)
    if missing:
        raise errors.JiraFileFormatError(
            f"El archivo no tiene la(s) columna(s) requerida(s): {', '.join(missing)}.",
            missing_columns=missing,
        )


def _group_column_indices(header: list[str]) -> dict[str, list[int]]:
    """Map each COLUMN NAME to every position it occurs at — a repeated
    header name (e.g. two "Labels" columns) collects more than one index.
    """

    indices: dict[str, list[int]] = {}
    for position, name in enumerate(header):
        if not name:
            continue
        indices.setdefault(name, []).append(position)
    return indices


def _cell_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _build_row(raw_values: list[Any], column_indices: dict[str, list[int]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for name, positions in column_indices.items():
        values = [
            _cell_text(raw_values[position])
            for position in positions
            if position < len(raw_values) and _cell_text(raw_values[position])
        ]
        row[name] = values if name in _MULTIVALUE_COLUMNS else (values[0] if values else None)
    return row


def _guard_limits(row_count: int, cell_count: int, settings: Settings) -> None:
    """Reject BEFORE the read finishes once either threshold is crossed —
    the file is never buffered/processed in full past this point (Threat
    Matrix, "Bomba de descompresión XLSX")."""

    if row_count > settings.JIRA_FILE_MAX_ROWS or cell_count > settings.JIRA_FILE_MAX_CELLS:
        raise errors.JiraFileTooLarge()


def parse_csv(
    content: bytes, *, settings: Settings = default_settings
) -> list[dict[str, Any]]:
    """Parse a Jira CSV export. ``utf-8-sig`` strips a leading BOM
    transparently (specs/jira-import/spec.md "CSV exportado de Jira con
    BOM UTF-8")."""

    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        header = []
    _validate_header(header)
    column_indices = _group_column_indices(header)

    rows: list[dict[str, Any]] = []
    cell_count = len(header)
    for row_count, raw_row in enumerate(reader, start=1):
        cell_count += len(raw_row)
        _guard_limits(row_count, cell_count, settings)
        rows.append(_build_row(raw_row, column_indices))
    return rows


def parse_xlsx(
    content: bytes, *, settings: Settings = default_settings
) -> list[dict[str, Any]]:
    """Parse a Jira XLSX export with ``openpyxl(read_only=True)`` — streams
    rows instead of loading the whole sheet, so the antibomb guard below
    bails out WITHOUT ever materializing a huge sheet in memory."""

    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        if sheet is None:
            raise errors.JiraFileFormatError()

        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            header_row = ()
        header = [_cell_text(cell) for cell in header_row]
        _validate_header(header)
        column_indices = _group_column_indices(header)

        rows: list[dict[str, Any]] = []
        cell_count = len(header)
        for row_count, raw_row in enumerate(rows_iter, start=1):
            cell_count += len(raw_row)
            _guard_limits(row_count, cell_count, settings)
            rows.append(_build_row(list(raw_row), column_indices))
        return rows
    finally:
        workbook.close()


def parse_file(
    content: bytes, filename: str, *, settings: Settings = default_settings
) -> list[dict[str, Any]]:
    """Dispatch to :func:`parse_csv`/:func:`parse_xlsx` by ``filename``
    extension (case-insensitive)."""

    lower = filename.lower()
    if lower.endswith(".xlsx"):
        return parse_xlsx(content, settings=settings)
    if lower.endswith(".csv"):
        return parse_csv(content, settings=settings)
    raise errors.JiraFileFormatError(f"Formato de archivo no soportado: {filename!r}")
