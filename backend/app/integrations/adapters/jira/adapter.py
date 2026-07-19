"""``JiraAdapter`` — the ``IntegrationAdapter`` implementation for Jira
(change 18-adapter-jira, design.md "adaptador `app/integrations/adapters/
jira/`"). Read-only; ``credential_kind=api_token`` (email + API token ->
HTTP Basic, validated via ``GET /rest/api/3/myself``, GA-precedent
``glpi/adapter.py``).

Two contracts coexist deliberately (design.md Architecture Decisions, "DTO
propio NormalizedJiraIssue, no el Ticket del puerto"):

- ``port_for(Capability.tickets)`` satisfies the core's generic
  ``TicketReaderPort`` with the THIN ``Ticket`` DTO (registry/discovery
  conformance — the minimum common contract every adapter honors).
- ``import_issues()``/``parse_file()`` are Jira-specific methods the
  ``jira_import`` module (Lote 8) calls DIRECTLY, returning the RICHER
  ``NormalizedJiraIssue`` (type/assignee/sprint/points/labels) the thin
  ``Ticket`` never models.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.config import settings as default_settings
from app.integrations.adapters.jira import errors, file_parser
from app.integrations.adapters.jira.client import JiraClient, JiraConfigError, resolve_field_ids
from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.integrations.adapters.jira.mappings import build_mappings
from app.integrations.adapters.jira.normalizer import normalize_api_batch, normalize_file_batch
from app.integrations.dtos import AccountRef, Ticket
from app.integrations.ports import (
    AccessContext,
    ApiTokenHandshake,
    Capability,
    CredentialKind,
    OAuthHandshake,
)

logger = logging.getLogger("solercia.jira.adapter")

# Fields every search requests regardless of custom-field resolution —
# ``story_points_field``/``sprint_field`` (when resolved) are appended by
# ``_search_fields`` at call time.
_BASE_SEARCH_FIELDS: tuple[str, ...] = (
    "summary",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "labels",
    "description",
    "created",
)


def _search_fields(story_points_field: str | None, sprint_field: str | None) -> tuple[str, ...]:
    fields = list(_BASE_SEARCH_FIELDS)
    if story_points_field:
        fields.append(story_points_field)
    if sprint_field:
        fields.append(sprint_field)
    return tuple(fields)


class _JiraApiTokenHandshake:
    """``ApiTokenHandshake`` implementation: validates ``email``+
    ``api_token`` by calling Jira's OWN ``GET /rest/api/3/myself`` — never
    persists anything itself (``app/modules/connectors/service.py`` owns
    that, mirrors ``_GlpiApiTokenHandshake``)."""

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
        email = raw.get("email")
        api_token = raw.get("api_token")
        if not base_url or not email or not api_token:
            raise errors.JiraAuthError(
                "Faltan base_url/email/api_token para validar las "
                "credenciales de Jira."
            )

        client: JiraClient | None = None
        try:
            client = JiraClient(
                base_url, email, api_token, transport=self._transport, settings=self._settings
            )
            myself = await client.get_myself()
        except JiraConfigError as exc:
            raise errors.JiraConfigInvalid(str(exc)) from exc
        finally:
            if client is not None:
                await client.aclose()

        account_id = myself.get("accountId")
        if account_id:
            external_account_id = f"jira-{account_id}"
        else:
            # `accountId` is a public identifier Jira Cloud always returns
            # for `/myself`; the hash fallback only guards against a
            # malformed/partial payload — never the raw email as-is.
            digest = hashlib.sha256(email.encode("utf-8")).hexdigest()[:16]
            external_account_id = f"jira-{digest}"

        return AccountRef(
            external_account_id=external_account_id,
            display_name=myself.get("displayName") or "Cuenta de servicio Jira",
        )


def encode_access_context(
    *,
    connector_id: str,
    base_url: str,
    email: str,
    api_token: str,
    jira_settings: Mapping[str, Any] | None = None,
) -> str:
    """Pack Jira-specific fields into the opaque JSON payload
    ``AccessContext.access_token`` carries — the core's ``AccessContext``
    is NEVER extended with provider-specific fields (mirrors
    ``glpi.adapter.encode_access_context``)."""

    payload = {
        "connector_id": connector_id,
        "base_url": base_url,
        "email": email,
        "api_token": api_token,
        "jira_settings": dict(jira_settings or {}),
    }
    return json.dumps(payload)


def _decode_access_context(ctx: AccessContext) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = json.loads(ctx.access_token)
    except (TypeError, ValueError) as exc:
        raise errors.JiraAuthError(
            "El contexto de acceso del conector Jira es inválido."
        ) from exc
    missing = [
        field
        for field in ("connector_id", "base_url", "email", "api_token")
        if not payload.get(field)
    ]
    if missing:
        raise errors.JiraAuthError(
            "El contexto de acceso del conector Jira está incompleto."
        )
    return payload


def _to_thin_ticket(issue: NormalizedJiraIssue) -> Ticket:
    """Downgrade a rich ``NormalizedJiraIssue`` to the core's thin
    ``Ticket`` DTO — the minimum common shape ``port_for(tickets)``
    exposes (design.md Architecture Decisions)."""

    return Ticket(
        external_id=issue.key,
        key=issue.key,
        summary=issue.title,
        status=issue.status_raw,
        priority=issue.priority,
        requester=None,
        created_at=issue.created_at or datetime.now(UTC),
        assignees=(),
    )


class _JiraTicketReader:
    """``TicketReaderPort`` implementation — decodes the packed
    ``AccessContext`` and delegates to ``JiraAdapter.import_issues``,
    mapping every result down to the thin ``Ticket`` (GA-R1)."""

    def __init__(self, adapter: "JiraAdapter") -> None:
        self._adapter = adapter

    async def list_tickets(
        self, ctx: AccessContext, *, since: Any = None, limit: int = 50
    ) -> list[Ticket]:
        payload = _decode_access_context(ctx)
        issues, _report = await self._adapter.import_issues(
            base_url=payload["base_url"],
            email=payload["email"],
            api_token=payload["api_token"],
            jql="",
            jira_settings=payload.get("jira_settings"),
            since=since,
        )
        return [_to_thin_ticket(issue) for issue in issues[:limit]]


class JiraAdapter:
    """Jira adapter — read-only, ``credential_kind=api_token``."""

    provider = "jira"
    capabilities = frozenset({Capability.tickets})
    credential_kind = CredentialKind.api_token

    def __init__(
        self,
        *,
        settings: Settings = default_settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """``transport`` is injectable (``httpx.MockTransport`` in tests)
        and threaded through to every ``JiraClient`` this adapter builds —
        the SAME dependency-injection shape ``GraphClient``/``GlpiClient``
        use, so tests never monkeypatch module internals."""

        self._settings = settings
        self._transport = transport
        self.oauth: OAuthHandshake | None = None
        self.api_token: ApiTokenHandshake | None = _JiraApiTokenHandshake(
            settings=settings, transport=transport
        )
        self._ports: dict[Capability, object] = {
            Capability.tickets: _JiraTicketReader(self),
        }

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when it is not supported (only ``tickets``)."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)

    async def import_issues(
        self,
        *,
        base_url: str,
        email: str,
        api_token: str,
        jql: str,
        jira_settings: Mapping[str, Any] | None = None,
        since: Any = None,
    ) -> tuple[list[NormalizedJiraIssue], NormalizationReport]:
        """Extract issues via the API vía: resolve custom fields, paginate
        ``/search/jql`` and normalize every issue (design.md Data Flow,
        "Vía API")."""

        jira_settings = jira_settings or {}
        mappings = build_mappings(jira_settings)

        client: JiraClient | None = None
        story_points_field: str | None = None
        sprint_field: str | None = None
        try:
            client = JiraClient(
                base_url, email, api_token, transport=self._transport, settings=self._settings
            )
            fields_json = await client.get_fields()
            story_points_field, sprint_field = resolve_field_ids(
                fields_json,
                story_points_override=jira_settings.get("story_points_field"),
                sprint_field_override=jira_settings.get("sprint_field"),
            )
            raw_issues = await client.list_issues(
                jql, _search_fields(story_points_field, sprint_field), since=since
            )
        except JiraConfigError as exc:
            raise errors.JiraConfigInvalid(str(exc)) from exc
        except errors.JiraRateLimited as exc:
            # specs/jira-import/spec.md "Reintentos agotados": normalize the
            # PREVIOUS pages' issues so `JiraImportService` can answer 200
            # with `truncated=true` instead of losing them behind a 503.
            partial_issues, partial_report = normalize_api_batch(
                exc.partial_issues,
                mappings=mappings,
                story_points_field=story_points_field,
                sprint_field=sprint_field,
            )
            exc.normalized_partial_issues = partial_issues
            exc.partial_report = partial_report
            raise
        finally:
            if client is not None:
                await client.aclose()

        return normalize_api_batch(
            raw_issues,
            mappings=mappings,
            story_points_field=story_points_field,
            sprint_field=sprint_field,
        )

    def parse_file(
        self,
        content: bytes,
        filename: str,
        *,
        jira_settings: Mapping[str, Any] | None = None,
    ) -> tuple[list[NormalizedJiraIssue], NormalizationReport]:
        """Extract issues via the file vía: parse CSV/XLSX and normalize
        every row (design.md Data Flow, "Vía archivo") — never resolves
        custom field ids (there is no ``/field`` call for a file import).
        """

        mappings = build_mappings(jira_settings or {})
        rows = file_parser.parse_file(content, filename, settings=self._settings)
        return normalize_file_batch(rows, mappings=mappings)


# Re-exported for callers that only need to type-check a raw row/issue
# sequence without importing the submodules directly.
__all__ = ["JiraAdapter", "encode_access_context"]
