"""Offline tests of the 45b plan importers (parsers, linker, use case).

Every source is SYNTHETIC and built inside the test with the same structure
as the institutional documents (never their content): a DOCX is a ZIP with
``word/document.xml``; the PAI is an openpyxl workbook.
"""

import uuid
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest
from openpyxl import Workbook

from app.modules.plans.importers.apply import apply_bundle, build_bundle
from app.modules.plans.importers.common import SourceFormatError
from app.modules.plans.importers.linker import resolve_cross_references
from app.modules.plans.importers.pai import parse_pai
from app.modules.plans.importers.pspi import parse_pspi
from app.modules.plans.importers.ptr import parse_ptr

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _p(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def _row(cells: list[str], span: int | None = None) -> str:
    pr = f'<w:tcPr><w:gridSpan w:val="{span}"/></w:tcPr>' if span else ""
    return "<w:tr>" + "".join(f"<w:tc>{pr}{_p(c)}</w:tc>" for c in cells) + "</w:tr>"


def _table(rows: list[str]) -> str:
    return "<w:tbl>" + "".join(rows) + "</w:tbl>"


def _docx(path: Path, blocks: list[str]) -> Path:
    body = "".join(blocks)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="{_NS}"><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


PSPI_HEADER = [
    "No.",
    "ACTIVIDAD",
    "PRODUCTO",
    "FECHA FIN",
    "RESPONSABLE",
    "META 2026",
    "CONTROL ISO",
]


def _pspi(tmp_path: Path, extra_rows: list[str] | None = None) -> Path:
    rows = [
        _row(PSPI_HEADER),
        _row(["1. GRUPO UNO"], span=7),
        _row(["1.1", "Actividad uno", "Producto uno", "15-dic-2026", "OAP", "0% → 100%", "5.34"]),
        _row(
            [
                "1.2",
                "(OM-01/OM-02) Doble código",
                "P",
                "30-jun-2026",
                "Otra área",
                "95% → 100%",
                "8.10, 8.15",
            ]
        ),  # fmt: skip
        _row(["2. GRUPO DOS"], span=7),
        _row(
            ["2.1", "(OM-03) Contingencia", "Guías", "30-sep-2026", "OAP, DGC", "0% → 50%", "5.30"]
        ),
        _row(["2.2", "Etiquetado", "DLP", "Continuo", "OAP", "0% → 100%", "8.12"]),
        *(extra_rows or []),
    ]
    return _docx(tmp_path / "pspi_v2_20260120.docx", [_p("Tabla 2. Actividades"), _table(rows)])


PTR_ACTIONS = ["Riesgo", "Acción", "Responsable", "Fecha", "Meta 2026", "Producto",
               "Control ISO 27001:2022", "Actividad Plan Seguridad"]  # fmt: skip


def _ptr(tmp_path: Path) -> Path:
    matrix = _table(
        [
            _row(["ID", "Descripción del Riesgo", "Nivel Res."]),
            *(_row([code, "Riesgo sintético", "ALTO"]) for code in ("R1", "R2", "R3", "R4", "R9")),
        ]
    )
    distribution = _table([_row(["Nivel", "Cantidad"]), _row(["TOTAL", "4"])])
    high = _table(
        [
            _row(PTR_ACTIONS),
            _row(
                [
                    "R1",
                    "Acción uno",
                    "OAP",
                    "30-sep-2026",
                    "0% → 100%",
                    "Prod",
                    "5.30 (Cont.)",
                    "2.2 (OM-03)",
                ]
            ),  # fmt: skip
            _row(
                [
                    "R2",
                    "Acción dos",
                    "OAP",
                    "30-sep-2026",
                    "0% → 100%",
                    "Prod",
                    "5.34 (Datos)",
                    "1.1, 1.2",
                ]
            ),  # fmt: skip
        ]
    )
    moderate = _table(
        [
            _row(PTR_ACTIONS),
            _row(
                [
                    "R3",
                    "Acción tres",
                    "DAF",
                    "31-dic-2026",
                    "0% → 100%",
                    "Prod",
                    "8.7 (Malware)",
                    "2.2",
                ]
            ),  # fmt: skip
            _row(["R4", "Acción cuatro", "OAP", "31-dic-2026", "0% → 100%", "Prod", "8.1", "-"]),
            _row(["R5", "Sin matriz", "OAP", "31-dic-2026", "0% → 100%", "Prod", "8.1", "-"]),
        ]
    )
    return _docx(
        tmp_path / "ptr_v2_20260120.docx",
        [
            _p("Tabla 6. Matriz"), matrix, _p("Tabla 7. Distribución"), distribution,
            _p("Tabla 9. Riesgos Altos"), high, _p("Tabla 10. Riesgos Moderados"), moderate,
        ],
    )  # fmt: skip


def _pai(tmp_path: Path, *, offset: int = 0) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PlandeacciónInstitucional"
    sheet.cell(2, 20, "Versión: 02")
    sheet.cell(3, 20, "Fecha: 09/06/2026")
    headers = [
        "POLÍTICAS MODELO INTEGRADO DE PLANEACIÓN Y GESTIÓN (MIPG)",
        "RESPONSABLE",
        "CÓDIGO ACTIVIDAD No.",
        "ACTIVIDAD DE GESTIÓN",
        "PRODUCTO",
        "EVIDENCIA",
        "PROGRAMADO / EJECUTADO",
        "Seguimiento I Cuatrimestre",
        "Seguimiento II Cuatrimestre",
        "Seguimiento III Cuatrimestre",
        "% de avance Cuatrimestral",
        "Avance cualitativo",
    ]
    for column, header in enumerate(headers, start=1 + offset):
        sheet.cell(8, column, header)
    rows = [
        ["10. Otra política", "Otra oficina", 1, "Ajena", "P", "E", "Programado", "x", None, None],
        [None, None, None, None, None, None, "Ejecutado"],
        ["11.Gobierno digital \n(Jefe)", "OAP - Equipo Arquitectura Empresarial TI", 1,
         "Sensibilizar", "Sensibilizaciones", "Listas", "Programado", None, "x", None],
        [None, None, None, None, None, None, "Ejecutado", None, "x"],
        [None, "OAP - Equipo Tecnología de Información", 2.0, "Contingencia", "Plan", "Doc",
         "Programado", "x", "x", "x", 1, "Avance"],
        [None, None, None, None, None, None, "Ejecutado"],
        ["12. Seguridad digital", "OAP - Equipo Tecnología de Información", 1, "Riesgos",
         "Matriz", "Publicación", "Programado", None, "x", None],
        [None, None, None, None, None, None, "Ejecutado"],
    ]  # fmt: skip
    for index, values in enumerate(rows, start=9):
        for column, value in enumerate(values, start=1 + offset):
            sheet.cell(index, column, value)
    path = tmp_path / "pai.xlsx"
    workbook.save(path)
    return path


def test_docx_reader_rejects_a_file_that_is_not_a_docx(tmp_path: Path) -> None:
    bogus = tmp_path / "x.docx"
    bogus.write_bytes(b"not a zip")
    with pytest.raises(SourceFormatError, match="no es un documento Word"):
        parse_pspi(bogus, period_year=2026)


def test_pspi_reads_groups_codes_dates_targets_and_om_codes(tmp_path: Path) -> None:
    parsed = parse_pspi(_pspi(tmp_path), period_year=2026)

    assert parsed.plan.code == "PSPI-2026"
    assert parsed.plan.version == "v2_20260120"
    assert [a.code for a in parsed.activities] == ["1.1", "1.2", "2.1", "2.2"]
    first, double, contingency, dlp = parsed.activities
    assert (first.group_code, first.group_name) == ("1", "GRUPO UNO")
    assert first.due_date == date(2026, 12, 15)
    assert (first.target_from, first.target_to) == (Decimal(0), Decimal(100))
    assert first.is_mine is True and double.is_mine is False
    assert double.external_codes == ["OM-01", "OM-02"]
    assert double.iso_controls == ["8.10", "8.15"]
    assert contingency.group_code == "2" and contingency.external_codes == ["OM-03"]
    assert dlp.due_date is None
    assert any("Continuo" in warning for warning in parsed.warnings)
    assert len(parsed.source.sha256) == 64


def test_pspi_refuses_repeated_activity_codes(tmp_path: Path) -> None:
    repeated = _row(["2.2", "Repetida", "P", "30-sep-2026", "OAP", "0% → 100%", "8.12"])
    with pytest.raises(SourceFormatError, match="repite códigos de actividad: 2.2"):
        parse_pspi(_pspi(tmp_path, [repeated]), period_year=2026)


def test_pspi_without_activity_table_is_a_format_error(tmp_path: Path) -> None:
    path = _docx(tmp_path / "otro.docx", [_table([_row(["Fase", "Descripción"])])])
    with pytest.raises(SourceFormatError, match="tabla de actividades del PSPI"):
        parse_pspi(path, period_year=2026)


def test_ptr_reads_actions_levels_references_and_source_gaps(tmp_path: Path) -> None:
    parsed = parse_ptr(_ptr(tmp_path), period_year=2026)

    assert [a.code for a in parsed.activities] == ["R1", "R2", "R3", "R4", "R5"]
    assert [a.group_code for a in parsed.activities] == ["ALTO", "ALTO"] + ["MODERADO"] * 3
    assert parsed.activities[0].iso_controls == ["5.30"]
    assert parsed.activities[2].is_mine is False
    assert parsed.cross_refs == {"R1": "2.2 (OM-03)", "R2": "1.1, 1.2", "R3": "2.2"}
    assert parsed.warnings == [
        "El riesgo R5 tiene acción de tratamiento pero no figura en la matriz.",
        "El riesgo R9 figura en la matriz sin acción de tratamiento ni aceptación.",
        "La distribución de riesgos declara 4 riesgos y la matriz tiene 5 filas.",
    ]


def test_linker_records_conflicts_and_never_invents_a_link(tmp_path: Path) -> None:
    pspi = parse_pspi(_pspi(tmp_path), period_year=2026)
    ptr = parse_ptr(_ptr(tmp_path), period_year=2026)

    links, review = resolve_cross_references(ptr, pspi)

    by_from = {(link.from_key, link.to_key): link for link in links}
    conflict = by_from[("PTR-2026/R1", "PSPI-2026/2.1")]
    assert conflict.resolution == "conflict"
    assert conflict.source_reference == "2.2 (OM-03)"
    assert "OM-03 pertenece a 2.1" in (conflict.note or "")
    assert by_from[("PTR-2026/R2", "PSPI-2026/1.1")].resolution == "exact"
    assert by_from[("PTR-2026/R2", "PSPI-2026/1.2")].resolution == "exact"
    assert not any(link.from_key == "PTR-2026/R3" for link in links)
    assert [(item.from_key, item.source_reference) for item in review] == [("PTR-2026/R3", "2.2")]


def test_pai_reads_two_row_activities_of_the_selected_policies(tmp_path: Path) -> None:
    parsed = parse_pai(_pai(tmp_path, offset=3), period_year=2026)

    assert parsed.plan.code == "PAI-2026"
    assert parsed.plan.version == "v02_20260609"
    assert [a.code for a in parsed.activities] == ["11.1", "11.2", "12.1"]
    first, second, third = parsed.activities
    assert (first.group_code, first.group_name) == ("11", "11. Gobierno digital")
    assert first.scheduled_periods == ["II"]
    assert second.scheduled_periods == ["I", "II", "III"]
    assert third.group_name == "12. Seguridad digital"
    assert all(a.is_mine for a in parsed.activities)
    assert parsed.facts["activities_in_source"] == 4
    assert parsed.facts["activities_per_policy"] == {"10": 1, "11": 2, "12": 1}
    assert any("11.1 ejecutado en II" in w and "11.2 con avance" in w for w in parsed.warnings)


def test_pai_never_selects_by_itself(tmp_path: Path) -> None:
    with pytest.raises(SourceFormatError, match="políticas seleccionadas"):
        parse_pai(_pai(tmp_path), period_year=2026, policies=("99",))


def test_bundle_warns_when_ptr_references_cannot_be_resolved(tmp_path: Path) -> None:
    bundle = build_bundle([parse_ptr(_ptr(tmp_path), period_year=2026)])
    assert bundle.links == [] and bundle.review == []
    assert "el PSPI no está en esta corrida" in bundle.warnings[0]


class _FakeUow:
    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on
        self.plans = self

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if name == self.fail_on:
            raise RuntimeError(name)

    async def upsert_plan(self, organization_id, data, actor_id=None):
        self._record("plan")
        return SimpleNamespace(id=uuid.uuid4(), code=data.code)

    async def upsert_activity(self, plan_id, data, actor_id=None):
        self._record("activity")
        return SimpleNamespace(id=uuid.uuid4())

    async def upsert_activity_link(self, *args, **kwargs):
        self._record("link")

    async def flush(self) -> None:
        self._record("flush")

    async def commit(self) -> None:
        self._record("commit")

    async def rollback(self) -> None:
        self.calls.append("rollback")


@pytest.mark.asyncio
async def test_apply_writes_everything_then_commits_once(tmp_path: Path) -> None:
    bundle = build_bundle(
        [parse_pspi(_pspi(tmp_path), period_year=2026), parse_ptr(_ptr(tmp_path), period_year=2026)]
    )
    uow = _FakeUow()
    assert await apply_bundle(uow, uuid.uuid4(), bundle) == 9
    assert uow.calls.count("commit") == 1 and uow.calls[-1] == "commit"
    assert uow.calls.index("flush") < uow.calls.index("link")
    assert uow.calls.count("link") == len(bundle.links) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on", ["plan", "activity", "flush", "link", "commit"])
async def test_apply_rolls_back_on_any_failure(tmp_path: Path, fail_on: str) -> None:
    bundle = build_bundle(
        [parse_pspi(_pspi(tmp_path), period_year=2026), parse_ptr(_ptr(tmp_path), period_year=2026)]
    )
    uow = _FakeUow(fail_on)
    with pytest.raises(RuntimeError, match=fail_on):
        await apply_bundle(uow, uuid.uuid4(), bundle)
    assert uow.calls[-1] == "rollback"
    assert "commit" not in uow.calls[:-1] or fail_on == "commit"
