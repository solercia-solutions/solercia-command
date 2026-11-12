"""Per-organization theme routes (feat/org-theme).

``GET`` is open to any authenticated member — the UI needs the theme at
session bootstrap. ``PUT``/``DELETE`` and the version history require the RBAC
``ADMIN`` role (``require_admin``), same gate as the admin pages that host the
editor. The tenant is ALWAYS the organization of the caller's JWT membership;
there is deliberately no ``/{organization_id}/theme`` variant, so cross-tenant
access is impossible by construction. Responses use the ``{data}`` envelope.
The history is read-only over HTTP: its entries are only ever added, as a side
effect of applying or resetting the theme.
"""

import uuid

from fastapi import APIRouter, Body, Depends, Path, Query, status
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
from app.modules.organizations.theme_repository import SessionThemeTransaction
from app.modules.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


#: Largest id a ``BIGINT`` version key can hold (query/path validation bound).
_MAX_VERSION_ID = 2**63 - 1


def get_theme_service(
    db: AsyncSession = Depends(get_db),
) -> OrganizationThemeService:
    """Bind the theme use cases to the request session."""

    return OrganizationThemeService(SessionThemeTransaction(db))


@router.get("/me/theme")
async def get_my_organization_theme(
    membership: OrganizationMember = Depends(get_current_membership),
    service: OrganizationThemeService = Depends(get_theme_service),
) -> dict:
    """Return the ThemeFile of the caller's organization (``null`` = default).

    Any authenticated member may read it: the frontend applies it during
    session hydration, before any role is known.
    """

    theme = await service.get_theme(membership.organization_id)
    return {"data": theme}


@router.put("/me/theme")
async def put_my_organization_theme(
    payload: dict = Body(...),
    source_version_id: int | None = Query(default=None, ge=1, le=_MAX_VERSION_ID),
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    service: OrganizationThemeService = Depends(get_theme_service),
) -> dict:
    """Store the ThemeFile for the caller's organization (RBAC ``ADMIN`` only).

    The body must be a JSON object (the ThemeFile) — any other JSON value
    (list, string, number) is rejected with **422** by validation. The stored
    object is returned as-is in ``data`` and ``organizations.updated_by`` is
    sealed with the actor. Non-admins get **403** (``forbidden``).

    Every apply is recorded in the theme history in the same transaction;
    ``meta.version`` describes the new entry. When restoring, pass the
    restored version as ``source_version_id``: it must belong to this
    organization, otherwise **422** (``theme_source_version_invalid``). A
    theme stored before the history existed is recorded first as the initial
    capture.
    """

    applied = await service.set_theme(
        membership.organization_id,
        payload,
        actor_id=actor_id,
        actor_name=admin.full_name,
        source_version_id=source_version_id,
    )
    return {
        "data": applied.theme,
        "message": "Tema de la organización actualizado.",
        "meta": {"version": applied.version},
    }


@router.delete("/me/theme")
async def delete_my_organization_theme(
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    service: OrganizationThemeService = Depends(get_theme_service),
) -> dict:
    """Reset the organization's theme to the default (RBAC ``ADMIN`` only).

    Sets the stored ThemeFile back to ``null`` so every client falls back to
    the bundled default theme. The theme history is kept, so any recorded
    version can still be restored. Non-admins get **403** (``forbidden``).
    """

    await service.reset_theme(membership.organization_id, actor_id=actor_id)
    return {"data": None, "message": "Tema de la organización restablecido."}


@router.get("/me/theme/versions")
async def list_my_organization_theme_versions(
    before: int | None = Query(default=None, ge=1, le=_MAX_VERSION_ID),
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    service: OrganizationThemeService = Depends(get_theme_service),
) -> dict:
    """List the theme history of the caller's organization (RBAC ``ADMIN`` only).

    Pages of 20, newest first. ``data.next`` is the cursor to send as
    ``before`` for the next page, or ``null`` when there are no older
    versions. The ThemeFile of each entry is served by the detail route.
    """

    page = await service.list_versions(membership.organization_id, before=before)
    return {"data": page}


@router.get("/me/theme/versions/{version_id}")
async def get_my_organization_theme_version(
    version_id: int = Path(ge=1, le=_MAX_VERSION_ID),
    admin: User = Depends(require_admin),
    membership: OrganizationMember = Depends(get_current_membership),
    service: OrganizationThemeService = Depends(get_theme_service),
) -> dict:
    """Return one history entry with its ThemeFile (RBAC ``ADMIN`` only).

    **404** (``theme_version_not_found``) for an unknown id and for a version
    of another organization alike.
    """

    version = await service.get_version(membership.organization_id, version_id)
    return {"data": version}


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
