"""Per-organization theme routes (feat/org-theme).

``GET`` is open to any authenticated member — the UI needs the theme at
session bootstrap. ``PUT``/``DELETE`` require the RBAC ``ADMIN`` role
(``require_admin``), same gate as the admin pages that host the editor.
The tenant is ALWAYS the organization of the caller's JWT membership; there
is deliberately no ``/{organization_id}/theme`` variant, so cross-tenant
access is impossible by construction. Responses use the ``{data}`` envelope.
"""

import uuid

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_actor_id,
    get_current_membership,
    get_current_user,
    require_admin,
    require_org_admin,
)
from app.modules.organizations.models import OrganizationMember
from app.modules.organizations.schemas import (
    MemberCreate,
    MemberUpdateRole,
    OrganizationCreate,
    OrganizationUpdate,
)
from app.modules.organizations.service import (
    OrganizationMemberService,
    OrganizationService,
    OrganizationThemeService,
)
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


# ---------------------------------------------------------------------------
# CRUD de empresas (organizations-admin R1/R2) + "mis empresas" (R5)
# ---------------------------------------------------------------------------
#
# Ordering matters: ``/mine`` MUST be registered before ``/{organization_id}``
# so FastAPI never tries to parse "mine" as a UUID path parameter.


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bootstrap a new organization; the creator becomes its sole ``admin``.

    Any authenticated user may call this — there is no global superadmin
    (design.md Decision 4). Rejects a duplicate ``slug`` with ``409``.
    """

    service = OrganizationService(db)
    data = await service.create_bootstrap(
        payload, creator_id=user.id, actor_id=actor_id
    )
    return {"data": data}


@router.get("/mine")
async def list_my_organizations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List every organization the caller belongs to, with their role in each."""

    service = OrganizationService(db)
    data = await service.list_mine(user.id)
    return {"data": data}


@router.get("/{organization_id}")
async def get_organization(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return an organization — any member may read it, ``404`` otherwise."""

    service = OrganizationService(db)
    data = await service.get(organization_id, user.id)
    return {"data": data}


@router.patch("/{organization_id}")
async def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    membership: OrganizationMember = Depends(require_org_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply a partial update — only an ``admin`` of THIS organization."""

    service = OrganizationService(db)
    data = await service.update(organization_id, payload, actor_id=actor_id)
    return {"data": data}


@router.delete("/{organization_id}")
async def delete_organization(
    organization_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_org_admin),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete the organization — only an ``admin`` of THIS organization."""

    service = OrganizationService(db)
    await service.soft_delete(organization_id, actor_id=actor_id)
    return {"data": None, "message": "Empresa eliminada."}


# ---------------------------------------------------------------------------
# Gestión de miembros (organizations-admin R2/R3)
# ---------------------------------------------------------------------------


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List members with their role — any member of the organization may read."""

    service = OrganizationMemberService(db)
    data = await service.list_members(organization_id, user.id)
    return {"data": data}


@router.post("/{organization_id}/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    organization_id: uuid.UUID,
    payload: MemberCreate,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add an EXISTING user (found by email) as a member — admin only."""

    service = OrganizationMemberService(db)
    data = await service.add_member(organization_id, payload)
    return {"data": data}


@router.patch("/{organization_id}/members/{member_id}")
async def update_member_role(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: MemberUpdateRole,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change a member's role — rejects leaving the empresa without an admin."""

    service = OrganizationMemberService(db)
    data = await service.update_role(organization_id, member_id, payload.role)
    return {"data": data}


@router.delete("/{organization_id}/members/{member_id}")
async def remove_member(
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a member — rejects leaving the empresa without an admin."""

    service = OrganizationMemberService(db)
    await service.remove_member(organization_id, member_id)
    return {"data": None, "message": "Miembro eliminado."}
