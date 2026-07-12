"""Data-access layer for boards and board columns.

Only this layer talks to SQLAlchemy; services and routers depend on it. Per
design.md C4, this repository is the ONLY place ``boards`` may touch ``Task``
rows — ``tasks.service`` is never imported here, and ``tasks`` reaches this
module only through a deferred import inside its methods.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn


class BoardRepository:
    """Async repository encapsulating board/column persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_for_project(
        self,
        project_id: uuid.UUID,
        columns: Sequence[tuple[str, str]],
    ) -> Board:
        """Create a board for ``project_id`` seeded with ``(name, status_key)`` pairs.

        Columns are persisted in the given order (``order`` 0..N-1). The board
        and its columns are added and flushed but NOT committed — the caller
        controls the transaction boundary (project creation commits once).
        """

        board = Board(project_id=project_id)
        self.db.add(board)
        await self.db.flush()

        for order, (name, status_key) in enumerate(columns):
            self.db.add(
                BoardColumn(
                    board_id=board.id,
                    name=name,
                    status_key=status_key,
                    order=order,
                )
            )
        await self.db.flush()
        return board

    async def get_board_with_columns(self, project_id: uuid.UUID) -> Board | None:
        """Return the active board for ``project_id`` with its active columns loaded.

        Columns are ordered by ``order, created_at`` (same tie-break pattern as
        ``Task.order, Task.created_at``). Returns ``None`` when the project has
        no board yet (legacy rows before this change; see ``ensure_board``).
        """

        result = await self.db.execute(
            select(Board).where(
                Board.project_id == project_id, Board.is_active.is_(True)
            )
        )
        board = result.scalar_one_or_none()
        if board is None:
            return None

        board.columns = await self.list_columns(board.id)
        return board

    async def list_columns(self, board_id: uuid.UUID) -> list[BoardColumn]:
        """Return the active columns of ``board_id``, ordered for display."""

        result = await self.db.execute(
            select(BoardColumn)
            .where(BoardColumn.board_id == board_id, BoardColumn.is_active.is_(True))
            .order_by(BoardColumn.order.asc(), BoardColumn.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_board_by_id(self, board_id: uuid.UUID) -> Board | None:
        """Return the active board by its own id, or ``None``."""

        result = await self.db.execute(
            select(Board).where(Board.id == board_id, Board.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_column(
        self, board_id: uuid.UUID, column_id: uuid.UUID
    ) -> BoardColumn | None:
        """Return an active column scoped to ``board_id``, or ``None``."""

        result = await self.db.execute(
            select(BoardColumn).where(
                BoardColumn.id == column_id,
                BoardColumn.board_id == board_id,
                BoardColumn.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def save(self, board: Board) -> Board:
        """Flush pending changes on an attached board and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(board)
        return board
