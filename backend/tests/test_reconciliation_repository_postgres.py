"""C05: reconciliation adapter against real PostgreSQL (disposable) —
window query with thread back-fill, mailbox, active tasks and keys,
REAL[] embeddings upsert, partial unique open proposal, filtered listing."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.intake.models import IntakeItem
from app.modules.reconciliation.models import IntakeProposal
from app.modules.reconciliation.repository import SqlReconciliationRepository
from app.modules.tasks.models import Task
from app.shared.enums import IntakeItemType
from tests.conftest import skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


async def _account(session, org_data):
    connector = Connector(organization_id=org_data.organization.id, provider="fake")
    session.add(connector)
    await session.flush()
    account = ConnectedAccount(
        organization_id=org_data.organization.id,
        connector_id=connector.id,
        user_id=org_data.user.id,
        external_account_id="Yo@Entidad.gov.co",
    )
    session.add(account)
    await session.flush()
    return connector, account


def _item(
    org_id,
    connector,
    account,
    minutes,
    *,
    conv="conv-1",
    item_type=IntakeItemType.email,
    direction="inbound",
    active=True,
):
    return IntakeItem(
        organization_id=org_id,
        source_provider="fake",
        connector_id=connector.id,
        connected_account_id=account.id,
        item_type=item_type,
        external_id=uuid.uuid4().hex,
        title="Asunto",
        snippet="corto",
        origin_actor="ana@entidad.gov.co",
        occurred_at=T0 + timedelta(minutes=minutes),
        raw_payload={
            "recipients": ["yo@entidad.gov.co"],
            "cc": ["jefa@entidad.gov.co"],
            "body_text": "Cuerpo completo",
        },
        conversation_id=conv,
        direction=direction,
        is_active=active,
    )


async def test_window_backfills_earlier_messages_of_touched_threads(session, two_orgs):
    org = two_orgs.a.organization.id
    connector, account = await _account(session, two_orgs.a)
    old_same_thread = _item(org, connector, account, -60 * 24 * 30)
    old_other_thread = _item(org, connector, account, -60 * 24 * 30, conv="conv-old")
    recent = _item(org, connector, account, 0, direction="outbound")
    calendar = _item(org, connector, account, 1, item_type=IntakeItemType.calendar_event, conv=None)
    deleted = _item(org, connector, account, 2, active=False)
    b_connector, b_account = await _account(session, two_orgs.b)
    other_org = _item(two_orgs.b.organization.id, b_connector, b_account, 3)
    session.add_all([old_same_thread, old_other_thread, recent, calendar, deleted, other_org])
    await session.flush()

    items = await SqlReconciliationRepository(session).list_mail_items(org, T0 - timedelta(days=1))

    assert {i.id for i in items} == {old_same_thread.id, recent.id}
    sample = next(i for i in items if i.id == recent.id)
    assert sample.mailbox == "yo@entidad.gov.co"
    assert sample.cc == ("jefa@entidad.gov.co",) and sample.body == "Cuerpo completo"
    assert sample.direction == "outbound"


async def test_active_tasks_exclude_completed_and_carry_keys(session, two_orgs):
    project = two_orgs.a.project
    open_task = Task(
        project_id=project.id,
        title="VPN",
        status="Backlog",
        source="checklist",
        external_key="T-07",
        task_number=3,
    )
    done = Task(project_id=project.id, title="Hecha", status="Done", completed_at=T0)
    session.add_all([open_task, done])
    await session.flush()

    tasks = await SqlReconciliationRepository(session).list_active_tasks(two_orgs.a.organization.id)

    by_id = {t.id: t for t in tasks}
    assert open_task.id in by_id and done.id not in by_id
    assert two_orgs.b.task.id not in by_id
    assert by_id[open_task.id].ref == "T-07"
    assert set(by_id[open_task.id].keys) == {"T-7", f"{project.code}-3"}


async def test_embeddings_upsert_and_round_trip(session, two_orgs):
    org, task = two_orgs.a.organization.id, two_orgs.a.task
    repo = SqlReconciliationRepository(session)
    await repo.save_embedding(org, task.id, "emb", "h1", [0.25, -0.5])
    await repo.save_embedding(org, task.id, "emb", "h2", [0.75, 0.125])
    await session.flush()

    found = await repo.find_embeddings(org, "emb", [task.id])
    assert found[task.id][0] == "h2"
    assert found[task.id][1] == pytest.approx([0.75, 0.125])
    assert await repo.find_embeddings(two_orgs.b.organization.id, "emb", [task.id]) == {}
    assert await repo.find_embeddings(org, "otro", [task.id]) == {}


def _proposal(org, key, status="propuesta", **kw):
    return IntakeProposal(
        organization_id=org,
        conversation_key=key,
        subject="Asunto",
        item_ids=[str(uuid.uuid4())],
        message_count=1,
        last_message_at=T0,
        thread_state="pendiente_respuesta",
        candidates=[],
        status=status,
        **kw,
    )


async def test_only_one_open_proposal_per_thread(session, two_orgs):
    org = two_orgs.a.organization.id
    repo = SqlReconciliationRepository(session)
    await repo.add_proposal(_proposal(org, "conv:x", status="descartada"))
    await repo.add_proposal(_proposal(org, "conv:x"))
    await repo.add_proposal(_proposal(two_orgs.b.organization.id, "conv:x"))
    assert (await repo.find_open_proposal(org, "conv:x")).status == "propuesta"
    assert (await repo.find_latest_decided(org, "conv:x")).status == "descartada"

    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        await repo.add_proposal(_proposal(org, "conv:x"))
    await savepoint.rollback()


async def test_list_proposals_filters_paginates_and_scopes(session, two_orgs):
    org, task = two_orgs.a.organization.id, two_orgs.a.task
    repo = SqlReconciliationRepository(session)
    for n in range(3):
        await repo.add_proposal(_proposal(org, f"conv:{n}", task_id=task.id))
    await repo.add_proposal(_proposal(org, "conv:9", status="aceptada"))
    await repo.add_proposal(_proposal(two_orgs.b.organization.id, "conv:b"))

    rows, total = await repo.list_proposals(org, status="propuesta", page=1, size=2)
    assert total == 3 and len(rows) == 2
    rows, total = await repo.list_proposals(org, task_id=task.id, page=1, size=20)
    assert total == 3
    rows, total = await repo.list_proposals(org, thread_state="respondido", page=1, size=20)
    assert total == 0
    rows, total = await repo.list_proposals(org, page=1, size=20)
    assert total == 4 and all(r.organization_id == org for r in rows)
    other = rows[0].id
    assert await repo.get_proposal(two_orgs.b.organization.id, other) is None
