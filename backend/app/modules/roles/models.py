"""Role ORM model plus the user_roles and role_menus association tables.

A Role is an org-scoped RBAC bundle. ``code`` is unique per organization. Roles
grant access to menus (role_menus) and are assigned to users (user_roles). Both
association tables carry their own surrogate id and a uniqueness constraint to
prevent duplicate links.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class Role(PkMixin, TenantMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An org-scoped RBAC role (e.g. ADMIN, MANAGER, MEMBER)."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_roles_org_code"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class UserRole(PkMixin, TimestampMixin, Base):
    """Association between a user and a role."""

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class RoleMenu(PkMixin, TimestampMixin, Base):
    """Association between a role and a menu it grants access to."""

    __tablename__ = "role_menus"
    __table_args__ = (
        UniqueConstraint("role_id", "menu_id", name="uq_role_menus_role_menu"),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    menu_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("menus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
