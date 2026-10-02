"""Immutable, database-neutral projections for a bounded personal daily query.

The future adapter must read a consistent snapshot and filter tenant, assignment,
active projects/boards/tasks and dependency endpoints before returning it. Limits
are admission bounds, not pagination: overflow must fail, never truncate totals.
Persisted ordered status keys are required; no methodology fallback is permitted.
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol
from uuid import UUID

DatePolicy = Literal['stored_calendar_date', 'instant']


@dataclass(frozen=True)
class DailyContext:
    """Trusted authenticated membership, supplied by the future application caller."""

    organization_id: UUID
    user_id: UUID


@dataclass(frozen=True)
class DailyTask:
    id: UUID
    organization_id: UUID
    project_id: UUID
    board_id: UUID | None
    assignee_id: UUID | None
    title: str
    status: str
    due_date: datetime | None
    updated_at: datetime | None
    completed_at: datetime | None
    is_active: bool
    task_key: str | None = None


@dataclass(frozen=True)
class BoardStatuses:
    organization_id: UUID
    project_id: UUID
    board_id: UUID
    statuses: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'statuses', tuple(self.statuses))


@dataclass(frozen=True)
class BlockingEdge:
    """An incoming blocks edge; target must be in the assigned task snapshot.

    Blocker carries its own tenant, active and board evidence. It need not be
    assigned to the caller. No blocker title is emitted in the summary.
    """

    organization_id: UUID
    target_id: UUID
    is_active: bool
    blocker: DailyTask


@dataclass(frozen=True)
class DailySnapshot:
    organization_id: UUID
    user_id: UUID
    tasks: tuple[DailyTask, ...]
    boards: tuple[BoardStatuses, ...]
    edges: tuple[BlockingEdge, ...]

    def __post_init__(self):
        for field in ('tasks', 'boards', 'edges'):
            object.__setattr__(self, field, tuple(getattr(self, field)))


class DailyQueryPort(Protocol):
    async def assigned_daily_snapshot(
        self, context: DailyContext, *, task_limit: int, edge_limit: int,
    ) -> DailySnapshot:
        """Return all scoped facts within limits or raise; never silently page."""
        ...


class DailyAccessPort(DailyQueryPort, Protocol):
    async def organization_available(self, context: DailyContext) -> bool:
        """Check the trusted tenant is active and not deleted before reading facts."""
        ...


class DailyClock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class DailyItem:
    id: UUID
    project_id: UUID
    title: str
    status: str
    due_date: date | None
    updated_at: datetime | None  # Local modification, NOT provider sync time.
    blocker_ids: tuple[UUID, ...]
    task_key: str | None = None


@dataclass(frozen=True)
class DailyGroup:
    items: tuple[DailyItem, ...]

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class DailySummary:
    organization_id: UUID
    user_id: UUID
    timezone: str
    date_policy: DatePolicy
    generated_at: datetime
    today_date: date
    tomorrow_date: date
    today: DailyGroup
    tomorrow: DailyGroup
    overdue: DailyGroup
    blocked: DailyGroup
    coverage_warnings: tuple[str, ...]
    provider_freshness: Literal['unknown'] = 'unknown'
