"""BoardAwareStrategy: wraps a base MethodologyStrategy with persisted board columns.

The single resolution helper :func:`resolve_board_strategy` is used at every
runtime call site that needs ``allowed_statuses()`` for a LIVE project — see
design.md, "Correcciones de gate", C1: tasks (create/move), dashboard
``_bounds_for``, sprints ``done_status`` and projects
``_attach_methodology_info``. It never hardcodes an ``if methodology == ...``
branch: for methodologies with fixed columns the persisted ``status_key``
values equal the strategy's own ``default_columns()`` right after seeding,
and for ``custom`` the persisted ``status_key`` values ARE the only source of
truth (the base ``CustomStrategy`` always returns ``[]``).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.methodology.base import MethodologyStrategy
from app.methodology.factory import get_strategy
from app.modules.projects.models import Project


class BoardAwareStrategy(MethodologyStrategy):
    """Overrides ``allowed_statuses()`` with the project's persisted columns.

    ``default_columns()`` still delegates to the base strategy — it is only
    used for seeding a NEW board, never for resolving the allowed statuses of
    an existing one. Every feature flag (``sprints_enabled``,
    ``estimation_mode``, ``has_backlog``, ``name``) delegates to the base
    strategy unconditionally: only the board's columns are runtime-configurable.
    """

    def __init__(self, base: MethodologyStrategy, status_keys: list[str]) -> None:
        self._base = base
        self._status_keys = list(status_keys)
        self.name = base.name

    def default_columns(self) -> list[str]:
        return self._base.default_columns()

    def allowed_statuses(self) -> list[str]:
        """Return the persisted ``status_key`` values, or the base's when empty.

        Falling back to the base is a defensive measure for boards that have
        not been seeded/backfilled yet (see design.md D4, ``ensure_board``) —
        it is never reachable in steady state for methodologies with fixed
        columns, since removing the last column is rejected (design.md D5).
        For ``custom`` the base itself always returns ``[]``, so an empty
        board correctly stays blocked (boards.md, "Bloqueo de custom sin
        columnas").
        """

        return list(self._status_keys) or self._base.allowed_statuses()

    @property
    def sprints_enabled(self) -> bool:
        return self._base.sprints_enabled

    @property
    def estimation_mode(self) -> str:
        return self._base.estimation_mode

    @property
    def has_backlog(self) -> bool:
        return self._base.has_backlog


async def resolve_board_strategy(project: Project, db: AsyncSession) -> BoardAwareStrategy:
    """Resolve the runtime strategy for ``project``: base strategy + persisted columns.

    Single helper used at every call site that needs ``allowed_statuses()``
    for a project that may already exist and have runtime-configured columns
    (design.md C1). The board's columns are loaded via ``BoardRepository``
    (async I/O); the wrapper itself is built synchronously so every caller
    keeps the existing synchronous ``strategy.allowed_statuses()`` contract.
    """

    # Deferred import: `methodology` must not depend on `modules.boards` at
    # module load time (mirrors the tasks->boards deferred-import pattern,
    # design.md C4) — avoids a hard coupling from the base Strategy layer to
    # a specific persistence module.
    from app.modules.boards.repository import BoardRepository

    base = get_strategy(project.methodology)
    board = await BoardRepository(db).get_board_with_columns(project.id)
    status_keys = [column.status_key for column in board.columns] if board else []
    return BoardAwareStrategy(base, status_keys)


def build_board_aware_strategy(
    project: Project, status_keys: list[str]
) -> BoardAwareStrategy:
    """Build a :class:`BoardAwareStrategy` from already-loaded ``status_keys``.

    Sync counterpart of :func:`resolve_board_strategy` for callers that
    batch-preload columns for many projects in one query to avoid N+1 (see
    ``ProjectRepository.list_boards_with_columns_for_projects`` and
    design.md C1, "precarga por lotes de columnas").
    """

    return BoardAwareStrategy(get_strategy(project.methodology), status_keys)
