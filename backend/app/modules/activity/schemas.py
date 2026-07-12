"""Pydantic schemas for the activity module.

The API contract exposes ``changed_at`` (activity-history.md alcance
propuesto); the ORM column is ``TaskHistory.created_at`` — the model has no
"updated_at" (append-only rows). ``TaskHistoryResponse.changed_at`` reads
that column via ``validation_alias`` (design.md, "Correcciones de gate
(2026-07-11)" #4), mirroring ``time_logs.schemas.TimeLogResponse.date``.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskHistoryResponse(BaseModel):
    """A single field change on a task, as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_type: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    changed_at: datetime = Field(validation_alias="created_at")
