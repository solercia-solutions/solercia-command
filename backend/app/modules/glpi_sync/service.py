"""Business logic for GLPI assignee homologation (change 17-adapter-glpi).

Two parts:

- The MATCHING CASCADE (Lote 7, UH-R2) — PURE functions, no DB session, no
  HTTP: ``org_users``/``existing_link`` are plain in-memory instances the
  caller resolves beforehand. Cascada determinística (design.md "Algoritmo
  de homologación"): correo exacto normalizado -> documento exacto
  normalizado -> nombre normalizado (``difflib.SequenceMatcher``, NUNCA
  auto-confirma, solo sugiere). Un link ``(connector_id, glpi_user_id)`` ya
  existente salta la cascada completa.
- ``GlpiSyncService`` (Lote 8, UH-R3/UH-R4/UH-R5/UH-R6) — the sync
  orchestration + queue/link persistence: resolves the connector's
  decrypted credentials, calls the registered ``glpi`` adapter's tickets
  port, runs the cascade per assignee and persists the outcome (link OR
  queue header+case).
"""

import json
import logging
import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.glpi.adapter import encode_access_context
from app.integrations.dtos import ExternalPerson, Ticket
from app.integrations.ports import AccessContext, Capability, TicketReaderPort
from app.integrations.registry import get_adapter
from app.modules.connectors.repository import ConnectedAccountRepository, ConnectorRepository
from app.modules.glpi_sync.repository import (
    GlpiUnmatchedRepository,
    GlpiUserLinkRepository,
    is_org_member,
    list_org_user_candidates,
)
from app.modules.glpi_sync.schemas import (
    GlpiUserLinkRead,
    SyncRunResponse,
    UnmatchedAssigneeRead,
)
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MatchMethod, UnmatchedStatus
from app.shared.exceptions import AppException

if TYPE_CHECKING:
    from app.modules.connectors.models import Connector
    from app.modules.glpi_sync.models import GlpiUnmatchedAssignee, GlpiUserLink
    from app.modules.users.models import User

logger = logging.getLogger("solercia.glpi_sync")

# Below this `difflib` similarity ratio, a name is NOT similar enough to
# suggest as a candidate at all (design.md doesn't fix an exact number —
# 0.75 is a deliberately conservative threshold: high enough to exclude
# unrelated names, low enough to still catch minor spelling variance
# between GLPI's `firstname realname` and the platform's four-part name).
_NAME_MATCH_THRESHOLD = 0.75


def norm_email(email: str) -> str:
    """Case-insensitive, whitespace-trimmed email normalization."""

    return email.strip().lower()


def norm_doc(document: str) -> str:
    """Keep only digits — strips dots/dashes/spaces/prefixes (e.g. "CC")
    from a Colombian identity document."""

    return "".join(char for char in document if char.isdigit())


def norm_name(name: str) -> str:
    """Lowercase, accent-stripped (Unicode NFKD), whitespace-collapsed
    normalization — "José  MARÍA" and "jose maria" normalize identically.
    """

    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", without_accents).strip().lower()


def _platform_full_name(user: "User") -> str:
    """GLPI's name is ``firstname realname``; the platform's is the four
    Colombian name parts (design.md "Algoritmo de homologación")."""

    parts = (
        user.primer_nombre,
        user.segundo_nombre,
        user.primer_apellido,
        user.segundo_apellido,
    )
    return " ".join(part for part in parts if part)


@dataclass(frozen=True)
class MatchCandidate:
    """A SUGGESTED (never auto-confirmed) name-match candidate."""

    user_id: uuid.UUID
    score: float
    reason: str = "name"


@dataclass(frozen=True)
class MatchResult:
    """Outcome of running :func:`match_assignee` for one GLPI person.

    ``matched_user_id``/``match_method`` are BOTH set together (an
    auto-confirmed match: ``email``/``document``, or ``skipped=True``
    reusing an existing link's ``match_method=None`` since the cascade
    never actually ran). ``candidates`` is populated ONLY by the name
    level — never alongside a confirmed match.
    """

    matched_user_id: uuid.UUID | None
    match_method: MatchMethod | None
    candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)
    skipped: bool = False


def match_assignee(
    person: ExternalPerson,
    org_users: Sequence["User"],
    existing_link: "GlpiUserLink | None",
) -> MatchResult:
    """Run the determinstic cascade (correo -> documento -> nombre) for one
    GLPI-assigned ``person`` against the organization's ``org_users``.

    An ``existing_link`` for this exact ``(connector_id, glpi_user_id)``
    short-circuits EVERYTHING — the cascade never runs (user-homologation
    spec, "link ya existente ... se salta la cascada completa").
    """

    if existing_link is not None:
        return MatchResult(
            matched_user_id=existing_link.user_id, match_method=None, skipped=True
        )

    if person.email:
        target_email = norm_email(person.email)
        for user in org_users:
            if user.email and norm_email(user.email) == target_email:
                return MatchResult(matched_user_id=user.id, match_method=MatchMethod.email)

    if person.document:
        target_doc = norm_doc(person.document)
        if target_doc:
            for user in org_users:
                if user.numero_documento and norm_doc(user.numero_documento) == target_doc:
                    return MatchResult(
                        matched_user_id=user.id, match_method=MatchMethod.document
                    )

    candidates = _name_candidates(person, org_users)
    return MatchResult(matched_user_id=None, match_method=None, candidates=candidates)


def _name_candidates(
    person: ExternalPerson, org_users: Sequence["User"]
) -> tuple[MatchCandidate, ...]:
    """Level 3 of the cascade — NEVER auto-confirms, only suggests
    candidates ordered by descending similarity score."""

    if not person.display_name:
        return ()

    target_name = norm_name(person.display_name)
    if not target_name:
        return ()

    scored: list[MatchCandidate] = []
    for user in org_users:
        candidate_name = norm_name(_platform_full_name(user))
        if not candidate_name:
            continue
        ratio = SequenceMatcher(None, target_name, candidate_name).ratio()
        if ratio >= _NAME_MATCH_THRESHOLD:
            scored.append(MatchCandidate(user_id=user.id, score=ratio, reason="name"))

    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return tuple(scored)


# Ceiling on how many tickets one `run_sync` call pulls from GLPI —
# deliberately generous (the manual on-demand sync is not paginated by the
# caller) while still bounded so a huge GLPI instance can never make a
# single request hang indefinitely; `GlpiClient`'s own `GLPI_MAX_PAGES`
# provides the hard floor underneath this.
_SYNC_TICKET_LIMIT = 200


class GlpiSyncService:
    """Orchestrates the manual on-demand GLPI sync + unmatched-queue/link
    management for a single organization scope (UH-R3/UH-R4/UH-R5/UH-R6).
    RBAC lives at the router layer (``require_role(admin, manager)``);
    this service assumes the caller already passed that gate.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connectors = ConnectorRepository(db)
        self.accounts = ConnectedAccountRepository(db)
        self.links = GlpiUserLinkRepository(db)
        self.unmatched = GlpiUnmatchedRepository(db)

    # -- Sync ----------------------------------------------------------------

    async def run_sync(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        membership: OrganizationMember,
    ) -> SyncRunResponse:
        """Extract tickets via the registered ``glpi`` adapter and run the
        matching cascade over every assignee (user-homologation spec,
        "Admin dispara la sincronización").

        404 if the connector does not exist, belongs to another
        organization, or is not a ``glpi`` connector (tasks.md T8.3;
        user-homologation spec, "Sincronización sobre conector ajeno").
        """

        connector = await self.connectors.get(organization_id, connector_id)
        if connector is None or connector.provider != "glpi":
            raise AppException(
                "El conector no existe, no tienes acceso a él o no es un "
                "conector GLPI.",
                code="connector_not_found",
                status_code=404,
            )

        adapter = get_adapter("glpi")
        if adapter is None:
            raise AppException(
                "El proveedor GLPI no está disponible.",
                code="provider_not_registered",
                status_code=404,
            )
        untyped_port = adapter.port_for(Capability.tickets)
        if untyped_port is None:
            raise AppException(
                "El adaptador GLPI no soporta la extracción de tickets.",
                code="capability_unavailable",
                status_code=503,
            )
        # `port_for` deliberately returns `object | None` (design.md, "un
        # Protocol por capacidad") — narrow to `TicketReaderPort` here,
        # the ONE place this service touches the adapter's tickets port.
        port = cast(TicketReaderPort, untyped_port)

        ctx = await self._build_access_context(connector)
        tickets = await port.list_tickets(ctx, limit=_SYNC_TICKET_LIMIT)
        org_users = await list_org_user_candidates(self.db, organization_id)

        links_created = 0
        queue_updated = 0
        try:
            for ticket in tickets:
                for person in ticket.assignees:
                    created, queued = await self._homologate_assignee(
                        organization_id, connector.id, person, ticket, org_users, membership
                    )
                    links_created += created
                    queue_updated += queued
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return SyncRunResponse(
            tickets_processed=len(tickets),
            links_created=links_created,
            queue_updated=queue_updated,
        )

    async def _homologate_assignee(
        self,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        person: ExternalPerson,
        ticket: Ticket,
        org_users: Sequence["User"],
        membership: OrganizationMember,
    ) -> tuple[int, int]:
        """Run the cascade for one assignee of one ticket and persist the
        outcome. Returns ``(links_created, queue_updated)`` — each ``0`` or
        ``1``, summed by the caller across every (ticket, assignee) pair.
        """

        existing_link = await self.links.get_by_glpi_user(connector_id, person.external_id)
        result = match_assignee(person, org_users, existing_link)
        if result.skipped:
            return (0, 0)

        if result.matched_user_id is not None and result.match_method is not None:
            await self.links.create(
                organization_id=organization_id,
                connector_id=connector_id,
                glpi_user_id=person.external_id,
                user_id=result.matched_user_id,
                match_method=result.match_method,
                glpi_username=person.display_name,
                glpi_email=person.email,
                actor_id=membership.user_id,
            )
            return (1, 0)

        header = await self.unmatched.upsert_header(
            organization_id=organization_id,
            connector_id=connector_id,
            glpi_user_id=person.external_id,
            glpi_username=person.display_name,
            glpi_email=person.email,
            glpi_document=person.document,
            candidates=[
                {"user_id": str(c.user_id), "score": c.score, "reason": c.reason}
                for c in result.candidates
            ]
            or None,
            actor_id=membership.user_id,
        )
        appended = await self.unmatched.append_case(
            header.id,
            glpi_ticket_id=ticket.external_id,
            glpi_ticket_title=ticket.summary,
            glpi_ticket_status=ticket.status,
        )
        return (0, 1 if appended is not None else 0)

    async def _build_access_context(self, connector: "Connector") -> AccessContext:
        """Decrypt the connector's api_token credentials and pack them (+
        ``connectors.settings``) into the opaque ``AccessContext.
        access_token`` payload the GLPI adapter expects
        (``app.integrations.adapters.glpi.adapter.encode_access_context``).
        """

        accounts = await self.accounts.list_accounts(connector.id, connector.organization_id)
        if not accounts:
            raise AppException(
                "El conector GLPI no tiene credenciales registradas. "
                "Regístralas primero (POST /connectors/{id}/credentials).",
                code="glpi_credentials_missing",
                status_code=400,
            )
        credentials = await self.accounts.get_credentials(accounts[0].id)
        if credentials is None:
            raise AppException(
                "El conector GLPI no tiene credenciales registradas. "
                "Regístralas primero (POST /connectors/{id}/credentials).",
                code="glpi_credentials_missing",
                status_code=400,
            )

        raw: dict[str, str] = json.loads(crypto.decrypt(credentials.access_token_enc))
        connector_settings = connector.settings or {}
        payload = encode_access_context(
            connector_id=str(connector.id),
            base_url=connector_settings.get("base_url", ""),
            app_token=raw.get("app_token", ""),
            user_token=raw.get("user_token", ""),
            document_field=connector_settings.get("document_field"),
        )
        return AccessContext(access_token=payload, refresh_token=None, scopes=())

    # -- Unmatched queue -------------------------------------------------------

    async def list_unmatched(
        self, organization_id: uuid.UUID
    ) -> list[UnmatchedAssigneeRead]:
        """List the org's PENDING unmatched-assignee queue entries."""

        rows = await self.unmatched.list_active(organization_id)
        return [UnmatchedAssigneeRead.model_validate(row) for row in rows]

    async def resolve_unmatched_entry(
        self,
        organization_id: uuid.UUID,
        header_id: uuid.UUID,
        user_id: uuid.UUID,
        membership: OrganizationMember,
    ) -> GlpiUserLinkRead:
        """Resolve a queue entry: create the confirmed link
        (``match_method=manual``), flip the header to ``resolved`` — its
        already-listed cases stay as historical detail (user-homologation
        spec, "Resolver una entrada crea el mapeo y drena la cola")."""

        header = await self.unmatched.get(organization_id, header_id)
        if header is None:
            raise AppException(
                "La entrada de la cola no existe o no tienes acceso a ella.",
                code="unmatched_not_found",
                status_code=404,
            )
        self._require_pending(header)

        # CRITICAL (revisión 4R, fix 1): `user_id` viene del request — sin
        # esta comprobación, un admin de `organization_id` podría enlazar
        # una persona GLPI de SU organización a un `user_id` de OTRA
        # organización (cruce de tenant). Rechazado ANTES de crear nada.
        if not await is_org_member(self.db, organization_id, user_id):
            raise AppException(
                "El usuario indicado no pertenece a esta organización.",
                code="glpi_resolve_user_not_member",
                status_code=422,
            )

        try:
            link = await self.links.create(
                organization_id=organization_id,
                connector_id=header.connector_id,
                glpi_user_id=header.glpi_user_id,
                user_id=user_id,
                match_method=MatchMethod.manual,
                glpi_username=header.glpi_username,
                glpi_email=header.glpi_email,
                actor_id=membership.user_id,
            )
            await self.unmatched.mark_resolved(
                header, user_id=user_id, actor_id=membership.user_id
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return GlpiUserLinkRead.model_validate(link)

    async def ignore_unmatched_entry(
        self, organization_id: uuid.UUID, header_id: uuid.UUID, membership: OrganizationMember
    ) -> None:
        """Ignore a queue entry — retires it from the active view WITHOUT
        creating any link (user-homologation spec, "Ignorar una entrada sin
        crear mapeo")."""

        header = await self.unmatched.get(organization_id, header_id)
        if header is None:
            raise AppException(
                "La entrada de la cola no existe o no tienes acceso a ella.",
                code="unmatched_not_found",
                status_code=404,
            )
        self._require_pending(header)
        await self.unmatched.mark_ignored(header, actor_id=membership.user_id)
        await self.db.commit()

    @staticmethod
    def _require_pending(header: "GlpiUnmatchedAssignee") -> None:
        """WARNING (revisión 4R, fix 5): resolve/ignore SOLO proceden sobre
        una entrada ``pending`` — una entrada ya resuelta o ignorada
        responde 409 en lugar de crear un segundo link o cambiar el estado
        de nuevo (máquina de estados)."""

        if header.status != UnmatchedStatus.pending:
            raise AppException(
                "Esta entrada de la cola ya fue procesada (resuelta o ignorada).",
                code="glpi_unmatched_already_processed",
                status_code=409,
            )

    # -- Confirmed links ---------------------------------------------------

    async def list_links(self, organization_id: uuid.UUID) -> list[GlpiUserLinkRead]:
        """List the org's confirmed ``glpi_user_links``."""

        rows = await self.links.list_links(organization_id)
        return [GlpiUserLinkRead.model_validate(row) for row in rows]

    async def revoke_link(
        self, organization_id: uuid.UUID, link_id: uuid.UUID, membership: OrganizationMember
    ) -> None:
        """Revoke a confirmed link — the next sync of this person re-runs
        the full cascade (user-homologation spec, "Admin revoca un
        mapeo"). 404 if the link does not exist or belongs to another
        organization."""

        link = await self.links.get(organization_id, link_id)
        if link is None:
            raise AppException(
                "El mapeo no existe o no tienes acceso a él.",
                code="glpi_link_not_found",
                status_code=404,
            )
        await self.links.revoke(link, actor_id=membership.user_id)
        await self.db.commit()
