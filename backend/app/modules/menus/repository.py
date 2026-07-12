"""Data-access layer for menus (global, hierarchical activities)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.modules.menus.models import Menu
from app.modules.roles.models import RoleMenu
from app.shared.pagination import PaginationParams, paginate

# Whitelist for ``?sort=`` on ``GET /admin/menus``. First entry is the
# default order when pagination is requested without an explicit ``sort``.
SORTABLE_FIELDS: dict[str, InstrumentedAttribute] = {
    "order": Menu.order,
    "name": Menu.name,
    "created_at": Menu.created_at,
}


class MenuRepository:
    """Async repository encapsulating menu persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_active(
        self, pagination: PaginationParams | None = None
    ) -> tuple[Sequence[Menu], int]:
        """Return ``(menus, total)`` — every active menu, ordered for display.

        Only affects the returned slice: callers that need the FULL active
        set regardless of pagination (e.g. the tree in ``meta.tree``) must
        call this with ``pagination=None``.
        """

        stmt = select(Menu).where(Menu.is_active.is_(True))

        if pagination is not None and pagination.requested:
            return await paginate(self.db, stmt, pagination, SORTABLE_FIELDS)

        stmt = stmt.order_by(Menu.order.asc(), Menu.name.asc())
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return rows, len(rows)

    async def list_for_roles(
        self, role_ids: Sequence[uuid.UUID]
    ) -> Sequence[Menu]:
        """Return the distinct active menus granted to any of ``role_ids``."""

        if not role_ids:
            return []
        result = await self.db.execute(
            select(Menu)
            .join(RoleMenu, RoleMenu.menu_id == Menu.id)
            .where(
                RoleMenu.role_id.in_(role_ids),
                Menu.is_active.is_(True),
            )
            .order_by(Menu.order.asc(), Menu.name.asc())
            .distinct()
        )
        return result.scalars().all()

    async def list_active_ids(
        self, menu_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Return the subset of ``menu_ids`` that map to active menus."""

        if not menu_ids:
            return set()
        result = await self.db.execute(
            select(Menu.id).where(
                Menu.id.in_(menu_ids),
                Menu.is_active.is_(True),
            )
        )
        return set(result.scalars().all())

    async def get(self, menu_id: uuid.UUID) -> Menu | None:
        """Return a single active menu, or ``None``."""

        result = await self.db.execute(
            select(Menu).where(
                Menu.id == menu_id,
                Menu.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, menu: Menu) -> Menu:
        """Persist a new menu and return the refreshed instance."""

        self.db.add(menu)
        await self.db.commit()
        await self.db.refresh(menu)
        return menu

    async def save(self, menu: Menu) -> Menu:
        """Flush pending changes on an attached menu and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(menu)
        return menu
