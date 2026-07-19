"""Per-provider OIDC configuration, loaded from the environment (design.md
D2, sso-oidc R6).

``load_provider_config`` reads ``OIDC_{PROVIDER}_ISSUER/CLIENT_ID/
CLIENT_SECRET/REDIRECT_URI`` straight off ``os.environ`` by provider name —
DELIBERATELY not as fixed ``app.config.Settings`` fields. This is what makes
"a second IdP is config-only, zero code changes" (R6) literally true: the
function is generic over ``provider``, so a new set of env vars is all a
second provider needs.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OidcProviderConfig:
    """Everything an :class:`~app.modules.auth.oidc.client.OidcClient`
    needs for one provider, resolved once from the environment."""

    provider: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str


def load_provider_config(provider: str) -> OidcProviderConfig | None:
    """Return ``provider``'s config, or ``None`` when it is not (fully)
    configured — any missing var means the provider is unconfigured, never
    a partially-usable config."""

    prefix = f"OIDC_{provider.upper()}_"
    issuer = os.environ.get(f"{prefix}ISSUER")
    client_id = os.environ.get(f"{prefix}CLIENT_ID")
    client_secret = os.environ.get(f"{prefix}CLIENT_SECRET")
    redirect_uri = os.environ.get(f"{prefix}REDIRECT_URI")

    if not (issuer and client_id and client_secret and redirect_uri):
        return None

    return OidcProviderConfig(
        provider=provider,
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )
