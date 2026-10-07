"""C05: candidate selection (cosine top-k + key priority) and validation of
the LLM output against the candidates. Pure, no database, no network."""

import uuid

import pytest
from pydantic import ValidationError

from app.modules.reconciliation.candidates import (
    TaskSnapshot,
    build_key_index,
    cosine,
    select_candidates,
    task_embedding_text,
)
from app.modules.reconciliation.prompt import ThreadClassification, validate_classification


def _task(ref: str | None, title: str, *, keys: tuple[str, ...] = ()) -> TaskSnapshot:
    return TaskSnapshot(
        id=uuid.uuid4(),
        ref=ref,
        title=title,
        description="Descripción larga " * 50,
        keys=keys or ((ref,) if ref else ()),
    )


def test_cosine_basics():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_task_embedding_text_has_key_title_and_short_description():
    text = task_embedding_text(_task("T-205", "Renovar antivirus"))
    assert text.startswith("T-205 Renovar antivirus")
    assert len(text) <= 400


def test_top_k_by_similarity_when_no_key_is_mentioned():
    tasks = [_task(f"T-{n}", f"Tarea {n}") for n in range(1, 8)]
    vectors = {t.id: [1.0, float(n)] for n, t in enumerate(tasks)}
    picked = select_candidates(
        mentioned_keys=set(),
        key_index=build_key_index(tasks),
        thread_vector=[1.0, 6.0],
        task_vectors=vectors,
        tasks={t.id: t for t in tasks},
        k=5,
    )
    assert len(picked) == 5
    assert all(c.via == "similitud" for c in picked)
    scores = [c.score for c in picked]
    assert scores == sorted(scores, reverse=True)


def test_mentioned_key_is_first_even_with_low_similarity():
    target = _task("SGSI-12", "Política de respaldo")
    others = [_task(f"T-{n}", f"Otra {n}") for n in range(1, 7)]
    tasks = [target, *others]
    vectors = {t.id: [1.0, 1.0] for t in others} | {target.id: [-1.0, 0.0]}
    picked = select_candidates(
        mentioned_keys={"SGSI-12", "ZZ-1"},
        key_index=build_key_index(tasks),
        thread_vector=[1.0, 1.0],
        task_vectors=vectors,
        tasks={t.id: t for t in tasks},
        k=5,
    )
    assert picked[0].task_id == target.id and picked[0].via == "clave"
    assert len(picked) == 5
    assert len({c.task_id for c in picked}) == 5


def test_key_candidates_survive_without_embeddings():
    target = _task("T-7", "Acceso VPN")
    picked = select_candidates(
        mentioned_keys={"T-7"},
        key_index=build_key_index([target]),
        thread_vector=None,
        task_vectors={},
        tasks={target.id: target},
        k=5,
    )
    assert [c.ref for c in picked] == ["T-7"]


def test_tasks_without_key_get_a_unique_label():
    a, b = _task(None, "Sin clave A"), _task(None, "Sin clave B")
    picked = select_candidates(
        mentioned_keys=set(),
        key_index={},
        thread_vector=[1.0],
        task_vectors={a.id: [1.0], b.id: [0.5]},
        tasks={a.id: a, b.id: b},
        k=5,
    )
    assert len({c.ref for c in picked}) == 2


# --- LLM output validation -----------------------------------------------------


def _output(**overrides) -> ThreadClassification:
    data = {
        "relacion": "tarea_existente",
        "task_ref": "T-7",
        "confianza": 0.9,
        "atendida": "parcial",
        "accion": "Dar acceso a la VPN",
        "solicitante": "Ana",
        "fecha_limite": "2026-10-10",
        "resumen": "Ana pide acceso a la VPN.",
        "motivo": "Menciona la VPN.",
    }
    data.update(overrides)
    return ThreadClassification.model_validate(data)


def _candidates():
    target = _task("T-7", "Acceso VPN")
    return select_candidates(
        mentioned_keys={"T-7"},
        key_index=build_key_index([target]),
        thread_vector=None,
        task_vectors={},
        tasks={target.id: target},
        k=5,
    )


def test_valid_reference_maps_to_the_candidate_task():
    candidates = _candidates()
    decision = validate_classification(_output(task_ref="t-7"), candidates)
    assert decision.relation == "tarea_existente"
    assert decision.task_id == candidates[0].task_id
    assert decision.confidence == pytest.approx(0.9)
    assert decision.payload["fecha_limite"] == "2026-10-10"


def test_reference_outside_candidates_degrades_to_new_task_with_low_confidence():
    decision = validate_classification(_output(task_ref="T-999"), _candidates())
    assert decision.relation == "tarea_nueva"
    assert decision.task_id is None
    assert decision.confidence <= 0.3
    assert decision.payload["degradada"] is True


def test_existing_without_reference_degrades_too():
    decision = validate_classification(_output(task_ref=None), _candidates())
    assert decision.relation == "tarea_nueva" and decision.task_id is None


def test_non_existing_relations_never_carry_a_task():
    decision = validate_classification(
        _output(relacion="irrelevante", task_ref="T-7"), _candidates()
    )
    assert decision.task_id is None and decision.payload["task_ref"] is None


def test_invalid_deadline_is_dropped():
    decision = validate_classification(_output(fecha_limite="el viernes"), _candidates())
    assert decision.payload["fecha_limite"] is None


def test_schema_rejects_out_of_range_confidence_and_unknown_relation():
    with pytest.raises(ValidationError):
        _output(confianza=1.5)
    with pytest.raises(ValidationError):
        _output(relacion="otra")
