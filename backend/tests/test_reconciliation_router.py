"""C05: /intake/proposals — list, accept, dismiss, create-task.

Admin/manager only, scoped to the caller's organization. Accepting links
the thread to the task with a comment and does NOT change the task status
unless the body asks for one explicitly.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.comments.models import TaskComment
from app.modules.intake.models import IntakeSettings
from app.modules.reconciliation.models import IntakeProposal
from app.modules.tasks.models import Task
from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db

pytestmark = [skip_no_db, pytest.mark.asyncio(loop_scope="session")]

T0 = datetime(2026, 10, 2, 15, 30, tzinfo=UTC)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _board(session, project) -> None:
    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()
    for order, key in enumerate(("Backlog", "Doing", "Done")):
        session.add(BoardColumn(board_id=board.id, name=key, status_key=key, order=order))
    await session.flush()


async def _proposal(session, org_data, *, relation="tarea_existente", task=True, **kw):
    proposal = IntakeProposal(
        organization_id=org_data.organization.id,
        conversation_key=f"conv:{uuid.uuid4().hex}",
        conversation_id="conv-x",
        subject="Solicitud de acceso VPN",
        item_ids=[str(uuid.uuid4())],
        message_count=2,
        last_message_at=T0,
        thread_state=kw.pop("thread_state", "pendiente_respuesta"),
        relation=relation,
        task_id=org_data.task.id if task else None,
        confidence=0.8,
        result={
            "resumen": "Ana pide acceso a la VPN.",
            "accion": "Dar acceso a la VPN",
            "solicitante": "Ana Pérez",
            "fecha_limite": "2026-10-10",
            "atendida": "no",
        },
        candidates=[],
        status=kw.pop("status", "propuesta"),
        **kw,
    )
    session.add(proposal)
    await session.flush()
    return proposal


async def test_list_is_scoped_filtered_and_paginated(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a, b = two_orgs.a, two_orgs.b
    for _ in range(3):
        await _proposal(session, a)
    await _proposal(session, a, status="descartada", thread_state="respondido")
    await _proposal(session, b)

    response = await client.get(
        "/intake/proposals", params={"status": "propuesta", "size": 2}, headers=_auth(a.token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"page": 1, "size": 2, "total": 3}
    assert len(body["data"]) == 2
    assert body["data"][0]["result"]["resumen"] == "Ana pide acceso a la VPN."

    by_state = await client.get(
        "/intake/proposals", params={"thread_state": "respondido"}, headers=_auth(a.token)
    )
    assert by_state.json()["meta"]["total"] == 1
    by_task = await client.get(
        "/intake/proposals", params={"task_id": str(a.task.id)}, headers=_auth(a.token)
    )
    assert by_task.json()["meta"]["total"] == 4


async def test_detail_is_scoped_and_role_guarded(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
):
    """C06: the task comment links to /intake/proposals/{id}; the UI reads it here."""

    a, b = two_orgs.a, two_orgs.b
    proposal = await _proposal(session, a)
    foreign = await _proposal(session, b)

    response = await client.get(f"/intake/proposals/{proposal.id}", headers=_auth(a.token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == str(proposal.id)
    assert data["result"]["solicitante"] == "Ana Pérez"

    missing = await client.get(f"/intake/proposals/{foreign.id}", headers=_auth(a.token))
    assert missing.status_code == 404
    assert missing.json()["code"] == "proposal_not_found"
    _, member_token = await make_member(session, a.organization, MemberRole.member)
    denied = await client.get(f"/intake/proposals/{proposal.id}", headers=_auth(member_token))
    assert denied.status_code == 403


async def test_anonymous_gets_401_and_member_gets_403(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
):
    proposal = await _proposal(session, two_orgs.a)
    assert (await client.get("/intake/proposals")).status_code == 401
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    assert (await client.get("/intake/proposals", headers=_auth(member_token))).status_code == 403
    denied = await client.post(
        f"/intake/proposals/{proposal.id}/accept", json={}, headers=_auth(member_token)
    )
    assert denied.status_code == 403


async def test_manager_may_decide(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
):
    proposal = await _proposal(session, two_orgs.a)
    _, token = await make_member(session, two_orgs.a.organization, MemberRole.manager)
    response = await client.post(f"/intake/proposals/{proposal.id}/dismiss", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "descartada"


async def test_accept_links_with_a_comment_and_keeps_the_status(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a = two_orgs.a
    proposal = await _proposal(session, a)

    response = await client.post(
        f"/intake/proposals/{proposal.id}/accept", json={}, headers=_auth(a.token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "aceptada" and data["decided_by"] == str(a.user.id)
    assert data["task_id"] == str(a.task.id)
    task = await session.get(Task, a.task.id)
    await session.refresh(task)
    assert task.status == "Backlog"
    comments = (
        (await session.execute(select(TaskComment).where(TaskComment.task_id == a.task.id)))
        .scalars()
        .all()
    )
    assert len(comments) == 1
    body = comments[0].body
    assert "Solicitud de acceso VPN" in body and "Ana pide acceso a la VPN." in body
    assert "Pendiente de respuesta" in body and str(proposal.id) in body
    assert comments[0].author_id == a.user.id


async def test_accept_with_explicit_status_moves_the_task(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a = two_orgs.a
    await _board(session, a.project)
    proposal = await _proposal(session, a)
    response = await client.post(
        f"/intake/proposals/{proposal.id}/accept", json={"status": "Doing"}, headers=_auth(a.token)
    )
    assert response.status_code == 200, response.text
    task = await session.get(Task, a.task.id)
    await session.refresh(task)
    assert task.status == "Doing"


async def test_accept_with_invalid_status_changes_nothing(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a = two_orgs.a
    await _board(session, a.project)
    proposal = await _proposal(session, a)
    response = await client.post(
        f"/intake/proposals/{proposal.id}/accept", json={"status": "Nada"}, headers=_auth(a.token)
    )
    assert response.status_code == 422
    await session.refresh(proposal)
    assert proposal.status == "propuesta"


async def test_accept_requires_a_task_and_only_of_the_same_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a, b = two_orgs.a, two_orgs.b
    without_task = await _proposal(session, a, relation="tarea_nueva", task=False)
    missing = await client.post(
        f"/intake/proposals/{without_task.id}/accept", json={}, headers=_auth(a.token)
    )
    assert missing.status_code == 422
    assert missing.json()["code"] == "proposal_task_required"

    foreign = await client.post(
        f"/intake/proposals/{without_task.id}/accept",
        json={"task_id": str(b.task.id)},
        headers=_auth(a.token),
    )
    assert foreign.status_code == 404

    chosen = await client.post(
        f"/intake/proposals/{without_task.id}/accept",
        json={"task_id": str(a.task.id)},
        headers=_auth(a.token),
    )
    assert chosen.status_code == 200
    assert chosen.json()["data"]["task_id"] == str(a.task.id)


async def test_other_organization_proposal_is_404_and_decided_is_409(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a, b = two_orgs.a, two_orgs.b
    foreign = await _proposal(session, b)
    for action in ("accept", "dismiss", "create-task"):
        response = await client.post(
            f"/intake/proposals/{foreign.id}/{action}", json={}, headers=_auth(a.token)
        )
        assert response.status_code == 404, action

    proposal = await _proposal(session, a)
    assert (
        await client.post(f"/intake/proposals/{proposal.id}/dismiss", headers=_auth(a.token))
    ).status_code == 200
    again = await client.post(
        f"/intake/proposals/{proposal.id}/accept", json={}, headers=_auth(a.token)
    )
    assert again.status_code == 409
    assert again.json()["code"] == "proposal_already_decided"


async def test_create_task_uses_the_intake_default_project(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
):
    a = two_orgs.a
    proposal = await _proposal(session, a, relation="tarea_nueva", task=False)

    response = await client.post(
        f"/intake/proposals/{proposal.id}/create-task", json={}, headers=_auth(a.token)
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "aceptada" and data["created_task_id"]
    task = await session.get(Task, uuid.UUID(data["created_task_id"]))
    assert task.title == "Dar acceso a la VPN"
    assert task.due_date is not None and task.due_date.date().isoformat() == "2026-10-10"
    assert "Ana pide acceso a la VPN." in task.description
    settings_row = (
        await session.execute(
            select(IntakeSettings).where(IntakeSettings.organization_id == a.organization.id)
        )
    ).scalar_one()
    assert task.project_id == settings_row.default_project_id
    assert data["task_id"] == data["created_task_id"]
