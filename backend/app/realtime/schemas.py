"""Versioned WebSocket message envelope shared by every realtime message."""
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

#: Catalog of message types the realtime channel emits.
EnvelopeType = Literal["connection.ack", "notification.created", "ping", "pong", "error"]


class Envelope(BaseModel):
    """``{v, type, ts, data}`` — the shape every WebSocket message follows."""

    v: int = 1
    type: EnvelopeType
    ts: str
    data: Any = None


def make_envelope(type: EnvelopeType, data: Any = None) -> dict:
    """Build a JSON-ready envelope dict: ``{v: 1, type, ts, data}``."""

    return Envelope(type=type, ts=datetime.now(UTC).isoformat(), data=data).model_dump()
