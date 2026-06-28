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
from app.dependencies import require_admin
from app.modules.menus.schemas import (
    MenuCreate,
    MenuNode,
    MenuRead,
    MenuUpdate,
)
from app.modules.menus.service import MenuService, build_menu_tree

router = APIRouter(
    prefix="/admin/menus",
    tags=["admin: menus"],
    dependencies=[Depends(require_admin)],
)


@router.get("")
async def list_menus(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the flat menu list (with ``parent_id``) and the nested tree."""

    service = MenuService(db)
    menus = await service.list_menus()
    data = [MenuRead.model_validate(menu) for menu in menus]
    tree = [MenuNode.model_validate(node) for node in build_menu_tree(menus)]
    return {"data": data, "meta": {"total": len(data), "tree": tree}}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_menu(
    payload: MenuCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a menu (activity)."""

    service = MenuService(db)
    menu = await service.create_menu(payload)
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update to a menu."""

    service = MenuService(db)
    menu = await service.update_menu(menu_id, payload)
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
