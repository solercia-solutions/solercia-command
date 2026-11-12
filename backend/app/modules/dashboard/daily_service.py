"""Pure daily-summary use case, intentionally not wired to an endpoint or SQL.

Date interpretation is mandatory per call until source policy is configured.
Calendar policy uses UTC date parts (the existing Gantt convention); instant
policy converts aware timestamps to the requested zone. Midnight is not a type.
Warnings describe incomplete coverage, not inferred cancellation or sync status.
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.dashboard.daily_contracts import (
    DailyClock, DailyContext, DailyGroup, DailyItem, DailyQueryPort, DailySummary,
    DatePolicy,
)

TASK_LIMIT = 1000
EDGE_LIMIT = 5000
BOARD_LIMIT = TASK_LIMIT + EDGE_LIMIT


class DailySummaryError(ValueError):
    """Safe reason code; never includes projected titles or foreign identities."""


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


class DailySummaryService:
    def __init__(self, query: DailyQueryPort, clock: DailyClock):
        self.query = query
        self.clock = clock

    async def summarize(
        self, context: DailyContext, *, timezone: str, date_policy: DatePolicy,
    ) -> DailySummary:
        if date_policy not in ('stored_calendar_date', 'instant'):
            raise DailySummaryError('invalid_date_policy')
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise DailySummaryError('invalid_timezone') from None
        now = self.clock.now()
        if not _aware(now):
            raise DailySummaryError('naive_clock')
        today = now.astimezone(zone).date()
        tomorrow = today + timedelta(days=1)
        snapshot = await self.query.assigned_daily_snapshot(
            context, task_limit=TASK_LIMIT, edge_limit=EDGE_LIMIT,
        )
        if (snapshot.organization_id != context.organization_id
                or snapshot.user_id != context.user_id):
            raise DailySummaryError('scope_mismatch')
        if (len(snapshot.tasks) > TASK_LIMIT or len(snapshot.edges) > EDGE_LIMIT
                or len(snapshot.boards) > BOARD_LIMIT):
            raise DailySummaryError('input_limit')
        tasks = {}
        for task in snapshot.tasks:
            if task.organization_id != context.organization_id or task.assignee_id != context.user_id:
                raise DailySummaryError('scope_mismatch')
            if task.id in tasks:
                raise DailySummaryError('duplicate_task')
            tasks[task.id] = task
        boards = {}
        for board in snapshot.boards:
            if board.organization_id != context.organization_id:
                raise DailySummaryError('scope_mismatch')
            if board.board_id in boards:
                raise DailySummaryError('duplicate_board')
            boards[board.board_id] = board
        # Validate all identities before classification, even for inactive facts.
        facts = dict(tasks)
        for edge in snapshot.edges:
            if (edge.organization_id != context.organization_id
                    or edge.blocker.organization_id != context.organization_id
                    or edge.target_id not in tasks):
                raise DailySummaryError('scope_mismatch')
            previous = facts.get(edge.blocker.id)
            if previous is not None and previous != edge.blocker:
                raise DailySummaryError('conflicting_task')
            facts[edge.blocker.id] = edge.blocker
        for task in facts.values():
            board = boards.get(task.board_id)
            if board is not None and board.project_id != task.project_id:
                raise DailySummaryError('scope_mismatch')

        warnings = {'cancellation_unsupported'}

        def active(task):
            if not task.is_active:
                return False
            board = boards.get(task.board_id)
            if board is None:
                warnings.add('unknown_board')
                return False
            statuses = board.statuses
            if (not statuses or len(set(statuses)) != len(statuses)
                    or any(not status for status in statuses) or task.status not in statuses):
                warnings.add('unknown_status')
                return False
            done = task.status == statuses[-1]
            # TaskService._resolve_completed_at defines final => timestamp,
            # nonfinal => None. Conflicts are omitted, not silently reclassified.
            if done != (task.completed_at is not None) or (
                task.completed_at is not None and not _aware(task.completed_at)
            ):
                warnings.add('completion_conflict')
                return False
            return not done

        eligible = {key: active(task) for key, task in facts.items()}
        blockers = {}
        for edge in snapshot.edges:
            if (edge.is_active and eligible[edge.target_id]
                    and eligible[edge.blocker.id]):
                blockers.setdefault(edge.target_id, set()).add(edge.blocker.id)
        groups = {key: [] for key in ('today', 'tomorrow', 'overdue', 'blocked')}
        for task in snapshot.tasks:
            if not eligible[task.id]:
                continue
            due = None
            if task.due_date is None:
                warnings.add('missing_due_date')
            elif not _aware(task.due_date):
                warnings.add('naive_due_date')
            else:
                due = task.due_date.astimezone(
                    UTC if date_policy == 'stored_calendar_date' else zone
                ).date()
            updated = task.updated_at
            if updated is not None and not _aware(updated):
                warnings.add('naive_updated_at')
                updated = None
            item = DailyItem(task.id, task.project_id, task.title, task.status,
                             due, updated, tuple(sorted(blockers.get(task.id, ()), key=str)),
                             task_key=task.task_key)
            if due is not None:
                if due < today:
                    groups['overdue'].append(item)
                elif due == today:
                    groups['today'].append(item)
                elif due == tomorrow:
                    groups['tomorrow'].append(item)
            if item.blocker_ids:
                groups['blocked'].append(item)
        ordered = {key: DailyGroup(tuple(sorted(items, key=lambda item: (
            item.due_date is None, item.due_date or tomorrow, str(item.id),
        )))) for key, items in groups.items()}
        return DailySummary(
            context.organization_id, context.user_id, timezone, date_policy,
            now, today, tomorrow, ordered['today'], ordered['tomorrow'],
            ordered['overdue'], ordered['blocked'], tuple(sorted(warnings)),
        )
