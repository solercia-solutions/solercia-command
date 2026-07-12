"""Data-access layer for the global search endpoint (change 10-busqueda-global).

Concentrates every SQL statement GET /search needs — the router and service
never touch SQLAlchemy directly (design.md, "el repository de búsqueda
concentra TODO el SQL"). Each entity branch (task/project/comment) is built
as an independent ``SELECT`` with an identical column shape and combined via
``UNION ALL`` into one flat, paginated result list (design.md Decision 3).

Tenant scope and soft-delete exclusion (design.md Decision 4) are enforced
independently per branch: ``tasks`` via the join to ``Project.organization_id``
(``Task`` carries no ``organization_id`` of its own); ``projects``/``comments``
directly via their own ``organization_id`` (``TenantMixin``). Every branch
also excludes ``is_active=false`` rows — the ``comment`` branch additionally
requires its parent ``Task``/``Project`` to be active, since a comment on a
deleted task has no usable context.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Row, Select, String, Uuid, case, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comments.models import TaskComment
from app.modules.projects.models import Project
from app.modules.search.schemas import escape_like
from app.modules.tasks.models import Task
from app.shared.pagination import PaginationParams

#: Length of the text fragment returned as ``snippet`` (design.md, Interfaces).
_SNIPPET_LENGTH = 160


class SearchRepository:
    """Async repository encapsulating the multi-entity search query."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search(
        self,
        organization_id: uuid.UUID,
        q: str,
        types: set[str],
        pagination: PaginationParams,
    ) -> tuple[Sequence[Row[Any]], int]:
        """Return ``(rows, total)`` — matches across the enabled ``types``.

        ``q`` must already be trimmed by the caller. Each row exposes
        ``entity_type, id, title, snippet, project_id, project_name,
        task_key, task_id`` (plus internal ``rank``/``created_at`` used only
        for ordering) — see :class:`app.modules.search.schemas.SearchResult`.
        """

        pattern = f"%{escape_like(q)}%"

        branches = []
        if "task" in types:
            branches.append(self._task_branch(organization_id, pattern, q))
        if "project" in types:
            branches.append(self._project_branch(organization_id, pattern, q))
        if "comment" in types:
            branches.append(self._comment_branch(organization_id, pattern, q))

        union_subquery = union_all(*branches).subquery("search_results")

        count_stmt = select(func.count()).select_from(union_subquery)
        total = (await self.db.execute(count_stmt)).scalar_one()

        page = pagination.page or 1
        sliced_stmt = (
            select(union_subquery)
            .order_by(
                union_subquery.c.rank.desc(),
                union_subquery.c.entity_type.asc(),
                union_subquery.c.created_at.desc(),
                union_subquery.c.id.asc(),
            )
            .limit(pagination.size)
            .offset((page - 1) * pagination.size)
        )
        result = await self.db.execute(sliced_stmt)
        return result.all(), total

    # -- branches ------------------------------------------------------

    def _task_branch(
        self, organization_id: uuid.UUID, pattern: str, q: str
    ) -> Select[Any]:
        matched_title = Task.title.ilike(pattern)
        matched_description = Task.description.ilike(pattern)
        snippet = case(
            (matched_title, func.substr(Task.title, 1, _SNIPPET_LENGTH)),
            (matched_description, func.substr(Task.description, 1, _SNIPPET_LENGTH)),
            else_=func.substr(Task.title, 1, _SNIPPET_LENGTH),
        )
        task_key = case(
            (
                (Project.code.isnot(None)) & (Task.task_number.isnot(None)),
                Project.code.concat("-").concat(func.cast(Task.task_number, String)),
            ),
            else_=None,
        )
        rank = func.greatest(
            func.similarity(Task.title, q),
            func.similarity(func.coalesce(Task.description, ""), q),
        )
        return (
            select(
                literal("task").label("entity_type"),
                Task.id.label("id"),
                Task.title.label("title"),
                snippet.label("snippet"),
                Task.project_id.label("project_id"),
                Project.name.label("project_name"),
                task_key.label("task_key"),
                literal(None, type_=Uuid).label("task_id"),
                rank.label("rank"),
                Task.created_at.label("created_at"),
            )
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Task.is_active.is_(True),
                Project.is_active.is_(True),
                (matched_title | matched_description),
            )
        )

    def _project_branch(
        self, organization_id: uuid.UUID, pattern: str, q: str
    ) -> Select[Any]:
        matched_name = Project.name.ilike(pattern)
        matched_description = Project.description.ilike(pattern)
        snippet = case(
            (matched_name, func.substr(Project.name, 1, _SNIPPET_LENGTH)),
            (
                matched_description,
                func.substr(Project.description, 1, _SNIPPET_LENGTH),
            ),
            else_=func.substr(Project.name, 1, _SNIPPET_LENGTH),
        )
        rank = func.greatest(
            func.similarity(Project.name, q),
            func.similarity(func.coalesce(Project.description, ""), q),
        )
        return select(
            literal("project").label("entity_type"),
            Project.id.label("id"),
            Project.name.label("title"),
            snippet.label("snippet"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            literal(None, type_=String).label("task_key"),
            literal(None, type_=Uuid).label("task_id"),
            rank.label("rank"),
            Project.created_at.label("created_at"),
        ).where(
            Project.organization_id == organization_id,
            Project.is_active.is_(True),
            (matched_name | matched_description),
        )

    def _comment_branch(
        self, organization_id: uuid.UUID, pattern: str, q: str
    ) -> Select[Any]:
        matched_body = TaskComment.body.ilike(pattern)
        snippet = func.substr(TaskComment.body, 1, _SNIPPET_LENGTH)
        rank = func.similarity(TaskComment.body, q)
        return (
            select(
                literal("comment").label("entity_type"),
                TaskComment.id.label("id"),
                Task.title.label("title"),
                snippet.label("snippet"),
                Task.project_id.label("project_id"),
                Project.name.label("project_name"),
                literal(None, type_=String).label("task_key"),
                TaskComment.task_id.label("task_id"),
                rank.label("rank"),
                TaskComment.created_at.label("created_at"),
            )
            .join(Task, Task.id == TaskComment.task_id)
            .join(Project, Project.id == Task.project_id)
            .where(
                TaskComment.organization_id == organization_id,
                TaskComment.is_active.is_(True),
                Task.is_active.is_(True),
                Project.is_active.is_(True),
                matched_body,
            )
        )
