"""Shared pagination: dependency, query helper, and ``meta`` merging.

Pagination is opt-in: a list endpoint called without ``page``, ``size``,
``sort`` or ``order`` keeps returning the full collection with
``meta = {"total": n}`` — this is a hard backward-compatibility requirement
with the frozen Angular frontend, not a design preference. As soon as the
caller supplies ``page`` or ``sort``, the response switches to an
offset-paginated slice with ``meta = {"page": n, "size": n, "total": n}``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.shared.exceptions import AppException

#: Default page size when the caller opts into pagination without ``size``.
DEFAULT_PAGE_SIZE = 20
#: Hard upper bound for ``size`` — protects against unbounded result sets.
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class PaginationParams:
    """Resolved and validated pagination query parameters."""

    page: int | None
    size: int
    sort: str | None
    order: Literal["asc", "desc"]

    @property
    def requested(self) -> bool:
        """Whether the caller opted into pagination.

        Only ``page`` and ``sort`` can signal intent: ``size`` and ``order``
        always carry a concrete default (``20``/``"desc"``), so their mere
        presence can't be distinguished from the default value.
        """

        return self.page is not None or self.sort is not None


def pagination_params(
    page: int | None = Query(
        default=None, ge=1, description="Número de página (base 1)."
    ),
    size: int = Query(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Registros por página (máximo 100).",
    ),
    sort: str | None = Query(
        default=None, description="Campo por el cual ordenar."
    ),
    order: Literal["asc", "desc"] = Query(
        default="desc", description="Dirección del ordenamiento."
    ),
) -> PaginationParams:
    """FastAPI dependency that resolves and validates pagination params."""

    return PaginationParams(page=page, size=size, sort=sort, order=order)


async def paginate(
    db: AsyncSession,
    stmt: Select[Any],
    params: PaginationParams,
    sortable: Mapping[str, InstrumentedAttribute[Any]],
) -> tuple[Sequence[Any], int]:
    """Apply ``ORDER BY``/``LIMIT``/``OFFSET`` to ``stmt`` and count the total.

    ``sort`` must be a key of ``sortable`` (mapped to the real ORM column),
    otherwise a ``422`` is raised BEFORE any query runs. When ``sort`` is
    omitted, the FIRST key of ``sortable`` is used as the default order —
    each module declares its default sort field first in the mapping.
    """

    if not sortable:
        raise AppException(
            "Este listado no admite ordenamiento.",
            code="invalid_sort_field",
            status_code=422,
        )

    sort_key = params.sort if params.sort is not None else next(iter(sortable))
    column = sortable.get(sort_key)
    if column is None:
        allowed = ", ".join(sortable)
        raise AppException(
            f"El campo de orden '{sort_key}' no es válido. "
            f"Campos permitidos: {allowed}.",
            code="invalid_sort_field",
            status_code=422,
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    order_expr = column.asc() if params.order == "asc" else column.desc()
    page = params.page or 1
    sliced_stmt = (
        stmt.order_by(order_expr).limit(params.size).offset((page - 1) * params.size)
    )
    result = await db.execute(sliced_stmt)
    rows = result.scalars().all()
    return rows, total


def build_list_meta(
    params: PaginationParams,
    total: int,
    *,
    base: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge ``total`` (and ``page``/``size`` when paginated) into ``base``.

    Never removes existing keys from ``base`` (e.g. menus' ``tree``) — only
    adds or overwrites ``page``, ``size`` and ``total``.
    """

    meta: dict[str, Any] = dict(base) if base else {}
    if params.requested:
        meta["page"] = params.page or 1
        meta["size"] = params.size
    meta["total"] = total
    return meta
