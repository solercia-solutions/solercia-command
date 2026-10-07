"""Human decisions on proposals (C05): accept, dismiss, create a task.

Every lookup is scoped by the caller's organization; a proposal or task of
another organization is a 404. Only an open proposal (``propuesta``) can be
decided (409 otherwise). Accepting links the thread to the task with a
comment; the task status changes ONLY when the request asks for it, and that
change goes first through ``TaskService.update_task`` (strategy validation
and history) so an invalid status leaves the proposal untouched.

Transactions: ``TaskService`` and ``CommentService`` commit their own work;
the proposal fields are flushed before the last of those commits so the
decision and its comment/task land together.
"""

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.schemas import CommentCreate
from app.modules.comments.service import CommentService
from app.modules.intake.service import IntakeService
from app.modules.tasks.schemas import TaskCreate, TaskUpdate
from app.modules.tasks.service import TaskService
from app.shared.exceptions import AppException

from .models import IntakeProposal
from .repository import SqlReconciliationRepository
from .schemas import ProposalAccept, ProposalCreateTask

_STATE_LABELS = {
    "respondido": "Respondido",
    "pendiente_respuesta": "Pendiente de respuesta",
    "solo_saliente": "Solo saliente (seguimiento propio)",
}
_ATTENDED_LABELS = {"si": "Sí", "no": "No", "parcial": "Parcial"}
_DESCRIPTION_CHARS = 4000


def _not_found() -> AppException:
    return AppException(
        "La propuesta no existe o no tienes acceso a ella.",
        code="proposal_not_found",
        status_code=404,
    )


def _thread_link(proposal: IntakeProposal) -> str:
    return f"/intake/proposals/{proposal.id}"


def _summary_lines(proposal: IntakeProposal) -> list[str]:
    result = proposal.result or {}
    lines = [
        f"Estado del hilo: {_STATE_LABELS.get(proposal.thread_state, proposal.thread_state)}"
        f" · {proposal.message_count} mensajes"
        f" · último {proposal.last_message_at:%Y-%m-%d %H:%M} UTC",
    ]
    for label, key in (
        ("Resumen", "resumen"),
        ("Acción", "accion"),
        ("Solicitante", "solicitante"),
        ("Fecha límite", "fecha_limite"),
    ):
        if result.get(key):
            lines.append(f"{label}: {result[key]}")
    if result.get("atendida"):
        lines.append(f"Atendida según el hilo: {_ATTENDED_LABELS.get(result['atendida'], '')}")
    return lines


def _comment_body(proposal: IntakeProposal, note: str | None) -> str:
    lines = [f"Hilo de correo vinculado: «{proposal.subject}»", *_summary_lines(proposal)]
    if note:
        lines.append(f"Nota: {note}")
    lines.append(f"Ver hilo: {_thread_link(proposal)}")
    return "\n".join(lines)


def _due_date(proposal: IntakeProposal) -> datetime | None:
    raw = (proposal.result or {}).get("fecha_limite")
    if not raw:
        return None
    try:
        return datetime.combine(date.fromisoformat(raw), time(23, 59), tzinfo=UTC)
    except ValueError:
        return None


class ProposalDecisionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = SqlReconciliationRepository(db)

    async def list_proposals(self, organization_id: uuid.UUID, **filters):
        return await self._repo.list_proposals(organization_id, **filters)

    async def get_proposal(
        self, organization_id: uuid.UUID, proposal_id: uuid.UUID
    ) -> IntakeProposal:
        """One proposal of the organization (any status); 404 otherwise."""

        proposal = await self._repo.get_proposal(organization_id, proposal_id)
        if proposal is None:
            raise _not_found()
        return proposal

    async def _open(self, organization_id: uuid.UUID, proposal_id: uuid.UUID) -> IntakeProposal:
        proposal = await self._repo.get_proposal(organization_id, proposal_id, for_update=True)
        if proposal is None:
            raise _not_found()
        if proposal.status != "propuesta":
            raise AppException(
                "Esta propuesta ya fue decidida.",
                code="proposal_already_decided",
                status_code=409,
            )
        return proposal

    def _decide(self, proposal: IntakeProposal, status: str, actor_id: uuid.UUID | None) -> None:
        proposal.status = status
        proposal.decided_by = actor_id
        proposal.decided_at = datetime.now(UTC)
        proposal.updated_by = actor_id

    async def accept(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        data: ProposalAccept,
        actor_id: uuid.UUID,
    ) -> IntakeProposal:
        proposal = await self._open(organization_id, proposal_id)
        task_id = data.task_id or proposal.task_id
        if task_id is None:
            raise AppException(
                "Elige la tarea a la que pertenece este hilo.",
                code="proposal_task_required",
                status_code=422,
            )
        if await self._repo.find_task(organization_id, task_id) is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        if data.status is not None:
            await TaskService(self._db).update_task(
                organization_id, task_id, TaskUpdate(status=data.status), actor_id=actor_id
            )
            # update_task committed: re-lock the proposal for this decision.
            proposal = await self._open(organization_id, proposal_id)
        proposal.task_id = task_id
        self._decide(proposal, "aceptada", actor_id)
        await self._db.flush()
        await CommentService(self._db).create_comment(
            organization_id,
            task_id,
            actor_id,
            CommentCreate(body=_comment_body(proposal, data.note)),
            actor_id=actor_id,
        )
        await self._db.commit()
        await self._db.refresh(proposal)
        return proposal

    async def dismiss(
        self, organization_id: uuid.UUID, proposal_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> IntakeProposal:
        proposal = await self._open(organization_id, proposal_id)
        self._decide(proposal, "descartada", actor_id)
        await self._db.commit()
        await self._db.refresh(proposal)
        return proposal

    async def create_task(
        self,
        organization_id: uuid.UUID,
        proposal_id: uuid.UUID,
        data: ProposalCreateTask,
        actor_id: uuid.UUID | None,
    ) -> IntakeProposal:
        proposal = await self._open(organization_id, proposal_id)
        result = proposal.result or {}
        title = data.title or result.get("accion") or proposal.subject or "Tarea desde correo"
        description = "\n".join(
            [f"Origen: hilo de correo «{proposal.subject}»", *_summary_lines(proposal)]
            + [f"Ver hilo: {_thread_link(proposal)}"]
        )[:_DESCRIPTION_CHARS]
        project_id = await IntakeService(self._db).ensure_default_project(organization_id)
        self._decide(proposal, "aceptada", actor_id)
        await self._db.flush()
        task = await TaskService(self._db).create_task(
            organization_id,
            project_id,
            TaskCreate(
                title=title[:200],
                description=description,
                priority=data.priority,
                assignee_id=data.assignee_id,
                due_date=_due_date(proposal),
            ),
            actor_id=actor_id,
        )
        proposal.created_task_id = task.id
        proposal.task_id = task.id
        await self._db.commit()
        await self._db.refresh(proposal)
        return proposal
