"""Data-access layer for labels and task-label links.

Labels are tenant-scoped directly via ``Label.organization_id`` (no join to
``Project`` needed for the tenant filter, unlike ``Task``).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.labels.models import Label, TaskLabel
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /projects/{id}/labels``. First entry is
# the default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "name": Label.name,
    "created_at": Label.created_at,
}


class LabelRepository:
    """Async repository encapsulating label and task-label persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_project(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Label], int]:
        """Return ``(labels, total)`` — active labels of a project, name-ordered."""

        stmt = select(Label).where(
            Label.project_id == project_id,
            Label.organization_id == organization_id,
            Label.is_active.is_(True),
        )
        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Label.name.asc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, organization_id: uuid.UUID, label_id: uuid.UUID
    ) -> Label | None:
        """Return a single active label scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Label).where(
                Label.id == label_id,
                Label.organization_id == organization_id,
                Label.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, name: str
    ) -> Label | None:
        """Return the active label with ``name`` in a project, or ``None``."""

        result = await self.db.execute(
            select(Label).where(
                Label.project_id == project_id,
                Label.organization_id == organization_id,
                Label.name == name,
                Label.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, label: Label) -> Label:
        """Persist a new label and return the refreshed instance."""

        self.db.add(label)
        await self.db.commit()
        await self.db.refresh(label)
        return label

    async def save(self, label: Label) -> Label:
        """Flush pending changes on an attached label and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(label)
        return label

    # -- TaskLabel -----------------------------------------------------

    async def get_link(
        self, task_id: uuid.UUID, label_id: uuid.UUID
    ) -> TaskLabel | None:
        """Return the ``TaskLabel`` row for a task/label pair, or ``None``."""

        result = await self.db.execute(
            select(TaskLabel).where(
                TaskLabel.task_id == task_id, TaskLabel.label_id == label_id
            )
        )
        return result.scalar_one_or_none()

    async def link(self, task_id: uuid.UUID, label_id: uuid.UUID) -> TaskLabel:
        """Create a ``TaskLabel`` row, assigning ``label_id`` to ``task_id``."""

        link_row = TaskLabel(task_id=task_id, label_id=label_id)
        self.db.add(link_row)
        await self.db.commit()
        await self.db.refresh(link_row)
        return link_row

    async def unlink(self, task_id: uuid.UUID, label_id: uuid.UUID) -> None:
        """Hard-delete the ``TaskLabel`` row for a task/label pair, if any."""

        await self.db.execute(
            delete(TaskLabel).where(
                TaskLabel.task_id == task_id, TaskLabel.label_id == label_id
            )
        )
        await self.db.commit()

    async def unlink_all_for_label(self, label_id: uuid.UUID) -> None:
        """Hard-delete every ``TaskLabel`` row for ``label_id``.

        Called when a ``Label`` is soft-deleted, to unlink it from every task
        it was assigned to (labels.md, "Eliminación de etiqueta sin afectar
        tareas"). ``TaskLabel`` carries no ``SoftDeleteMixin`` (design.md,
        hard-delete association convention), so "unlink" here means removing
        the association rows outright — the tasks themselves are never
        touched. Caller is responsible for committing (the label's own
        soft-delete save() commits both changes together).
        """

        await self.db.execute(delete(TaskLabel).where(TaskLabel.label_id == label_id))

    async def list_labels_for_task(self, task_id: uuid.UUID) -> Sequence[Label]:
        """Return the active labels assigned to a task, name-ordered."""

        result = await self.db.execute(
            select(Label)
            .join(TaskLabel, TaskLabel.label_id == Label.id)
            .where(TaskLabel.task_id == task_id, Label.is_active.is_(True))
            .order_by(Label.name.asc())
        )
        return result.scalars().all()
