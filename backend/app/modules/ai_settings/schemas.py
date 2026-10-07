"""Request/response models for ``/ai`` (C04). No response model has a field
that could carry the API key: only ``has_api_key`` and ``api_key_last4``."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReasoningEffort = Literal["none", "low", "medium", "high"]
SettingsSource = Literal["organization", "global", "default"]


class AiSettingsUpdate(BaseModel):
    """``PUT /ai/settings`` body (also the optional ``POST /ai/settings/test``
    proposal). ``api_key``: omitted or blank = keep the stored key (only
    while the destination URL stays the same); ``null`` = delete it."""

    model_config = ConfigDict(extra="forbid")

    preset: str = Field(min_length=1, max_length=32)
    base_url: str | None = Field(default=None, max_length=500)
    chat_model: str | None = Field(default=None, max_length=200)
    embedding_model: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default="", max_length=500)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    temperature: float = Field(default=0.0, ge=0, le=2)
    reasoning_effort: ReasoningEffort | None = "none"
    num_ctx: int | None = Field(default=None, ge=256, le=262144)
    enabled: bool = True


class AiSettingsRead(BaseModel):
    """Effective configuration and where it comes from (``source``)."""

    preset: str
    preset_label: str
    locality: Literal["local", "external"]
    base_url: str
    chat_model: str
    embedding_model: str | None
    has_api_key: bool
    api_key_last4: str | None
    timeout_seconds: float
    max_tokens: int
    temperature: float
    reasoning_effort: ReasoningEffort | None
    num_ctx: int | None
    enabled: bool
    source: SettingsSource
    updated_at: datetime | None = None
    updated_by: uuid.UUID | None = None


class AiPresetRead(BaseModel):
    key: str
    label: str
    locality: Literal["local", "external"]
    base_url: str | None
    base_url_editable: bool
    chat_model: str
    embedding_model: str | None
    requires_api_key: bool


class AiConnectionError(BaseModel):
    stage: Literal["chat", "embeddings"]
    code: str
    detail: str


class AiConnectionTestResult(BaseModel):
    ok: bool
    preset: str
    locality: Literal["local", "external"]
    chat_model: str
    chat_latency_ms: int | None = None
    embedding_model: str | None = None
    embedding_latency_ms: int | None = None
    embedding_dimensions: int | None = None
    error: AiConnectionError | None = None
