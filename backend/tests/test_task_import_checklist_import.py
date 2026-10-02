"""T05f pure plan: identity, project/status mapping, dates and provenance (no DB)."""

from datetime import UTC, datetime

import pytest

from app.modules.task_import.checklist_import import (
    CHECKLIST_SOURCE,
    GENERALES,
    PANDORA,
    PROVENANCE_MARKER,
    SGSI,
    body_of,
    build_checklist_plan,
    due_datetime,
    map_project,
    work_folders_from_names,
)
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot

HEADER = (
    "ID;Estado;Vencido;Urgencia;Categoría;Tarea;Detalle;Fecha Límite;Solicitante;Apoyo IA;"
    "Observaciones"
)


def _preview(*rows: str):
    data = ("﻿" + "\n".join((HEADER, *rows)) + "\n").encode("utf-8")
    return parse_checklist(SourceSnapshot("CHECKLIST.csv", data), ChecklistProfile(), ParseLimits())


def _plan(*rows: str, **kwargs):
    return build_checklist_plan(_preview(*rows), source_name="CHECKLIST.csv", **kwargs)


def test_source_is_the_registered_checklist_family():
    assert CHECKLIST_SOURCE == "checklist_xlsx"


@pytest.mark.parametrize(
    ("category", "code", "basis"),
    [
        ("Pandora / SIG", PANDORA, "rule"),
        ("Gestión Documental / Pandora", PANDORA, "rule"),
        ("Plan Seguridad D612", SGSI, "rule"),
        ("SGSI / Plan de cierre de brechas SoA", SGSI, "rule"),
        ("Protección de Datos", SGSI, "rule"),
        ("Seguridad / Azure AD", SGSI, "rule"),
        ("MIPG / Documentación", GENERALES, "default"),
        ("", GENERALES, "default"),
    ],
)
def test_project_comes_only_from_the_category(category, code, basis):
    decision = map_project(category)
    assert (decision.code, decision.basis) == (code, basis)


def test_identity_is_namespace_plus_source_id_not_title_or_hash():
    first = _plan("T-01;PENDIENTE;No;ALTA;Seguridad;Título A;;2026-05-15;Ana;No;")
    renamed = _plan("T-01;PENDIENTE;No;ALTA;Seguridad;Título B;;2026-05-15;Ana;No;")
    assert first.sha256 != renamed.sha256
    assert first.drafts[0].external_key == renamed.drafts[0].external_key == "CHECKLIST_TAREAS:T-01"
    other = _plan("T-01;PENDIENTE;No;ALTA;Seguridad;Título A;;;Ana;No;", namespace="OTRO")
    assert other.drafts[0].external_key == "OTRO:T-01"


def test_status_maps_to_the_target_board_columns():
    plan = _plan(
        "T-01;PENDIENTE;No;ALTA;Seguridad;A;;;x;No;",
        "T-02;EN CURSO;No;ALTA;Pandora / SIG;B;;;x;No;",
        "T-03;COMPLETADA;No;BAJA;MIPG;C;;;x;No;",
    )
    assert [(d.project_code, d.status_key) for d in plan.drafts] == [
        (SGSI, "Sin iniciar"),
        (PANDORA, "Doing"),
        (GENERALES, "COMPLETADA"),
    ]


def test_state_without_column_in_pandora_falls_back_to_generales_and_is_listed():
    plan = _plan("T-10;REMOVIDA;No;ALTA;Pandora / Soporte;A;;;x;No;")
    draft = plan.drafts[0]
    assert (draft.project_code, draft.status_key, draft.project_basis) == (
        GENERALES,
        "REMOVIDA",
        "state_fallback",
    )
    assert [n.kind for n in plan.review] == ["estado_sin_columna"]


def test_dates_only_from_explicit_values_and_prose_goes_to_review():
    plan = _plan(
        "T-01;PENDIENTE;No;ALTA;Seguridad;A;;2026-05-15;x;No;",
        "T-02;PENDIENTE;No;ALTA;Seguridad;B;;Sin fecha (por definir);x;No;",
        "T-03;PENDIENTE;No;ALTA;Seguridad;C;;Recurrente;x;No;",
        "T-04;PENDIENTE;No;ALTA;Seguridad;D;;Sin fecha;x;No;",
    )
    dues = {d.source_id: d.due_date for d in plan.drafts}
    assert dues["T-01"] == due_datetime(datetime(2026, 5, 15).date())
    assert dues["T-01"].astimezone(UTC).date().isoformat() == "2026-05-15"
    assert dues["T-02"] is dues["T-03"] is dues["T-04"] is None
    assert [(n.kind, n.source_id) for n in plan.review] == [("fecha_en_prosa", "T-04")]
    assert len(plan.drafts) == 4 and not plan.skipped


def test_rows_rejected_for_other_reasons_are_skipped_and_listed():
    plan = _plan(
        "T-01;PENDIENTE;No;ALTA;Seguridad;A;;;x;No;",
        "T-01;PENDIENTE;No;ALTA;Seguridad;B;;;x;No;",
        "T-02;INVENTADO;No;ALTA;Seguridad;C;;;x;No;",
    )
    assert plan.drafts == []
    assert {n.source_id for n in plan.skipped} == {"T-01", "T-02"}


def test_empty_urgency_uses_default_priority_and_is_listed():
    plan = _plan(
        "T-01;PENDIENTE;No;-;Seguridad;A;;;x;No;", "T-02;PENDIENTE;No;CRÍTICA;Seguridad;B;;;x;No;"
    )
    assert [d.priority for d in plan.drafts] == ["medium", "critical"]
    assert [n.kind for n in plan.review] == ["urgencia_vacia"]


def test_description_keeps_body_and_provenance_separately():
    plan = _plan(
        "T-07;EN CURSO;No;ALTA;Seguridad / DLP;Tarea;Detalle largo;;Ana;Total;Nota",
        work_folders={"T-07": "T-07_DLP"},
    )
    draft = plan.drafts[0]
    assert draft.body == "Detalle largo\n\n**Observaciones**\n\nNota"
    assert PROVENANCE_MARKER in draft.description
    assert "ID T-07 · registro 2" in draft.provenance
    assert "Carpeta de trabajo (relativa a TAREAS): T-07_DLP/" in draft.provenance
    assert body_of(draft.description) == draft.body
    assert body_of(None) == ""


def test_work_folders_ignore_ambiguous_ids():
    assert work_folders_from_names(["T-01", "T-02_X", "T-02_Y", "BITACORA", "T-3x"]) == {
        "T-01": "T-01"
    }


def test_incomplete_preview_is_refused():
    preview = parse_checklist(SourceSnapshot("x.csv", b""), ChecklistProfile(), ParseLimits())
    with pytest.raises(ValueError):
        build_checklist_plan(preview, source_name="x.csv")
