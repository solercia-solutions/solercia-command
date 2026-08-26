"""Sole SQLAlchemy adapter for the maintenance package (design.md D1).

The ONE place that knows the FK graph. No method here ever calls
``commit()``/``rollback()`` — the caller owns the transaction. Tables
removed for free by ``ON DELETE CASCADE`` (verified against every model in
``app/modules/*/models.py``) get NO explicit method: task children cascade
from ``tasks.id``; sprints/boards/labels cascade from ``projects.id``;
instantiations/connected_accounts/asset_licenses/membership rows cascade
from their parent. Only tables WITHOUT a cascading FK (``attachments``,
``notifications`` by ``target_id``, ``notification_deliveries``,
``reminders``) get an explicit delete.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Integer, cast, delete, func, literal, select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select
from sqlalchemy.sql.selectable import CompoundSelect

from app.maintenance.report import ConnectedAccountRisk, InventoryRow
from app.maintenance.scope import DemoScope
from app.modules.assets.models import Asset
from app.modules.attachments.models import Attachment
from app.modules.boards.models import Board, BoardColumn
from app.modules.comments.models import TaskComment
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.intake.models import IntakeSettings
from app.modules.notifications.models import Notification
from app.modules.org_role_templates.models import OrgRoleTemplateInstantiation
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.reminders.models import Reminder
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.notify.models import NotificationDelivery


@dataclass(frozen=True)
class ResolvedScope:
    """Concrete row ids matching one ``DemoScope``, resolved once up front.
    ``project_ids`` is ordered LEAF-FIRST (design.md D4) — every descendant
    sorts before its own ancestor."""

    organization_ids: tuple[uuid.UUID, ...]
    user_ids: tuple[uuid.UUID, ...]
    project_ids: tuple[uuid.UUID, ...]
    task_ids: tuple[uuid.UUID, ...]
    comment_ids: tuple[uuid.UUID, ...]
    connector_ids: tuple[uuid.UUID, ...]
    asset_ids: tuple[uuid.UUID, ...]


class MaintenanceRepository:
    """Async adapter encapsulating every maintenance-package query."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _scalars(self, stmt: Select) -> tuple[uuid.UUID, ...]:
        result = await self.db.execute(stmt)
        return tuple(result.scalars().all())

    async def _delete_by_ids(self, model: type, column, ids: Sequence[uuid.UUID]) -> int:
        """Shared body for every simple "delete rows whose ``column`` is in
        ``ids``" method below — ``synchronize_session=False`` since every
        assertion in this package re-queries instead of trusting the ORM
        identity map (test_purge_demo_data.py's ``_exists`` helper)."""

        if not ids:
            return 0
        result = await self.db.execute(
            delete(model).where(column.in_(ids)).execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    # -- scope resolution ----------------------------------------------

    async def resolve_demo_scope(self, scope: DemoScope) -> ResolvedScope:
        """Resolve ``scope`` into concrete row ids, closed under the full
        project subtree (design.md D3)."""

        organization_ids = await self._scalars(
            select(Organization.id).where(Organization.name.in_(scope.organization_names))
        )
        user_ids = await self._scalars(select(User.id).where(User.email.in_(scope.user_emails)))

        project_seed_parts: list[Select] = [
            select(Project.id).where(Project.name.in_(scope.project_names))
        ]
        if organization_ids:
            project_seed_parts.append(
                select(Project.id).where(Project.organization_id.in_(organization_ids))
            )
        if scope.include_template_instantiations and organization_ids:
            project_seed_parts.append(
                select(OrgRoleTemplateInstantiation.project_id).where(
                    OrgRoleTemplateInstantiation.organization_id.in_(organization_ids)
                )
            )
        seed_projects: Select | CompoundSelect = (
            union(*project_seed_parts) if len(project_seed_parts) > 1 else project_seed_parts[0]
        )

        project_ids = await self._project_ids_leaf_first(seed_projects)

        task_ids = (
            await self._scalars(select(Task.id).where(Task.project_id.in_(project_ids)))
            if project_ids
            else ()
        )
        comment_ids = (
            await self._scalars(select(TaskComment.id).where(TaskComment.task_id.in_(task_ids)))
            if task_ids
            else ()
        )
        connector_ids = await self._scalars(
            select(Connector.id).where(Connector.provider.in_(scope.connector_providers))
        )
        asset_ids = await self._scalars(select(Asset.id).where(Asset.name.in_(scope.asset_names)))

        return ResolvedScope(
            organization_ids=organization_ids,
            user_ids=user_ids,
            project_ids=project_ids,
            task_ids=task_ids,
            comment_ids=comment_ids,
            connector_ids=connector_ids,
            asset_ids=asset_ids,
        )

    async def _project_ids_leaf_first(
        self, seed_projects: Select | CompoundSelect
    ) -> tuple[uuid.UUID, ...]:
        """Recursive CTE over ``parent_project_id`` (``SET NULL``, never
        cascades), same pattern as ``ProjectRepository._subtree_ids_select``
        minus tenant/``is_active`` filters — catches a soft-deleted demo
        project too (design.md D3, "activos y con borrado suave")."""

        base = select(Project.id, cast(literal(0), Integer).label("depth")).where(
            Project.id.in_(seed_projects)
        )
        subtree = base.cte(name="demo_project_subtree", recursive=True)
        child = aliased(Project)
        recursive_step = select(child.id, (subtree.c.depth + 1).label("depth")).join(
            subtree, child.parent_project_id == subtree.c.id
        )
        subtree = subtree.union_all(recursive_step)

        result = await self.db.execute(
            select(subtree.c.id, func.max(subtree.c.depth).label("depth"))
            .group_by(subtree.c.id)
            .order_by(func.max(subtree.c.depth).desc())
        )
        return tuple(row.id for row in result.all())

    async def find_connected_accounts_owned_by(
        self, user_ids: Sequence[uuid.UUID]
    ) -> tuple[ConnectedAccountRisk, ...]:
        """Fail-closed guard input: every account owned by ``user_ids``."""

        if not user_ids:
            return ()
        stmt = (
            select(Connector.provider, ConnectedAccount.display_name, User.email)
            .select_from(ConnectedAccount)
            .join(Connector, Connector.id == ConnectedAccount.connector_id)
            .join(User, User.id == ConnectedAccount.user_id)
            .where(ConnectedAccount.user_id.in_(user_ids))
        )
        result = await self.db.execute(stmt)
        return tuple(
            ConnectedAccountRisk(
                provider=row.provider, display_name=row.display_name, owner_email=row.email
            )
            for row in result.all()
        )

    async def count_inventory(self, resolved: ResolvedScope) -> tuple[InventoryRow, ...]:
        """Row counts about to be affected — resolved once, before any
        ``DELETE`` (design.md D8)."""

        return (
            InventoryRow("organizations", len(resolved.organization_ids), 0),
            InventoryRow("users", len(resolved.user_ids), 0),
            InventoryRow("projects", len(resolved.project_ids), 0),
            InventoryRow("tasks", len(resolved.task_ids), 0),
            InventoryRow("connectors", len(resolved.connector_ids), 0),
            InventoryRow("assets", len(resolved.asset_ids), 0),
        )

    # -- deletion, in design.md D4 order --------------------------------

    async def delete_attachments_for_targets(self, target_ids: Sequence[uuid.UUID]) -> int:
        """``attachments.target_id`` carries no FK — matched explicitly by
        id, covers both ``target_type in {task, comment}``."""

        return await self._delete_by_ids(Attachment, Attachment.target_id, target_ids)

    async def delete_notifications_for_tasks(self, task_ids: Sequence[uuid.UUID]) -> int:
        """``notifications.target_id`` has no FK either; deliveries go first
        (``notification_id`` is ``SET NULL`` — deleting the notification
        first would just orphan the delivery)."""

        if not task_ids:
            return 0
        notification_ids = await self._scalars(
            select(Notification.id).where(Notification.target_id.in_(task_ids))
        )
        if not notification_ids:
            return 0
        await self.db.execute(
            delete(NotificationDelivery)
            .where(NotificationDelivery.notification_id.in_(notification_ids))
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(
            delete(Notification)
            .where(Notification.id.in_(notification_ids))
            .execution_options(synchronize_session=False)
        )
        return result.rowcount or 0

    async def delete_reminders_for_tasks(self, task_ids: Sequence[uuid.UUID]) -> int:
        """``reminders.task_id`` is ``SET NULL`` — deleting the task alone
        would orphan the reminder instead of removing it."""

        return await self._delete_by_ids(Reminder, Reminder.task_id, task_ids)

    async def delete_tasks(self, task_ids: Sequence[uuid.UUID]) -> int:
        """Cascades checklists/logs/comments/dependencies/labels/asset_tasks."""

        return await self._delete_by_ids(Task, Task.id, task_ids)

    async def delete_projects_leaf_first(self, ordered_project_ids: Sequence[uuid.UUID]) -> int:
        """One statement for the whole ordered id set — safe regardless of
        order since every id deletes together. Cascades sprints/boards/
        columns/labels/instantiations."""

        return await self._delete_by_ids(Project, Project.id, ordered_project_ids)

    async def delete_fake_connectors(self, connector_ids: Sequence[uuid.UUID]) -> int:
        """Cascades connected_accounts + connection_credentials."""

        return await self._delete_by_ids(Connector, Connector.id, connector_ids)

    async def delete_demo_assets(self, asset_ids: Sequence[uuid.UUID]) -> int:
        """Cascades asset_licenses + asset_tasks."""

        return await self._delete_by_ids(Asset, Asset.id, asset_ids)

    async def delete_demo_users(self, user_ids: Sequence[uuid.UUID]) -> int:
        """Cascades membership/roles/connected_accounts/notifications."""

        return await self._delete_by_ids(User, User.id, user_ids)

    async def delete_demo_organizations(self, organization_ids: Sequence[uuid.UUID]) -> int:
        """Run LAST — cascades every remaining tenant-scoped row."""

        return await self._delete_by_ids(Organization, Organization.id, organization_ids)

    # -- protected identity lookups (D2, runner.py resolves bootstrap args) --

    async def find_organization_id_by_name(self, name: str) -> uuid.UUID | None:
        """Resolve e.g. ``scope.protected_organization_names[0]`` to an id."""

        result = await self.db.execute(select(Organization.id).where(Organization.name == name))
        return result.scalar_one_or_none()

    async def find_user_id_by_email(self, email: str) -> uuid.UUID | None:
        """Resolve e.g. ``scope.protected_admin_email`` to an id."""

        result = await self.db.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none()

    # -- bootstrap (design.md D6) ----------------------------------------

    async def find_project_by_code(self, organization_id: uuid.UUID, code: str) -> Project | None:
        """Reuse point for idempotent bootstrap — one project per ``code``
        within ``organization_id`` (``uq_project_code_per_org``)."""

        result = await self.db.execute(
            select(Project).where(
                Project.organization_id == organization_id,
                Project.code == code,
                Project.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def ensure_board_columns(self, board_id: uuid.UUID, columns: Sequence[str]) -> int:
        """Add every missing column of ``columns`` (in order) to ``board_id``
        and fix the ``order`` of any that already exist but drifted.

        ``status_key`` is the column name VERBATIM — never slugified, in
        contrast to ``BoardService.add_column`` (design.md D6). Returns how
        many NEW columns were inserted (``0`` on the idempotent re-run).
        """

        result = await self.db.execute(
            select(BoardColumn).where(
                BoardColumn.board_id == board_id, BoardColumn.is_active.is_(True)
            )
        )
        existing = {column.status_key: column for column in result.scalars().all()}

        inserted = 0
        for order, name in enumerate(columns):
            column = existing.get(name)
            if column is None:
                self.db.add(
                    BoardColumn(board_id=board_id, name=name, status_key=name, order=order)
                )
                inserted += 1
            elif column.order != order:
                column.order = order
        await self.db.flush()
        return inserted

    async def upsert_intake_default_project(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> None:
        """Point ``intake_settings.default_project_id`` at ``project_id`` —
        direct ORM upsert, NEVER ``IntakeSettingsRepository.get_or_create``
        (it commits, ``intake/repository.py:265``, design.md D6)."""

        result = await self.db.execute(
            select(IntakeSettings).where(IntakeSettings.organization_id == organization_id)
        )
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            self.db.add(
                IntakeSettings(organization_id=organization_id, default_project_id=project_id)
            )
        elif settings_row.default_project_id != project_id:
            settings_row.default_project_id = project_id
        await self.db.flush()

    async def find_board_id_for_project(self, project_id: uuid.UUID) -> uuid.UUID | None:
        """Resolved here (not via ``BoardRepository``) so ``bootstrap.py``
        never imports it directly — D1, single adapter."""

        result = await self.db.execute(
            select(Board.id).where(Board.project_id == project_id, Board.is_active.is_(True))
        )
        return result.scalar_one_or_none()
