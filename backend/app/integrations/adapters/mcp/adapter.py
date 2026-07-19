"""``McpAdapter`` — the ``IntegrationAdapter`` implementation for the Model
Context Protocol (change 19-mcp-connector, mcp-connector/spec.md MC-R1/MC-R2).
Read-only via the ``external_resources`` capability. Transport EXCLUSIVELY
Streamable HTTP remote — there is no ``stdio``/subprocess option (MC-R2,
"NINGÚN transporte stdio/subprocess DEBE estar disponible").
"""

from app.integrations.adapters.mcp.reader import McpResourceReader
from app.integrations.ports import ApiTokenHandshake, Capability, CredentialKind, OAuthHandshake


class McpAdapter:
    """MCP adapter — read-only; ``credential_kind`` is a per-CONNECTOR
    choice (``api_token`` or ``none``), not a fixed adapter-level value like
    GLPI/Jira (see ``credential_kinds`` below and its docstring on
    ``IntegrationAdapter``, IP-R3).
    """

    provider = "mcp"
    capabilities = frozenset({Capability.external_resources})
    # Class-level `credential_kind` (singular) stays a FIXED representative
    # value ONLY for the pre-19 core code paths that check
    # `!= CredentialKind.oauth` regardless of which non-oauth kind it is
    # (`app/integrations/oauth.py`'s `_require_oauth_handshake`,
    # `app/modules/connectors/service.py`'s `authorize()` reads the
    # CONNECTOR row's own `credential_kind`, never this class attribute, for
    # the api_token/none distinction — see `credential_kinds` below, the
    # field the connectors service validates a REGISTRATION request's
    # chosen `credential_kind` against).
    credential_kind = CredentialKind.api_token
    credential_kinds = frozenset({CredentialKind.api_token, CredentialKind.none})

    def __init__(self) -> None:
        # Neither handshake Protocol applies: MCP's credential (token or
        # none) travels in the SAME `POST /connectors` request the
        # connector is created with (specs/connectors/spec.md delta,
        # "Registro de conector con credencial directa") — never through
        # `authorize`/`callback` NOR the separate `register_api_token_
        # credentials` endpoint GLPI/Jira use.
        self.oauth: OAuthHandshake | None = None
        self.api_token: ApiTokenHandshake | None = None
        self._ports: dict[Capability, object] = {
            Capability.external_resources: McpResourceReader(),
        }

    def port_for(self, capability: Capability) -> object | None:
        """Return this adapter's implementation of ``capability``'s port,
        or ``None`` when it is not supported (only ``external_resources``)."""

        if capability not in self.capabilities:
            return None
        return self._ports.get(capability)
