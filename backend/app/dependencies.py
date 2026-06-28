"""Shared FastAPI dependencies for authentication and tenant scoping."""

import uuid

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.menus.repository import MenuRepository
from app.modules.menus.service import build_menu_tree
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.models import Role, UserRole
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import User
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException
from app.shared.security import ACCESS_TOKEN_TYPE, decode_token

# RBAC code that grants administrator privileges.
ADMIN_ROLE_CODE = "ADMIN"


def _extract_bearer_token(request: Request) -> str:
    """Read and validate the ``Authorization: Bearer <token>`` header."""

    header = request.headers.get("Authorization")
    if not header or not header.lower().startswith("bearer "):
        raise AppException(
            "No has iniciado sesión. Inicia sesión para continuar.",
            code="not_authenticated",
            status_code=401,
        )
    return header.split(" ", 1)[1].strip()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer (access) token."""

    token = _extract_bearer_token(request)

    try:
        payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except Exception as exc:  # noqa: BLE001 - any JWT error maps to 401
        raise AppException(
            "Tu sesión no es válida o ha expirado. Inicia sesión nuevamente.",
            code="invalid_token",
            status_code=401,
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise AppException(
            "Tu sesión no es válida. Inicia sesión nuevamente.",
            code="invalid_token",
            status_code=401,
        )

    try:
        user_id = uuid.UUID(str(subject))
    except ValueError as exc:
        raise AppException(
            "Tu sesión no es válida. Inicia sesión nuevamente.",
            code="invalid_token",
            status_code=401,
        ) from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AppException(
            "El usuario no existe o está inactivo.",
            code="user_not_found",
            status_code=401,
        )
    return user


async def get_current_membership(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OrganizationMember:
    """Return the user's first organization membership (current tenant scope)."""

    result = await db.execute(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at.asc())
    )
    membership = result.scalars().first()
    if membership is None:
        raise AppException(
            "No perteneces a ninguna organización.",
            code="no_membership",
            status_code=403,
        )
    return membership


def require_role(*roles: MemberRole):
    """Build a dependency that enforces the membership role is one of ``roles``."""

    async def _checker(
        membership: OrganizationMember = Depends(get_current_membership),
    ) -> OrganizationMember:
        if membership.role not in roles:
            raise AppException(
                "No tienes permisos suficientes para realizar esta acción.",
                code="forbidden",
                status_code=403,
            )
        return membership

    return _checker


async def _has_admin_role(
    db: AsyncSession, user_id: uuid.UUID, organization_id: uuid.UUID
) -> bool:
    """Return whether the user holds the ADMIN RBAC role in the organization."""

    result = await db.execute(
        select(Role.id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Role.organization_id == organization_id,
            Role.code == ADMIN_ROLE_CODE,
            Role.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none() is not None


async def require_admin(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_current_membership),
) -> User:
    """Allow only callers holding the ADMIN role in their current organization."""

    if not await _has_admin_role(db, user.id, membership.organization_id):
        raise AppException(
            "No tienes permisos de administrador para realizar esta acción.",
            code="forbidden",
            status_code=403,
        )
    return user


async def load_accessible_menus(
    db: AsyncSession, user: User, organization_id: uuid.UUID
) -> list[dict]:
    """Return the nested menu tree the user can access in an organization.

    Administrators see every active menu; everyone else sees the distinct menus
    granted by their roles via ``role_menus``.
    """

    menu_repo = MenuRepository(db)
    if await _has_admin_role(db, user.id, organization_id):
        menus = await menu_repo.list_active()
    else:
        role_ids = await RoleRepository(db).role_ids_for_user(
            user.id, organization_id
        )
        menus = await menu_repo.list_for_roles(role_ids)
    return build_menu_tree(menus)
