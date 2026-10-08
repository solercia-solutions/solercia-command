"""E03: prompt v2 (8 classes), post-rules and evidence-calibrated confidence.

The model's own confidence is never used: confidence comes from HOW the
chosen task was reached (explicit ID > object identifier > similarity) and
whether the quoted evidence really is in the record. SYNTHETIC data only.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.ai.determinism import Determinism, determinism_profile
from app.modules.reconciliation.prompt_v2 import (
    PROMPT_VERSION_V2,
    SYSTEM_PROMPT_V2,
    ClassificationV2,
    apply_post_rules,
    build_user_message_v2,
)
from app.modules.reconciliation.stages import CandidateV2, MailRecord, build_units

TEXT = "Hola, adjunto el informe final de la VPN ya publicado. Quedo atento."
CANDIDATES = [
    CandidateV2("id7", "T-7", "VPN", "EN CURSO", 1.0, "id_explicito"),
    CandidateV2("id9", "T-9", "Informe", "PENDIENTE", 1.0, "identificador:caso"),
    CandidateV2("id3", "T-3", "Antivirus", "COMPLETADA", 0.71, "similitud"),
]


def _out(**fields):
    base = {
        "clase": "avanza",
        "task_ref": "T-7",
        "evidencia": "adjunto el informe final de la VPN",
        "accion": None,
        "solicitante": None,
        "fecha_limite": None,
        "resumen": "Envía el informe.",
    }
    base.update(fields)
    return ClassificationV2.model_validate(base)


def test_schema_accepts_exactly_the_eight_classes():
    for clase in (
        "cierra",
        "avanza",
        "confirma",
        "tarea_nueva",
        "solo_bitacora",
        "informativo",
        "descartado",
        "no_concluyente",
    ):
        assert _out(clase=clase).clase == clase
    with pytest.raises(ValidationError):
        _out(clase="irrelevante")


def test_prompt_is_versioned_and_states_the_closing_criterion():
    assert PROMPT_VERSION_V2.startswith("reconciliation-v2")
    for phrase in ("ante la duda", "no_concluyente", "evidencia", "borrador"):
        assert phrase in SYSTEM_PROMPT_V2.lower()


@pytest.mark.parametrize(
    ("via_ref", "expected"),
    [("T-7", 0.9), ("T-9", 0.75), ("T-3", 0.5)],
)
def test_confidence_comes_from_how_the_task_was_reached(via_ref, expected):
    verdict = apply_post_rules(_out(task_ref=via_ref), CANDIDATES, TEXT)
    assert verdict.clase == "avanza"
    assert verdict.confidence == expected


def test_evidence_not_in_the_record_lowers_confidence():
    verdict = apply_post_rules(_out(evidencia="el contrato fue firmado"), CANDIDATES, TEXT)
    assert verdict.confidence == pytest.approx(0.54)
    assert verdict.payload["evidencia_valida"] is False


def test_task_ref_outside_candidates_is_not_conclusive():
    verdict = apply_post_rules(_out(task_ref="T-99"), CANDIDATES, TEXT)
    assert verdict.clase == "no_concluyente"
    assert verdict.task_id is None
    assert verdict.payload["ajustes"] == ["task_ref_fuera_de_candidatas"]
    assert verdict.payload["task_ref_original"] == "T-99"


def test_task_class_without_task_is_not_conclusive():
    verdict = apply_post_rules(_out(clase="cierra", task_ref=None), CANDIDATES, TEXT)
    assert verdict.clase == "no_concluyente"
    assert verdict.payload["ajustes"] == ["clase_sin_tarea"]


def test_non_task_classes_drop_the_task_and_case_insensitive_refs_match():
    new = apply_post_rules(_out(clase="tarea_nueva", task_ref="T-7"), CANDIDATES, TEXT)
    assert new.task_id is None and new.confidence == 0.55
    lower = apply_post_rules(_out(task_ref="t-07"), CANDIDATES, TEXT)
    assert lower.task_ref == "T-7" and lower.task_id == "id7"


def test_user_message_shows_kind_state_and_candidates_with_status():
    record = MailRecord(
        id="m1",
        kind="in",
        conversation_id="c1",
        subject="Informe VPN",
        sender="ana@otra.gov.co",
        to=("yo@x",),
        cc=(),
        occurred_at=datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        body=TEXT,
    )
    (unit,) = [u for u in build_units([record]) if u.kind == "thread"]
    message = build_user_message_v2(unit, CANDIDATES, max_chars=4000)
    assert "hilo de correo" in message.lower()
    assert "pendiente_respuesta" in message
    assert "- T-7 [EN CURSO] (id_explicito): VPN" in message
    assert TEXT in message


def test_determinism_profiles():
    mac = determinism_profile("mac")
    assert mac == Determinism()
    assert mac.temperature == 0 and mac.top_k == 1 and mac.top_p == 1 and mac.think is False
    server = determinism_profile("server", num_thread=12)
    assert server.num_gpu == 0 and server.num_thread == 12
    options = server.ollama_options(max_tokens=300)
    assert options == {
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "seed": 42,
        "num_ctx": 8192,
        "num_predict": 300,
        "num_gpu": 0,
        "num_thread": 12,
    }
    assert "num_gpu" not in mac.ollama_options(max_tokens=300)
    with pytest.raises(ValueError):
        determinism_profile("gpu-cluster")
