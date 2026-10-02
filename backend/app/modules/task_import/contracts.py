"""Immutable, in-memory preview DTOs. No paths are opened by this package.

A snapshot's bytes are authoritative; XLSX cells are openpyxl projections, not
lossless XML. SHA-256 identifies a byte version, never a task/business identity.
Provenance is caller-declared metadata, not verified authorship. Avoid logging
snapshots or rows: only Issue objects are safe diagnostic payloads.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Literal


class Availability(StrEnum):
    AVAILABLE = 'available'
    UNAVAILABLE = 'unavailable'
    ERROR = 'error'


IssueCode = Literal[
    'unsafe_locator', 'locator_collision', 'unsupported_format', 'unavailable',
    'source_error', 'empty_source', 'encoding_error', 'parse_error',
    'limit_exceeded', 'missing_sheet', 'other_sheets', 'unsupported_structure',
    'external_link', 'duplicate_header', 'unknown_header', 'missing_header',
    'invalid_id', 'duplicate_id', 'invalid_date', 'formula', 'cell_error',
]


@dataclass(frozen=True)
class Issue:
    """Stable code and coordinates only; never embeds source contents/exceptions."""
    code: IssueCode
    severity: Literal['error', 'warning', 'info'] = 'error'
    row: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class SourceSnapshot:
    relative_path: str
    data: bytes = field(repr=False)
    provenance: str = ''

    def __post_init__(self):
        if not isinstance(self.data, bytes):
            raise TypeError('Se requiere una copia inmutable de bytes.')
        if not isinstance(self.relative_path, str) or not isinstance(self.provenance, str):
            raise TypeError('El localizador y la procedencia deben ser texto.')


@dataclass(frozen=True)
class UnavailableSource:
    """Unavailable/error entries have unknown size/hash, never invented zeroes."""
    relative_path: str
    availability: Availability
    provenance: str = ''

    def __post_init__(self):
        if self.availability not in (Availability.UNAVAILABLE, Availability.ERROR):
            raise ValueError('La entrada debe indicar indisponibilidad o error.')
        if not isinstance(self.relative_path, str) or not isinstance(self.provenance, str):
            raise TypeError('El localizador y la procedencia deben ser texto.')


@dataclass(frozen=True)
class ManifestEntry:
    source: SourceSnapshot | UnavailableSource
    availability: Availability
    size_bytes: int | None
    sha256: str | None
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class ChecklistProfile:
    """Explicit preview profile based on checklist 44's source headings/dates.

    Exact headings (no trimming/case guessing); unknown/duplicate extra columns
    remain ordered. Missing or duplicate required headings reject all nonblank
    rows. IDs are nonblank strings, preserved verbatim; exact duplicates reject
    ALL occurrences. No inferred T-number grammar or cross-file identity.
    Dates: YYYY-MM-DD, native date/datetime (date part), empty, '-', 'Recurrente',
    or 'Sin fecha (...)'. Other strings/numbers are invalid, not locale guesses.
    This profile does NOT implement 44's superseded routing/owner/merge rules.
    """
    headers: tuple[str, ...] = (
        'ID', 'Estado', 'Vencido', 'Urgencia', 'Categoría', 'Tarea', 'Detalle',
        'Fecha Límite', 'Solicitante', 'Apoyo IA', 'Observaciones',
    )
    sheet: str = 'Checklist Tareas'
    id_header: str = 'ID'
    date_header: str = 'Fecha Límite'

    def __post_init__(self):
        if (not isinstance(self.headers, tuple) or not self.headers
                or not all(isinstance(h, str) and h for h in self.headers)
                or len(set(self.headers)) != len(self.headers)
                or self.id_header not in self.headers or self.date_header not in self.headers
                or self.sheet != 'Checklist Tareas'):
            raise ValueError('El perfil del checklist no es válido.')


@dataclass(frozen=True)
class ParseLimits:
    """Hard caps, not truncation: row cap includes header; cells include padding.

    XLSX ZIP caps cover every member/sheet before openpyxl. No wall-clock
    deadline or process sandbox is provided: callers must add isolation before
    exposing this foundation to hostile public uploads.
    """
    max_input_bytes: int = 5 * 1024 * 1024
    max_zip_members: int = 128
    max_expanded_bytes: int = 20 * 1024 * 1024
    max_compression_ratio: int = 100
    max_rows: int = 10000
    max_columns: int = 64
    max_cells: int = 200000
    max_cell_chars: int = 100000

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in vars(self).values()):
            raise ValueError('Los límites deben ser enteros positivos.')


CellValue = str | int | float | bool | date | datetime | time | timedelta | None


@dataclass(frozen=True)
class RawCell:
    coordinate: str
    value: CellValue = field(repr=False)
    kind: str  # CSV: text/absent. XLSX: openpyxl data_type or absent.


@dataclass(frozen=True)
class ChecklistRow:
    number: int  # logical record number for CSV, worksheet row for XLSX
    sheet: str | None
    line_start: int | None
    line_end: int | None
    cells: tuple[RawCell, ...]
    source_id: str | None = field(repr=False)
    due_date: date | None
    disposition: Literal['candidate', 'blank_skipped', 'rejected']
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class PreviewCounts:
    candidate: int
    blank_skipped: int
    rejected: int

    @property
    def total(self) -> int:
        return self.candidate + self.blank_skipped + self.rejected


@dataclass(frozen=True)
class ChecklistPreview:
    """Rows derive from this exact snapshot/hash, never persisted task records.

    Complete means fully parsed, not validated/approved. Counts are exclusive
    and include blank rows retained in `rows`. Fatal parse/limit failures return
    complete=False, counts=None and no partial rows. Row/header issues remain
    visible on complete previews; candidate does not imply import permission.
    """
    source: SourceSnapshot
    sha256: str
    profile: ChecklistProfile
    headers: tuple[RawCell, ...] = ()
    rows: tuple[ChecklistRow, ...] = ()
    sheet_names: tuple[str, ...] = ()
    issues: tuple[Issue, ...] = ()
    complete: bool = False
    counts: PreviewCounts | None = None
