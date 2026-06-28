"""Pydantic schemas for the attachments module."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentRead(BaseModel):
    """Attachment metadata returned by the API (no binary content)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    original_name: str
    content_type: str
    size_bytes: int
    uploaded_by: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
