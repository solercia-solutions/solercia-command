"""Pydantic schemas for the boards module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BoardColumnRead(BaseModel):
    """A board column as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    board_id: uuid.UUID
    name: str
    status_key: str
    order: int
    wip_limit: int | None = None
    created_at: datetime


class BoardRead(BaseModel):
    """A project's board with its columns, as returned by the API.

    The column set is a bounded, nested collection — never paginated (see
    design.md, "Exención documentada del contrato de paginación de 02").
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    columns: list[BoardColumnRead] = []
    created_at: datetime


class BoardColumnRename(BaseModel):
    """Payload to rename a column. ``status_key`` is immutable and never changes."""

    name: str = Field(min_length=1, max_length=120)


class BoardColumnsReorder(BaseModel):
    """Payload to reorder a board's columns.

    ``ordered_ids`` MUST contain exactly the board's current active column
    ids, in the desired display order — a partial or foreign set is rejected.
    """

    ordered_ids: list[uuid.UUID]


class BoardColumnCreate(BaseModel):
    """Payload to add a new column to a board.

    ``status_key`` is derived from ``name`` (a unique slug per board) and
    never accepted from the client — it becomes immutable once created.
    """

    name: str = Field(min_length=1, max_length=120)
    wip_limit: int | None = Field(default=None, ge=1)
