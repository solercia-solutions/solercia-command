"""Response shapes of ``/sync``."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScheduledSyncStepRead(BaseModel):
    name: str
    status: str
    counts: dict[str, Any] = {}
    detail: str | None = None
    error: dict[str, str] | None = None


class ScheduledSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime
    actor_id: uuid.UUID | None = None
    steps: list[ScheduledSyncStepRead]
