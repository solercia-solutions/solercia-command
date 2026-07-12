"""Pydantic schemas for the task_links module."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TaskDependencyLink(BaseModel):
    """Payload to link the path task to ``related_task_id``.

    ``type="blocks"`` (default): the path task blocks ``related_task_id``.
    ``type="is_blocked_by"``: ``related_task_id`` blocks the path task — the
    edge is inverted before persisting to the canonical ``blocks`` direction
    (design.md gate correction #2).
    """

    related_task_id: uuid.UUID
    type: Literal["blocks", "is_blocked_by"] = "blocks"


class TaskDependencyRead(BaseModel):
    """A dependency edge as seen from the perspective of the queried task."""

    id: uuid.UUID
    related_task_id: uuid.UUID
    direction: Literal["blocks", "is_blocked_by"]
    created_at: datetime


class BlockerRef(BaseModel):
    """A reference to a task currently blocking another task."""

    model_config = ConfigDict(from_attributes=True)

    task_id: uuid.UUID
    title: str
