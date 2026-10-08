"""E03: channel v2 orchestration without a database (fakes only).

Deterministic stages decide first (noise, unattended events) without calling
the LLM; the rest goes to the LLM with forced + top-k candidates, prompt v2
and the determinism parameters; post-rules and calibrated confidence apply.
SYNTHETIC data only.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.ai.errors import LlmUnavailable
from app.modules.reconciliation.channel_v2 import (
    ChannelV2,
    ChannelV2Config,
    MemoryEmbeddingCache,
    ProviderDown,
)
from app.modules.reconciliation.prompt_versions import (
    DEFAULT_PROMPT_VERSION_V2 as PROMPT_VERSION_V2,
)
from app.modules.reconciliation.rules import compile_rules
from app.modules.reconciliation.stages import MailRecord, TaskEntry, build_units

pytestmark = pytest.mark.asyncio

ME = "yo@ejemplo.gov.co"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
RULES = compile_rules(
    {
        "version": "2.0.0",
        "buzon": ME,
        "ruido": {"remitentes_lista": {"valores": ["boletin@"]}},
        "identificadores": {"tarea": {"regex": "\\bT-\\d{1,3}\\b"}},
    }
)
TASKS = [
    TaskEntry(id="T-1", ref="T-1", title="Informe de gestión", status="PENDIENTE"),
    TaskEntry(id="T-2", ref="T-2", title="Renovar antivirus", status="EN CURSO"),
    TaskEntry(id="T-3", ref="T-3", title="Matriz de riesgos", status="COMPLETADA"),
]


def _mail(rid, *, subject="Asunto", sender="ana@otra.gov.co", to=(ME,), body="", kind="in"):
    return MailRecord(rid, kind, f"c-{rid}", subject, sender, tuple(to), (), T0, body)


def _answer(**fields):
    base = {"clase": "avanza", "task_ref": "T-2", "evidencia": None, "resumen": "r"}
    base.update(fields)
    return json.dumps(base)


def _channel(llm, *, cache=None, k=2):
    return ChannelV2(
        RULES,
        chat=llm,
        embedder=llm,
        embedding_model="emb-1",
        cache=cache if cache is not None else MemoryEmbeddingCache(),
        config=ChannelV2Config(top_k=k),
    )


async def test_noise_is_decided_by_rules_without_calling_the_llm():
    llm = FakeLlmAdapter()
    channel = _channel(llm)
    vectors = await channel.task_vectors(TASKS)
    (unit,) = build_units([_mail("1", sender="boletin@x", to=("lista@x",))])
    result = await channel.classify(unit, TASKS, vectors)
    assert (result.clase, result.stage, result.reason) == ("descartado", "regla", "ruido:remitente")
    assert result.confidence == 1.0
    assert llm.calls == []


async def test_llm_gets_forced_candidate_first_and_v2_request():
    llm = FakeLlmAdapter()
    llm.next_text = _answer(task_ref="T-2", evidencia="adjunto la licencia renovada")
    channel = _channel(llm)
    vectors = await channel.task_vectors(TASKS)
    (unit,) = build_units([_mail("1", subject="T-2", body="Hola, adjunto la licencia renovada.")])
    result = await channel.classify(unit, TASKS, vectors)
    request = llm.calls[0]
    assert request.prompt_version == PROMPT_VERSION_V2 and request.temperature == 0.0
    assert result.candidates[0].ref == "T-2" and result.candidates[0].via == "id_explicito"
    assert len(result.candidates) == 2
    assert (result.clase, result.task_ref, result.confidence) == ("avanza", "T-2", 0.9)
    assert result.stage == "llm" and result.output_hash


async def test_ref_outside_candidates_becomes_not_conclusive():
    llm = FakeLlmAdapter()
    llm.next_text = _answer(task_ref="T-99")
    channel = _channel(llm, k=1)
    vectors = await channel.task_vectors(TASKS)
    (unit,) = build_units([_mail("1", body="texto")])
    result = await channel.classify(unit, TASKS, vectors)
    assert result.clase == "no_concluyente" and result.task_id is None


async def test_invalid_json_is_a_unit_error_and_provider_down_raises():
    llm = FakeLlmAdapter()
    llm.next_text = "no es json"
    channel = _channel(llm)
    (unit,) = build_units([_mail("1")])
    result = await channel.classify(unit, TASKS, await channel.task_vectors(TASKS))
    assert (result.clase, result.error, result.stage) == (
        "no_concluyente",
        "llm_schema_mismatch",
        "error_llm",
    )

    class Down(FakeLlmAdapter):
        async def complete(self, request):
            raise LlmUnavailable()

    with pytest.raises(ProviderDown):
        await _channel(Down()).classify(unit, TASKS, {})


async def test_embeddings_are_cached_by_model_and_text_hash():
    llm = FakeLlmAdapter()
    cache = MemoryEmbeddingCache()
    first = await _channel(llm, cache=cache).task_vectors(TASKS)
    calls = len(llm.embed_calls)
    second = await _channel(llm, cache=cache).task_vectors(TASKS)
    assert first == second and len(llm.embed_calls) == calls
    assert all(key[0] == "emb-1" for key in cache.items)


async def test_same_input_gives_identical_candidates_and_hash():
    llm = FakeLlmAdapter()
    llm.next_text = _answer()
    records = [_mail(str(i), body=f"texto {i}") for i in range(3)]
    runs = []
    for _ in range(2):
        channel = _channel(llm)
        vectors = await channel.task_vectors(TASKS)
        runs.append(
            [
                (r.clase, [c.ref for c in r.candidates], r.output_hash)
                for r in [await channel.classify(u, TASKS, vectors) for u in build_units(records)]
            ]
        )
    assert runs[0] == runs[1]


async def test_without_llm_keeps_forced_candidates_and_no_class():
    channel = ChannelV2(
        RULES,
        chat=None,
        embedder=None,
        embedding_model=None,
        cache=MemoryEmbeddingCache(),
        config=ChannelV2Config(),
    )
    (unit,) = build_units([_mail("1", subject="T-3 listo")])
    result = await channel.classify(unit, TASKS, {})
    assert result.clase is None and result.stage == "sin_llm"
    assert [c.ref for c in result.candidates] == ["T-3"]


async def test_event_without_attendance_skips_the_llm():
    llm = FakeLlmAdapter()
    event = MailRecord(
        "e1",
        "event",
        None,
        "Comité",
        "jefa@x",
        (ME,),
        (),
        T0 + timedelta(hours=1),
        "",
        response_status="NotResponded",
    )
    (unit,) = build_units([event])
    result = await _channel(llm).classify(unit, TASKS, {})
    assert result.clase == "no_concluyente" and llm.calls == []
