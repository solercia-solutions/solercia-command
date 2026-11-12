"""Persistence adapter for the Jira organization feed.

Semantic, tenant-scoped methods only; every write is ``add`` + ``flush`` and
NEVER a commit — :mod:`app.modules.jira_import.apply` owns the single
transaction (solercia-persistence: repositories never complete transactions).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import FederatedIdentity
from app.modules.boards.models import Board, BoardColumn
from app.modules.connectors.models import ConnectedAccount, Connector
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.roles.models import Role, UserRole
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.modules.users.models import User

JIRA_SOURCE = "jira"
JIRA_IDENTITY_PROVIDER = "jira"


class JiraFeedRepository:
    """Reads/writes for one organization feed inside the caller's session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def flush(self) -> None:
        await self.db.flush()

    # ---------------------------------------------------------------- organization

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        result = await self.db.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def jira_account_links(self, organization_id: uuid.UUID) -> dict[str, uuid.UUID]:
        """``{jira accountId: user_id}`` from the org's connected Jira accounts
        (``external_account_id`` is ``jira-<accountId>``)."""

        result = await self.db.execute(
            select(ConnectedAccount.external_account_id, ConnectedAccount.user_id)
            .join(Connector, Connector.id == ConnectedAccount.connector_id)
            .where(
                Connector.organization_id == organization_id,
                Connector.provider == JIRA_SOURCE,
                ConnectedAccount.is_active.is_(True),
            )
        )
        links: dict[str, uuid.UUID] = {}
        for external_id, user_id in result.all():
            if external_id and external_id.startswith("jira-"):
                links[external_id.removeprefix("jira-")] = user_id
        return links

    async def role_by_code(self, organization_id: uuid.UUID, code: str) -> Role | None:
        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.code == code,
                Role.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    # ---------------------------------------------------------------- users

    async def identities_by_subject(self, issuer: str) -> dict[str, uuid.UUID]:
        result = await self.db.execute(
            select(FederatedIdentity.subject, FederatedIdentity.user_id).where(
                FederatedIdentity.issuer == issuer,
                FederatedIdentity.is_active.is_(True),
            )
        )
        return dict(result.tuples().all())

    async def users_by_emails(self, emails: Sequence[str]) -> dict[str, User]:
        if not emails:
            return {}
        result = await self.db.execute(select(User).where(User.email.in_(list(emails))))
        return {user.email.lower(): user for user in result.scalars()}

    async def add_user(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user

    async def add_identity(self, identity: FederatedIdentity) -> None:
        self.db.add(identity)

    async def memberships(self, organization_id: uuid.UUID) -> dict[uuid.UUID, OrganizationMember]:
        result = await self.db.execute(
            select(OrganizationMember).where(OrganizationMember.organization_id == organization_id)
        )
        return {member.user_id: member for member in result.scalars()}

    async def add_membership(self, membership: OrganizationMember) -> None:
        self.db.add(membership)

    async def users_with_org_role(self, organization_id: uuid.UUID) -> set[uuid.UUID]:
        """Users holding ANY active RBAC role of this organization."""

        result = await self.db.execute(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.organization_id == organization_id, Role.is_active.is_(True))
        )
        return set(result.scalars())

    async def add_user_role(self, user_role: UserRole) -> None:
        self.db.add(user_role)

    # ---------------------------------------------------------------- projects

    async def project_by_code(self, organization_id: uuid.UUID, code: str) -> Project | None:
        result = await self.db.execute(
            select(Project).where(Project.organization_id == organization_id, Project.code == code)
        )
        return result.scalar_one_or_none()

    async def add_project(self, project: Project) -> Project:
        self.db.add(project)
        await self.db.flush()
        return project

    async def board_with_columns(
        self, project_id: uuid.UUID
    ) -> tuple[Board | None, list[BoardColumn]]:
        board = (
            await self.db.execute(
                select(Board).where(Board.project_id == project_id, Board.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if board is None:
            return None, []
        columns = (
            await self.db.execute(
                select(BoardColumn)
                .where(BoardColumn.board_id == board.id)
                .order_by(BoardColumn.order.asc())
            )
        ).scalars()
        return board, list(columns)

    async def add_board(self, board: Board) -> Board:
        self.db.add(board)
        await self.db.flush()
        return board

    async def add_column(self, column: BoardColumn) -> BoardColumn:
        self.db.add(column)
        await self.db.flush()
        return column

    # ---------------------------------------------------------------- sprints

    async def sprints_by_name(self, project_id: uuid.UUID) -> dict[str, Sprint]:
        result = await self.db.execute(
            select(Sprint).where(Sprint.project_id == project_id, Sprint.is_active.is_(True))
        )
        return {sprint.name: sprint for sprint in result.scalars()}

    async def add_sprint(self, sprint: Sprint) -> Sprint:
        self.db.add(sprint)
        await self.db.flush()
        return sprint

    # ---------------------------------------------------------------- tasks

    async def jira_tasks(
        self, organization_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[str, Task]:
        """Active Jira-anchored tasks of one project of the organization."""

        result = await self.db.execute(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Task.project_id == project_id,
                Task.source == JIRA_SOURCE,
                Task.external_key.is_not(None),
                Task.is_active.is_(True),
            )
        )
        return {task.external_key: task for task in result.scalars() if task.external_key}

    async def used_task_numbers(self, project_id: uuid.UUID) -> set[int]:
        result = await self.db.execute(
            select(Task.task_number).where(
                Task.project_id == project_id, Task.task_number.is_not(None)
            )
        )
        return {number for number in result.scalars() if number is not None}

    async def add_task(self, task: Task) -> Task:
        self.db.add(task)
        return task
