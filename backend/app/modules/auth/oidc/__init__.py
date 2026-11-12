"""Generic OIDC Authorization Code + PKCE client (change 20-sso-keycloak).

Provider-agnostic: adding a second IdP is new ``OIDC_{PROVIDER}_*`` env
vars alone, never a code change (design.md D2/R6).
"""
