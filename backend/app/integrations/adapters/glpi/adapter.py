"""``GlpiAdapter`` — the ``IntegrationAdapter`` implementation for GLPI
(change 17-adapter-glpi, design.md "adaptador `app/integrations/adapters/
glpi/`"). Read-only; ``credential_kind=api_token`` (App-Token + user_token
-> ``initSession``, GA-R2). Only ``Capability.tickets`` is supported.

``AccessContext`` (the 14's core DTO) is NEVER extended with GLPI-specific
fields — ``connector_id``/``base_url``/``app_token``/``user_token`` are
packed by :func:`encode_access_context` into ``AccessContext.access_token``
as an opaque JSON string that ONLY this package ever decodes
(:func:`_decode_access_context`). The caller (``app/modules/glpi_sync/
service.py``, Lote 8) builds this payload from the connector's decrypted
credentials + ``connectors.settings`` (``base_url``/``document_field``)
before calling ``port_for(Capability.tickets).list_tickets(ctx)``.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from typing import Any, NoReturn

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.glpi import errors
from app.integrations.adapters.glpi import session as glpi_session
from app.integrations.adapters.glpi.client import GlpiClient
from app.integrations.adapters.glpi.mapper import map_person, map_ticket
from app.integrations.dtos import AccountRef, Ticket
from app.integrations.ports import (
    AccessContext,
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)

logger = logging.getLogger("solercia.glpi.adapter")

# GLPI's `Ticket_User.type`: 1=solicitante, 2=ASIGNADO, 3=observador
# (design.md Interfaces). Only these two roles are ever resolved — an
# observer never becomes `requester` nor `assignees` (GA-R4).
_ASSIGNEE_TYPE = 2
_REQUESTER_TYPE = 1


def encode_access_context(
    *,
    connector_id: str,
    base_url: str,
    app_token: str,
    user_token: str,
    document_field: str | None = None,
) -> str:
    """Build the opaque JSON payload for ``AccessContext.access_token`` the
    GLPI tickets port expects — the ONE place that packs GLPI-specific
    fields without touching the core's ``AccessContext`` shape."""

    payload = {
        "connector_id": connector_id,
        "base_url": base_url,
        "app_token": app_token,
        "user_token": user_token,
        "document_field": document_field or default_settings.GLPI_DEFAULT_DOCUMENT_FIELD,
    }
    return json.dumps(payload)


def _decode_access_context(ctx: AccessContext) -> dict[str, str]:
    try:
        payload: dict[str, str] = json.loads(ctx.access_token)
    except (TypeError, ValueError) as exc:
        raise errors.GlpiAuthError(
            "El contexto de acceso del conector GLPI es inválido."
        ) from exc
    missing = [
        field
        for field in ("connector_id", "base_url", "app_token", "user_token")
        if not payload.get(field)
    ]
    if missing:
        raise errors.GlpiAuthError(
            "El contexto de acceso del conector GLPI está incompleto."
        )
    return payload


async def _translate_transport_errors(exc: Exception) -> NoReturn:
    """Translate a caught httpx exception into a GLPI domain error.

    ALWAYS raises — never returns normally (``NoReturn``), so a caller's
    ``except (...) as exc: await _translate_transport_errors(exc)`` needs
    no trailing ``raise``: mypy already knows control flow never falls
    through past this call.
    """

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            raise errors.GlpiAuthError() from exc
        raise errors.GlpiUnavailable() from exc
    if isinstance(exc, httpx.TimeoutException):
        raise errors.GlpiUnavailable() from exc
    if isinstance(exc, httpx.RequestError):
        raise errors.GlpiUnavailable() from exc
    raise exc


class _GlpiApiTokenHandshake:
    """``ApiTokenHandshake`` implementation (GA-R2): validates App-Token +
    user_token by round-tripping GLPI's OWN session lifecycle
    (``initSession`` then immediately ``killSession``) — never persists
    anything itself (``app/modules/connectors/service.py`` owns that)."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        base_url = raw.get("base_url")
        app_token = raw.get("app_token")
        user_token = raw.get("user_token")
        if not base_url or not app_token or not user_token:
            raise errors.GlpiAuthError(
                "Faltan base_url/app_token/user_token para validar las "
                "credenciales de GLPI."
            )

        client = GlpiClient(base_url, transport=self._transport, settings=self._settings)
        try:
            session_token = await client.init_session(app_token, user_token)
            await client.kill_session(session_token, app_token)
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            await _translate_transport_errors(exc)
        finally:
            await client.aclose()

        # A public, non-secret identifier: a one-way hash of the
        # user_token, never the raw secret itself (mirrors the fake test
        # adapter used by test_connectors_api_token.py).
        digest = hashlib.sha256(user_token.encode("utf-8")).hexdigest()[:16]
        return AccountRef(
            external_account_id=f"glpi-{digest}",
            display_name="Cuenta de servicio GLPI",
        )


class _GlpiTicketReader:
    """``TicketReaderPort`` implementation (GA-R4): lists tickets and
    resolves each one's assigned technician(s)/requester by walking
    ``Ticket_User`` -> ``User``/``UserEmail`` (GA-R5, read-only: GET only,
    plus the session lifecycle)."""

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def list_tickets(
        self, ctx: AccessContext, *, since: Any = None, limit: int = 50
    ) -> list[Ticket]:
        payload = _decode_access_context(ctx)
        connector_id = payload["connector_id"]
        base_url = payload["base_url"]
        app_token = payload["app_token"]
        user_token = payload["user_token"]
        document_field = (
            payload.get("document_field") or self._settings.GLPI_DEFAULT_DOCUMENT_FIELD
        )

        client = GlpiClient(base_url, transport=self._transport, settings=self._settings)
        try:
            return await self._list_tickets_with_client(
                client,
                connector_id=connector_id,
                app_token=app_token,
                user_token=user_token,
                document_field=document_field,
                limit=limit,
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            await _translate_transport_errors(exc)
        finally:
            await client.aclose()

    async def _list_tickets_with_client(
        self,
        client: GlpiClient,
        *,
        connector_id: str,
        app_token: str,
        user_token: str,
        document_field: str,
        limit: int,
    ) -> list[Ticket]:
        async def _fetch_tickets(token: str) -> list[dict[str, Any]]:
            return await client.list_tickets(
                token, app_token, range_start=0, range_end=max(limit - 1, 0)
            )

        raw_tickets = await glpi_session.with_session_retry(
            connector_id, client, app_token, user_token, _fetch_tickets, settings=self._settings
        )

        tickets: list[Ticket] = []
        for raw_ticket in raw_tickets:
            ticket_id = str(raw_ticket["id"])

            async def _fetch_ticket_users(
                token: str, tid: str = ticket_id
            ) -> list[dict[str, Any]]:
                return await client.get_ticket_users(tid, token, app_token)

            ticket_users = await glpi_session.with_session_retry(
                connector_id,
                client,
                app_token,
                user_token,
                _fetch_ticket_users,
                settings=self._settings,
            )

            assignees = []
            requester_name: str | None = None
            for entry in ticket_users:
                role_type = entry.get("type")
                user_id = str(entry.get("users_id") or "")
                if not user_id or role_type not in (_ASSIGNEE_TYPE, _REQUESTER_TYPE):
                    continue

                async def _fetch_user(token: str, uid: str = user_id) -> dict[str, Any]:
                    return await client.get_user(uid, token, app_token)

                user_json = await glpi_session.with_session_retry(
                    connector_id,
                    client,
                    app_token,
                    user_token,
                    _fetch_user,
                    settings=self._settings,
                )

                if role_type == _ASSIGNEE_TYPE:

                    async def _fetch_user_email(
                        token: str, uid: str = user_id
                    ) -> list[dict[str, Any]]:
                        return await client.get_user_email(uid, token, app_token)

                    emails_json = await glpi_session.with_session_retry(
                        connector_id,
                        client,
                        app_token,
                        user_token,
                        _fetch_user_email,
                        settings=self._settings,
                    )
                    assignees.append(
                        map_person(user_json, emails_json, document_field=document_field)
                    )
                else:  # _REQUESTER_TYPE
                    requester_name = map_person(
                        user_json, [], document_field=document_field
                    ).display_name

            tickets.append(map_ticket(raw_ticket, assignees=assignees, requester=requester_name))

        return tickets


class GlpiAdapter:
    """GLPI adapter — read-only, ``credential_kind=api_token``."""

    provider = "glpi"
    capabilities = frozenset({Capability.tickets})
    credential_kind = CredentialKind.api_token

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """``transport`` is injectable (``httpx.MockTransport`` in tests)
        and threaded through to every ``GlpiClient`` this adapter builds —
        the SAME dependency-injection shape ``GraphClient``/``GoogleClient``
        use, so tests never monkeypatch module internals."""

        self._settings = settings
        self._transport = transport
        self.oauth: OAuthHandshake | None = None
        self.api_token: ApiTokenHandshake | None = _GlpiApiTokenHandshake(
            settings=settings, transport=transport
        )
        self._ports: dict[Capability, object] = {
            Capability.tickets: _GlpiTicketReader(settings=settings, transport=transport),
        }

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when it is not supported (only ``tickets``, GA-R1)."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)
