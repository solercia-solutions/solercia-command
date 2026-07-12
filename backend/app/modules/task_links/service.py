"""Business logic for task dependency edges: linking, cycle prevention, unlinking."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.task_links.models import TaskDependency
from app.modules.task_links.repository import TaskDependencyRepository
from app.modules.task_links.schemas import BlockerRef, TaskDependencyLink, TaskDependencyRead
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


def detects_cycle(
    edges: Sequence[tuple[uuid.UUID, uuid.UUID]],
    new_blocker_id: uuid.UUID,
    new_blocked_id: uuid.UUID,
) -> bool:
    """Return whether inserting ``new_blocker_id -> new_blocked_id`` closes a cycle.

    Pure function — no DB access, easy to unit-test in isolation. Builds the
    adjacency map from existing ``blocker -> blocked`` edges, then DFS from
    ``new_blocked_id``: if the traversal reaches ``new_blocker_id``, the new
    edge would close a cycle (design.md, "Detección de ciclos por DFS en el
    servicio" — covers both direct and transitive cycles).
    """

    adjacency: dict[uuid.UUID, list[uuid.UUID]] = {}
    for blocker_id, blocked_id in edges:
        adjacency.setdefault(blocker_id, []).append(blocked_id)

    visited: set[uuid.UUID] = set()
    stack = [new_blocked_id]
    while stack:
        current = stack.pop()
        if current == new_blocker_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, []))
    return False


class TaskDependencyService:
    """Orchestrates dependency-edge use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = TaskDependencyRepository(db)
        self.tasks = TaskRepository(db)

    async def list_dependencies(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[list[TaskDependencyRead], int]:
        """Return ``(edges, total)`` from the perspective of ``task_id``, both directions."""

        await self._require_task(organization_id, task_id)
        rows, total = await self.repo.list_for_task(organization_id, task_id, pagination)
        return [self._to_read(row, task_id) for row in rows], total

    async def link(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        data: TaskDependencyLink,
    ) -> TaskDependencyRead:
        """Create (or reactivate) a dependency edge, rejecting self-loops, cross-project
        pairs and cycles (labels.md's task-dependencies R8/R9).
        """

        task = await self._require_task(organization_id, task_id)
        related = await self._require_task(organization_id, data.related_task_id)

        if related.id == task.id:
            raise AppException(
                "Una tarea no puede depender de sí misma.",
                code="dependency_self_loop",
                status_code=422,
            )
        if related.project_id != task.project_id:
            raise AppException(
                "Solo puedes enlazar tareas del mismo proyecto.",
                code="dependency_project_mismatch",
                status_code=422,
            )

        if data.type == "is_blocked_by":
            # Inverted before persisting: related_task_id -> blocker,
            # path task -> blocked (design.md gate correction #2).
            blocker_id, blocked_id = related.id, task.id
        else:
            blocker_id, blocked_id = task.id, related.id

        existing = await self.repo.get_edge_any_state(blocker_id, blocked_id)
        if existing is not None and existing.is_active:
            return self._to_read(existing, task_id)

        edges = await self.repo.list_active_edges_for_project(task.project_id)
        if detects_cycle(edges, blocker_id, blocked_id):
            raise AppException(
                "Este enlace introduciría un ciclo de dependencias entre tareas.",
                code="dependency_cycle",
                status_code=422,
            )

        if existing is not None:
            # Reactivate a previously soft-deleted edge instead of inserting
            # a duplicate row (the UniqueConstraint is not is_active-scoped).
            existing.is_active = True
            existing.deleted_at = None
            existing = await self.repo.save(existing)
            return self._to_read(existing, task_id)

        dependency = TaskDependency(
            organization_id=organization_id,
            blocker_task_id=blocker_id,
            blocked_task_id=blocked_id,
        )
        dependency = await self.repo.create(dependency)
        return self._to_read(dependency, task_id)

    async def unlink(
        self,
        organization_id: uuid.UUID,
        task_id: uuid.UUID,
        dependency_id: uuid.UUID,
    ) -> None:
        """Soft-delete a dependency edge touching ``task_id`` (never a physical delete)."""

        await self._require_task(organization_id, task_id)
        dependency = await self.repo.get_for_task(organization_id, task_id, dependency_id)
        if dependency is None:
            raise AppException(
                "El enlace de dependencia no existe o no tienes acceso a él.",
                code="dependency_not_found",
                status_code=404,
            )
        dependency.is_active = False
        dependency.deleted_at = datetime.now(UTC)
        await self.repo.save(dependency)

    async def get_blocking_state(
        self, task_id: uuid.UUID
    ) -> tuple[bool, list[BlockerRef]]:
        """Return ``(is_blocked, blockers)`` for a task's detail view (R11).

        A task is blocked while at least one active ``is_blocked_by`` edge
        points to a blocker whose ``completed_at`` is still ``NULL``.
        """

        rows = await self.repo.get_incomplete_blockers(task_id)
        blockers = [BlockerRef(task_id=tid, title=title) for tid, title in rows]
        return (len(blockers) > 0, blockers)

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _to_read(dependency: TaskDependency, task_id: uuid.UUID) -> TaskDependencyRead:
        direction: Literal["blocks", "is_blocked_by"]
        if dependency.blocker_task_id == task_id:
            direction = "blocks"
            related_task_id = dependency.blocked_task_id
        else:
            direction = "is_blocked_by"
            related_task_id = dependency.blocker_task_id
        return TaskDependencyRead(
            id=dependency.id,
            related_task_id=related_task_id,
            direction=direction,
            created_at=dependency.created_at,
        )

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
