"""Pydantic schemas for the connectors module (change 14-integration-ports;
``credential_kind``/``settings``/``ApiTokenCredentials`` are a delta of
change 17-adapter-glpi, specs/connectors/spec.md; ``token``/
``ExternalResourceOut``/``ExternalToolOut``/``ExternalResourceContentOut``/
``McpToolCallRequest`` are a delta of change 19-mcp-connector)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.ports import CredentialKind
from app.shared.enums import AccountStatus, ConnectorStatus


class ConnectorCreate(BaseModel):
    """Payload to create a connector (provider configuration).

    ``credential_kind`` is FIXED at creation (specs/connectors/spec.md,
    "Tipo de credencial del conector") — there is deliberately no way to
    change it via ``ConnectorUpdate``; recreate the connector instead.
    """

    provider: str = Field(min_length=1, max_length=50)
    scopes: list[str] | None = None
    status: ConnectorStatus = ConnectorStatus.active
    credential_kind: CredentialKind = CredentialKind.oauth
    settings: dict | None = None
    # Change 19-mcp-connector, specs/connectors/spec.md delta ("Registro de
    # conector con credencial directa") — a static bearer token for
    # adapters whose protocol declares direct credential acquisition (e.g.
    # `mcp` with `credential_kind=api_token`), supplied in THIS SAME
    # request instead of the separate `POST /connectors/{id}/credentials`
    # GLPI/Jira use. `repr=False` keeps it out of any accidental
    # `repr(payload)` in a log line; `ConnectorRead` below never declares
    # this field at all, so it can never round-trip into a response.
    token: str | None = Field(default=None, repr=False)


class ConnectorUpdate(BaseModel):
    """Partial payload to edit a connector.

    Deliberately excludes ``credential_kind`` (fixed at creation); includes
    ``settings`` since non-secret provider config (e.g. GLPI's
    ``base_url``) is expected to change without recreating the connector.
    """

    provider: str | None = Field(default=None, min_length=1, max_length=50)
    scopes: list[str] | None = None
    status: ConnectorStatus | None = None
    settings: dict | None = None


class ApiTokenCredentials(BaseModel):
    """Generic ``api_token`` credential payload (change 17-adapter-glpi,
    C17-R2) — e.g. GLPI's ``app_token``/``user_token``.

    Deliberately NOT a fixed key/value shape: the connectors service stays
    provider-agnostic (mirrors the core's "sin lógica específica del
    proveedor en el núcleo") — each provider's own
    ``ApiTokenHandshake.connect()`` is what interprets/validates the raw
    mapping. ``extra="allow"`` accepts any provider-specific keys.
    """

    model_config = ConfigDict(extra="allow")

    def as_mapping(self) -> dict[str, str]:
        """Return every submitted field (including ``extra``) as a plain
        ``dict[str, str]`` for :meth:`ApiTokenHandshake.connect`."""

        return {key: str(value) for key, value in self.model_dump().items()}


class AuthorizeResponse(BaseModel):
    """Result of the OAuth authorize step.

    Used internally by the service layer; the router converts this into an
    HTTP ``302`` redirect to ``authorize_url`` (design.md, "es una
    navegación de navegador que responde una redirección 302 al IdP").
    """

    authorize_url: str


class ConnectorRead(BaseModel):
    """A connector as returned by the API.

    Never exposes tokens — a connector has none: OAuth tokens live isolated
    in ``ConnectionCredentials``, a separate table this schema never touches.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    scopes: list[str] | None = None
    status: ConnectorStatus
    credential_kind: CredentialKind
    settings: dict | None = None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class ConnectedAccountRead(BaseModel):
    """A connected account as returned by the API.

    Never exposes tokens — those live isolated in ``ConnectionCredentials``,
    a table this schema never touches (specs/connectors/spec.md, "Tokens
    ausentes en la respuesta de la API").
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_id: uuid.UUID
    user_id: uuid.UUID
    external_account_id: str
    display_name: str | None = None
    status: AccountStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Change 19-mcp-connector — REST envelope for the `/mcp/*` read routes.
# Mirror `app.integrations.dtos`' frozen dataclasses field-for-field, kept
# as SEPARATE Pydantic models (not the dataclasses themselves) so the
# `/mcp/*` routes get normal FastAPI/OpenAPI schema documentation, same as
# every other connectors response.
# ---------------------------------------------------------------------------


class ExternalResourceOut(BaseModel):
    """A resource published by the MCP server (mirrors `ExternalResource`)."""

    uri: str
    name: str
    mime_type: str | None = None
    description: str | None = None


class ExternalToolOut(BaseModel):
    """A tool published by the MCP server (mirrors `ExternalTool`)."""

    name: str
    description: str | None = None
    read_only: bool
    input_schema: dict


class ExternalResourceContentOut(BaseModel):
    """The content of a resource read or a `call_tool` result (mirrors
    `ExternalResourceContent`)."""

    uri: str | None = None
    mime_type: str | None = None
    text: str | None = None
    blob_b64: str | None = None
    truncated: bool = False


class McpToolCallRequest(BaseModel):
    """Payload for `POST /connectors/{id}/mcp/tools/{tool_name}/call`."""

    arguments: dict = Field(default_factory=dict)
