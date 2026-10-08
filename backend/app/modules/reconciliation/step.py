"""Step 3 of daily_sync (C02): run the classification channel (C05).

Replaces the no-op extension point. Counts go to the run record; when the
LLM provider was down the step raises ``StepFailed`` WITH those counts, so
the run shows what was still saved (deterministic state, key candidates)
and the other steps are unaffected.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduled_sync.service import StepFailed, StepSkipped

from .repository import SqlReconciliationRepository
from .rules import CompiledRules, load_rules_for_org
from .service import ClassifierBackend, ReconciliationConfig, ReconciliationService


class WindowClassifier(Protocol):
    async def classify_window(
        self, organization_id: uuid.UUID, since: datetime
    ) -> dict[str, Any]: ...


class ReconciliationClassificationStep:
    def __init__(
        self,
        service_factory: Callable[[], WindowClassifier],
        *,
        enabled: bool,
        window_days: int,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._service_factory = service_factory
        self._enabled = enabled
        self._window = timedelta(days=window_days)
        self._clock = clock

    async def __call__(self, organization_id: uuid.UUID) -> dict[str, Any]:
        if not self._enabled:
            raise StepSkipped("La clasificación de correos está desactivada.")
        since = self._clock() - self._window
        counts = await self._service_factory().classify_window(organization_id, since)
        if counts.get("llm_error"):
            raise StepFailed(
                f"El proveedor de IA no respondió ({counts['llm_error']}); se guardó el estado "
                "de los hilos y las candidatas por clave.",
                counts,
            )
        return counts


def build_reconciliation_service(session: AsyncSession, settings: Any) -> ReconciliationService:
    from app.modules.ai_settings.service import get_llm_for_org

    async def backend_factory(organization_id: uuid.UUID) -> ClassifierBackend:
        port, resolved = await get_llm_for_org(organization_id, session)
        name = resolved.config.embedding_model if resolved.config else None
        # The cache key carries the provider: same model name, other vectors.
        embedding_model = f"{resolved.preset}/{name}" if name else None
        return ClassifierBackend(
            port=port, embedding_model=embedding_model, provider=resolved.preset
        )

    repository = SqlReconciliationRepository(session)

    async def rules_factory(organization_id: uuid.UUID) -> CompiledRules:
        slug = await repository.find_organization_slug(organization_id) or ""
        return load_rules_for_org(getattr(settings, "RECONCILIATION_RULES_PATH", ""), slug)

    return ReconciliationService(
        repository,
        backend_factory=backend_factory,
        rules_factory=rules_factory,
        commit=session.commit,
        config=ReconciliationConfig.from_settings(settings),
    )


def session_classification_step(
    session: AsyncSession, settings: Any
) -> ReconciliationClassificationStep:
    return ReconciliationClassificationStep(
        lambda: build_reconciliation_service(session, settings),
        enabled=settings.RECONCILIATION_ENABLED,
        window_days=settings.RECONCILIATION_WINDOW_DAYS,
    )
