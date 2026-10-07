"""``/intake/proposals`` (C05) — the classifier's proposals per mail thread.

Admin and manager only (the summaries carry mail content), always scoped to
the caller's organization. Deciding never changes a task status unless the
accept body asks for one.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

from .decisions import ProposalDecisionService
from .schemas import IntakeProposalRead, ProposalAccept, ProposalCreateTask

router = APIRouter(prefix="/intake/proposals", tags=["intake-proposals"])

require_proposal_role = require_role(MemberRole.admin, MemberRole.manager)

ProposalStatus = Literal["propuesta", "aceptada", "descartada"]
ThreadState = Literal["respondido", "pendiente_respuesta", "solo_saliente"]


def _read(proposal) -> IntakeProposalRead:
    return IntakeProposalRead.model_validate(proposal)


@router.get("")
async def list_proposals(
    status: ProposalStatus | None = Query(default=None),
    task_id: uuid.UUID | None = Query(default=None),
    thread_state: ThreadState | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    membership: OrganizationMember = Depends(require_proposal_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Proposals of the caller's organization, newest thread first."""

    rows, total = await ProposalDecisionService(db).list_proposals(
        membership.organization_id,
        status=status,
        task_id=task_id,
        thread_state=thread_state,
        page=page,
        size=size,
    )
    return {
        "data": [_read(row) for row in rows],
        "meta": {"page": page, "size": size, "total": total},
    }


@router.get("/{proposal_id}")
async def get_proposal(
    proposal_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_proposal_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One proposal of the caller's organization (the task comment links
    here). 404 ``proposal_not_found`` for another organization's id."""

    proposal = await ProposalDecisionService(db).get_proposal(
        membership.organization_id, proposal_id
    )
    return {"data": _read(proposal)}


@router.post("/{proposal_id}/accept")
async def accept_proposal(
    proposal_id: uuid.UUID,
    data: ProposalAccept = Body(default_factory=ProposalAccept),
    membership: OrganizationMember = Depends(require_proposal_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Link the thread to the task (comment with summary and link). The
    task status changes only when ``status`` is sent."""

    proposal = await ProposalDecisionService(db).accept(
        membership.organization_id, proposal_id, data, membership.user_id
    )
    return {"data": _read(proposal), "message": "Hilo vinculado a la tarea."}


@router.post("/{proposal_id}/dismiss")
async def dismiss_proposal(
    proposal_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_proposal_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Discard the proposal; the thread is proposed again only if it grows."""

    proposal = await ProposalDecisionService(db).dismiss(
        membership.organization_id, proposal_id, membership.user_id
    )
    return {"data": _read(proposal), "message": "Propuesta descartada."}


@router.post("/{proposal_id}/create-task")
async def create_task_from_proposal(
    proposal_id: uuid.UUID,
    data: ProposalCreateTask = Body(default_factory=ProposalCreateTask),
    membership: OrganizationMember = Depends(require_proposal_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a task in the organization's default intake project."""

    proposal = await ProposalDecisionService(db).create_task(
        membership.organization_id, proposal_id, data, membership.user_id
    )
    return {"data": _read(proposal), "message": "Tarea creada desde el hilo."}
