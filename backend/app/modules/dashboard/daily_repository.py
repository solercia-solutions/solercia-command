"""Read-only PostgreSQL DailyQueryPort adapter; not wired to HTTP.

One Core statement reads one MVCC statement snapshot, including under READ
COMMITTED. The caller owns the session/transaction; no isolation changes,
locks, flushes or transaction completion occur here. Independent bounded CTE
streams avoid tasks x columns x edges multiplication. Limits are admission
bounds, never pagination: each stream includes one overflow sentinel.

Boards are canonical by project (Task has no board_id), matching the persisted
board-aware workflow. Missing/inactive boards and empty status sets stay unknown.
TaskDependency stores only directed blocks edges; there is no type column or
persisted inverse edge. SQL behavior still requires the guarded PostgreSQL suite.
"""
from datetime import datetime
from uuid import UUID

from sqlalchemy import String, func, literal, select, union, union_all
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.dashboard.daily_contracts import (
    BlockingEdge, BoardStatuses, DailyContext, DailySnapshot, DailyTask,
)
from app.modules.dashboard.daily_service import (
    BOARD_LIMIT, EDGE_LIMIT, TASK_LIMIT, DailySummaryError,
)
from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.task_links.models import TaskDependency
from app.modules.tasks.models import Task

# Global column projection bound, independent of the number of boards.
COLUMN_LIMIT = 20_000


def _live(table):
    return table.c.is_active.is_(True), table.c.deleted_at.is_(None)


def _task_fields(task, project):
    return [task.c.id, project.c.organization_id, task.c.project_id,
            task.c.assignee_id, task.c.title, task.c.status, task.c.due_date,
            task.c.updated_at, task.c.completed_at, task.c.is_active,
            project.c.code.label('project_code'), task.c.task_number]


def _stream(kind, cte):
    fields = [value for col in cte.c for value in (literal(str(col.key), String), col)]
    return select(literal(kind).label('kind'), func.jsonb_build_object(*fields, type_=JSONB).label('payload'))


def _statement(context, task_limit, edge_limit, board_limit):
    task, project = Task.__table__, Project.__table__
    blocker, blocker_project = task.alias('blocker'), project.alias('blocker_project')
    edge, board, column = TaskDependency.__table__, Board.__table__, BoardColumn.__table__
    assigned = (select(*_task_fields(task, project))
                .select_from(task.join(project, task.c.project_id == project.c.id))
                .where(project.c.organization_id == context.organization_id,
                       task.c.assignee_id == context.user_id, *_live(task), *_live(project))
                .limit(task_limit + 1).cte('assigned_tasks'))
    incoming = (select(edge.c.blocked_task_id.label('target_id'), *_task_fields(blocker, blocker_project))
                .select_from(edge.join(assigned, edge.c.blocked_task_id == assigned.c.id)
                             .join(blocker, edge.c.blocker_task_id == blocker.c.id)
                             .join(blocker_project, blocker.c.project_id == blocker_project.c.id))
                .where(edge.c.organization_id == context.organization_id,
                       blocker_project.c.organization_id == context.organization_id,
                       *_live(edge), *_live(blocker), *_live(blocker_project))
                .limit(edge_limit + 1).cte('incoming_edges'))
    projects = union(select(assigned.c.project_id), select(incoming.c.project_id))
    boards = (select(board.c.id, board.c.project_id, project.c.organization_id)
              .select_from(board.join(project, board.c.project_id == project.c.id))
              .where(board.c.project_id.in_(projects),
                     project.c.organization_id == context.organization_id,
                     *_live(board), *_live(project))
              .limit(board_limit + 1).cte('canonical_boards'))
    columns = (select(column.c.board_id, column.c.status_key, column.c.column_order, column.c.created_at)
               .where(column.c.board_id.in_(select(boards.c.id)), *_live(column))
               .limit(COLUMN_LIMIT + 1).cte('status_columns'))
    return union_all(_stream('task', assigned), _stream('edge', incoming),
                     _stream('board', boards), _stream('column', columns)).execution_options(autoflush=False)


def _uuid(value):
    return UUID(value) if isinstance(value, str) else value


def _datetime(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


class DailyRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def organization_available(self, context: DailyContext) -> bool:
        """Local daily gate; shared authentication behavior is unchanged."""
        organization = Organization.__table__
        result = await self._session.execute(
            select(organization.c.id).where(
                organization.c.id == context.organization_id, *_live(organization),
            ).execution_options(autoflush=False)
        )
        return result.scalar_one_or_none() is not None

    async def assigned_daily_snapshot(
        self, context: DailyContext, *, task_limit: int, edge_limit: int,
    ) -> DailySnapshot:
        if (type(task_limit) is not int or not 0 < task_limit <= TASK_LIMIT
                or type(edge_limit) is not int or not 0 < edge_limit <= EDGE_LIMIT):
            raise DailySummaryError('input_limit')
        board_limit = min(BOARD_LIMIT, task_limit + edge_limit)
        result = await self._session.execute(_statement(context, task_limit, edge_limit, board_limit))
        streams = {name: [] for name in ('task', 'edge', 'board', 'column')}
        for row in result.mappings().all():
            streams[row['kind']].append(row['payload'])
        limits = dict(task=task_limit, edge=edge_limit, board=board_limit, column=COLUMN_LIMIT)
        if any(len(streams[name]) > limit for name, limit in limits.items()):
            raise DailySummaryError('input_limit')

        board_by_project = {}
        statuses = {}
        for row in streams['board']:
            project_id, board_id = _uuid(row['project_id']), _uuid(row['id'])
            if project_id in board_by_project:
                raise DailySummaryError('ambiguous_board')
            board_by_project[project_id] = board_id
            statuses[board_id] = []
        for row in streams['column']:
            statuses[_uuid(row['board_id'])].append(row)
        for rows in statuses.values():
            # Canonical repository order has no UUID tiebreak. An exact tie
            # cannot establish the final status; fail instead of guessing.
            keys = [(row['column_order'], _datetime(row['created_at'])) for row in rows]
            if len(set(keys)) != len(keys) or any(key[1] is None for key in keys):
                raise DailySummaryError('ambiguous_board_order')
            rows.sort(key=lambda row: (row['column_order'], _datetime(row['created_at'])))

        def task_fact(row):
            project_id = _uuid(row['project_id'])
            return DailyTask(
                _uuid(row['id']), _uuid(row['organization_id']), project_id,
                board_by_project.get(project_id), _uuid(row['assignee_id']),
                row['title'], row['status'], _datetime(row['due_date']),
                _datetime(row['updated_at']), _datetime(row['completed_at']), row['is_active'],
                # Match TaskService._to_read exactly: no normalization or fallback.
                task_key=(f"{row['project_code']}-{row['task_number']}"
                          if row['project_code'] and row['task_number'] is not None else None),
            )

        return DailySnapshot(
            context.organization_id, context.user_id,
            tuple(task_fact(row) for row in streams['task']),
            tuple(BoardStatuses(_uuid(row['organization_id']), _uuid(row['project_id']),
                                _uuid(row['id']), tuple(col['status_key'] for col in statuses[_uuid(row['id'])]))
                  for row in streams['board']),
            tuple(BlockingEdge(context.organization_id, _uuid(row['target_id']), True, task_fact(row))
                  for row in streams['edge']),
        )
