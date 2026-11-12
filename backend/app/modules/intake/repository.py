"""Data-access layer for the intake module (change 22-intake-classifier).

Every query is scoped by ``organization_id`` (design.md, "Aislamiento
multi-tenant"). ``IntakeItemRepository`` owns ``intake_items`` + ``intake_runs``
(Fase 2); ``IntakeRuleRepository``/``IntakeSettingsRepository`` are added in
Fases 3/5.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.intake.models import IntakeItem, IntakeRule, IntakeRun, IntakeSettings
from app.shared.enums import IntakeItemStatus, IntakeItemType

_SIGNAL_COLUMNS = ("conversation_id", "internet_message_id", "direction")


def _refresh_signals(existing: IntakeItem, incoming: IntakeItem) -> None:
    """Copy the observed thread signals of ``incoming`` onto ``existing``.

    A value the new read did not observe (``None``) never erases a known one,
    and ``raw_payload`` only gains/updates the keys the new read carries —
    the original payload is never shrunk.
    """

    for column in _SIGNAL_COLUMNS:
        value = getattr(incoming, column)
        if value is not None and getattr(existing, column) != value:
            setattr(existing, column, value)

    current = existing.raw_payload or {}
    observed = {
        key: value
        for key, value in (incoming.raw_payload or {}).items()
        if value is not None and value != [] and current.get(key) != value
    }
    if observed:
        # A NEW dict so SQLAlchemy sees the JSONB change (no MutableDict here).
        existing.raw_payload = {**current, **observed}


class IntakeItemRepository:
    """Async repository encapsulating ``intake_items``/``intake_runs``
    persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_external_id(
        self, organization_id: uuid.UUID, connector_id: uuid.UUID, external_id: str
    ) -> IntakeItem | None:
        """Return the existing item for the idempotency key, or ``None``.

        Scoped only by ``is_active`` implicitly NOT applied here on purpose:
        idempotency must find a soft-deleted row too (it still occupies the
        ``UNIQUE(organization_id, connector_id, external_id)`` slot).
        """

        result = await self.db.execute(
            select(IntakeItem).where(
                IntakeItem.organization_id == organization_id,
                IntakeItem.connector_id == connector_id,
                IntakeItem.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_item(self, item: IntakeItem) -> tuple[IntakeItem, bool]:
        """Insert ``item`` if its idempotency key is new; otherwise refresh
        ONLY the thread signals of the EXISTING row (design.md,
        "Idempotencia"; C03).

        Returns ``(item, created)`` — ``created=False`` on a duplicate lets
        the caller increment ``IntakeRun.items_duplicated`` without a second
        query. Never re-classifies or overwrites the triage state of an
        existing (possibly already ``converted``) row: ``status``,
        ``created_task_id``, ``matched_rule_id`` and ``classified_at`` are
        left as they are (intake-items spec, "Re-pull de un ítem ya
        convertido no crea una segunda tarea"). Re-ingesting a window is
        therefore the backfill path for rows stored before the signals
        existed. Changes are staged on the session; the caller commits.
        """

        existing = await self.get_by_external_id(
            item.organization_id, item.connector_id, item.external_id
        )
        if existing is not None:
            _refresh_signals(existing, item)
            return existing, False

        self.db.add(item)
        await self.db.flush()
        return item, True

    async def get_item(self, organization_id: uuid.UUID, item_id: uuid.UUID) -> IntakeItem | None:
        """Return a single active item scoped to the organization, or ``None``."""

        result = await self.db.execute(
            select(IntakeItem).where(
                IntakeItem.id == item_id,
                IntakeItem.organization_id == organization_id,
                IntakeItem.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_items(
        self,
        organization_id: uuid.UUID,
        *,
        status: IntakeItemStatus | None = None,
        item_type: IntakeItemType | None = None,
        connector_id: uuid.UUID | None = None,
    ) -> Sequence[IntakeItem]:
        """Return the org's active items, newest first, honoring filters."""

        stmt = select(IntakeItem).where(
            IntakeItem.organization_id == organization_id,
            IntakeItem.is_active.is_(True),
        )
        if status is not None:
            stmt = stmt.where(IntakeItem.status == status)
        if item_type is not None:
            stmt = stmt.where(IntakeItem.item_type == item_type)
        if connector_id is not None:
            stmt = stmt.where(IntakeItem.connector_id == connector_id)
        stmt = stmt.order_by(IntakeItem.occurred_at.desc())

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def save_item(self, item: IntakeItem, *, commit: bool = True) -> IntakeItem:
        """Persist pending changes on an attached item (classification result).

        ``commit=True`` (default) commits — matches the sibling repositories
        (``IntakeRuleRepository.save``/``IntakeSettingsRepository.save``) and
        the "write flows seal their own transaction" convention
        (``connectors/repository.py``'s ``_commit_or_flush``). ``commit=False``
        only flushes: used by ``classify_and_convert``'s auto-ingest path,
        whose caller (``pull``'s ``close_run``) seals items + run in ONE
        commit — see ``IntakeService.classify_and_convert``.
        """

        if commit:
            await self.db.commit()
            await self.db.refresh(item)
        else:
            await self.db.flush()
        return item

    # -- intake_runs ---------------------------------------------------------

    async def create_run(
        self,
        *,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        connected_account_id: uuid.UUID | None,
        started_at: datetime,
        actor_id: uuid.UUID | None = None,
    ) -> IntakeRun:
        """Open a new ``IntakeRun`` (flushed, not committed — the caller
        seals the whole account's processing in one commit, see
        ``IntakeService._pull_account``)."""

        run = IntakeRun(
            organization_id=organization_id,
            connector_id=connector_id,
            connected_account_id=connected_account_id,
            started_at=started_at,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    async def close_run(self, run: IntakeRun) -> IntakeRun:
        """Commit the run's final counts/status (seals the account's
        processing transaction — items + run in ONE commit)."""

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(self, organization_id: uuid.UUID) -> Sequence[IntakeRun]:
        """Return the org's ingestion bitácora, newest first."""

        result = await self.db.execute(
            select(IntakeRun)
            .where(IntakeRun.organization_id == organization_id)
            .order_by(IntakeRun.started_at.desc())
        )
        return result.scalars().all()


class IntakeRuleRepository:
    """Async repository encapsulating ``intake_rules`` persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, rule: IntakeRule) -> IntakeRule:
        """Persist a new rule and return the refreshed instance."""

        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        return rule

    async def get(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> IntakeRule | None:
        """Return a single active (not soft-deleted) rule scoped to the
        organization, or ``None`` — regardless of ``is_active`` toggled via
        ``PATCH`` (a deactivated-but-not-deleted rule is still gettable)."""

        result = await self.db.execute(
            select(IntakeRule).where(
                IntakeRule.id == rule_id,
                IntakeRule.organization_id == organization_id,
                IntakeRule.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_rules(self, organization_id: uuid.UUID) -> Sequence[IntakeRule]:
        """Return every non-deleted rule of the org (active or deactivated),
        ordered by ``rule_order`` — listings show BOTH so an admin can
        re-activate a deactivated rule via ``PATCH``."""

        result = await self.db.execute(
            select(IntakeRule)
            .where(
                IntakeRule.organization_id == organization_id,
                IntakeRule.deleted_at.is_(None),
            )
            .order_by(IntakeRule.rule_order.asc())
        )
        return result.scalars().all()

    async def list_active_rules_ordered(self, organization_id: uuid.UUID) -> Sequence[IntakeRule]:
        """Return ONLY active rules, ordered by ``rule_order`` ascending —
        exactly what ``RuleBasedClassifier.classify`` expects (intake-rules
        spec, "Precedencia determinista por orden de regla")."""

        result = await self.db.execute(
            select(IntakeRule)
            .where(
                IntakeRule.organization_id == organization_id,
                IntakeRule.is_active.is_(True),
            )
            .order_by(IntakeRule.rule_order.asc())
        )
        return result.scalars().all()

    async def save(self, rule: IntakeRule) -> IntakeRule:
        """Flush pending changes on an attached rule and return it refreshed."""

        await self.db.commit()
        await self.db.refresh(rule)
        return rule


class IntakeSettingsRepository:
    """Async repository encapsulating ``intake_settings`` persistence — ONE
    row per organization (``UNIQUE(organization_id)``, design.md "Tablas")."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, organization_id: uuid.UUID) -> IntakeSettings | None:
        result = await self.db.execute(
            select(IntakeSettings).where(IntakeSettings.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, organization_id: uuid.UUID) -> IntakeSettings:
        """Return the org's settings row, creating an empty one (committed)
        the FIRST time it is needed (design.md, "Proyecto por defecto de la
        organización" — lazy resolution)."""

        existing = await self.get(organization_id)
        if existing is not None:
            return existing

        settings_row = IntakeSettings(organization_id=organization_id)
        self.db.add(settings_row)
        await self.db.commit()
        await self.db.refresh(settings_row)
        return settings_row

    async def save(self, settings_row: IntakeSettings) -> IntakeSettings:
        """Flush pending changes on an attached settings row."""

        await self.db.commit()
        await self.db.refresh(settings_row)
        return settings_row
