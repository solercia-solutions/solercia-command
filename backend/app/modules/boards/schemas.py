"""Pydantic schemas for the boards module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
