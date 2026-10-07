"""``/ai`` routes (C04) — the AI provider of the caller's organization.

``admin`` reads, writes and tests; ``manager`` only reads; ``member`` and
``viewer`` get 403. Everything is scoped to the organization resolved from
the caller's membership: another tenant's settings are unreachable. No
response ever carries the API key (only ``has_api_key``/``api_key_last4``).
"""

import httpx
from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.presets import PRESETS
from app.ai.url_guard import Resolver, default_resolver
from app.database import get_db
from app.dependencies import get_actor_id, require_role
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

from .repository import SqlAiProviderSettingsRepository
from .schemas import AiPresetRead, AiSettingsUpdate
from .service import AiSettingsService

router = APIRouter(prefix="/ai", tags=["ai-settings"])

require_ai_reader = require_role(MemberRole.admin, MemberRole.manager)
require_ai_admin = require_role(MemberRole.admin)


def get_ai_transport() -> httpx.AsyncBaseTransport | None:
    """Real network by default; tests override it with a fake transport."""

    return None


def get_ai_resolver() -> Resolver:
    """Real DNS by default; tests override it (anti-SSRF guard input)."""

    return default_resolver


def _service(db: AsyncSession, resolver: Resolver) -> AiSettingsService:
    return AiSettingsService(
        SqlAiProviderSettingsRepository(db), commit=db.commit, resolver=resolver
    )


@router.get("/settings")
async def get_ai_settings(
    membership: OrganizationMember = Depends(require_ai_reader),
    db: AsyncSession = Depends(get_db),
    resolver: Resolver = Depends(get_ai_resolver),
) -> dict:
    """Effective AI provider of the caller's organization (admin, manager).

    ``source`` says where it comes from: ``organization`` (saved here),
    ``global`` (server ``LLM_*``) or ``default`` (local Ollama preset). The
    key is never returned: only ``has_api_key`` and ``api_key_last4``."""

    data = await _service(db, resolver).get_settings(membership.organization_id)
    return {"data": data, "message": "Proveedor de IA de la organización."}


@router.put("/settings")
async def put_ai_settings(
    payload: AiSettingsUpdate,
    membership: OrganizationMember = Depends(require_ai_admin),
    actor_id=Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
    resolver: Resolver = Depends(get_ai_resolver),
) -> dict:
    """Save the organization's AI provider (admin only, BYOK).

    ``api_key``: omitted or blank keeps the stored key while the destination
    URL is unchanged; ``null`` deletes it. External presets require a key.
    ``custom`` URLs must be HTTPS to a public host (or explicit loopback);
    otherwise 422 ``llm_base_url_rejected``."""

    data = await _service(db, resolver).update_settings(
        membership.organization_id, actor_id, payload
    )
    return {"data": data, "message": "Proveedor de IA actualizado."}


@router.get("/presets")
async def list_ai_presets(
    membership: OrganizationMember = Depends(require_ai_reader),
) -> dict:
    """Available provider presets, each marked ``local`` or ``external``
    (external ones send content outside the machine)."""

    data = [
        AiPresetRead(
            key=p.key,
            label=p.label,
            locality=p.locality,
            base_url=p.base_url,
            base_url_editable=p.base_url_editable,
            chat_model=p.chat_model,
            embedding_model=p.embedding_model,
            requires_api_key=p.requires_api_key,
        )
        for p in PRESETS.values()
    ]
    return {"data": data, "message": "Presets de proveedores de IA."}


@router.post("/settings/test")
async def test_ai_settings(
    proposal: AiSettingsUpdate | None = Body(default=None),
    membership: OrganizationMember = Depends(require_ai_admin),
    db: AsyncSession = Depends(get_db),
    resolver: Resolver = Depends(get_ai_resolver),
    transport: httpx.AsyncBaseTransport | None = Depends(get_ai_transport),
) -> dict:
    """Try a short chat and one embedding (admin only).

    Without a body it tests the saved/effective configuration; with a body
    it tests that proposal WITHOUT saving it. Returns latency and models;
    provider failures come back as ``ok=false`` with ``error.stage`` and a
    stable ``error.code``. The key is never returned."""

    data = await _service(db, resolver).test_connection(
        membership.organization_id, proposal, transport=transport
    )
    return {"data": data, "message": "Prueba de conexión ejecutada."}
