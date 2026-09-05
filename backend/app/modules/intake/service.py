"""Business logic for the intake module (change 22-intake-classifier).

``pull()`` orchestrates the read→store cycle over the 14's read-only ports:
per connected account, read every capability the adapter declares that maps
to an ``IntakeItemType``, upsert each DTO idempotently, and close the
account's ``IntakeRun`` with its counts. A failure in ONE account (unreadable
token, provider not registered) closes THAT account's run in ``error``
WITHOUT blocking the others (design.md Data Flow; intake-items spec, "Error
en una cuenta no bloquea las demás").

Classification wiring (``classify_and_convert`` at the close of each
account's ingestion) is added in Fase 4 — this file stays storage-only here.
"""

import dataclasses
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations import crypto
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import AccessContext, Capability, CredentialKind
from app.integrations.registry import get_adapter
from app.modules.connectors.models import Connector
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.intake.classifier import RuleBasedClassifier
from app.modules.intake.models import IntakeItem, IntakeRule, IntakeRun
from app.modules.intake.repository import (
    IntakeItemRepository,
    IntakeRuleRepository,
    IntakeSettingsRepository,
)
from app.modules.intake.schemas import (
    IntakeConvertRequest,
    IntakeItemRead,
    IntakeRuleCreate,
    IntakeRuleRead,
    IntakeRuleUpdate,
    IntakeRunRead,
    IntakeSettingsRead,
    IntakeSettingsUpdate,
)
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import TaskService
from app.modules.tasks.sources import KNOWN_TASK_SOURCES
from app.shared.enums import IntakeItemStatus, IntakeItemType, IntakeRunStatus, Methodology
from app.shared.exceptions import AppException

logger = logging.getLogger("solercia.intake")

# Truncation guard for the created Task's description — MailMessage.snippet
# is unbounded Text, TaskCreate.description caps at 4000 (schemas.py).
_TASK_DESCRIPTION_MAX_CHARS = 2000

_ANCHOR_CONFLICT_CODE = "task_external_anchor_conflict"

# One IntakeItemType per read capability of the 14 (intake-items spec,
# "mapeo 1:1 con las 5 capacidades de puerto del 14"). `external_resources`
# (change 19-mcp-connector) is deliberately absent: it has no intake mapping.
_CAPABILITY_TO_ITEM_TYPE: dict[Capability, IntakeItemType] = {
    Capability.mail: IntakeItemType.email,
    Capability.calendar: IntakeItemType.calendar_event,
    Capability.external_tasks: IntakeItemType.external_task,
    Capability.meeting_notes: IntakeItemType.meeting_note,
    Capability.tickets: IntakeItemType.ticket,
}


def _jsonable(value: Any) -> Any:
    """Recursively convert ``value`` into a JSON-serializable structure.

    DTOs (``app/integrations/dtos.py``) are frozen dataclasses carrying
    ``datetime``/``tuple`` fields — neither is JSON-serializable as-is, so
    ``raw_payload`` (JSONB) needs this pass before persisting (design.md,
    "el raw_payload original DEBE conservarse").
    """

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(val) for val in value]
    return value


async def _fetch_for_capability(
    port: object,
    capability: Capability,
    ctx: AccessContext,
    limit: int,
    *,
    since: datetime | None = None,
) -> Sequence[Any]:
    """Dispatch to the correctly-named method of ``port``'s Protocol.

    Each read Protocol (``MailReaderPort``/``CalendarReaderPort``/...) names
    its single method differently — this is the ONE place that knows the
    mapping, so ``pull`` itself stays capability-agnostic. ``since`` is the
    Protocols' shared optional window; ``None`` keeps each port's default.
    """

    if capability == Capability.mail:
        return await port.list_messages(ctx, since=since, limit=limit)  # type: ignore[attr-defined]
    if capability == Capability.calendar:
        return await port.list_events(ctx, since=since, limit=limit)  # type: ignore[attr-defined]
    if capability == Capability.external_tasks:
        return await port.list_tasks(ctx, since=since, limit=limit)  # type: ignore[attr-defined]
    if capability == Capability.meeting_notes:
        return await port.list_notes(ctx, since=since, limit=limit)  # type: ignore[attr-defined]
    if capability == Capability.tickets:
        return await port.list_tickets(ctx, since=since, limit=limit)  # type: ignore[attr-defined]
    raise AssertionError(f"Capacidad sin mapeo de intake: {capability}")  # pragma: no cover


def _external_origin(item: IntakeItem) -> tuple[str, str] | None:
    """The ``(source, external_key)`` anchor a converted insumo hands to
    ``TaskService.create_task`` — provenance that makes a second conversion of
    the same message a detectable conflict instead of a duplicate task.

    Only a provider the task vocabulary knows (``KNOWN_TASK_SOURCES``) is
    anchored: an unknown one would make ``validate_task_source`` reject
    EVERY conversion of that connector, which is worse than an unanchored
    task. Empty ids are never anchored either.
    """

    source = (item.source_provider or "").strip()
    key = (item.external_id or "").strip()
    if not source or not key or source not in KNOWN_TASK_SOURCES:
        return None
    return source, key


def _failure_code(failure: Exception) -> str:
    code = getattr(failure, "code", None)
    return code if isinstance(code, str) and code else "unexpected_error"


def _failure_detail(failure: Exception) -> str:
    detail = getattr(failure, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail
    text = str(failure).strip()
    return text or failure.__class__.__name__


@dataclasses.dataclass(frozen=True)
class IntakeRunOutcome:
    """One ``IntakeRun`` plus WHY it failed, for callers that must tell "the
    person has to log in again" from "the provider is down" — the run row
    itself only records ``status=error`` (no migration for a reason column).

    ``anchor_conflicts`` counts insumos left in triage because a task with
    their external provenance already existed.
    """

    run: IntakeRunRead
    error_code: str | None = None
    error_detail: str | None = None
    anchor_conflicts: int = 0


def _dto_to_item(
    dto: Any,
    *,
    capability: Capability,
    organization_id: uuid.UUID,
    connector: Connector,
    connected_account_id: uuid.UUID | None,
    source_provider: str,
) -> IntakeItem:
    """Normalize one capability DTO (design.md Data Flow, "DTOs del 14")
    into an unpersisted ``IntakeItem`` row, dispatched by ``capability``."""

    item_type = _CAPABILITY_TO_ITEM_TYPE[capability]
    raw_payload = _jsonable(dataclasses.asdict(dto))

    if capability == Capability.mail:
        title, snippet, origin_actor, occurred_at = (
            dto.subject,
            dto.snippet,
            dto.sender,
            dto.received_at,
        )
    elif capability == Capability.calendar:
        title, snippet, origin_actor, occurred_at = (
            dto.title,
            dto.location,
            dto.organizer,
            dto.starts_at,
        )
    elif capability == Capability.external_tasks:
        title, snippet, origin_actor, occurred_at = (
            dto.title,
            dto.status,
            dto.assignee or "",
            dto.due_at or datetime.now(UTC),
        )
    elif capability == Capability.meeting_notes:
        title = dto.meeting_title
        snippet = dto.transcript[:500] if dto.transcript else None
        origin_actor = dto.participants[0] if dto.participants else ""
        occurred_at = dto.occurred_at
    else:  # Capability.tickets
        title, snippet, origin_actor, occurred_at = (
            f"{dto.key}: {dto.summary}",
            dto.status,
            dto.requester or "",
            dto.created_at,
        )

    return IntakeItem(
        organization_id=organization_id,
        source_provider=source_provider,
        connector_id=connector.id,
        connected_account_id=connected_account_id,
        item_type=item_type,
        external_id=dto.external_id,
        title=title,
        snippet=snippet,
        origin_actor=origin_actor,
        occurred_at=occurred_at,
        raw_payload=raw_payload,
        status=IntakeItemStatus.pending,
    )


def _build_task_description(item: IntakeItem) -> str:
    """Compose the created ``Task.description`` from the origin insumo
    (design.md Data Flow) — snippet plus a traceable "Origen" line, capped
    well under ``TaskCreate.description``'s 4000-char limit."""

    snippet = (item.snippet or "").strip()
    origin_line = f"Origen: {item.source_provider} — {item.origin_actor}"
    description = f"{snippet}\n\n{origin_line}" if snippet else origin_line
    return description[:_TASK_DESCRIPTION_MAX_CHARS]


class IntakeService:
    """Orchestrates intake use-cases for a single organization scope."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.items = IntakeItemRepository(db)
        self.connectors = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)
        self.rules = IntakeRuleRepository(db)
        self.settings_repo = IntakeSettingsRepository(db)
        self.classifier = RuleBasedClassifier()

    async def pull(
        self,
        organization_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        connector_id: uuid.UUID | None = None,
        since: datetime | None = None,
    ) -> list[IntakeRunRead]:
        """Ingest every connected account of the organization's connectors.

        One ``IntakeRun`` per (connector, account) pair — a connector with
        zero connected accounts is skipped entirely (nothing to read yet).
        ``connector_id`` restricts the pull to ONE connector of the
        organization (a foreign or unknown id simply reads nothing);
        ``since`` bounds every read window. Both default to the historical
        behaviour: every connector, each port's own default window.
        """

        outcomes = await self.pull_outcomes(
            organization_id, actor_id=actor_id, connector_id=connector_id, since=since
        )
        return [outcome.run for outcome in outcomes]

    async def pull_outcomes(
        self,
        organization_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        connector_id: uuid.UUID | None = None,
        since: datetime | None = None,
    ) -> list[IntakeRunOutcome]:
        """:meth:`pull`, keeping the failure behind each ``status=error`` run
        (see :class:`IntakeRunOutcome`) for callers that map it further."""

        connectors = await self.connectors.list_connectors(organization_id)
        outcomes: list[IntakeRunOutcome] = []
        for connector in connectors:
            if connector_id is not None and connector.id != connector_id:
                continue
            accounts = await self.accounts.list_accounts(connector.id, organization_id)
            for account in accounts:
                outcome = await self._pull_account(
                    organization_id, connector, account.id, actor_id=actor_id, since=since
                )
                outcomes.append(outcome)
        return outcomes

    async def _pull_account(
        self,
        organization_id: uuid.UUID,
        connector: Connector,
        connected_account_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None,
        since: datetime | None = None,
    ) -> IntakeRunOutcome:
        """Ingest ONE connected account, isolated from every other account's
        outcome (intake-items spec, "Error en una cuenta no bloquea las
        demás")."""

        run = await self.items.create_run(
            organization_id=organization_id,
            connector_id=connector.id,
            connected_account_id=connected_account_id,
            started_at=datetime.now(UTC),
            actor_id=actor_id,
        )

        failure: Exception | None = None
        anchor_conflicts = 0
        try:
            anchor_conflicts = await self._ingest_account_items(
                organization_id, connector, connected_account_id, run, since=since
            )
            run.status = IntakeRunStatus.completed
        except Exception as exc:  # noqa: BLE001 - isolate this account, never re-raise
            run.status = IntakeRunStatus.error
            failure = exc

        run.finished_at = datetime.now(UTC)
        closed = await self.items.close_run(run)
        return IntakeRunOutcome(
            run=IntakeRunRead.model_validate(closed),
            error_code=_failure_code(failure) if failure is not None else None,
            error_detail=_failure_detail(failure) if failure is not None else None,
            anchor_conflicts=anchor_conflicts,
        )

    async def _ingest_account_items(
        self,
        organization_id: uuid.UUID,
        connector: Connector,
        connected_account_id: uuid.UUID,
        run: IntakeRun,
        *,
        since: datetime | None = None,
    ) -> int:
        """Read, store and classify one account's items; returns how many new
        items were left in triage because their external anchor already
        belonged to a task."""

        adapter = get_adapter(connector.provider)
        if adapter is None:
            raise AppException(
                "El proveedor del conector no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )

        ctx = await self._build_access_context(organization_id, connector, connected_account_id)

        new_items: list[IntakeItem] = []
        for capability in _CAPABILITY_TO_ITEM_TYPE:
            if capability not in adapter.capabilities:
                continue
            port = adapter.port_for(capability)
            if port is None:
                continue

            dtos = await _fetch_for_capability(
                port, capability, ctx, settings.INTAKE_PULL_MAX_ITEMS, since=since
            )
            # GLPI-style service-level credentials (api_token) are not a
            # personal mailbox/calendar — items from such a connector are
            # NOT attributed to the shared account (intake-items spec,
            # "Insumo de conector sin cuenta individual").
            item_account_id = (
                connected_account_id
                if connector.credential_kind == CredentialKind.oauth
                else None
            )
            for dto in dtos:
                item = _dto_to_item(
                    dto,
                    capability=capability,
                    organization_id=organization_id,
                    connector=connector,
                    connected_account_id=item_account_id,
                    source_provider=connector.provider,
                )
                stored_item, created = await self.items.upsert_item(item)
                run.items_fetched += 1
                if created:
                    run.items_new += 1
                    new_items.append(stored_item)
                else:
                    run.items_duplicated += 1

        # Classification runs ONCE, at the close of THIS account's ingestion
        # (tasks.md T4.3) — never on re-pulled duplicates (intake-classifier
        # spec, "Ejecución del clasificador tras cada ingesta" evaluates only
        # the items stored by the CURRENT execution).
        anchor_conflicts = 0
        for item in new_items:
            if await self.classify_and_convert(organization_id, item):
                anchor_conflicts += 1
            if item.status == IntakeItemStatus.converted:
                run.items_converted += 1
        return anchor_conflicts

    async def _build_access_context(
        self, organization_id: uuid.UUID, connector: Connector, connected_account_id: uuid.UUID
    ) -> AccessContext:
        """Decrypt the account's credentials into an ``AccessContext``.

        Refreshes PROACTIVELY, BEFORE any read, when ``expires_at`` is in
        the past (delta specs/connectors/spec.md, "Token vencido se refresca
        y persiste antes de leer") — a token still valid never triggers
        ``adapter.oauth.refresh`` (delta, "Token vigente no dispara
        refresco"). The RESULTING context also carries the
        ``on_tokens_refreshed`` sink so an adapter that refreshes silently
        MID-read (e.g. on its own 401→retry, changes 15/16) persists that
        rotation too — both paths converge on the SAME
        ``save_refreshed_credentials`` (change 22 materializes the 14's
        addendum, see ``app/integrations/ports.py::AccessContext``).
        """

        credentials = await self.accounts.get_credentials(connected_account_id)
        if credentials is None:
            raise AppException(
                "La cuenta conectada no tiene credenciales registradas.",
                code="credentials_not_found",
                status_code=404,
            )

        async def _on_tokens_refreshed(tokens: OAuthTokens) -> None:
            await self.accounts.save_refreshed_credentials(
                connected_account_id, organization_id, tokens
            )

        now = datetime.now(UTC)
        if credentials.expires_at is not None and credentials.expires_at <= now:
            adapter = get_adapter(connector.provider)
            if adapter is None or adapter.oauth is None:
                raise AppException(
                    "El proveedor del conector no está disponible para refrescar el token.",
                    code="provider_not_registered",
                    status_code=404,
                )
            if not credentials.refresh_token_enc:
                raise AppException(
                    "La cuenta conectada no tiene un refresh_token disponible.",
                    code="refresh_token_missing",
                    status_code=422,
                )
            refresh_token_plain = crypto.decrypt(credentials.refresh_token_enc)
            # A failing refresh raises here and propagates to `_pull_account`'s
            # try/except — existing credentials are NEVER touched (delta,
            # "Refresco fallido no persiste credenciales corruptas").
            new_tokens = await adapter.oauth.refresh(refresh_token_plain)
            await _on_tokens_refreshed(new_tokens)
            return AccessContext(
                access_token=new_tokens.access_token,
                refresh_token=new_tokens.refresh_token,
                scopes=tuple(new_tokens.scopes or ()),
                on_tokens_refreshed=_on_tokens_refreshed,
            )

        access_token = crypto.decrypt(credentials.access_token_enc)
        refresh_token = (
            crypto.decrypt(credentials.refresh_token_enc)
            if credentials.refresh_token_enc
            else None
        )
        return AccessContext(
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=tuple(credentials.scopes or []),
            on_tokens_refreshed=_on_tokens_refreshed,
        )

    # -- reads -----------------------------------------------------------

    async def list_items(
        self,
        organization_id: uuid.UUID,
        *,
        status: IntakeItemStatus | None = None,
        item_type: IntakeItemType | None = None,
        connector_id: uuid.UUID | None = None,
    ) -> list[IntakeItemRead]:
        rows = await self.items.list_items(
            organization_id, status=status, item_type=item_type, connector_id=connector_id
        )
        return [IntakeItemRead.model_validate(row) for row in rows]

    async def get_item(
        self, organization_id: uuid.UUID, item_id: uuid.UUID
    ) -> IntakeItemRead:
        item = await self.items.get_item(organization_id, item_id)
        if item is None:
            raise AppException(
                "El insumo no existe o no tienes acceso a él.",
                code="intake_item_not_found",
                status_code=404,
            )
        return IntakeItemRead.model_validate(item)

    async def list_runs(self, organization_id: uuid.UUID) -> list[IntakeRunRead]:
        rows = await self.items.list_runs(organization_id)
        return [IntakeRunRead.model_validate(row) for row in rows]

    # -- intake_rules (Fase 3) --------------------------------------------

    async def create_rule(
        self,
        organization_id: uuid.UUID,
        data: IntakeRuleCreate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> IntakeRuleRead:
        """Create an ``IntakeRule`` — active by default (intake-rules spec,
        "Manager crea una regla ... activa is_active=true por defecto")."""

        rule = IntakeRule(
            organization_id=organization_id,
            name=data.name,
            criteria=[criterion.model_dump() for criterion in data.criteria],
            convert_to_task=data.convert_to_task,
            target_project_id=data.target_project_id,
            task_priority=data.task_priority,
            assignee_id=data.assignee_id,
            rule_order=data.rule_order,
            created_by=actor_id,
            updated_by=actor_id,
        )
        rule = await self.rules.create(rule)
        return IntakeRuleRead.model_validate(rule)

    async def list_rules(self, organization_id: uuid.UUID) -> list[IntakeRuleRead]:
        rows = await self.rules.list_rules(organization_id)
        return [IntakeRuleRead.model_validate(row) for row in rows]

    async def get_rule(
        self, organization_id: uuid.UUID, rule_id: uuid.UUID
    ) -> IntakeRuleRead:
        rule = await self._require_rule(organization_id, rule_id)
        return IntakeRuleRead.model_validate(rule)

    async def update_rule(
        self,
        organization_id: uuid.UUID,
        rule_id: uuid.UUID,
        data: IntakeRuleUpdate,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> IntakeRuleRead:
        """Apply a partial update — ``is_active=false`` deactivates WITHOUT
        soft-deleting (``deleted_at`` stays ``NULL``, see models.py's
        ``IntakeRule`` docstring)."""

        rule = await self._require_rule(organization_id, rule_id)
        changes = data.model_dump(exclude_unset=True)
        if "criteria" in changes and changes["criteria"] is not None:
            changes["criteria"] = [
                criterion if isinstance(criterion, dict) else criterion.model_dump()
                for criterion in changes["criteria"]
            ]
        for field in (
            "name",
            "criteria",
            "convert_to_task",
            "target_project_id",
            "task_priority",
            "assignee_id",
            "rule_order",
            "is_active",
        ):
            if field in changes:
                setattr(rule, field, changes[field])

        rule.updated_by = actor_id
        rule = await self.rules.save(rule)
        return IntakeRuleRead.model_validate(rule)

    async def delete_rule(self, organization_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        """Soft-delete a rule — excluded from BOTH listings and evaluation
        (intake-rules spec, "DELETE DEBE ser borrado suave")."""

        rule = await self._require_rule(organization_id, rule_id)
        rule.is_active = False
        rule.deleted_at = datetime.now(UTC)
        await self.rules.save(rule)

    async def _require_rule(
        self, organization_id: uuid.UUID, rule_id: uuid.UUID
    ) -> IntakeRule:
        rule = await self.rules.get(organization_id, rule_id)
        if rule is None:
            raise AppException(
                "La regla no existe o no tienes acceso a ella.",
                code="intake_rule_not_found",
                status_code=404,
            )
        return rule

    # -- classification + conversion (Fase 4) -----------------------------

    async def classify_and_convert(
        self, organization_id: uuid.UUID, item: IntakeItem
    ) -> bool:
        """Evaluate ``item`` against the org's active rules and, if a rule
        matches with ``convert_to_task=true``, create a real ``Task``
        (intake-classifier spec, "Conversión a tarea cuando una regla casa").

        Mutates ``item`` in place and flushes (``commit=False``) via
        ``IntakeItemRepository.save_item`` — the caller (``pull``'s
        ``close_run``, which commits items + run in ONE transaction) owns
        the transaction boundary. ``convert_manual`` (Fase 5) is a
        DIFFERENT call site that commits per item (``save_item``'s
        default); see its own docstring.

        Returns ``True`` when the conversion was SKIPPED because a task with
        the item's external provenance already exists
        (``task_external_anchor_conflict``): the item stays ``pending`` in
        triage and the run goes on — one duplicate must never abort the
        ingestion of everything else.
        """

        active_rules = await self.rules.list_active_rules_ordered(organization_id)
        matched_rule = self.classifier.classify(item, active_rules)

        if matched_rule is None:
            # intake-classifier spec, "Ítems sin regla coincidente van a
            # triage manual" — stays pending, no matched_rule_id.
            await self.items.save_item(item, commit=False)
            return False

        if not matched_rule.convert_to_task:
            # intake-classifier spec, "Regla con convert_to_task=false no
            # crea tarea" — `ignored`, NEVER reaches the triage queue.
            item.status = IntakeItemStatus.ignored
            await self.items.save_item(item, commit=False)
            return False

        if matched_rule.assignee_id is not None:
            task_repo = TaskRepository(self.db)
            eligible = await task_repo.is_org_member(organization_id, matched_rule.assignee_id)
            if not eligible:
                # intake-classifier spec, "Asignado no elegible bloquea la
                # conversión automática" — stays `pending` in triage, NEVER
                # mutates membership. `matched_rule_id` IS the recorded
                # reason (deviation from design.md, documented in
                # apply-progress: no dedicated `rejection_reason` column
                # exists; the rule that rejected it — and therefore its
                # ineligible `assignee_id` — is fully queryable/consultable
                # via this FK without a new migration).
                item.matched_rule_id = matched_rule.id
                await self.items.save_item(item, commit=False)
                return False

        project_id = matched_rule.target_project_id or await self._ensure_default_project(
            organization_id
        )
        description = _build_task_description(item)
        task_service = TaskService(self.db)
        try:
            task = await task_service.create_task(
                organization_id,
                project_id,
                TaskCreate(
                    title=item.title,
                    description=description,
                    priority=matched_rule.task_priority,
                    assignee_id=matched_rule.assignee_id,
                ),
                external_origin=_external_origin(item),
            )
        except AppException as failure:
            if failure.code != _ANCHOR_CONFLICT_CODE:
                raise
            logger.warning(
                "Insumo con procedencia ya anclada a una tarea; queda en triage: "
                "connector_id=%s external_id=%s",
                item.connector_id,
                item.external_id,
            )
            await self.items.save_item(item, commit=False)
            return True

        item.status = IntakeItemStatus.converted
        item.created_task_id = task.id
        item.matched_rule_id = matched_rule.id
        item.classified_at = datetime.now(UTC)
        await self.items.save_item(item, commit=False)
        return False

    async def _ensure_default_project(self, organization_id: uuid.UUID) -> uuid.UUID:
        """Resolve the org's default project, creating it (lazily, ONCE)
        the first time it is needed (intake-classifier spec, "Proyecto por
        defecto de la organización")."""

        settings_row = await self.settings_repo.get_or_create(organization_id)
        if settings_row.default_project_id is not None:
            return settings_row.default_project_id

        project_name = settings_row.default_project_name or settings.INTAKE_DEFAULT_PROJECT_NAME
        project_service = ProjectService(self.db)
        project = await project_service.create_project(
            organization_id,
            ProjectCreate(name=project_name, methodology=Methodology.planner),
        )

        settings_row.default_project_id = project.id
        await self.settings_repo.save(settings_row)
        return project.id

    # -- manual triage + settings (Fase 5) --------------------------------

    async def convert_manual(
        self,
        organization_id: uuid.UUID,
        item_id: uuid.UUID,
        data: IntakeConvertRequest,
        *,
        actor_id: uuid.UUID | None = None,
    ) -> IntakeItemRead:
        """Manually convert a `pending` ``IntakeItem`` into a `Task` in the
        organization's default project (intake-classifier spec,
        "Reclasificación manual desde triage").

        ``matched_rule_id`` stays ``None`` — this is the ONE signal that
        distinguishes a manual conversion from an automatic one (spec,
        "DEBE dejar matched_rule_id nulo").

        Unlike ``classify_and_convert``, THIS call site has no outer commit
        (the router returns straight after it) — ``save_item`` therefore
        commits (its default), sealing ``item``'s ``converted`` status
        durably before the request's session closes. Without it the
        mutation only lived in a pending transaction that got rolled back
        on session teardown, leaving the item ``pending`` while its `Task`
        stayed committed (orphaned) — a second ``convert_manual`` call
        would then pass the "already converted" guard and create a
        DUPLICATE task (violates "un ítem converted NO DEBE poder
        convertirse de nuevo").
        """

        item = await self.items.get_item(organization_id, item_id)
        if item is None:
            raise AppException(
                "El insumo no existe o no tienes acceso a él.",
                code="intake_item_not_found",
                status_code=404,
            )
        if item.status == IntakeItemStatus.converted:
            raise AppException(
                "Este insumo ya fue convertido en una tarea.",
                code="intake_item_already_converted",
                status_code=422,
            )

        project_id = await self._ensure_default_project(organization_id)
        description = _build_task_description(item)
        task_service = TaskService(self.db)
        # The anchor conflict (409 `task_external_anchor_conflict`) propagates
        # here on purpose: there is no run to keep going, and the person who
        # clicked "convertir" needs to learn that a task already exists.
        task = await task_service.create_task(
            organization_id,
            project_id,
            TaskCreate(
                title=item.title,
                description=description,
                priority=data.priority,
                assignee_id=data.assignee_id,
            ),
            actor_id=actor_id,
            external_origin=_external_origin(item),
        )

        item.status = IntakeItemStatus.converted
        item.created_task_id = task.id
        item.matched_rule_id = None
        item.classified_at = datetime.now(UTC)
        await self.items.save_item(item)
        return IntakeItemRead.model_validate(item)

    async def get_settings(self, organization_id: uuid.UUID) -> IntakeSettingsRead:
        settings_row = await self.settings_repo.get_or_create(organization_id)
        return IntakeSettingsRead.model_validate(settings_row)

    async def update_settings(
        self, organization_id: uuid.UUID, data: IntakeSettingsUpdate
    ) -> IntakeSettingsRead:
        settings_row = await self.settings_repo.get_or_create(organization_id)
        settings_row.default_project_name = data.default_project_name
        settings_row = await self.settings_repo.save(settings_row)
        return IntakeSettingsRead.model_validate(settings_row)
