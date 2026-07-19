"""Data-access layer for projects.

Only this layer talks to SQLAlchemy; services and routers depend on it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import Integer, and_, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, aliased
from sqlalchemy.sql import Select

from app.config import settings
from app.modules.boards.models import Board, BoardColumn
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /projects``. First entry is the default
# order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "created_at": Project.created_at,
    "name": Project.name,
    "code": Project.code,
}


class ProjectRepository:
    """Async repository encapsulating project persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_org(
        self,
        organization_id: uuid.UUID,
        pagination: PaginationParams | None = None,
    ) -> tuple[Sequence[Project], int]:
        """Return ``(projects, total)`` — active projects, newest first."""

        stmt = select(Project).where(
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
        )

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Project.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def get(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Project | None:
        """Return a single project scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
                Project.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(
        self, organization_id: uuid.UUID, code: str
    ) -> Project | None:
        """Return the active project matching ``code`` within the organization."""

        result = await self.db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.code == code.upper(),
                Project.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def code_exists(
        self, organization_id: uuid.UUID, code: str, exclude_id: uuid.UUID | None = None
    ) -> bool:
        """Return True if ``code`` is already used in the organization."""

        stmt = select(Project.id).where(
            Project.organization_id == organization_id,
            Project.code == code.upper(),
            Project.is_active.is_(True),
        )
        if exclude_id is not None:
            stmt = stmt.where(Project.id != exclude_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(self, project: Project) -> Project:
        """Persist a new project and return the refreshed instance."""

        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def save(self, project: Project) -> Project:
        """Flush pending changes on an attached project and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(project)
        return project

    # -- hierarchy (change 21-project-hierarchy) ----------------------------

    async def ancestor_ids(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Walk ``parent_project_id`` upward from ``project_id``.

        Returns ancestor ids ordered from the IMMEDIATE parent to the root;
        ``project_id`` itself is never included. Bounded by
        ``settings.PROJECT_HIERARCHY_MAX_DEPTH`` iterations (design.md
        Decision 3, "la caminata de ancestros está acotada... corta barato en
        ciclo") so a pre-existing corrupted cycle can never loop forever —
        each iteration is one cheap single-row lookup, never a recursive
        query, since the chain length is bounded by the same small constant
        used to reject excessive depth.
        """

        ancestors: list[uuid.UUID] = []
        current_id: uuid.UUID | None = project_id
        for _ in range(settings.PROJECT_HIERARCHY_MAX_DEPTH):
            result = await self.db.execute(
                select(Project.parent_project_id).where(
                    Project.id == current_id,
                    Project.organization_id == organization_id,
                )
            )
            parent_id = result.scalar_one_or_none()
            if parent_id is None:
                break
            ancestors.append(parent_id)
            current_id = parent_id
        return ancestors

    async def subtree_height(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> int:
        """Return the height of the subtree rooted at ``project_id``.

        ``0`` for a project with no active children. Small recursive CTE
        (design.md Decision 3, "altura_subárbol(C) ... con un CTE recursivo
        pequeño"); filters ``organization_id`` + ``is_active`` at every
        level, same defensive posture as :meth:`fetch_subtree`.
        """

        base = select(
            Project.id, cast(literal(0), Integer).label("depth")
        ).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
        )
        subtree_cte = base.cte(name="project_height_subtree", recursive=True)
        child = aliased(Project)
        recursive_step = (
            select(child.id, (subtree_cte.c.depth + 1).label("depth"))
            .join(subtree_cte, child.parent_project_id == subtree_cte.c.id)
            .where(
                child.organization_id == organization_id,
                child.is_active.is_(True),
            )
        )
        subtree_cte = subtree_cte.union_all(recursive_step)

        result = await self.db.execute(
            select(func.coalesce(func.max(subtree_cte.c.depth), 0))
        )
        return int(result.scalar_one())

    def _subtree_ids_select(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Select:
        """Build the recursive CTE selecting every active id of the subtree.

        Base term: ``project_id`` itself. Recursive term: children whose
        ``parent_project_id`` matches an id already in the CTE. Filters
        ``organization_id`` + ``is_active`` at EVERY level (both base and
        recursive terms) — an inactive or cross-tenant row can never be a
        traversal hop, so its descendants are excluded transitively even if
        they are individually active/same-tenant (design.md Decision 3,
        "filtra organization_id + is_active en cada nivel").
        """

        base = select(Project.id).where(
            Project.id == project_id,
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
        )
        subtree_cte = base.cte(name="project_subtree_ids", recursive=True)
        child = aliased(Project)
        recursive_step = (
            select(child.id)
            .join(subtree_cte, child.parent_project_id == subtree_cte.c.id)
            .where(
                child.organization_id == organization_id,
                child.is_active.is_(True),
            )
        )
        subtree_cte = subtree_cte.union_all(recursive_step)
        return select(subtree_cte.c.id)

    async def fetch_subtree(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[Project]:
        """Return ``project_id`` and every active descendant of its subtree.

        Never crosses ``organization_id`` — see :meth:`_subtree_ids_select`.
        Order is unspecified; the service layer nests the tree by
        ``parent_project_id``.
        """

        subtree_ids = self._subtree_ids_select(organization_id, project_id)
        result = await self.db.execute(
            select(Project).where(Project.id.in_(subtree_ids))
        )
        return result.scalars().all()

    async def rollup_progress(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> Sequence[tuple[uuid.UUID, int, int]]:
        """Return ``(project_id, done, total)`` for every node of the subtree.

        ``done`` counts a project's OWN tasks whose ``status`` matches the
        LAST board column (``status_key``) of that SAME project — the
        ``DISTINCT ON (board.project_id) ... ORDER BY column_order DESC,
        created_at DESC`` CTE below reproduces
        ``DashboardService._bounds_for``'s "last allowed status = done"
        rule exactly (design.md Decision 1). ``total`` excludes ``cancelled``
        tasks from BOTH terms (design.md Decision 2). Every row is scoped to
        the caller's ``organization_id`` transitively through
        :meth:`_subtree_ids_select`. The caller (service layer) sums these
        rows to build the consolidated roll-up of the requested root.
        """

        subtree_ids = self._subtree_ids_select(organization_id, project_id)

        last_status = (
            select(
                Board.project_id.label("project_id"),
                BoardColumn.status_key.label("status_key"),
            )
            .distinct(Board.project_id)
            .select_from(Board)
            .join(BoardColumn, BoardColumn.board_id == Board.id)
            .where(
                Board.project_id.in_(subtree_ids),
                Board.is_active.is_(True),
                BoardColumn.is_active.is_(True),
            )
            .order_by(
                Board.project_id,
                BoardColumn.order.desc(),
                BoardColumn.created_at.desc(),
            )
            .subquery("last_status")
        )

        not_cancelled = Task.status != "cancelled"

        stmt = (
            select(
                Project.id.label("project_id"),
                func.count(Task.id).filter(not_cancelled).label("total"),
                func.count(Task.id)
                .filter(not_cancelled, Task.status == last_status.c.status_key)
                .label("done"),
            )
            .select_from(Project)
            .outerjoin(
                Task, and_(Task.project_id == Project.id, Task.is_active.is_(True))
            )
            .outerjoin(last_status, last_status.c.project_id == Project.id)
            .where(Project.id.in_(subtree_ids))
            .group_by(Project.id)
        )

        result = await self.db.execute(stmt)
        return [(row.project_id, row.done, row.total) for row in result.all()]
