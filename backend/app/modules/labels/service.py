"""Business logic for labels and their assignment to tasks."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.labels.models import Label
from app.modules.labels.repository import LabelRepository
from app.modules.labels.schemas import LabelCreate, LabelRead, LabelUpdate
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


class LabelService:
    """Orchestrates label use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = LabelRepository(db)
        self.tasks = TaskRepository(db)

    async def list_labels(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[LabelRead], int]:
        """Return ``(labels, total)`` — the project's active labels."""

        labels, total = await self.repo.list_for_project(
            organization_id, project_id, pagination
        )
        return [LabelRead.model_validate(label) for label in labels], total

    async def create_label(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        data: LabelCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> LabelRead:
        """Create a label, rejecting a name already used by an active label (422)."""

        await self._reject_duplicate_name(organization_id, project_id, data.name)

        label = Label(
            organization_id=organization_id,
            project_id=project_id,
            name=data.name,
            color=data.color,
            created_by=actor_id,
            updated_by=actor_id,
        )
        label = await self.repo.create(label)
        return LabelRead.model_validate(label)

    async def update_label(
        self,
        organization_id: uuid.UUID,
        label_id: uuid.UUID,
        data: LabelUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> LabelRead:
        """Apply a partial update (rename/recolor), re-checking name uniqueness."""

        label = await self._require_label(organization_id, label_id)
        changes = data.model_dump(exclude_unset=True)

        if "name" in changes and changes["name"] != label.name:
            await self._reject_duplicate_name(
                organization_id, label.project_id, changes["name"]
            )
            label.name = changes["name"]

        if "color" in changes:
            label.color = changes["color"]

        label.updated_by = actor_id
        label = await self.repo.save(label)
        return LabelRead.model_validate(label)

    async def delete_label(
        self, organization_id: uuid.UUID, label_id: uuid.UUID
    ) -> None:
        """Soft-delete a label and unlink it from every task (labels.md R4).

        ``TaskLabel`` has no ``SoftDeleteMixin`` (hard-delete association
        convention, design.md); unlinking here removes those rows outright.
        Tasks themselves are never touched.
        """

        label = await self._require_label(organization_id, label_id)
        await self.repo.unlink_all_for_label(label.id)
        label.is_active = False
        label.deleted_at = datetime.now(UTC)
        await self.repo.save(label)

    # -- TaskLabel -----------------------------------------------------

    async def assign_label(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        label_id: uuid.UUID,
    ) -> None:
        """Assign a label to a task. Both must belong to the same project (422)."""

        task = await self._require_task(organization_id, task_id)
        label = await self._require_label(organization_id, label_id)
        if label.project_id != task.project_id:
            raise AppException(
                "La etiqueta no pertenece al mismo proyecto de la tarea.",
                code="label_project_mismatch",
                status_code=422,
            )
        existing = await self.repo.get_link(task_id, label_id)
        if existing is not None:
            return
        await self.repo.link(task_id, label_id)

    async def unassign_label(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        label_id: uuid.UUID,
    ) -> None:
        """Unassign a label from a task (no-op if it wasn't assigned)."""

        await self._require_task(organization_id, task_id)
        await self.repo.unlink(task_id, label_id)

    async def list_labels_for_task(self, task_id: uuid.UUID) -> list[LabelRead]:
        """Return the active labels assigned to a task."""

        labels = await self.repo.list_labels_for_task(task_id)
        return [LabelRead.model_validate(label) for label in labels]

    # -- helpers ---------------------------------------------------------

    async def _reject_duplicate_name(
        self, organization_id: uuid.UUID, project_id: uuid.UUID, name: str
    ) -> None:
        existing = await self.repo.get_by_name(organization_id, project_id, name)
        if existing is not None:
            raise AppException(
                f"Ya existe una etiqueta activa llamada '{name}' en este proyecto.",
                code="duplicate_label_name",
                status_code=422,
            )

    async def _require_label(
        self, organization_id: uuid.UUID, label_id: uuid.UUID
    ) -> Label:
        label = await self.repo.get(organization_id, label_id)
        if label is None:
            raise AppException(
                "La etiqueta no existe o no tienes acceso a ella.",
                code="label_not_found",
                status_code=404,
            )
        return label

    async def _require_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID
    ) -> Task:
        task = await self.tasks.get(organization_id, task_id)
        if task is None:
            raise AppException(
                "La tarea no existe o no tienes acceso a ella.",
                code="task_not_found",
                status_code=404,
            )
        return task
