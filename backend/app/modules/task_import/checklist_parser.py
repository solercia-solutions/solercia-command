"""Bounded, pure checklist preview. No formulas evaluated or links followed.

CSV is explicitly UTF-8 (optional BOM), semicolon-delimited, double-quoted,
with embedded newlines. Cells/headers stay positional. XLSX uses only the
explicit profile sheet; every ZIP member is checked before workbook loading.
"""
from collections import Counter
import csv
from dataclasses import replace
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO, StringIO
import re
import warnings
from xml.etree import ElementTree
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_to_tuple, get_column_letter, range_boundaries

from .contracts import (
    ChecklistPreview, ChecklistProfile, ChecklistRow, Issue, ParseLimits,
    PreviewCounts, RawCell, SourceSnapshot,
)
from .source_manifest import locator_issues, source_format


class _Stop(Exception):
    def __init__(self, code):
        self.code = code


def _require(condition: bool, code='limit_exceeded'):
    if not condition:
        raise _Stop(code)


def _cells(values, number, width, limits):
    _require(width <= limits.max_columns)
    result = []
    for index in range(width):
        value, kind = values[index] if index < len(values) else (None, 'absent')
        _require(not isinstance(value, str) or len(value) <= limits.max_cell_chars)
        result.append(RawCell(f'{get_column_letter(index + 1)}{number}', value, kind))
    return tuple(result)


def _csv_records(source, limits):
    # Do not mutate csv.field_size_limit (process-global, unsafe concurrently).
    # Its own hard cap may reject a field even if caller requests a larger one.
    text = source.data.decode('utf-8-sig')
    reader = csv.reader(StringIO(text, newline=''), delimiter=';', quotechar='"', strict=True)
    header_width = 0
    total = 0
    for number, values in enumerate(reader, 1):
        _require(number <= limits.max_rows)
        if number == 1:
            header_width = len(values)
        width = max(header_width, len(values))
        total += width
        _require(total <= limits.max_cells)
        cells = _cells([(v, 'text') for v in values], number, width, limits)
        start = 1 if number == 1 else end + 1
        end = reader.line_num
        yield cells, start, end


def _zip_preflight(data, limits):
    """Bound total expansion, scan XML safety/coordinates before openpyxl.

    XML projections intentionally reject unsupported active/structural parts.
    ZIP input bytes bound central directory work; member cap is checked as soon
    as ZipFile exposes it. XML DTD/entity declarations and UTF-16 XML are refused.
    """
    unsupported_parts = ('vbaproject', 'embeddings/', 'drawings/', 'comments', 'activex/', 'pivot', 'charts/', 'connections', 'querytables/')
    unsupported_tags = {'mergeCells', 'tableParts', 'drawing', 'legacyDrawing', 'dataValidations', 'extLst', 'oleObjects', 'controls'}
    with ZipFile(BytesIO(data)) as archive:
        members = archive.infolist()
        _require(len(members) <= limits.max_zip_members)
        _require(sum(m.file_size for m in members) <= limits.max_expanded_bytes)
        names = [m.filename for m in members]
        _require(len(set(names)) == len(names), 'unsupported_structure')
        for member in members:
            _require(not locator_issues(member.filename), 'unsupported_structure')
            _require(not member.flag_bits & 1, 'unsupported_structure')
            _require(member.file_size / max(1, member.compress_size) <= limits.max_compression_ratio)
            lower = member.filename.lower()
            if 'externallinks/' in lower:
                raise _Stop('external_link')
            if any(part in lower for part in unsupported_parts):
                raise _Stop('unsupported_structure')
            # Read all members to verify CRC and actual bounded expansion.
            with archive.open(member) as stream:
                content = stream.read(limits.max_expanded_bytes + 1)
            _require(len(content) == member.file_size and len(content) <= limits.max_expanded_bytes)
            if not lower.endswith(('.xml', '.rels')):
                continue
            upper = content.upper()
            _require(b'<!DOCTYPE' not in upper and b'<!ENTITY' not in upper and b'\x00' not in content, 'unsupported_structure')
            count = last_row = last_column = 0
            stack = []
            worksheet = False
            sheet_data_count = 0
            namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
            structural_paths = {
                'worksheet': (),
                'sheetData': ('worksheet',),
                'row': ('worksheet', 'sheetData'),
                'c': ('worksheet', 'sheetData', 'row'),
                'f': ('worksheet', 'sheetData', 'row', 'c'),
                'v': ('worksheet', 'sheetData', 'row', 'c'),
                'is': ('worksheet', 'sheetData', 'row', 'c'),
            }
            data_children = {'sheetData': {'row'}, 'row': {'c'}, 'c': {'f', 'v', 'is'}}
            for event, element in ElementTree.iterparse(BytesIO(content), events=('start', 'end')):
                tag = element.tag.rsplit('}', 1)[-1]
                if event == 'start':
                    if not stack:
                        worksheet = tag == 'worksheet' or (lower.startswith('xl/worksheets/') and lower.endswith('.xml'))
                        if worksheet:
                            _require(tag == 'worksheet', 'unsupported_structure')
                    if worksheet:
                        # Compare expanded names, not prefixes/local names. Do
                        # not accept structures that openpyxl may silently skip.
                        _require(element.tag == namespace + tag, 'unsupported_structure')
                        if tag in structural_paths:
                            _require(tuple(stack) == structural_paths[tag], 'unsupported_structure')
                        if stack and stack[-1] in data_children:
                            _require(tag in data_children[stack[-1]], 'unsupported_structure')
                        if tag == 'sheetData':
                            sheet_data_count += 1
                            _require(sheet_data_count == 1, 'unsupported_structure')
                    stack.append(tag)
                    if tag == 'row':
                        row = int(element.get('r', '0'))
                        _require(0 < row <= limits.max_rows)
                        _require(row > last_row, 'unsupported_structure')
                        last_row, last_column = row, 0
                    if tag == 'c':
                        count += 1
                        row, column = coordinate_to_tuple(element.get('r', ''))
                        _require(0 < row <= limits.max_rows and 0 < column <= limits.max_columns)
                        _require(count <= limits.max_cells)
                        _require(row == last_row and column > last_column, 'unsupported_structure')
                        last_column = column
                    continue
                if tag == 'Relationship' and element.get('TargetMode', '').lower() == 'external':
                    raise _Stop('external_link')
                if tag in unsupported_tags:
                    raise _Stop('unsupported_structure')
                if tag == 'f' and element.get('t', 'normal') != 'normal':
                    raise _Stop('unsupported_structure')
                if tag == 'dimension':
                    _, _, column, row = range_boundaries(element.get('ref', 'A1'))
                    _require(row is not None and column is not None)
                    _require(row <= limits.max_rows and column <= limits.max_columns and row * column <= limits.max_cells)
                if tag == 't' and element.text:
                    _require(len(element.text) <= limits.max_cell_chars)
                element.clear()
                stack.pop()
            if worksheet:
                _require(sheet_data_count == 1, 'unsupported_structure')


def _xlsx_records(book, profile, limits):
    sheet = book[profile.sheet]
    # Never trust a false small dimension to silently hide source rows.
    sheet.reset_dimensions()
    total = 0
    header_width = 0
    for number, row in enumerate(sheet.iter_rows(), 1):
        _require(number <= limits.max_rows)
        if number == 1:
            header_width = len(row)
        width = max(header_width, len(row))
        total += width
        _require(total <= limits.max_cells)
        values = [(cell.value, cell.data_type if hasattr(cell, 'coordinate') else 'absent') for cell in row]
        yield _cells(values, number, width, limits), None, None


def _date_value(value):
    if value is None or value == '' or value in ('-', 'Recurrente'):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        if re.fullmatch(r'Sin fecha \([^\r\n]+\)', value):
            return None
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value)
    raise ValueError('Fecha no válida.')


def _derive(records, profile, sheet):
    if not records:
        raise _Stop('empty_source')
    headers = records[0][0]
    heading_values = [cell.value for cell in headers]
    frequencies = Counter(heading_values)
    issues = []
    for index, heading in enumerate(heading_values, 1):
        if frequencies[heading] > 1:
            issues.append(Issue('duplicate_header', 'error' if heading in profile.headers else 'warning', 1, index))
        if heading not in profile.headers:
            issues.append(Issue('unknown_header', 'warning', 1, index))
    for required in profile.headers:
        if required not in heading_values:
            issues.append(Issue('missing_header', row=1))
    bad_headers = any(i.severity == 'error' for i in issues)
    id_index = heading_values.index(profile.id_header) if frequencies[profile.id_header] == 1 else None
    date_index = heading_values.index(profile.date_header) if frequencies[profile.date_header] == 1 else None
    rows = []
    for number, (cells, start, end) in enumerate(records[1:], 2):
        row_issues = []
        blank = all(c.value is None or isinstance(c.value, str) and not c.value.strip() for c in cells)
        source_id, due = None, None
        if not blank:
            for column, cell in enumerate(cells, 1):
                if cell.kind == 'f' or isinstance(cell.value, str) and cell.value.lstrip().startswith('='):
                    row_issues.append(Issue('formula', row=number, column=column))
                if cell.kind == 'e':
                    row_issues.append(Issue('cell_error', row=number, column=column))
            if id_index is not None:
                value = cells[id_index].value
                if isinstance(value, str) and value.strip():
                    source_id = value
                else:
                    row_issues.append(Issue('invalid_id', row=number, column=id_index + 1))
            if date_index is not None:
                try:
                    due = _date_value(cells[date_index].value)
                except (ValueError, TypeError):
                    row_issues.append(Issue('invalid_date', row=number, column=date_index + 1))
        disposition = 'blank_skipped' if blank else 'rejected' if bad_headers or row_issues else 'candidate'
        rows.append(ChecklistRow(number, sheet, start, end, cells, source_id, due, disposition, tuple(row_issues)))
    ids = Counter(row.source_id for row in rows if row.source_id is not None)
    for index, row in enumerate(rows):
        if row.source_id is not None and ids[row.source_id] > 1:
            rows[index] = replace(row, disposition='rejected', issues=row.issues + (Issue('duplicate_id', row=row.number, column=id_index + 1),))
    issues.extend(issue for row in rows for issue in row.issues)
    counts = Counter(row.disposition for row in rows)
    return headers, tuple(rows), tuple(issues), PreviewCounts(counts['candidate'], counts['blank_skipped'], counts['rejected'])


def parse_checklist(snapshot: SourceSnapshot, profile: ChecklistProfile, limits: ParseLimits) -> ChecklistPreview:
    """Return a source-linked preview, including typed/safe failures, never log.

    Only caller-acquired immutable bytes are accepted. All derived state is
    discarded on fatal errors; the authoritative snapshot remains accessible.
    No permissions, owners, projects, status mappings or business IDs inferred.
    """
    result = ChecklistPreview(snapshot, sha256(snapshot.data).hexdigest(), profile)
    book = None
    try:
        _require(not locator_issues(snapshot.relative_path), 'unsafe_locator')
        _require(len(snapshot.data) <= limits.max_input_bytes)
        _require(bool(snapshot.data), 'empty_source')
        format_ = source_format(snapshot.relative_path)
        if format_ == '.csv':
            records = list(_csv_records(snapshot, limits))
        elif format_ == '.xlsx':
            _zip_preflight(snapshot.data, limits)
            # Suppress library warnings that may embed unsupported source text;
            # convert them to a safe typed failure instead of dropping content.
            with warnings.catch_warnings():
                warnings.simplefilter('error', UserWarning)
                book = load_workbook(BytesIO(snapshot.data), read_only=True, data_only=False, keep_links=False)
                result = replace(result, sheet_names=tuple(book.sheetnames))
                _require(profile.sheet in book.sheetnames, 'missing_sheet')
                records = list(_xlsx_records(book, profile, limits))
        else:
            raise _Stop('unsupported_format')
        headers, rows, issues, counts = _derive(records, profile, profile.sheet if format_ == '.xlsx' else None)
        if len(result.sheet_names) > 1:
            issues += (Issue('other_sheets', 'info'),)
        return replace(result, headers=headers, rows=rows, issues=issues, complete=True, counts=counts)
    except _Stop as exc:
        return replace(result, issues=(Issue(exc.code),))
    except UnicodeDecodeError:
        return replace(result, issues=(Issue('encoding_error'),))
    except UserWarning:
        return replace(result, issues=(Issue('unsupported_structure'),))
    except Exception:
        # Boundary for malformed CSV/ZIP/XML and openpyxl exceptions. Never
        # return exception text, a cell value, or an apparent empty success.
        return replace(result, issues=(Issue('parse_error'),))
    finally:
        if book is not None:
            book.close()
