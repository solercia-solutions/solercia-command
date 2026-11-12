"""Bounded read-only projections for explicit review IDs, not authorization.

The caller supplies the trusted tenant and owns the session/transaction. Loading
uses at most two SELECTs; subsequent synchronous port calls never perform I/O.
This is a detached facts snapshot, not a repeatable-read database guarantee or a
promise that facts remain valid when an import is eventually performed.
"""
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.users.models import User

from .review_ports import ProjectFacts

# Per supplied list, BEFORE deduplication. Conservatively bounds Python work and
# SQL IN parameters to 1,000 IDs, well below asyncpg's parameter ceiling. This is
# a server-owned adapter budget, independent of client/parser row limits.
MAX_REVIEW_FACT_IDS = 1000


class ReviewFactsInputError(ValueError):
    """Safe input-shape/budget failure; never includes submitted identifiers."""


def _bounded_ids(values: list[str] | tuple[str, ...]) -> dict[str, UUID]:
    # Only materialized built-ins: no unbounded/lazy iterable or custom iterator.
    if type(values) not in (list, tuple) or len(values) > MAX_REVIEW_FACT_IDS:
        raise ReviewFactsInputError('La lista de identificadores supera el límite o no es válida.')
    result = {}
    for value in values:
        if not isinstance(value, str) or len(value) != 36:
            continue
        try:
            parsed = UUID(value)
        except ValueError:
            continue
        # Exact port IDs; never alias alternate spellings to a different ID.
        if str(parsed) == value:
            result[value] = parsed
    return result


@dataclass(frozen=True)
class ReviewFactsSnapshot:
    tenant_id: str
    projects: Mapping[str, ProjectFacts] = field(repr=False)
    members: frozenset[str] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, 'projects', MappingProxyType(dict(self.projects)))
        object.__setattr__(self, 'members', frozenset(self.members))

    def active_project(self, tenant_id: str, project_id: str) -> ProjectFacts | None:
        return self.projects.get(project_id) if tenant_id == self.tenant_id else None

    def active_member(self, tenant_id: str, user_id: str) -> bool:
        return tenant_id == self.tenant_id and user_id in self.members


class ReviewFactsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def load(
        self, tenant_id: str, project_ids: list[str] | tuple[str, ...],
        user_ids: list[str] | tuple[str, ...],
    ) -> ReviewFactsSnapshot:
        """Load active, nondeleted records; invalid/unknown IDs remain absent.

        IDs use canonical UUID strings as required by the synchronous string
        port. Membership eligibility means tenant membership plus a usable user,
        not a role/project permission. No default project resolution occurs.
        """
        # Core table projections avoid ORM entity hydration/selectin loaders and
        # do not require unrelated role mappers to be configured.
        project = Project.__table__.c
        board = Board.__table__.c
        column = BoardColumn.__table__.c
        member = OrganizationMember.__table__.c
        user = User.__table__.c
        projects = _bounded_ids(project_ids)
        users = _bounded_ids(user_ids)
        tenants = _bounded_ids([tenant_id])
        if not tenants:
            raise ReviewFactsInputError('El identificador del contexto no es válido.')
        tenant = tenants[tenant_id]
        statuses: dict[str, set[str]] = {}
        members: set[str] = set()
        if projects:
            statement = (
                select(project.id, column.status_key)
                .select_from(Project.__table__)
                .outerjoin(Board.__table__, and_(
                    board.project_id == project.id,
                    board.is_active.is_(True), board.deleted_at.is_(None),
                ))
                .outerjoin(BoardColumn.__table__, and_(
                    column.board_id == board.id,
                    column.is_active.is_(True), column.deleted_at.is_(None),
                ))
                .where(
                    project.organization_id == tenant,
                    project.id.in_(projects.values()),
                    project.is_active.is_(True), project.deleted_at.is_(None),
                ).execution_options(autoflush=False)
            )
            for project_id, status in (await self._session.execute(statement)).all():
                key = str(project_id)
                if key in projects:
                    supported = statuses.setdefault(key, set())
                    if status is not None:
                        supported.add(status)
        if users:
            statement = (
                select(member.user_id)
                .select_from(OrganizationMember.__table__)
                .join(User.__table__, user.id == member.user_id)
                .where(
                    member.organization_id == tenant,
                    member.user_id.in_(users.values()),
                    user.is_active.is_(True), user.deleted_at.is_(None),
                ).execution_options(autoflush=False)
            )
            members = {str(user_id) for (user_id,) in
                       (await self._session.execute(statement)).all() if str(user_id) in users}
        return ReviewFactsSnapshot(
            tenant_id,
            {key: ProjectFacts(tenant_id, key, frozenset(values)) for key, values in statuses.items()},
            frozenset(members),
        )
