"""Data-access layer for boards and board columns.

Only this layer talks to SQLAlchemy; services and routers depend on it. Per
design.md C4, this repository is the ONLY place ``boards`` may touch ``Task``
rows — ``tasks.service`` is never imported here, and ``tasks`` reaches this
module only through a deferred import inside its methods.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.tasks.models import Task


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

    async def list_boards_with_columns_for_projects(
        self, project_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[BoardColumn]]:
        """Return ``{project_id: [active columns...]}`` for every id in ``project_ids``.

        Exactly two queries total (one for boards, one for their columns),
        REGARDLESS of how many ``project_ids`` are given — never N+1. Used by
        ``ProjectService.list_projects`` to batch-resolve ``BoardAwareStrategy``
        for every row of a listing in one shot (design.md C1).
        """

        if not project_ids:
            return {}

        boards_result = await self.db.execute(
            select(Board).where(
                Board.project_id.in_(project_ids), Board.is_active.is_(True)
            )
        )
        boards = list(boards_result.scalars().all())
        if not boards:
            return {}

        board_id_to_project_id = {board.id: board.project_id for board in boards}
        columns_by_board: dict[uuid.UUID, list[BoardColumn]] = {
            board.id: [] for board in boards
        }

        columns_result = await self.db.execute(
            select(BoardColumn)
            .where(
                BoardColumn.board_id.in_(board_id_to_project_id),
                BoardColumn.is_active.is_(True),
            )
            .order_by(BoardColumn.order.asc(), BoardColumn.created_at.asc())
        )
        for column in columns_result.scalars().all():
            columns_by_board[column.board_id].append(column)

        return {
            board_id_to_project_id[board_id]: columns
            for board_id, columns in columns_by_board.items()
        }

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

    async def lock_column(self, column_id: uuid.UUID) -> BoardColumn | None:
        """``SELECT ... FOR UPDATE`` a single active column, or ``None``.

        Serializes concurrent movers into the SAME target column: whoever
        acquires the row lock first counts and writes; the next transaction
        blocks until the first commits, then sees the up-to-date count
        (design.md D3/C5 — lock -> count -> conditional write).
        """

        result = await self.db.execute(
            select(BoardColumn)
            .where(BoardColumn.id == column_id, BoardColumn.is_active.is_(True))
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def count_active_tasks_in_column(self, column_id: uuid.UUID) -> int:
        """Count active tasks currently assigned to ``column_id``.

        Queries ``Task`` directly — this repository is the ONLY place the
        ``boards`` module may touch ``Task`` rows (design.md C4); `tasks`
        itself is never imported here.
        """

        result = await self.db.execute(
            select(func.count())
            .select_from(Task)
            .where(Task.board_column_id == column_id, Task.is_active.is_(True))
        )
        return result.scalar_one() or 0

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
