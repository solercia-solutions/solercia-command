"""User ORM model."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Uuid, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    # Import-time cycle guard: roles.models imports users only under
    # TYPE_CHECKING too, so this stays a type-only reference.
    from app.modules.roles.models import Role


class User(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """An authenticatable user.

    ``is_active`` is provided by :class:`SoftDeleteMixin` and doubles as the
    account-enabled flag. The display name is split into the four Colombian
    name parts; :attr:`full_name` recomposes the common short form.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    primer_nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    segundo_nombre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primer_apellido: Mapped[str] = mapped_column(String(120), nullable=False)
    segundo_apellido: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    dependency_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("dependencies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Read-only view of the user's RBAC roles, resolved through user_roles.
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        lazy="selectin",
        viewonly=True,
        order_by="Role.name",
    )

    @hybrid_property
    def full_name(self) -> str:
        """Short display name: ``primer_nombre`` + ``primer_apellido``.

        Blank parts are skipped so a partially filled name never produces
        stray whitespace. This preserves every existing ``user.full_name``
        read site after the name column was split.
        """

        parts = [self.primer_nombre, self.primer_apellido]
        return " ".join(part for part in parts if part)

    @full_name.expression  # type: ignore[no-redef]
    def full_name(cls):  # noqa: N805 - hybrid expression receives the class
        """SQL form so ``User.full_name`` is usable in ``order_by`` clauses."""

        return func.trim(
            func.concat(
                func.coalesce(cls.primer_nombre, ""),
                " ",
                func.coalesce(cls.primer_apellido, ""),
            )
        )
