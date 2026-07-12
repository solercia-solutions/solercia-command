"""Business logic for the global search endpoint (change 10-busqueda-global)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.repository import SearchRepository
from app.modules.search.schemas import SearchResult, parse_types
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams

#: Minimum length of ``q`` (after trimming) — global-search.md R2.
_MIN_QUERY_LENGTH = 2


class SearchService:
    """Orchestrates the multi-entity search use case for a single organization."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = SearchRepository(db)

    async def search(
        self,
        organization_id: uuid.UUID,
        q: str,
        types: str | None,
        pagination: PaginationParams,
    ) -> tuple[list[SearchResult], int]:
        """Validate ``q``/``types`` and return ``(results, total)``.

        ``pagination`` always paginates for this endpoint — see
        ``search/router.py`` (design.md, "NOTA de paginación").
        """

        cleaned_q = q.strip()
        if len(cleaned_q) < _MIN_QUERY_LENGTH:
            raise AppException(
                "La búsqueda debe tener al menos 2 caracteres.",
                code="query_too_short",
                status_code=422,
            )

        try:
            parsed_types = parse_types(types)
        except ValueError as exc:
            raise AppException(
                str(exc), code="invalid_search_type", status_code=422
            ) from exc

        rows, total = await self.repo.search(
            organization_id, cleaned_q, parsed_types, pagination
        )
        results = [
            SearchResult(
                entity_type=row.entity_type,
                id=row.id,
                title=row.title,
                snippet=row.snippet,
                project_id=row.project_id,
                project_name=row.project_name,
                task_key=row.task_key,
                task_id=row.task_id,
            )
            for row in rows
        ]
        return results, total
