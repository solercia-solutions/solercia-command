"""Per-organization theme routes (feat/org-theme).

``GET`` is open to any authenticated member — the UI needs the theme at
session bootstrap. ``PUT``/``DELETE`` require the RBAC ``ADMIN`` role
(``require_admin``), same gate as the admin pages that host the editor.
The tenant is ALWAYS the organization of the caller's JWT membership; there
is deliberately no ``/{organization_id}/theme`` variant, so cross-tenant
access is impossible by construction. Responses use the ``{data}`` envelope.
"""

import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_admin
from app.modules.organizations.models import OrganizationMember
from app.modules.organizations.service import OrganizationThemeService
from app.modules.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/me/theme")
async def get_my_organization_theme(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the ThemeFile of the caller's organization (``null`` = default).

    Any authenticated member may read it: the frontend applies it during
    session hydration, before any role is known.
    """

    service = OrganizationThemeService(db)
    theme = await service.get_theme(membership.organization_id)
    return {"data": theme}


@router.put("/me/theme")
async def put_my_organization_theme(
    payload: dict = Body(...),
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Store the ThemeFile for the caller's organization (RBAC ``ADMIN`` only).

    The body must be a JSON object (the ThemeFile) — any other JSON value
    (list, string, number) is rejected with **422** by validation. The stored
    object is returned as-is and ``organizations.updated_by`` is sealed with
    the actor. Non-admins get **403** (``forbidden``).
    """

    service = OrganizationThemeService(db)
    saved = await service.set_theme(
        membership.organization_id, payload, actor_id=actor_id
    )
    return {"data": saved, "message": "Tema de la organización actualizado."}


@router.delete("/me/theme")
async def delete_my_organization_theme(
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset the organization's theme to the default (RBAC ``ADMIN`` only).

    Sets the stored ThemeFile back to ``null`` so every client falls back to
    the bundled default theme. Non-admins get **403** (``forbidden``).
    """

    service = OrganizationThemeService(db)
    await service.reset_theme(membership.organization_id, actor_id=actor_id)
    return {"data": None, "message": "Tema de la organización restablecido."}
