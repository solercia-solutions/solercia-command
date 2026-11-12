"""Reconciliation persistence (C05): port + SQLAlchemy adapter.

Every read and write is scoped by ``organization_id``. The adapter only
flushes; ``ReconciliationService`` (classification) and the proposal
use cases own completion. PostgreSQL specifics (``REAL[]`` upsert, JSONB,
the partial unique index) stay here and are proven against PostgreSQL.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.connectors.models import ConnectedAccount
from app.modules.intake.models import IntakeItem
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.enums import IntakeItemType

from .candidates import TaskSnapshot
from .models import IntakeProposal, TaskEmbedding
from .threads import MailItem, normalize_task_key

#: Hard ceiling on items read per window (the per-run thread limit is
#: applied afterwards by the service).
_MAX_ITEMS = 5000


class ReconciliationRepository(Protocol):
    async def list_mail_items(
        self, organization_id: uuid.UUID, since: datetime
    ) -> list[MailItem]: ...

    async def list_active_tasks(self, organization_id: uuid.UUID) -> list[TaskSnapshot]: ...

    async def find_embeddings(
        self, organization_id: uuid.UUID, model: str, task_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, list[float]]]: ...

    async def save_embedding(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
        text_hash: str,
        vector: Sequence[float],
    ) -> None: ...

    async def find_open_proposal(
        self, organization_id: uuid.UUID, conversation_key: str
    ) -> IntakeProposal | None: ...

    async def find_latest_decided(
        self, organization_id: uuid.UUID, conversation_key: str
    ) -> IntakeProposal | None: ...

    async def add_proposal(self, proposal: IntakeProposal) -> None: ...

    async def flush(self) -> None: ...


def _addresses(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(v).strip().lower() for v in value if v)


def _mail_item(row: IntakeItem, mailbox: str | None) -> MailItem:
    payload = row.raw_payload or {}
    return MailItem(
        id=row.id,
        conversation_id=row.conversation_id,
        subject=row.title or "",
        sender=(row.origin_actor or "").strip().lower(),
        recipients=_addresses(payload.get("recipients")),
        cc=_addresses(payload.get("cc")),
        direction=row.direction,
        occurred_at=row.occurred_at,
        body=payload.get("body_text") or row.snippet or "",
        mailbox=mailbox.strip().lower() if mailbox else None,
    )


class SqlReconciliationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def flush(self) -> None:
        await self._session.flush()

    async def find_organization_slug(self, organization_id: uuid.UUID) -> str | None:
        """Slug that names the organization's rules file (channel v2)."""

        return await self._session.scalar(
            select(Organization.slug).where(Organization.id == organization_id)
        )

    # --- mail -------------------------------------------------------------------

    async def list_mail_items(self, organization_id: uuid.UUID, since: datetime) -> list[MailItem]:
        """Mail items since ``since`` plus the earlier messages of the
        conversations they belong to (the state needs the whole thread)."""

        base = (
            select(IntakeItem, ConnectedAccount.external_account_id)
            .outerjoin(
                ConnectedAccount,
                and_(
                    ConnectedAccount.id == IntakeItem.connected_account_id,
                    ConnectedAccount.organization_id == organization_id,
                ),
            )
            .where(
                IntakeItem.organization_id == organization_id,
                IntakeItem.item_type == IntakeItemType.email,
                IntakeItem.is_active.is_(True),
            )
        )
        touched = (
            select(IntakeItem.conversation_id)
            .where(
                IntakeItem.organization_id == organization_id,
                IntakeItem.item_type == IntakeItemType.email,
                IntakeItem.is_active.is_(True),
                IntakeItem.occurred_at >= since,
                IntakeItem.conversation_id.is_not(None),
            )
            .scalar_subquery()
        )
        stmt = (
            base.where(
                or_(IntakeItem.occurred_at >= since, IntakeItem.conversation_id.in_(touched))
            )
            .order_by(IntakeItem.occurred_at.desc())
            .limit(_MAX_ITEMS)
        )
        rows = (await self._session.execute(stmt)).all()
        return [_mail_item(item, mailbox) for item, mailbox in rows]

    # --- tasks ------------------------------------------------------------------

    async def list_active_tasks(self, organization_id: uuid.UUID) -> list[TaskSnapshot]:
        stmt = (
            select(Task, Project.code)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
                Task.is_active.is_(True),
                Task.completed_at.is_(None),
            )
            .order_by(Task.created_at.asc(), Task.id.asc())
        )
        snapshots = []
        for task, code in (await self._session.execute(stmt)).all():
            project_key = f"{code}-{task.task_number}" if code and task.task_number else None
            keys = [
                key
                for key in (
                    normalize_task_key(task.external_key or ""),
                    normalize_task_key(project_key or ""),
                )
                if key
            ]
            snapshots.append(
                TaskSnapshot(
                    id=task.id,
                    ref=task.external_key or project_key,
                    title=task.title,
                    description=task.description or "",
                    keys=tuple(dict.fromkeys(keys)),
                )
            )
        return snapshots

    async def find_task(self, organization_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
        stmt = (
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Task.id == task_id,
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # --- embeddings -------------------------------------------------------------

    async def find_embeddings(
        self, organization_id: uuid.UUID, model: str, task_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, list[float]]]:
        if not task_ids:
            return {}
        stmt = select(TaskEmbedding).where(
            TaskEmbedding.organization_id == organization_id,
            TaskEmbedding.model == model,
            TaskEmbedding.task_id.in_(list(task_ids)),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return {row.task_id: (row.text_hash, list(row.vector)) for row in rows}

    async def save_embedding(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        model: str,
        text_hash: str,
        vector: Sequence[float],
    ) -> None:
        values = list(vector)
        stmt = insert(TaskEmbedding).values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            task_id=task_id,
            model=model,
            text_hash=text_hash,
            vector=values,
            dimensions=len(values),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_task_embeddings_task_model",
            set_={
                "text_hash": stmt.excluded.text_hash,
                "vector": stmt.excluded.vector,
                "dimensions": stmt.excluded.dimensions,
                "updated_at": func.now(),
            },
            # Never overwrite a row of another organization.
            where=TaskEmbedding.organization_id == organization_id,
        )
        await self._session.execute(stmt)

    # --- proposals --------------------------------------------------------------

    async def find_open_proposal(
        self, organization_id: uuid.UUID, conversation_key: str
    ) -> IntakeProposal | None:
        stmt = select(IntakeProposal).where(
            IntakeProposal.organization_id == organization_id,
            IntakeProposal.conversation_key == conversation_key,
            IntakeProposal.status == "propuesta",
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_latest_decided(
        self, organization_id: uuid.UUID, conversation_key: str
    ) -> IntakeProposal | None:
        stmt = (
            select(IntakeProposal)
            .where(
                IntakeProposal.organization_id == organization_id,
                IntakeProposal.conversation_key == conversation_key,
                IntakeProposal.status != "propuesta",
            )
            .order_by(IntakeProposal.updated_at.desc(), IntakeProposal.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def add_proposal(self, proposal: IntakeProposal) -> None:
        self._session.add(proposal)
        await self._session.flush()

    async def get_proposal(
        self, organization_id: uuid.UUID, proposal_id: uuid.UUID, *, for_update: bool = False
    ) -> IntakeProposal | None:
        stmt = select(IntakeProposal).where(
            IntakeProposal.organization_id == organization_id,
            IntakeProposal.id == proposal_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_proposals(
        self,
        organization_id: uuid.UUID,
        *,
        status: str | None = None,
        task_id: uuid.UUID | None = None,
        thread_state: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[IntakeProposal], int]:
        conditions = [IntakeProposal.organization_id == organization_id]
        if status is not None:
            conditions.append(IntakeProposal.status == status)
        if task_id is not None:
            conditions.append(IntakeProposal.task_id == task_id)
        if thread_state is not None:
            conditions.append(IntakeProposal.thread_state == thread_state)
        total = await self._session.scalar(
            select(func.count()).select_from(IntakeProposal).where(*conditions)
        )
        stmt = (
            select(IntakeProposal)
            .where(*conditions)
            .order_by(IntakeProposal.last_message_at.desc(), IntakeProposal.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), int(total or 0)
