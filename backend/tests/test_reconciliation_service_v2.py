"""E03: ``ReconciliationService`` with ``channel="v2"`` (in-memory fakes).

v1 stays the default; v2 maps its 8 classes onto ``intake_proposals``
without a migration (``relation`` + ``result["clase"]``), decides noise by
rules without the LLM and keeps the C05 idempotency. SYNTHETIC data only.
"""

import json
import uuid

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.ai.errors import LlmUnavailable
from app.modules.reconciliation.prompt_v2 import PROMPT_VERSION_V2
from app.modules.reconciliation.rules import RulesError, compile_rules
from app.modules.reconciliation.service import (
    ClassifierBackend,
    ReconciliationConfig,
    ReconciliationService,
)
from tests.test_reconciliation_service import (
    _ME,
    _SINCE,
    ORG,
    CountingCommit,
    FakeRepository,
    _mail,
    _task,
)

pytestmark = pytest.mark.asyncio

RULES = compile_rules(
    {
        "version": "2.0.0",
        "buzon": _ME,
        "ruido": {"remitentes_lista": {"valores": ["boletin@"]}},
        "identificadores": {"tarea": {"regex": "\\bT-\\d{1,3}\\b"}},
    }
)


def _answer(**fields):
    base = {
        "clase": "avanza",
        "task_ref": "T-7",
        "evidencia": "Necesito VPN",
        "accion": "Dar acceso",
        "solicitante": "Ana",
        "fecha_limite": None,
        "resumen": "Pide VPN.",
    }
    base.update(fields)
    return json.dumps(base)


def _service(repo, port, *, rules_error=None, channel="v2"):
    async def factory(organization_id):
        return ClassifierBackend(port=port, embedding_model="emb-1", provider="fake")

    async def rules_factory(organization_id):
        if rules_error is not None:
            raise rules_error
        return RULES

    return ReconciliationService(
        repo,
        backend_factory=factory,
        rules_factory=rules_factory,
        commit=CountingCommit(),
        config=ReconciliationConfig(max_threads=10, top_k=3, channel=channel),
    )


@pytest.fixture
def repo():
    repository = FakeRepository()
    repository.tasks[ORG] = [_task("T-7", "Acceso VPN"), _task("T-8", "Backup")]
    return repository


@pytest.fixture
def port():
    adapter = FakeLlmAdapter()
    adapter.next_text = _answer()
    return adapter


async def test_v1_remains_the_default_channel():
    assert ReconciliationConfig().channel == "v1"


async def test_v2_maps_the_class_onto_the_proposal(repo, port):
    repo.items[ORG] = [_mail(0, body="Necesito VPN para T-7")]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)
    (proposal,) = repo.proposals
    assert counts["created"] == 1 and counts["classified"] == 1
    assert counts["rules_version"] == "2.0.0"
    assert proposal.relation == "tarea_existente"
    assert proposal.task_id == repo.tasks[ORG][0].id
    assert proposal.result["clase"] == "avanza"
    assert proposal.confidence == 0.9
    assert proposal.prompt_version == PROMPT_VERSION_V2
    assert proposal.conversation_key == "conv:conv-1"
    assert proposal.candidates[0]["via"] == "id_explicito"
    assert port.calls[0].prompt_version == PROMPT_VERSION_V2


async def test_v2_noise_is_decided_by_rules_without_the_llm(repo, port):
    noisy = _mail(0, body="Boletín")
    repo.items[ORG] = [
        type(noisy)(**{**noisy.__dict__, "sender": "boletin@entidad.gov.co", "recipients": ()})
    ]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)
    (proposal,) = repo.proposals
    assert counts["decided_by_rules"] == 1 and port.calls == []
    assert proposal.relation == "irrelevante"
    assert proposal.result["clase"] == "descartado"
    assert proposal.prompt_version == "reglas-2.0.0"


async def test_v2_rerun_without_new_messages_is_a_no_op(repo, port):
    repo.items[ORG] = [_mail(0)]
    service = _service(repo, port)
    await service.classify_window(ORG, _SINCE)
    calls = len(port.calls)
    counts = await service.classify_window(ORG, _SINCE)
    assert counts["unchanged"] == 1 and len(port.calls) == calls


async def test_v2_provider_down_keeps_state_and_reports_llm_error(repo):
    class Down(FakeLlmAdapter):
        async def complete(self, request):
            self.calls.append(request)
            raise LlmUnavailable()

    repo.items[ORG] = [_mail(0, conv="a", body="T-8"), _mail(1, conv="b")]
    down = Down()
    counts = await _service(repo, down).classify_window(ORG, _SINCE)
    assert counts["llm_error"] == "llm_unavailable"
    assert len(repo.proposals) == 2
    keyed = next(p for p in repo.proposals if p.conversation_key == "conv:a")
    assert keyed.relation is None and keyed.task_id == repo.tasks[ORG][1].id
    assert len(down.calls) == 1


async def test_v2_invalid_rules_stop_the_run_without_calling_the_llm(repo, port):
    repo.items[ORG] = [_mail(0)]
    counts = await _service(repo, port, rules_error=RulesError("x")).classify_window(ORG, _SINCE)
    assert counts["llm_error"] == "reconciliation_rules_invalid"
    assert repo.proposals == [] and port.calls == []


async def test_v2_other_organization_is_untouched(repo, port):
    other = uuid.uuid4()
    repo.items[other] = []
    repo.tasks[other] = []
    repo.items[ORG] = [_mail(0)]
    await _service(repo, port).classify_window(ORG, _SINCE)
    assert all(p.organization_id == ORG for p in repo.proposals)
