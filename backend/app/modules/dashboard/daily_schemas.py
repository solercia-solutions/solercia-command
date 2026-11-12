"""Explicit public daily projection; blocker identities never cross HTTP."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.modules.dashboard.daily_contracts import DailyGroup, DailySummary, DatePolicy


class DailyItemResponse(BaseModel):
    id: UUID
    project_id: UUID
    task_key: str | None
    title: str
    status: str
    due_date: date | None
    updated_at: datetime | None
    blocked_count: int


class DailyGroupResponse(BaseModel):
    count: int
    items: list[DailyItemResponse]


class DailyData(BaseModel):
    timezone: str
    date_policy: DatePolicy
    generated_at: datetime
    today_date: date
    tomorrow_date: date
    today: DailyGroupResponse
    tomorrow: DailyGroupResponse
    overdue: DailyGroupResponse
    blocked: DailyGroupResponse
    coverage_warnings: list[str]
    provider_freshness: Literal['unknown']


class DailyResponse(BaseModel):
    data: DailyData


def project_daily(summary: DailySummary) -> DailyResponse:
    warnings = set(summary.coverage_warnings)
    seen = set()

    def group(source: DailyGroup) -> DailyGroupResponse:
        items = []
        for item in source.items:
            if item.id in seen:
                warnings.add('groups_overlap')
            seen.add(item.id)
            if item.task_key is None:
                warnings.add('missing_task_key')
            items.append(DailyItemResponse(
                id=item.id, project_id=item.project_id, task_key=item.task_key,
                title=item.title, status=item.status, due_date=item.due_date,
                updated_at=item.updated_at, blocked_count=len(item.blocker_ids),
            ))
        return DailyGroupResponse(count=len(items), items=items)

    groups = {name: group(getattr(summary, name))
              for name in ('today', 'tomorrow', 'overdue', 'blocked')}
    return DailyResponse(data=DailyData(
        timezone=summary.timezone, date_policy=summary.date_policy,
        generated_at=summary.generated_at, today_date=summary.today_date,
        tomorrow_date=summary.tomorrow_date, **groups,
        coverage_warnings=sorted(warnings), provider_freshness=summary.provider_freshness,
    ))
