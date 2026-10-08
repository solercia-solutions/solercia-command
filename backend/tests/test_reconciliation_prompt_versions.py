"""E05a: versioned prompts of channel v2.

Every iteration of the prompt is a NEW version: older ones stay registered
so a prediction can always be traced to the exact text that produced it.
The channel sends the configured version; the default is the one the
evaluation chose. SYNTHETIC data only.
"""

import json
from datetime import UTC, datetime

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.modules.reconciliation.channel_v2 import ChannelV2, ChannelV2Config, MemoryEmbeddingCache
from app.modules.reconciliation.prompt_v2 import PROMPT_VERSION_V2, SYSTEM_PROMPT_V2
from app.modules.reconciliation.prompt_versions import (
    DEFAULT_PROMPT_VERSION_V2,
    PROMPTS_V2,
    get_prompt_v2,
)
from app.modules.reconciliation.rules import compile_rules
from app.modules.reconciliation.stages import MailRecord, TaskEntry, build_units

ME = "yo@ejemplo.gov.co"
RULES = compile_rules(
    {
        "version": "2.0.0",
        "buzon": ME,
        "identificadores": {"tarea": {"regex": "\\bT-\\d{1,3}\\b"}},
    }
)
TASKS = [TaskEntry(id="T-1", ref="T-1", title="Informe de gestión", status="PENDIENTE")]


def test_first_version_stays_registered_and_default_is_registered():
    assert PROMPTS_V2[PROMPT_VERSION_V2].system == SYSTEM_PROMPT_V2
    assert DEFAULT_PROMPT_VERSION_V2 in PROMPTS_V2
    assert all(spec.version == key for key, spec in PROMPTS_V2.items())


def test_unknown_version_is_refused():
    with pytest.raises(ValueError):
        get_prompt_v2("reconciliation-v9.9")


@pytest.mark.parametrize("version", sorted(PROMPTS_V2))
def test_every_version_names_the_eight_classes(version):
    system = get_prompt_v2(version).system
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
        assert clase in system


@pytest.mark.asyncio
@pytest.mark.parametrize("version", sorted(PROMPTS_V2))
async def test_channel_sends_the_configured_version(version):
    llm = FakeLlmAdapter()
    llm.next_text = json.dumps({"clase": "informativo", "task_ref": None, "resumen": "r"})
    channel = ChannelV2(
        RULES,
        chat=llm,
        embedder=llm,
        embedding_model="emb-1",
        cache=MemoryEmbeddingCache(),
        config=ChannelV2Config(top_k=1, prompt_version=version),
    )
    vectors = await channel.task_vectors(TASKS)
    mail = MailRecord(
        "1", "in", "c-1", "Hola", "ana@otra.gov.co", (ME,), (), datetime(2026, 9, 1, tzinfo=UTC)
    )
    (unit,) = build_units([mail])
    result = await channel.classify(unit, TASKS, vectors)
    (request,) = llm.calls
    assert request.prompt_version == version
    assert request.system == get_prompt_v2(version).system
    assert result.prompt_version == version


def test_default_channel_config_uses_the_default_version():
    assert ChannelV2Config().prompt_version == DEFAULT_PROMPT_VERSION_V2


@pytest.mark.asyncio
async def test_versions_with_candidate_notes_send_the_latest_task_note():
    from app.modules.reconciliation.prompt_versions import PromptSpec

    noted = [v for v, spec in PROMPTS_V2.items() if spec.candidate_notes]
    assert noted, "at least one version shows candidate notes"
    assert PromptSpec("x", "s").candidate_notes is False
    tasks = [
        TaskEntry(
            id="T-1",
            ref="T-1",
            title="Informe de gestión",
            status="PENDIENTE",
            observations="[Corte 1-sep] Se pidió el informe | antes",
        )
    ]
    for version, expected in ((noted[0], True), (PROMPT_VERSION_V2, False)):
        llm = FakeLlmAdapter()
        llm.next_text = json.dumps({"clase": "informativo", "task_ref": None, "resumen": "r"})
        channel = ChannelV2(
            RULES,
            chat=llm,
            embedder=None,
            embedding_model=None,
            cache=MemoryEmbeddingCache(),
            config=ChannelV2Config(top_k=1, prompt_version=version),
        )
        mail = MailRecord(
            "1", "in", "c-1", "T-1", "ana@otra.gov.co", (ME,), (), datetime(2026, 9, 1, tzinfo=UTC)
        )
        (unit,) = build_units([mail])
        await channel.classify(unit, tasks, {})
        content = llm.calls[0].messages[0].content
        assert ("Última nota: [Corte 1-sep] Se pidió el informe" in content) is expected


def test_default_is_the_version_chosen_by_test_macro_f1():
    # E05a: v2.2 had the best macro-F1 on the test cuts (2026-10-01 + 2026-10-05).
    assert DEFAULT_PROMPT_VERSION_V2 == "reconciliation-v2.2"
