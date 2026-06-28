"""Menu ("actividad") ORM model.

App-level activities the RBAC roles grant access to. Menus are global (not
org-scoped) and hierarchical via a self-referencing ``parent_id``.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin, SoftDeleteMixin, TimestampMixin


class Menu(PkMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A navigable application activity, optionally nested under a parent."""

    __tablename__ = "menus"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("menus.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Display order within a level. Mapped to a non-reserved column name to stay
    # clear of the SQL ``ORDER`` keyword.
    order: Mapped[int] = mapped_column(
        "menu_order", Integer, default=0, nullable=False
    )
