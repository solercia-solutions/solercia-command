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
from app.modules.boards.models import Board, BoardColumn
from app.modules.boards.repository import BoardRepository
from app.modules.tasks.models import Task
from app.shared.exceptions import AppException


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

    async def move_to_column(
        self,
        task: Task,
        target_column: BoardColumn,
        *,
        actor_id: uuid.UUID | None,
        enforce_wip: bool = True,
        commit: bool = True,
    ) -> Task:
        """Move ``task`` into ``target_column``, deriving ``status`` from its ``status_key``.

        Sets ``board_column_id``/``status`` atomically and stamps
        ``updated_by = actor_id`` (design.md D3 — the `02` audit contract
        applies to every UPDATE on an audited row). When ``enforce_wip`` and
        the (freshly row-locked) target column has a non-null ``wip_limit``,
        rejects with **409** if accepting the move would exceed it. A move
        that leaves the task in its CURRENT column never double-counts it.

        ``commit``: the canonical ``PATCH /tasks/{id}/column`` entry point
        wants this call to persist by itself (``commit=True``, the default).
        ``TaskService.update_task`` composes this move with OTHER field
        changes in the SAME transaction, so it passes ``commit=False`` and
        performs a single commit itself afterwards — still the SAME WIP
        code path either way (design.md, "un solo camino WIP").
        """

        if enforce_wip:
            locked = await self.repo.lock_column(target_column.id)
            if locked is None:
                raise AppException(
                    "La columna destino no existe o no está activa.",
                    code="invalid_board_column",
                    status_code=422,
                )
            if locked.wip_limit is not None:
                current_count = await self.repo.count_active_tasks_in_column(
                    locked.id
                )
                already_here = task.board_column_id == locked.id
                effective_count = current_count - (1 if already_here else 0)
                if effective_count >= locked.wip_limit:
                    raise AppException(
                        f"La columna '{locked.name}' alcanzó su límite WIP "
                        f"({locked.wip_limit}).",
                        code="wip_limit_exceeded",
                        status_code=409,
                    )

        task.board_column_id = target_column.id
        task.status = target_column.status_key
        task.updated_by = actor_id

        if commit:
            await self.repo.db.commit()
            await self.repo.db.refresh(task)
        return task

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
