"""Data-access layer for glpi_sync (change 17-adapter-glpi). Every query is
scoped by ``organization_id`` — directly on ``GlpiUserLink``/
``GlpiUnmatchedAssignee`` (both carry ``TenantMixin``), or via the header's
own ``organization_id`` for ``GlpiUnmatchedCase`` (UH-R7, aislamiento
multi-tenant).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.glpi_sync.models import GlpiUnmatchedAssignee, GlpiUnmatchedCase, GlpiUserLink
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.shared.enums import MatchMethod, UnmatchedStatus


class GlpiUserLinkRepository:
    """Async repository for confirmed ``glpi_user_links`` mappings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_glpi_user(
        self, connector_id: uuid.UUID, glpi_user_id: str
    ) -> GlpiUserLink | None:
        """Return the active link for ``(connector_id, glpi_user_id)``, or
        ``None`` — the cascade's short-circuit check."""

        result = await self.db.execute(
            select(GlpiUserLink).where(
                GlpiUserLink.connector_id == connector_id,
                GlpiUserLink.glpi_user_id == glpi_user_id,
                GlpiUserLink.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        glpi_user_id: str,
        user_id: uuid.UUID,
        match_method: MatchMethod,
        glpi_username: str | None,
        glpi_email: str | None,
        actor_id: uuid.UUID | None,
    ) -> GlpiUserLink:
        """Create (or REACTIVATE a previously revoked) link for
        ``(connector_id, glpi_user_id)`` — the UNIQUE constraint does not
        exclude soft-deleted rows, so a revoked link is reactivated in
        place instead of colliding on re-sync/re-resolve (mirrors
        ``ConnectedAccountRepository.upsert_account``, change 14)."""

        result = await self.db.execute(
            select(GlpiUserLink).where(
                GlpiUserLink.connector_id == connector_id,
                GlpiUserLink.glpi_user_id == glpi_user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.user_id = user_id
            existing.match_method = match_method
            existing.glpi_username = glpi_username
            existing.glpi_email = glpi_email
            existing.updated_by = actor_id
            if not existing.is_active:
                existing.is_active = True
                existing.deleted_at = None
            await self.db.flush()
            return existing

        link = GlpiUserLink(
            organization_id=organization_id,
            connector_id=connector_id,
            glpi_user_id=glpi_user_id,
            user_id=user_id,
            match_method=match_method,
            glpi_username=glpi_username,
            glpi_email=glpi_email,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.db.add(link)
        await self.db.flush()
        return link

    async def list_links(self, organization_id: uuid.UUID) -> Sequence[GlpiUserLink]:
        """Return the org's active links, newest first."""

        result = await self.db.execute(
            select(GlpiUserLink)
            .where(
                GlpiUserLink.organization_id == organization_id,
                GlpiUserLink.is_active.is_(True),
            )
            .order_by(GlpiUserLink.created_at.desc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, link_id: uuid.UUID
    ) -> GlpiUserLink | None:
        """Return a single active link scoped to the organization, or
        ``None`` (UH-R7)."""

        result = await self.db.execute(
            select(GlpiUserLink).where(
                GlpiUserLink.id == link_id,
                GlpiUserLink.organization_id == organization_id,
                GlpiUserLink.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def revoke(
        self, link: GlpiUserLink, *, actor_id: uuid.UUID | None
    ) -> None:
        """Soft-delete a link — the next sync of this person re-runs the
        full cascade (user-homologation spec, "Admin revoca un mapeo")."""

        link.is_active = False
        link.deleted_at = datetime.now(UTC)
        link.updated_by = actor_id
        await self.db.flush()


class GlpiUnmatchedRepository:
    """Async repository for the unmatched-assignee queue (header + detail)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_header(
        self,
        *,
        organization_id: uuid.UUID,
        connector_id: uuid.UUID,
        glpi_user_id: str,
        glpi_username: str | None,
        glpi_email: str | None,
        glpi_document: str | None,
        candidates: list[dict] | None,
        actor_id: uuid.UUID | None,
    ) -> GlpiUnmatchedAssignee:
        """Create the header for ``(connector_id, glpi_user_id)``, or
        return the EXISTING one untouched — a case with the SAME person
        never duplicates the header (user-homologation spec, "Segundo caso
        sin homologar de la misma persona")."""

        result = await self.db.execute(
            select(GlpiUnmatchedAssignee).where(
                GlpiUnmatchedAssignee.connector_id == connector_id,
                GlpiUnmatchedAssignee.glpi_user_id == glpi_user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        header = GlpiUnmatchedAssignee(
            organization_id=organization_id,
            connector_id=connector_id,
            glpi_user_id=glpi_user_id,
            glpi_username=glpi_username,
            glpi_email=glpi_email,
            glpi_document=glpi_document,
            candidates=candidates,
            status=UnmatchedStatus.pending,
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.db.add(header)
        await self.db.flush()
        return header

    async def append_case(
        self,
        header_id: uuid.UUID,
        *,
        glpi_ticket_id: str,
        glpi_ticket_title: str | None,
        glpi_ticket_status: str | None,
    ) -> GlpiUnmatchedCase | None:
        """Append a case to the header's detail — idempotent: a case
        already listed for this ticket is a NO-OP (``UNIQUE
        (unmatched_assignee_id, glpi_ticket_id)``, re-sync safe)."""

        result = await self.db.execute(
            select(GlpiUnmatchedCase).where(
                GlpiUnmatchedCase.unmatched_assignee_id == header_id,
                GlpiUnmatchedCase.glpi_ticket_id == glpi_ticket_id,
            )
        )
        if result.scalar_one_or_none() is not None:
            return None

        case = GlpiUnmatchedCase(
            unmatched_assignee_id=header_id,
            glpi_ticket_id=glpi_ticket_id,
            glpi_ticket_title=glpi_ticket_title,
            glpi_ticket_status=glpi_ticket_status,
        )
        self.db.add(case)
        await self.db.flush()
        return case

    async def list_active(
        self, organization_id: uuid.UUID
    ) -> Sequence[GlpiUnmatchedAssignee]:
        """Return the org's PENDING queue entries (``resolved``/``ignored``
        entries drop out of the active view, user-homologation spec)."""

        result = await self.db.execute(
            select(GlpiUnmatchedAssignee)
            .where(
                GlpiUnmatchedAssignee.organization_id == organization_id,
                GlpiUnmatchedAssignee.status == UnmatchedStatus.pending,
            )
            .order_by(GlpiUnmatchedAssignee.created_at.desc())
        )
        return result.scalars().all()

    async def get(
        self, organization_id: uuid.UUID, header_id: uuid.UUID
    ) -> GlpiUnmatchedAssignee | None:
        """Return a single queue header scoped to the organization, or
        ``None`` (UH-R7)."""

        result = await self.db.execute(
            select(GlpiUnmatchedAssignee).where(
                GlpiUnmatchedAssignee.id == header_id,
                GlpiUnmatchedAssignee.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_resolved(
        self,
        header: GlpiUnmatchedAssignee,
        *,
        user_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> None:
        header.status = UnmatchedStatus.resolved
        header.resolved_user_id = user_id
        header.resolved_at = datetime.now(UTC)
        header.updated_by = actor_id
        await self.db.flush()

    async def mark_ignored(
        self, header: GlpiUnmatchedAssignee, *, actor_id: uuid.UUID | None
    ) -> None:
        header.status = UnmatchedStatus.ignored
        # WARNING (revisión 4R, fix 5): limpia los campos del estado
        # contrario (``resolved``) — defensivo ante un futuro flujo de
        # reapertura, hoy inalcanzable porque el servicio ya exige
        # ``status == pending`` antes de llegar aquí.
        header.resolved_user_id = None
        header.resolved_at = None
        header.updated_by = actor_id
        await self.db.flush()


async def is_org_member(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Return whether ``user_id`` belongs to ``organization_id`` (CRITICAL,
    revisión 4R fix 1 — mirrors ``tasks/repository.py``'s
    ``TaskRepository.is_org_member``): the membership gate a manual
    resolution's ``user_id`` MUST pass before a ``glpi_user_links`` row is
    ever created for it, so an admin of one organization can never link a
    GLPI person to a user from a DIFFERENT organization."""

    result = await db.execute(
        select(OrganizationMember.id).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def list_org_user_candidates(
    db: AsyncSession, organization_id: uuid.UUID
) -> Sequence[User]:
    """Return the ACTIVE users belonging to ``organization_id`` — the name
    cascade's candidate pool. ``User`` has no ``TenantMixin`` (it is not
    org-scoped directly), so this joins through ``organization_members``.
    """

    result = await db.execute(
        select(User)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .where(
            OrganizationMember.organization_id == organization_id,
            User.is_active.is_(True),
        )
    )
    return result.scalars().all()
