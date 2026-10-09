"""E07b: candidate retrieval options of channel v2, measured one by one.

- Task text for retrieval can include the checklist detail AND observations.
- A simple BM25 lexical ranking over the task text.
- Reciprocal rank fusion (RRF) of the embedding and lexical rankings with a
  stable tie-break by task ref.
- Object identifiers (GLPI, Orfeo, contracts…) as forced candidates can be
  switched off to measure their contribution.

Pure functions and fakes; SYNTHETIC data only.
"""

from datetime import UTC, datetime

import pytest

from app.modules.reconciliation.channel_v2 import ChannelV2, ChannelV2Config, MemoryEmbeddingCache
from app.modules.reconciliation.rules import compile_rules
from app.modules.reconciliation.stages import (
    LexicalIndex,
    MailRecord,
    TaskEntry,
    build_units,
    fused_candidates,
    lexical_tokens,
    task_embedding_text,
)

ME = "yo@ejemplo.gov.co"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
RULES = compile_rules(
    {
        "version": "2.0.0",
        "buzon": ME,
        "identificadores": {
            "tarea": {"regex": "\\bT-\\d{1,3}\\b"},
            "glpi": {"regex": "\\bGLPI\\s*#?\\s*0*(\\d{5})\\b"},
        },
    }
)
TASKS = [
    TaskEntry(id="T-1", ref="T-1", title="Informe de gestión", detail="Trimestral"),
    TaskEntry(
        id="T-2",
        ref="T-2",
        title="Renovar antivirus",
        detail="Licencias de la consola",
        observations="[Corte 1-sep] Proveedor envió cotización; GLPI 01234",
    ),
    TaskEntry(id="T-3", ref="T-3", title="Matriz de riesgos", detail="Revisión anual"),
    TaskEntry(id="T-10", ref="T-10", title="Cotización de impresoras", detail=""),
]


def _thread(subject, body=""):
    record = MailRecord("m1", "in", "c1", subject, "ana@otra.gov.co", (ME,), (), T0, body)
    (unit,) = build_units([record])
    return unit


# --- task text ---------------------------------------------------------------------------


def test_full_task_text_adds_observations_and_whole_detail():
    task = TaskEntry(
        id="x", ref="T-5", title="Título", detail="d " * 400, observations="Nota final"
    )
    base = task_embedding_text(task)
    full = task_embedding_text(task, full=True)
    assert "Nota final" not in base and len(base) < 320
    assert full.startswith("T-5 Título.") and "Nota final" in full
    assert len(task_embedding_text(task, full=True, max_chars=100)) == 100


# --- lexical ranking ------------------------------------------------------------------------


def test_lexical_tokens_fold_accents_and_drop_stopwords_and_short_words():
    assert lexical_tokens("La Cotización DE las Impresoras, 2026 y GT-PR-18") == [
        "cotizacion",
        "impresoras",
        "2026",
        "gt",
        "pr",
        "18",
    ]


def test_bm25_ranks_by_shared_rare_terms_and_breaks_ties_by_ref():
    index = LexicalIndex(TASKS, full=True)
    ranked = index.rank("Cotización del antivirus para la consola")
    assert [t.ref for t, _ in ranked][:2] == ["T-2", "T-10"]
    assert all(score > 0 for _, score in ranked)
    assert "T-3" not in {t.ref for t, _ in ranked}
    tie = LexicalIndex(
        [TaskEntry(id="b", ref="T-9", title="Firma"), TaskEntry(id="a", ref="T-8", title="Firma")]
    )
    assert [t.ref for t, _ in tie.rank("firma")] == ["T-8", "T-9"]


def test_base_lexical_index_ignores_observations():
    assert LexicalIndex(TASKS, full=False).rank("proveedor") == []
    assert [t.ref for t, _ in LexicalIndex(TASKS, full=True).rank("proveedor")] == ["T-2"]


# --- reciprocal rank fusion ------------------------------------------------------------------


def test_rrf_rewards_agreement_keeps_forced_first_and_has_stable_ties():
    by_id = {t.id: t for t in TASKS}
    embedding = [by_id["T-3"], by_id["T-2"], by_id["T-1"]]
    lexical = [by_id["T-2"], by_id["T-10"]]
    fused = fused_candidates([], [embedding, lexical], k=3)
    assert [c.ref for c in fused] == ["T-2", "T-3", "T-10"]
    assert {c.via for c in fused} == {"rrf"}
    # Same rank in two lists → same score; the lower ref wins.
    tie = fused_candidates([], [[by_id["T-10"]], [by_id["T-1"]]], k=2)
    assert [c.ref for c in tie] == ["T-1", "T-10"]
    from app.modules.reconciliation.stages import CandidateV2

    forced = [CandidateV2("T-1", "T-1", "Informe", "", 1.0, "id_explicito")]
    fused = fused_candidates(forced, [embedding, lexical], k=2)
    assert [(c.ref, c.via) for c in fused] == [("T-1", "id_explicito"), ("T-2", "rrf")]


# --- channel options ---------------------------------------------------------------------------


def _channel(**config):
    return ChannelV2(
        RULES,
        chat=None,
        embedder=None,
        embedding_model=None,
        cache=MemoryEmbeddingCache(),
        config=ChannelV2Config(**config),
    )


@pytest.mark.asyncio
async def test_object_identifiers_can_be_switched_off():
    unit = _thread("Seguimiento", "Ver GLPI 01234 por favor")
    on = await _channel(top_k=3, ranking="embedding").classify(unit, TASKS, {})
    off = await _channel(top_k=3, ranking="embedding", object_match="off").classify(unit, TASKS, {})
    assert [(c.ref, c.via) for c in on.candidates] == [("T-2", "identificador:glpi")]
    assert off.candidates == []


@pytest.mark.asyncio
async def test_lexical_and_rrf_rankings_work_without_embeddings():
    unit = _thread("Cotización", "Adjunto la cotización del antivirus")
    bm25 = await _channel(top_k=2, ranking="bm25", task_text="full").classify(unit, TASKS, {})
    assert [(c.ref, c.via) for c in bm25.candidates] == [("T-2", "lexico"), ("T-10", "lexico")]
    rrf = await _channel(top_k=2, ranking="rrf", task_text="full").classify(unit, TASKS, {})
    assert [c.ref for c in rrf.candidates] == ["T-2", "T-10"]


@pytest.mark.asyncio
async def test_task_vectors_follow_the_configured_task_text():
    class Recorder:
        def __init__(self):
            self.texts = []

        async def embed(self, texts):
            self.texts += list(texts)
            return [[1.0, 0.0] for _ in texts]

    recorder = Recorder()
    channel = ChannelV2(
        RULES,
        chat=None,
        embedder=recorder,
        embedding_model="emb",
        cache=MemoryEmbeddingCache(),
        config=ChannelV2Config(task_text="full"),
    )
    await channel.task_vectors(TASKS)
    assert any("Proveedor envió cotización" in text for text in recorder.texts)


# --- object identifiers: specific vs. generic ---------------------------------------------------

GENERIC = [
    TaskEntry(id="T-1", ref="T-1", title="Procedimiento", detail="Aplica GLPI 11111"),
    TaskEntry(id="T-2", ref="T-2", title="Formato", detail="Aplica GLPI 11111 y GLPI 22222"),
    TaskEntry(id="T-3", ref="T-3", title="Guía", detail="Aplica GLPI 11111"),
    TaskEntry(id="T-4", ref="T-4", title="Caso puntual", detail="Seguimiento GLPI 22222"),
]


@pytest.mark.asyncio
async def test_specific_objects_force_only_tokens_shared_by_few_tasks():
    unit = _thread("Seguimiento", "Ver GLPI 11111 y GLPI 22222")
    forced = await _channel(top_k=5, ranking="embedding", object_match="forced").classify(
        unit, GENERIC, {}
    )
    assert [c.ref for c in forced.candidates] == ["T-1", "T-2", "T-3", "T-4"]
    specific = await _channel(top_k=5, ranking="embedding", object_match="specific").classify(
        unit, GENERIC, {}
    )
    # 22222 is shared by two tasks (specific); 11111 by three (generic, not forced).
    assert [(c.ref, c.via) for c in specific.candidates] == [
        ("T-2", "identificador:glpi"),
        ("T-4", "identificador:glpi"),
    ]


@pytest.mark.asyncio
async def test_fused_objects_join_the_rrf_ranking_instead_of_being_forced():
    unit = _thread("Seguimiento", "Ver GLPI 22222")
    fused = await _channel(top_k=1, ranking="rrf", object_match="fused").classify(unit, GENERIC, {})
    assert [(c.ref, c.via) for c in fused.candidates] == [("T-2", "rrf")]


def test_fused_objects_need_the_rrf_ranking():
    with pytest.raises(ValueError):
        ChannelV2Config(ranking="embedding", object_match="fused")


# --- E07b: chosen configuration (best PRUEBA coverage with k <= 8) --------------------------------


def test_channel_v2_defaults_are_the_e07b_choice():
    config = ChannelV2Config()
    assert (config.top_k, config.ranking, config.task_text) == (8, "rrf", "full")
    assert config.subject_match is True and config.object_match == "specific"


def test_evaluator_and_service_follow_the_channel_defaults():
    from app.config import Settings
    from app.eval.runner import EvalOptions
    from app.modules.reconciliation.service import ReconciliationConfig
    from scripts.eval_classifier import _parser

    channel = ChannelV2Config()
    options = EvalOptions(golden_dir=".", cuts=[], rules_path=".")
    args = _parser().parse_args(["--golden-dir", ".", "--cortes", "x", "--rules", "r"])
    for source in (options, args):
        assert (source.top_k, source.ranking, source.task_text) == (8, "rrf", "full")
        assert source.subject_match is True and source.object_match == "specific"
    assert ReconciliationConfig().v2_top_k == channel.top_k
    assert Settings.model_fields["RECONCILIATION_V2_TOP_K"].default == channel.top_k
