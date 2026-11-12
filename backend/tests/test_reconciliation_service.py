"""C05: ReconciliationService.classify_window with in-memory fakes.

Proves orchestration only: idempotency per thread, update with new
messages, embedding cache, key priority, task_ref validation and that a
missing LLM still persists the deterministic state and key candidates.
The SQL adapter is proven in ``test_reconciliation_repository_postgres``.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.ai.errors import LlmProviderDisabled, LlmUnavailable
from app.modules.reconciliation.candidates import TaskSnapshot
from app.modules.reconciliation.models import IntakeProposal
from app.modules.reconciliation.service import (
    ClassifierBackend,
    ReconciliationConfig,
    ReconciliationService,
)
from app.modules.reconciliation.threads import MailItem

pytestmark = pytest.mark.asyncio

ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
_ME = "yo@entidad.gov.co"
_T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_SINCE = _T0 - timedelta(days=7)


class FakeRepository:
    """Tenant-scoped in-memory adapter; enforces one open proposal per key."""

    def __init__(self) -> None:
        self.items: dict[uuid.UUID, list[MailItem]] = {ORG: [], OTHER_ORG: []}
        self.tasks: dict[uuid.UUID, list[TaskSnapshot]] = {ORG: [], OTHER_ORG: []}
        self.embeddings: dict[tuple[uuid.UUID, uuid.UUID, str], tuple[str, list[float]]] = {}
        self.proposals: list[IntakeProposal] = []
        self.embedding_writes = 0

    async def list_mail_items(self, organization_id, since):
        return [m for m in self.items[organization_id] if m.occurred_at >= since]

    async def list_active_tasks(self, organization_id):
        return list(self.tasks[organization_id])

    async def find_embeddings(self, organization_id, model, task_ids):
        return {
            task_id: self.embeddings[(organization_id, task_id, model)]
            for task_id in task_ids
            if (organization_id, task_id, model) in self.embeddings
        }

    async def save_embedding(self, organization_id, task_id, model, text_hash, vector):
        self.embedding_writes += 1
        self.embeddings[(organization_id, task_id, model)] = (text_hash, list(vector))

    async def find_open_proposal(self, organization_id, conversation_key):
        return next(
            (
                p
                for p in self.proposals
                if p.organization_id == organization_id
                and p.conversation_key == conversation_key
                and p.status == "propuesta"
            ),
            None,
        )

    async def find_latest_decided(self, organization_id, conversation_key):
        decided = [
            p
            for p in self.proposals
            if p.organization_id == organization_id
            and p.conversation_key == conversation_key
            and p.status != "propuesta"
        ]
        return decided[-1] if decided else None

    async def add_proposal(self, proposal):
        assert (
            await self.find_open_proposal(proposal.organization_id, proposal.conversation_key)
            is None
        )
        proposal.id = uuid.uuid4()
        self.proposals.append(proposal)

    async def flush(self):
        return None


class CountingCommit:
    def __init__(self) -> None:
        self.count = 0

    async def __call__(self) -> None:
        self.count += 1


def _mail(
    minutes, *, direction="inbound", conv="conv-1", subject="Acceso VPN", body="Necesito VPN"
):
    sender = _ME if direction == "outbound" else "ana@entidad.gov.co"
    to = ("ana@entidad.gov.co",) if direction == "outbound" else (_ME,)
    return MailItem(
        id=uuid.uuid4(),
        conversation_id=conv,
        subject=subject,
        sender=sender,
        recipients=to,
        cc=(),
        direction=direction,
        occurred_at=_T0 + timedelta(minutes=minutes),
        body=body,
        mailbox=_ME,
    )


def _task(ref, title):
    return TaskSnapshot(id=uuid.uuid4(), ref=ref, title=title, description="", keys=(ref,))


def _llm_text(**overrides):
    data = {
        "relacion": "tarea_existente",
        "task_ref": "T-7",
        "confianza": 0.8,
        "atendida": "no",
        "accion": "Dar acceso VPN",
        "solicitante": "Ana",
        "fecha_limite": None,
        "resumen": "Pide VPN.",
        "motivo": "Coincide con T-7.",
    }
    data.update(overrides)
    return json.dumps(data)


def _service(repo, port, *, embedding_model="emb-1", commit=None, factory_error=None):
    async def factory(organization_id):
        if factory_error is not None:
            raise factory_error
        return ClassifierBackend(port=port, embedding_model=embedding_model, provider="fake")

    return ReconciliationService(
        repo,
        backend_factory=factory,
        commit=commit or CountingCommit(),
        config=ReconciliationConfig(
            max_threads=10, max_thread_chars=2000, top_k=5, llm_max_tokens=400
        ),
    )


@pytest.fixture
def repo():
    repository = FakeRepository()
    repository.tasks[ORG] = [_task("T-7", "Acceso VPN"), _task("T-8", "Backup")]
    return repository


@pytest.fixture
def port():
    adapter = FakeLlmAdapter()
    adapter.next_text = _llm_text()
    return adapter


async def test_classifies_a_thread_into_one_proposal(repo, port):
    repo.items[ORG] = [_mail(0), _mail(5, direction="outbound")]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)

    assert counts["threads"] == 1 and counts["created"] == 1 and counts["classified"] == 1
    (proposal,) = repo.proposals
    assert proposal.thread_state == "respondido"
    assert proposal.relation == "tarea_existente"
    assert proposal.task_id == repo.tasks[ORG][0].id
    assert proposal.confidence == pytest.approx(0.8)
    assert proposal.status == "propuesta"
    assert proposal.provider == "fake" and proposal.model == "fake-model"
    assert proposal.result["atendida"] == "no"
    assert sorted(proposal.item_ids) == sorted(str(m.id) for m in repo.items[ORG])
    request = port.calls[0]
    assert request.temperature == 0.0 and request.output_schema is not None
    assert "T-7" in request.messages[0].content


async def test_rerun_without_new_messages_is_a_no_op(repo, port):
    repo.items[ORG] = [_mail(0)]
    service = _service(repo, port)
    await service.classify_window(ORG, _SINCE)
    calls, writes = len(port.calls), repo.embedding_writes

    counts = await service.classify_window(ORG, _SINCE)

    assert counts["unchanged"] == 1 and counts["created"] == counts["updated"] == 0
    assert len(repo.proposals) == 1
    assert len(port.calls) == calls
    assert repo.embedding_writes == writes  # task vectors come from the cache


async def test_new_message_updates_the_open_proposal(repo, port):
    repo.items[ORG] = [_mail(0)]
    service = _service(repo, port)
    await service.classify_window(ORG, _SINCE)
    repo.items[ORG].append(_mail(30, direction="outbound"))

    counts = await service.classify_window(ORG, _SINCE)

    assert counts["updated"] == 1
    (proposal,) = repo.proposals
    assert proposal.thread_state == "respondido"
    assert proposal.message_count == 2


async def test_decided_thread_is_not_reproposed_until_it_grows(repo, port):
    repo.items[ORG] = [_mail(0)]
    service = _service(repo, port)
    await service.classify_window(ORG, _SINCE)
    repo.proposals[0].status = "descartada"

    assert (await service.classify_window(ORG, _SINCE))["unchanged"] == 1
    repo.items[ORG].append(_mail(40))
    assert (await service.classify_window(ORG, _SINCE))["created"] == 1
    assert [p.status for p in repo.proposals] == ["descartada", "propuesta"]


async def test_task_text_change_refreshes_its_embedding(repo, port):
    repo.items[ORG] = [_mail(0)]
    service = _service(repo, port)
    await service.classify_window(ORG, _SINCE)
    writes = repo.embedding_writes
    old = repo.tasks[ORG][0]
    repo.tasks[ORG][0] = TaskSnapshot(old.id, old.ref, "Acceso VPN y MFA", "", old.keys)
    repo.items[ORG].append(_mail(50))

    await service.classify_window(ORG, _SINCE)

    assert repo.embedding_writes == writes + 1


async def test_invalid_task_ref_is_degraded(repo, port):
    port.next_text = _llm_text(task_ref="T-404")
    repo.items[ORG] = [_mail(0)]
    await _service(repo, port).classify_window(ORG, _SINCE)
    (proposal,) = repo.proposals
    assert proposal.relation == "tarea_nueva" and proposal.task_id is None
    assert proposal.confidence <= 0.3


async def test_mentioned_key_is_candidate_with_priority(repo, port):
    repo.items[ORG] = [_mail(0, subject="Seguimiento T-8", body="Va el T-8")]
    await _service(repo, port).classify_window(ORG, _SINCE)
    (proposal,) = repo.proposals
    assert proposal.candidates[0]["ref"] == "T-8" and proposal.candidates[0]["via"] == "clave"


async def test_llm_down_keeps_deterministic_state_and_key_candidates(repo):
    class DownPort(FakeLlmAdapter):
        async def complete(self, request):
            self.calls.append(request)
            raise LlmUnavailable()

        async def embed(self, texts):
            raise LlmUnavailable()

    port = DownPort()
    repo.items[ORG] = [
        _mail(0, subject="T-7 caído"),
        _mail(5, conv="conv-2", subject="Otro"),
    ]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)

    assert counts["llm_error"] == "llm_unavailable"
    assert counts["created"] == 2 and counts["classified"] == 0
    assert len(port.calls) == 1  # stops calling a provider that is down
    by_subject = {p.subject: p for p in repo.proposals}
    keyed = by_subject["T-7 caído"]
    assert keyed.thread_state == "pendiente_respuesta"
    assert keyed.relation is None and keyed.classification_error == "llm_unavailable"
    assert keyed.task_id == repo.tasks[ORG][0].id
    assert keyed.candidates[0]["via"] == "clave"


async def test_unclassified_open_proposal_is_retried_next_run(repo, port):
    repo.items[ORG] = [_mail(0)]
    await _service(repo, port, factory_error=LlmProviderDisabled()).classify_window(ORG, _SINCE)
    assert repo.proposals[0].relation is None

    counts = await _service(repo, port).classify_window(ORG, _SINCE)

    assert counts["updated"] == 1 and counts["classified"] == 1
    assert repo.proposals[0].relation == "tarea_existente"
    assert repo.proposals[0].classification_error is None


async def test_no_threads_never_builds_a_backend(repo):
    async def factory(organization_id):
        raise AssertionError("no debe construirse")

    service = ReconciliationService(
        repo, backend_factory=factory, commit=CountingCommit(), config=ReconciliationConfig()
    )
    counts = await service.classify_window(ORG, _SINCE)
    assert counts["threads"] == 0


async def test_max_threads_per_run_keeps_the_most_recent(repo, port):
    repo.items[ORG] = [_mail(i, conv=f"c{i}") for i in range(15)]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)
    assert counts["threads"] == 15 and counts["processed"] == 10
    assert {p.conversation_key for p in repo.proposals} == {f"conv:c{i}" for i in range(5, 15)}


async def test_other_organization_is_untouched(repo, port):
    repo.items[OTHER_ORG] = [_mail(0)]
    counts = await _service(repo, port).classify_window(ORG, _SINCE)
    assert counts["threads"] == 0 and repo.proposals == []


async def test_commits_once_per_thread(repo, port):
    commit = CountingCommit()
    repo.items[ORG] = [_mail(0), _mail(1, conv="c2")]
    await _service(repo, port, commit=commit).classify_window(ORG, _SINCE)
    assert commit.count >= 2
