"""Follow-up readers (pure, synthetic sources): PAI reports, declared links, cruce, DOCX."""

import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.modules.plans.importers.followup import (
    LinkCandidate,
    _progress,
    checklist_link_candidates,
    merge_links,
    monthly_report_review,
    parse_cruce_report,
    parse_pai_followup,
)

HEADERS = [
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
    "OBSERVACIONES",
    "% de avance Cuatrimestral",
    "Avance cualitativo Cuatrimestral",
    "Evidencia",
    "Se cumplió la actividad (Si / No)",
    "Se cumplió en la fecha programada (SI / No)",
]


def _pai(tmp_path: Path, rows: list[list]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "PlandeacciónInstitucional"
    for column, header in enumerate(HEADERS, start=1):
        sheet.cell(8, column, header)
    for index, values in enumerate(rows, start=9):
        for column, value in enumerate(values, start=1):
            sheet.cell(index, column, value)
    path = tmp_path / "pai.xlsx"
    workbook.save(path)
    return path


PROGRAMMED = ["12. Seguridad digital", "OAP - Equipo Tecnología de Información", 1, "Sensibilizar",
              "Sesiones", "Listas", "Programado", "x", "x", "x", "Se hizo el 24-ago.", 1,
              "Sensibilización a la Entidad.", "Convocatoria · Lista de asistencia",
              "Si", "No"]  # fmt: skip


def test_pai_report_takes_the_period_marked_in_the_executed_row(tmp_path):
    path = _pai(tmp_path, [PROGRAMMED, [None] * 6 + ["Ejecutado", None, "x", None]])
    reports, review = parse_pai_followup(path, period_year=2026)
    assert review == []
    (report,) = reports
    assert (report.activity_key, report.period) == ("PAI-2026/12.1", "II")
    assert report.reported_progress == Decimal("100.00") and report.raw_progress == "1"
    assert report.evidence_refs == ["Convocatoria", "Lista de asistencia"]
    assert (report.is_met, report.met_on_time) == (True, False)
    assert report.qualitative_summary.startswith("Sensibilización a la Entidad.")
    assert "Observaciones: Se hizo el 24-ago." in report.qualitative_summary
    assert "filas 9/10" in report.source_ref


def test_pai_without_a_single_executed_period_goes_to_review(tmp_path):
    path = _pai(tmp_path, [PROGRAMMED, [None] * 6 + ["Ejecutado", "x", "x", None]])
    reports, review = parse_pai_followup(path, period_year=2026)
    assert reports == [] and review[0].subject == "PAI-2026/12.1"


def test_pai_activity_without_follow_up_produces_nothing(tmp_path):
    empty = PROGRAMMED[:10] + [None] * 6
    path = _pai(tmp_path, [empty, [None] * 6 + ["Ejecutado", None, "x", None]])
    assert parse_pai_followup(path, period_year=2026) == ([], [])


def test_pai_unselected_policy_is_ignored(tmp_path):
    other = ["10. Otra", *PROGRAMMED[1:]]
    path = _pai(tmp_path, [other, [None] * 6 + ["Ejecutado", None, "x", None]])
    assert parse_pai_followup(path, period_year=2026) == ([], [])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, Decimal("100.00")), (0.5, Decimal("50.00")), (75, Decimal("75.00")), (None, None),
     (150, None), ("abc", None)],
)  # fmt: skip
def test_progress_never_invents_a_figure(raw, expected):
    assert _progress(raw)[0] == expected


def _rows(*items):
    return [(sid, n, values) for n, (sid, values) in enumerate(items, start=2)]


def test_declared_links_primary_contributes_and_review():
    rows = _rows(
        ("T-82", {"Tarea": "[PSPI 1.1] Datos personales", "Observaciones": "actividad 1.1"}),
        (
            "T-122",
            {"Tarea": "Cronograma", "Observaciones": "y a la actividad 4.8 del Plan de Seguridad."},
        ),
        ("T-162", {"Tarea": "Soportes de retiros (control R25)", "Detalle": "carpeta R25"}),
        ("T-153", {"Tarea": "Riesgos", "Observaciones": "evidencias de R23 y R35"}),
        ("T-136", {"Tarea": "Activos", "Observaciones": "la Actividad 3.1 en el repositorio PTEP"}),
        ("T-90", {"Tarea": "Varios", "Detalle": "Hallazgo OM-05"}),
    )
    links, review = checklist_link_candidates(rows, source_name="c.csv", period_year=2026)
    found = {
        (lk.source_id, lk.activity_key or lk.external_code, lk.role, lk.resolution) for lk in links
    }
    assert found == {
        ("T-82", "PSPI-2026/1.1", "primary", "exact"),
        ("T-122", "PSPI-2026/4.8", "contributes", "exact"),
        ("T-162", "PTR-2026/R25", "contributes", "by_external_code"),
        ("T-90", "OM-05", "contributes", "by_external_code"),
    }
    subjects = [r.subject for r in review]
    assert "T-153" in subjects and "T-136" in subjects
    assert "T-82" not in subjects and "T-162" not in subjects


def test_cruce_links_except_rows_without_coverage(tmp_path):
    path = tmp_path / "cruce.md"
    path.write_text(
        "## 2. Vencidas\n\n| No. | Actividad | Estado real |\n|---|---|---|\n"
        "| **2.1** | Publicar | **Parcial.** T-01 figura COMPLETADA. |\n\n"
        "## 3. Próximas\n\n| No. | Actividad | Estado real |\n|---|---|---|\n"
        "| **3.2** | Matriz | **Sin cobertura.** Se relaciona con T-32. |\n\n"
        "## 4. Vigentes\n\n| No. | Actividad | Fecha | Tarea | Obs |\n|---|---|---|---|---|\n"
        "| 4.1 | Seguimiento | 31-dic | T-61, T-62 | Exige 3 informes. |\n\n"
        "## 6. Acciones\n\n| 9.9 | x | T-99 |\n",
        encoding="utf-8",
    )
    links, review = parse_cruce_report(path, period_year=2026)
    assert {(lk.source_id, lk.activity_key) for lk in links} == {
        ("T-01", "PSPI-2026/2.1"),
        ("T-61", "PSPI-2026/4.1"),
        ("T-62", "PSPI-2026/4.1"),
    }
    assert all(lk.role == "contributes" for lk in links)
    assert [r.subject for r in review] == ["T-32 → PSPI-2026/3.2"]


def test_merge_keeps_primary_and_every_reference():
    a = LinkCandidate("T-07", "PSPI-2026/4.3", None, "contributes", "exact", "csv", "q1")
    b = LinkCandidate("T-07", "PSPI-2026/4.3", None, "primary", "exact", "cruce", "q2")
    (merged,) = merge_links([a, b])
    assert merged.role == "primary" and merged.source_ref == "csv; cruce"


def test_monthly_docx_is_review_only(tmp_path):
    path = tmp_path / "Reporte Enero.docx"
    body = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Porcentaje de avance en la implementación de la Política de "
        "Seguridad Digital</w:t></w:r></w:p><w:p><w:r><w:t>ENERO 2026 - PORCENTAJE DE AVANCE "
        "(Sumatoria): %</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", body)
    (item,) = monthly_report_review([path])
    assert item.origin == "reporte_mensual" and "vacía" in item.reason
