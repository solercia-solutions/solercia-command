"""Menu (activity) admin routes.

Menus are global application activities; managing them requires an
administrator (``require_admin``). Responses use the ``{data, meta}`` envelope;
the flat list lives in ``data`` (each item carries ``parent_id``) and the
nested tree is provided in ``meta.tree``.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, require_admin
from app.modules.menus.schemas import (
    MenuCreate,
    MenuNode,
    MenuRead,
    MenuUpdate,
)
from app.modules.menus.service import MenuService
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(
    prefix="/admin/menus",
    tags=["admin: menus"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
async def list_menus(
    pagination: PaginationParams = Depends(pagination_params),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the flat menu list (with ``parent_id``) and the nested tree.

    ``data`` supports opt-in pagination; ``meta.tree`` always reflects the
    FULL active catalog regardless of any ``page``/``size`` slice (gate #1).
    """

    service = MenuService(db)
    menus, total = await service.list_menus(pagination)
    data = [MenuRead.model_validate(menu) for menu in menus]
    tree = [MenuNode.model_validate(node) for node in await service.tree()]
    meta = build_list_meta(pagination, total, base={"tree": tree})
    return {"data": data, "meta": meta}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_menu(
    payload: MenuCreate,
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a menu (activity)."""

    service = MenuService(db)
    menu = await service.create_menu(payload, actor_id=actor_id)
    return {"data": MenuRead.model_validate(menu)}


@router.get("/{menu_id}")
async def get_menu(
    menu_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a single menu."""

    service = MenuService(db)
    menu = await service.get_menu(menu_id)
    return {"data": MenuRead.model_validate(menu)}


@router.patch("/{menu_id}")
async def update_menu(
    menu_id: uuid.UUID,
    payload: MenuUpdate,
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a menu."""

    service = MenuService(db)
    menu = await service.update_menu(menu_id, payload, actor_id=actor_id)
    return {"data": MenuRead.model_validate(menu)}


@router.delete("/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu(
    menu_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a menu."""

    service = MenuService(db)
    await service.delete_menu(menu_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
