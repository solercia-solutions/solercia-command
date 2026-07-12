"""Business logic for boards: seeding and runtime column configuration.

Seeding derives the initial columns from the project methodology Strategy
(``strategy.default_columns()``); every other behaviour in this service reads
and writes the persisted ``Board``/``BoardColumn`` rows directly, since those
rows become the runtime source of truth once a project is created (see
``app.methodology.board_aware.BoardAwareStrategy``).
"""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.base import MethodologyStrategy
from app.modules.boards.models import Board, BoardColumn
from app.modules.boards.repository import BoardRepository
from app.modules.tasks.models import Task
from app.shared.exceptions import AppException

# status_key column width (see BoardColumn.status_key).
_STATUS_KEY_MAX_LEN = 60
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Turn a display name into a lowercase, underscore-separated slug.

    The result becomes an immutable ``status_key`` once persisted — uniqueness
    per board is enforced by :meth:`BoardService.add_column`, which appends a
    numeric suffix on collision (design.md D5, "status_key derivado del name,
    slug único por board").
    """

    slug = _SLUG_STRIP_RE.sub("_", name.strip().lower()).strip("_")
    return slug or "column"


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

    async def rename_column(
        self,
        organization_id: uuid.UUID,
        board_id: uuid.UUID,
        column_id: uuid.UUID,
        name: str,
        *,
        actor_id: uuid.UUID | None,
    ) -> BoardColumn:
        """Rename a column. ``status_key`` (and every assigned task) is untouched.

        boards.md, "Renombrar columna no afecta tareas asignadas".
        """

        board = await self._require_board(organization_id, board_id)
        column = await self.repo.get_column(board.id, column_id)
        if column is None:
            raise AppException(
                "La columna no existe en este board.",
                code="column_not_found",
                status_code=404,
            )

        column.name = name
        column.updated_by = actor_id
        await self.repo.db.commit()
        await self.repo.db.refresh(column)
        return column

    async def reorder_columns(
        self,
        organization_id: uuid.UUID,
        board_id: uuid.UUID,
        ordered_ids: list[uuid.UUID],
        *,
        actor_id: uuid.UUID | None,
    ) -> list[BoardColumn]:
        """Persist a new column order. ``ordered_ids`` must match the board exactly.

        boards.md, "Reordenar columnas".
        """

        board = await self._require_board(organization_id, board_id)
        columns = await self.repo.list_columns(board.id)
        columns_by_id = {column.id: column for column in columns}

        if set(ordered_ids) != set(columns_by_id):
            raise AppException(
                "La lista de columnas no coincide con las columnas actuales del board.",
                code="invalid_column_order",
                status_code=422,
            )

        for index, column_id in enumerate(ordered_ids):
            column = columns_by_id[column_id]
            column.order = index
            column.updated_by = actor_id

        await self.repo.db.commit()
        return await self.repo.list_columns(board.id)

    async def add_column(
        self,
        organization_id: uuid.UUID,
        board_id: uuid.UUID,
        name: str,
        wip_limit: int | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> BoardColumn:
        """Append a new column, deriving a unique ``status_key`` slug from ``name``.

        Makes ``custom`` boards usable from a zero-column state (boards.md,
        "Agregar columna a un board custom vacío").
        """

        board = await self._require_board(organization_id, board_id)
        columns = await self.repo.list_columns(board.id)
        existing_keys = {column.status_key for column in columns}

        base_slug = _slugify(name)[:_STATUS_KEY_MAX_LEN]
        status_key = base_slug
        suffix = 2
        while status_key in existing_keys:
            status_key = f"{base_slug}_{suffix}"[:_STATUS_KEY_MAX_LEN]
            suffix += 1

        next_order = max((column.order for column in columns), default=-1) + 1
        column = BoardColumn(
            board_id=board.id,
            name=name,
            status_key=status_key,
            order=next_order,
            wip_limit=wip_limit,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.repo.db.add(column)
        await self.repo.db.commit()
        await self.repo.db.refresh(column)
        return column

    async def remove_column(
        self,
        organization_id: uuid.UUID,
        board_id: uuid.UUID,
        column_id: uuid.UUID,
        target_column_id: uuid.UUID | None,
        *,
        actor_id: uuid.UUID | None,
    ) -> int:
        """Remove a column: soft-delete if empty, or reassign-then-delete.

        Rejects removing the LAST column of a board (**422**, it would leave
        tasks with no status) and removing a column that has tasks without a
        valid ``target_column_id`` (**409**). Returns the number of tasks
        reassigned (``0`` when the column had none). boards.md, "Reglas de
        eliminación de columnas con tareas".
        """

        board = await self._require_board(organization_id, board_id)
        columns = await self.repo.list_columns(board.id)
        column = next((c for c in columns if c.id == column_id), None)
        if column is None:
            raise AppException(
                "La columna no existe en este board.",
                code="column_not_found",
                status_code=404,
            )

        if len(columns) == 1:
            raise AppException(
                "No puedes eliminar la última columna del board: dejaría "
                "tareas sin estado.",
                code="cannot_remove_last_column",
                status_code=422,
            )

        reassigned = 0
        task_count = await self.repo.count_active_tasks_in_column(column.id)
        if task_count > 0:
            if target_column_id is None:
                raise AppException(
                    "Esta columna tiene tareas asignadas. Indica una columna "
                    "destino (target_column_id) para reasignarlas.",
                    code="column_has_tasks",
                    status_code=409,
                )
            target = next((c for c in columns if c.id == target_column_id), None)
            if target is None:
                raise AppException(
                    "La columna destino no pertenece a este board.",
                    code="invalid_board_column",
                    status_code=422,
                )
            reassigned = await self.reassign_column_tasks(
                column.id, target.id, target.status_key, actor_id=actor_id
            )

        column.is_active = False
        column.deleted_at = datetime.now(UTC)
        column.updated_by = actor_id
        await self.repo.db.commit()
        return reassigned

    async def reassign_column_tasks(
        self,
        source_column_id: uuid.UUID,
        target_column_id: uuid.UUID,
        target_status_key: str,
        *,
        actor_id: uuid.UUID | None,
    ) -> int:
        """Bulk-move every active task from ``source_column_id`` to the target.

        Intentional WIP bypass, no cross-column locking (design.md D5/C5):
        this is a column-deletion cleanup operation, not a user-initiated
        move, so the target's ``wip_limit`` is never checked here. Stamps
        ``updated_by = actor_id`` on every affected row.
        """

        return await self.repo.reassign_tasks(
            source_column_id, target_column_id, target_status_key, actor_id
        )

    async def _require_board(
        self, organization_id: uuid.UUID, board_id: uuid.UUID
    ) -> Board:
        board = await self.repo.get_board_scoped(organization_id, board_id)
        if board is None:
            raise AppException(
                "El board no existe o no tienes acceso a él.",
                code="board_not_found",
                status_code=404,
            )
        return board

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
