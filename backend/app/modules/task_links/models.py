"""TaskDependency ORM model.

Models a directed "blocks" edge between two tasks of the same project:
``blocker_task_id`` blocks ``blocked_task_id``. There is only ever ONE row
per ordered pair — ``is_blocked_by`` is the inverse VIEW of the same edge,
never a second row (design.md, "Decisión: Arista dirigida canónica").

Deliberately named ``task_links`` (module) / ``task_dependencies`` (table) /
``TaskDependency`` (class) to avoid any collision with
``app.modules.dependencies`` (organizational areas, table ``dependencies``,
class ``Dependency`` — an unrelated RBAC/admin concept).
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import PkMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class TaskDependency(PkMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """A directed 'blocks' edge: ``blocker_task_id`` blocks ``blocked_task_id``.

    No ``AuditMixin`` (design.md, "Decisión: Modelo de datos" — deliberately
    excluded from this entity's mixin set, unlike ``Label``/``TaskChecklist``/
    ``ChecklistItem``). Unlinking sets ``is_active=False`` — NEVER a physical
    ``DELETE`` (design.md gate correction #1, CRITICAL): the cycle-detection
    DFS and the ``is_blocked`` computation both filter ``is_active == true``.
    """

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "blocker_task_id", "blocked_task_id", name="uq_task_dependencies_edge"
        ),
    )

    blocker_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blocked_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
