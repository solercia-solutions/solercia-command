"""Pydantic schemas for the connectors module (change 14-integration-ports;
``credential_kind``/``settings``/``ApiTokenCredentials`` are a delta of
change 17-adapter-glpi, specs/connectors/spec.md)."""

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
