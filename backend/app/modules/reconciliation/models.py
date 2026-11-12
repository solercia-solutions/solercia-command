"""``task_embeddings`` and ``intake_proposals`` (C05, migration 0032).

``TaskEmbedding`` caches one vector per (task, embedding model); the
``text_hash`` of the embedded text says when it must be recomputed. Vectors
are ``REAL[]`` (no pgvector: cosine runs in Python).

``IntakeProposal`` is what the classifier PROPOSES for one mail thread.
``status`` is its lifecycle (``propuesta`` → ``aceptada``/``descartada``),
so there is no soft delete. A partial unique index keeps at most ONE open
proposal per (organization, thread); re-classifying updates it in place.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    REAL,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, TenantMixin, TimestampMixin

PROPOSAL_STATUSES = ("propuesta", "aceptada", "descartada")
RELATIONS = ("tarea_existente", "tarea_nueva", "irrelevante")


class TaskEmbedding(PkMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "task_embeddings"
    __table_args__ = (UniqueConstraint("task_id", "model", name="uq_task_embeddings_task_model"),)

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector: Mapped[list[float]] = mapped_column(ARRAY(REAL), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)


class IntakeProposal(PkMixin, TimestampMixin, AuditMixin, TenantMixin, Base):
    __tablename__ = "intake_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('propuesta', 'aceptada', 'descartada')",
            name="ck_intake_proposals_status",
        ),
        CheckConstraint(
            "thread_state IN ('respondido', 'pendiente_respuesta', 'solo_saliente')",
            name="ck_intake_proposals_thread_state",
        ),
        CheckConstraint(
            "relation IS NULL OR relation IN ('tarea_existente', 'tarea_nueva', 'irrelevante')",
            name="ck_intake_proposals_relation",
        ),
        Index(
            "uq_intake_proposals_open_thread",
            "organization_id",
            "conversation_key",
            unique=True,
            postgresql_where=text("status = 'propuesta'"),
        ),
        Index("ix_intake_proposals_org_status", "organization_id", "status"),
        Index("ix_intake_proposals_org_task", "organization_id", "task_id"),
    )

    #: ``conv:<conversation_id>`` or ``subj:<hash>`` (see ``threads.py``).
    conversation_key: Mapped[str] = mapped_column(Text, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Sorted ``intake_items.id`` (as text) of the thread when classified.
    item_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    thread_state: Mapped[str] = mapped_column(String(24), nullable=False)
    #: ``NULL`` while the LLM has not classified the thread.
    relation: Mapped[str | None] = mapped_column(String(24), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Validated LLM output (``prompt.validate_classification`` payload).
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidates: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Error code of the last failed classification attempt (never its text).
    classification_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="propuesta", server_default="propuesta"
    )
    created_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
