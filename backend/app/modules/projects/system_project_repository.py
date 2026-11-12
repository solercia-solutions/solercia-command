"""Flush-only Generales adapter; deliberately independent of legacy repositories.

The caller supplies one active transaction and owns rollback after every error.
Organization locking coordinates cooperative provisioning entrypoints; database
constraints remain the final defense. This does not establish concurrency proof.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.projects.system_project import GENERALES
from app.modules.projects.system_project_ports import BoardSnapshot, ColumnSnapshot, ProjectSnapshot
from app.modules.projects.system_project_provisioning import SystemProjectConflict
from app.shared.enums import Methodology, ProjectKind, ProjectStatus


def _project_snapshot(project: Project) -> ProjectSnapshot:
    return ProjectSnapshot(
        project.id, project.organization_id, project.code, project.is_system,
        project.methodology, project.status, project.is_active, project.deleted_at,
    )


class SystemProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_organization(self, organization_id: UUID) -> bool:
        result = await self.session.execute(
            select(Organization.id).where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
                Organization.deleted_at.is_(None),
            ).with_for_update().execution_options(autoflush=False)
        )
        return result.scalar_one_or_none() is not None

    async def find_reserved(self, organization_id: UUID) -> ProjectSnapshot | None:
        # Include inactive/deleted collisions: no takeover or reactivation.
        result = await self.session.execute(select(Project).where(
            Project.organization_id == organization_id, Project.code == GENERALES.code,
        ))
        project = result.scalar_one_or_none()
        return _project_snapshot(project) if project is not None else None

    async def read_board(
        self, organization_id: UUID, project_id: UUID,
    ) -> BoardSnapshot | None:
        result = await self.session.execute(
            select(Board).join(Project, Project.id == Board.project_id).where(
                Project.organization_id == organization_id, Project.id == project_id,
            )
        )
        board = result.scalar_one_or_none()
        if board is None:
            return None
        result = await self.session.execute(
            select(BoardColumn).join(Board, Board.id == BoardColumn.board_id)
            .join(Project, Project.id == Board.project_id).where(
                Project.organization_id == organization_id, Project.id == project_id,
                BoardColumn.board_id == board.id,
            ).order_by(BoardColumn.order)
        )
        return BoardSnapshot(board.is_active, board.deleted_at, tuple(
            ColumnSnapshot(c.name, c.status_key, c.order, c.is_active, c.deleted_at)
            for c in result.scalars().all()
        ))

    async def _flush(self) -> None:
        try:
            await self.session.flush()
        except IntegrityError as exc:
            # Do not expose database details; caller must roll back, not retry
            # on this failed transaction. Unexpected constraints remain errors.
            name = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None)
            if name is None:
                name = getattr(getattr(exc.orig, '__cause__', None), 'constraint_name', None)
            if name in {
                'uq_project_code_per_org', 'ck_projects_system_shape',
                'boards_project_id_key', 'uq_board_column_status_key',
            }:
                raise SystemProjectConflict() from exc
            raise

    async def create_generales(
        self, organization_id: UUID, actor_id: UUID, parent_id: UUID | None,
    ) -> ProjectSnapshot:
        """Called only after the organization lock and absence check.

        Parent authorization/validation belongs to the caller, not this adapter.
        No lazy board helpers: all seven columns are explicit in this transaction.
        """
        audit = dict(created_by=actor_id, updated_by=actor_id, is_active=True, deleted_at=None)
        project = Project(
            organization_id=organization_id, name='Generales', code=GENERALES.code,
            is_system=True, methodology=Methodology.custom, status=ProjectStatus.active,
            parent_project_id=parent_id, project_kind=ProjectKind.proyecto,
            lead_user_id=None, **audit,
        )
        self.session.add(project)
        await self._flush()
        board = Board(project_id=project.id, **audit)
        self.session.add(board)
        await self._flush()
        for order, status in enumerate(GENERALES.statuses):
            self.session.add(BoardColumn(
                board_id=board.id, name=status, status_key=status, order=order,
                wip_limit=None, **audit,
            ))
        await self._flush()
        return _project_snapshot(project)
