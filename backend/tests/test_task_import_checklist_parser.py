"""No source files, DB fixtures, filesystem outputs, or network calls."""
import csv
from dataclasses import replace
from datetime import date
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from openpyxl import Workbook

from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot
from app.modules.task_import.checklist_parser import parse_checklist

PROFILE = ChecklistProfile()
HEADERS = PROFILE.headers


def record(source_id='T-001', due='2026-08-16'):
    return [source_id, 'PENDIENTE', '', 'ALTA', 'Área', 'Revisión', ' detalle ', due, 'Solicitante sintético', '', '']


def csv_source(rows, headers=HEADERS, bom=False):
    out = StringIO(newline='')
    csv.writer(out, delimiter=';').writerows([headers, *rows])
    return SourceSnapshot('check.csv', (('\ufeff' if bom else '') + out.getvalue()).encode('utf-8'))


def xlsx_source(rows, headers=HEADERS, sheet='Checklist Tareas', extra=False):
    book = Workbook()
    ws = book.active
    ws.title = sheet
    ws.append(list(headers))
    for row in rows:
        ws.append(row)
    if extra:
        book.create_sheet('Otra')
    out = BytesIO()
    book.save(out)
    book.close()
    return SourceSnapshot('check.xlsx', out.getvalue())


def codes(result):
    return {issue.code for issue in result.issues}


def test_csv_preserves_bom_accents_multiline_duplicate_unknown_headers_and_long_text():
    row = record()
    row[6] = '  Información; "texto"\n' + 'ñ' * 6000
    source = csv_source([row + ['001', ' dos ']], (*HEADERS, 'Extra', 'Extra'), bom=True)
    result = parse_checklist(source, PROFILE, ParseLimits())
    assert result.complete and result.counts.candidate == 1
    assert result.source is source
    assert [c.value for c in result.headers] == [*HEADERS, 'Extra', 'Extra']
    assert result.rows[0].cells[6].value == row[6]
    assert result.rows[0].cells[-2].value == '001'
    assert result.rows[0].source_id == 'T-001'
    assert result.rows[0].cells[0].coordinate == 'A2'
    assert result.rows[0].line_start == 2
    assert result.rows[0].line_end == 3
    assert {'duplicate_header', 'unknown_header'} <= codes(result)
    assert not hasattr(result.rows[0], 'assignee_id')


def test_equivalent_csv_xlsx_projections_have_distinct_versions():
    csv_result = parse_checklist(csv_source([record()]), PROFILE, ParseLimits())
    xlsx_result = parse_checklist(xlsx_source([record(due=date(2026, 8, 16))], extra=True), PROFILE, ParseLimits())
    assert csv_result.rows[0].source_id == xlsx_result.rows[0].source_id
    assert csv_result.rows[0].due_date == xlsx_result.rows[0].due_date == date(2026, 8, 16)
    assert csv_result.sha256 != xlsx_result.sha256
    assert xlsx_result.sheet_names == ('Checklist Tareas', 'Otra')
    assert 'other_sheets' in codes(xlsx_result)
    assert xlsx_result.rows[0].sheet == 'Checklist Tareas'


def test_blank_zero_absent_and_empty_are_not_conflated():
    row = record()
    result = parse_checklist(csv_source([[], [''] * 11, row[:-1], record('T-002') + ['0', '']]), PROFILE, ParseLimits())
    assert result.counts.blank_skipped == 2
    assert result.counts.candidate == 2
    assert result.rows[2].cells[-1].kind == 'absent'
    assert result.rows[3].cells[-2].value == '0'
    assert result.rows[3].cells[-1].value == ''
    assert result.counts.total == 4


@pytest.mark.parametrize('factory', [csv_source, xlsx_source])
def test_invalid_dates_ids_duplicates_and_formulas_are_retained_but_rejected(factory):
    formula = record('T-003')
    formula[5] = '=1+1'
    result = parse_checklist(factory([record(), record(), record('', '16/08/2026'), formula]), PROFILE, ParseLimits())
    assert result.complete
    assert result.counts.rejected == 4
    assert result.counts.candidate == 0
    assert {'duplicate_id', 'invalid_id', 'invalid_date', 'formula'} <= codes(result)
    assert result.rows[-1].cells[5].value == '=1+1'
    assert all(row.disposition == 'rejected' for row in result.rows)
    assert '16/08/2026' not in repr(result.issues)


@pytest.mark.parametrize('due', ['-', 'Recurrente', 'Sin fecha (por definir)', '', None])
def test_documented_no_date_literals_are_preserved(due):
    result = parse_checklist(xlsx_source([record(due=due)]), PROFILE, ParseLimits())
    assert result.counts.candidate == 1
    assert result.rows[0].due_date is None


def test_required_duplicate_and_whitespace_headers_do_not_overwrite_values():
    headers = (*HEADERS, 'ID')
    result = parse_checklist(csv_source([record() + ['T-002']], headers), PROFILE, ParseLimits())
    assert result.counts.rejected == 1
    assert result.rows[0].source_id is None
    assert len(result.rows[0].cells) == 12
    result = parse_checklist(csv_source([record()], (' ID ', *HEADERS[1:])), PROFILE, ParseLimits())
    assert result.headers[0].value == ' ID '
    assert 'missing_header' in codes(result)
    assert result.counts.rejected == 1


@pytest.mark.parametrize('source,code', [
    (SourceSnapshot('bad.csv', b'\xff'), 'encoding_error'),
    (SourceSnapshot('bad.csv', b'ID;Tarea\n"unterminated'), 'parse_error'),
    (SourceSnapshot('bad.xlsx', b'not zip'), 'parse_error'),
    (SourceSnapshot('empty.csv', b''), 'empty_source'),
    (SourceSnapshot('other.pdf', b'content'), 'unsupported_format'),
    (SourceSnapshot('../bad.csv', b'ID'), 'unsafe_locator'),
])
def test_failed_parse_is_not_empty_success(source, code):
    result = parse_checklist(source, PROFILE, ParseLimits())
    assert not result.complete and result.counts is None
    assert code in codes(result)


def test_wrong_sheet_is_explicit_failure():
    result = parse_checklist(xlsx_source([record()], sheet='Wrong'), PROFILE, ParseLimits())
    assert not result.complete and 'missing_sheet' in codes(result)
    assert result.sheet_names == ('Wrong',)


@pytest.mark.parametrize('factory', [csv_source, xlsx_source])
@pytest.mark.parametrize('change', [dict(max_input_bytes=10), dict(max_rows=1), dict(max_columns=2), dict(max_cells=12), dict(max_cell_chars=3)])
def test_limits_never_return_truncated_success(factory, change):
    result = parse_checklist(factory([record(), record('T-002')]), PROFILE, replace(ParseLimits(), **change))
    assert not result.complete and result.counts is None
    assert 'limit_exceeded' in codes(result)
    assert result.rows == ()


@pytest.mark.parametrize('change', [dict(max_zip_members=1), dict(max_expanded_bytes=100), dict(max_compression_ratio=1)])
def test_zip_limits_before_workbook_load(monkeypatch, change):
    import app.modules.task_import.checklist_parser as parser
    source = xlsx_source([record()])
    monkeypatch.setattr(parser, 'load_workbook', lambda *a, **k: pytest.fail('must reject before openpyxl'))
    result = parse_checklist(source, PROFILE, replace(ParseLimits(), **change))
    assert not result.complete and 'limit_exceeded' in codes(result)


def rewrite_zip(source, name, content):
    output = BytesIO()
    with ZipFile(BytesIO(source.data)) as original, ZipFile(output, 'w', ZIP_DEFLATED) as target:
        for member in original.infolist():
            target.writestr(member.filename, content if member.filename == name else original.read(member))
    return SourceSnapshot(source.relative_path, output.getvalue())


def test_external_links_are_flagged_without_following_them():
    source = xlsx_source([record()])
    source = rewrite_zip(source, '_rels/.rels', b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="external" TargetMode="External" Target="https://invalid.example/"/></Relationships>')
    result = parse_checklist(source, PROFILE, ParseLimits())
    assert not result.complete and 'external_link' in codes(result)


def test_xlsx_numeric_zero_is_not_blank_and_empty_string_is_not_absent():
    row = record()
    row[6] = 0
    result = parse_checklist(xlsx_source([row]), PROFILE, ParseLimits())
    cells = result.rows[0].cells
    assert result.counts.candidate == 1
    assert cells[6].value == 0 and cells[6].kind == 'n'
    assert cells[10].value is None and cells[10].kind == 'inlineStr'


def test_false_small_xlsx_dimension_cannot_hide_rows():
    source = xlsx_source([record(), record('T-002')])
    with ZipFile(BytesIO(source.data)) as archive:
        xml = archive.read('xl/worksheets/sheet1.xml')
    xml = xml.replace(b'ref="A1:K3"', b'ref="A1:A1"')
    result = parse_checklist(rewrite_zip(source, 'xl/worksheets/sheet1.xml', xml), PROFILE, ParseLimits())
    assert result.complete and result.counts.candidate == 2


@pytest.mark.parametrize('replacement', [
    b'<row r="2"><c r="A2" t="inlineStr"><is><t>T-002</t></is></c></row></sheetData>',
    b'<row r="1"><c r="A1" t="inlineStr"><is><t>T-002</t></is></c></row></sheetData>',
])
def test_duplicate_or_out_of_order_xml_rows_cannot_disappear(replacement):
    source = xlsx_source([record()])
    with ZipFile(BytesIO(source.data)) as archive:
        xml = archive.read('xl/worksheets/sheet1.xml')
    xml = xml.replace(b'</sheetData>', replacement)
    result = parse_checklist(rewrite_zip(source, 'xl/worksheets/sheet1.xml', xml), PROFILE, ParseLimits())
    assert not result.complete and 'unsupported_structure' in codes(result)


@pytest.mark.parametrize('fragment,inside_data', [
    (b'<row xmlns="urn:unknown" r="3"><c r="A3" t="inlineStr"><is><t>002</t></is></c></row>', True),
    (b'<row r="3"><c xmlns="urn:unknown" r="A3" t="inlineStr"><is><t>002</t></is></c></row>', True),
    (b'<row xmlns="" r="3"><c r="A3"/></row>', True),
    (b'<wrapper><row r="3"><c r="A3"/></row></wrapper>', True),
    (b'<row r="3"><wrapper><c r="A3"/></wrapper></row>', True),
    (b'<row r="3"><c r="A3"/></row>', False),
    (b'<sheetData><row r="3"><c r="A3"/></row></sheetData>', False),
    (b'<row r="3"><c r="A3"><wrapper><v>002</v></wrapper></c></row>', True),
])
def test_ambiguous_worksheet_structure_is_not_partial_success(fragment, inside_data):
    source = xlsx_source([record()])
    with ZipFile(BytesIO(source.data)) as archive:
        xml = archive.read('xl/worksheets/sheet1.xml')
    closing = b'</sheetData>' if inside_data else b'</worksheet>'
    xml = xml.replace(closing, fragment + closing)
    source = rewrite_zip(source, 'xl/worksheets/sheet1.xml', xml)
    result = parse_checklist(source, PROFILE, ParseLimits())
    assert not result.complete
    assert result.counts is None and result.rows == ()
    assert 'unsupported_structure' in codes(result)
    assert result.source is source


def test_supported_prefixed_namespace_and_harmless_sheet_structures():
    from xml.etree import ElementTree

    source = xlsx_source([record()])
    with ZipFile(BytesIO(source.data)) as archive:
        root = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    ElementTree.SubElement(root, ns + 'printOptions', {'gridLines': '1'})
    # ElementTree serializes with a namespace prefix, without global registration.
    xml = ElementTree.tostring(root)
    result = parse_checklist(rewrite_zip(source, 'xl/worksheets/sheet1.xml', xml), PROFILE, ParseLimits())
    assert result.complete and result.counts.candidate == 1
    assert result.rows[0].source_id == 'T-001'


def test_xml_dtd_is_rejected_before_workbook_load(monkeypatch):
    import app.modules.task_import.checklist_parser as parser
    source = xlsx_source([record()])
    source = rewrite_zip(source, 'xl/worksheets/sheet1.xml', b'<!DOCTYPE worksheet [<!ENTITY x "secret">]><worksheet>&x;</worksheet>')
    monkeypatch.setattr(parser, 'load_workbook', lambda *a, **k: pytest.fail('DTD reached openpyxl'))
    result = parse_checklist(source, PROFILE, ParseLimits())
    assert not result.complete and 'unsupported_structure' in codes(result)


def test_header_only_is_complete_zero_rows_not_empty_source():
    result = parse_checklist(csv_source([]), PROFILE, ParseLimits())
    assert result.complete and result.counts.total == 0


def test_unsupported_merged_cells_are_not_silently_lost():
    source = xlsx_source([record()])
    with ZipFile(BytesIO(source.data)) as archive:
        xml = archive.read('xl/worksheets/sheet1.xml')
    xml = xml.replace(b'</worksheet>', b'<mergeCells count="1"><mergeCell ref="A2:B2"/></mergeCells></worksheet>')
    result = parse_checklist(rewrite_zip(source, 'xl/worksheets/sheet1.xml', xml), PROFILE, ParseLimits())
    assert not result.complete and 'unsupported_structure' in codes(result)
