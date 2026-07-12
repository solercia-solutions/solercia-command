"""Business logic for boards: seeding and runtime column configuration.

Seeding derives the initial columns from the project methodology Strategy
(``strategy.default_columns()``); every other behaviour in this service reads
and writes the persisted ``Board``/``BoardColumn`` rows directly, since those
rows become the runtime source of truth once a project is created (see
``app.methodology.board_aware.BoardAwareStrategy``).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.base import MethodologyStrategy
from app.modules.boards.models import Board
from app.modules.boards.repository import BoardRepository


class BoardService:
    """Orchestrates board use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.repo = BoardRepository(db)

    async def seed_board(
        self, project_id: uuid.UUID, strategy: MethodologyStrategy
    ) -> Board:
        """Create a board for ``project_id`` seeded from ``strategy.default_columns()``.

        Each seeded column's ``status_key`` equals its display name verbatim —
        the strategy's default columns ARE the seed statuses, matching the
        ``Task.status`` values the methodology strategies have always produced
        (see methodology-strategies.md). Does not commit; the caller controls
        the transaction (project creation flushes/commits once).
        """

        columns = [(name, name) for name in strategy.default_columns()]
        return await self.repo.create_for_project(project_id, columns)

    async def get_board(self, project_id: uuid.UUID) -> Board | None:
        """Return the project's board with its columns, or ``None``."""

        return await self.repo.get_board_with_columns(project_id)

    async def ensure_board(
        self, project_id: uuid.UUID, strategy: MethodologyStrategy
    ) -> Board:
        """Return the project's board, lazily seeding one if it is missing.

        Defensive fallback for legacy rows created between the schema
        migration and the backfill migration of this change (design.md D4).
        """

        board = await self.repo.get_board_with_columns(project_id)
        if board is not None:
            return board
        board = await self.seed_board(project_id, strategy)
        await self.repo.save(board)
        board.columns = await self.repo.list_columns(board.id)
        return board
