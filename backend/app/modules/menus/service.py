"""Business logic for menus (global, hierarchical activities)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.menus.models import Menu
from app.modules.menus.repository import MenuRepository
from app.modules.menus.schemas import MenuCreate, MenuUpdate
from app.shared.exceptions import AppException
from app.shared.pagination import PaginationParams


def build_menu_tree(menus: Sequence[Menu]) -> list[dict]:
    """Nest a flat menu collection into a tree of plain dicts.

    A menu is nested under its parent only when that parent is also present in
    ``menus``; otherwise it surfaces at the root. This keeps a restricted menu
    set (e.g. the ones a non-admin role grants) from dropping items whose
    parent is not accessible. Siblings are ordered by ``order`` then ``name``.
    """

    nodes: dict[uuid.UUID, dict] = {
        menu.id: {
            "id": menu.id,
            "name": menu.name,
            "icon": menu.icon,
            "path": menu.path,
            "order": menu.order,
            "children": [],
        }
        for menu in menus
    }

    roots: list[dict] = []
    for menu in menus:
        node = nodes[menu.id]
        parent = nodes.get(menu.parent_id) if menu.parent_id else None
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)

    def _sort(level: list[dict]) -> None:
        level.sort(key=lambda item: (item["order"], item["name"]))
        for item in level:
            _sort(item["children"])

    _sort(roots)
    return roots


class MenuService:
    """Orchestrates menu use-cases. Menus are global (not org-scoped)."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = MenuRepository(db)

    async def list_menus(
        self, pagination: PaginationParams | None = None
    ) -> tuple[Sequence[Menu], int]:
        """Return ``(menus, total)`` — every active menu (flat)."""

        return await self.repo.list_active(pagination)

    async def tree(self) -> list[dict]:
        """Return the full active menu tree — NEVER paginated (gate #1).

        ``meta.tree`` must reflect the complete catalog regardless of any
        ``page``/``size`` slice applied to ``data``.
        """

        menus, _ = await self.repo.list_active()
        return build_menu_tree(menus)

    async def get_menu(self, menu_id: uuid.UUID) -> Menu:
        """Return a single menu or raise a 404 ``AppException``."""

        return await self._require(menu_id)

    async def create_menu(
        self, data: MenuCreate, *, actor_id: uuid.UUID | None = None
    ) -> Menu:
        """Persist a new menu, validating the optional parent."""

        await self._verify_parent(data.parent_id)
        menu = Menu(
            name=data.name,
            icon=data.icon,
            path=data.path,
            parent_id=data.parent_id,
            order=data.order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        return await self.repo.create(menu)

    async def update_menu(
        self,
        menu_id: uuid.UUID,
        data: MenuUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> Menu:
        """Apply a partial update to a menu."""

        menu = await self._require(menu_id)
        changes = data.model_dump(exclude_unset=True)

        if "parent_id" in changes:
            if changes["parent_id"] == menu_id:
                raise AppException(
                    "Una actividad no puede ser su propio elemento padre.",
                    code="invalid_parent",
                    status_code=422,
                )
            await self._verify_parent(changes["parent_id"])

        for field in ("name", "icon", "path", "parent_id", "order", "is_active"):
            if field in changes:
                setattr(menu, field, changes[field])
        menu.updated_by = actor_id
        return await self.repo.save(menu)

    async def delete_menu(self, menu_id: uuid.UUID) -> None:
        """Soft-delete a menu."""

        menu = await self._require(menu_id)
        menu.is_active = False
        menu.deleted_at = datetime.now(UTC)
        await self.repo.save(menu)

    async def _require(self, menu_id: uuid.UUID) -> Menu:
        menu = await self.repo.get(menu_id)
        if menu is None:
            raise AppException(
                "La actividad no existe.",
                code="menu_not_found",
                status_code=404,
            )
        return menu

    async def _verify_parent(self, parent_id: uuid.UUID | None) -> None:
        if parent_id is None:
            return
        if await self.repo.get(parent_id) is None:
            raise AppException(
                "La actividad padre indicada no existe.",
                code="invalid_parent",
                status_code=422,
            )
