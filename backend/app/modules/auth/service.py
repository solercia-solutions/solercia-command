"""Authentication business logic."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.schemas import RoleBrief, UserRead
from app.modules.organizations.models import OrganizationMember
from app.modules.roles.repository import RoleRepository
from app.modules.users.models import User
from app.shared.security import verify_password


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Return the user when credentials are valid, otherwise ``None``."""

    normalized_email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def primary_organization_id(
    db: AsyncSession, user: User
) -> uuid.UUID | None:
    """Return the user's first (current) organization id, or ``None``."""

    result = await db.execute(
        select(OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id)
        .order_by(OrganizationMember.created_at.asc())
    )
    return result.scalars().first()


async def build_user_read(
    db: AsyncSession,
    user: User,
    organization_id: uuid.UUID | None = None,
) -> UserRead:
    """Assemble the ``UserRead`` payload with the user's roles for an org.

    When ``organization_id`` is not given it is resolved from the user's
    primary membership. Roles are scoped to that organization.
    """

    if organization_id is None:
        organization_id = await primary_organization_id(db, user)

    roles: list[RoleBrief] = []
    if organization_id is not None:
        role_rows = await RoleRepository(db).roles_for_user(
            user.id, organization_id
        )
        roles = [RoleBrief.model_validate(role) for role in role_rows]

    return UserRead(
        id=user.id,
        email=user.email,
        primer_nombre=user.primer_nombre,
        segundo_nombre=user.segundo_nombre,
        primer_apellido=user.primer_apellido,
        segundo_apellido=user.segundo_apellido,
        full_name=user.full_name,
        dependency_id=user.dependency_id,
        is_active=user.is_active,
        created_at=user.created_at,
        roles=roles,
        created_by=user.created_by,
        updated_by=user.updated_by,
    )
