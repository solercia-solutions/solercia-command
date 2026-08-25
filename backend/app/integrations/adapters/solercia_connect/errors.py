"""Typed failures for the Solercia Connect adapter.

Every failure here is deliberately distinguishable, because the platform
decision record (``docs/decisions/2026-08-23-solercia-platform-decisions.md``,
§2.3) requires that a Connect outage degrade only the capabilities Connect
backs — never the Command core. A caller that cannot tell "Connect is not
running" from "Connect answered that the account is wrong" cannot honour that.
"""


class SolerciaConnectError(Exception):
    """Base class for every Solercia Connect adapter failure."""


class SolerciaConnectConfigError(SolerciaConnectError):
    """The connector's stored settings are unusable.

    Raised before any network call — a base URL outside the allowlist, a
    missing API key, a malformed access context.
    """


class SolerciaConnectUnavailableError(SolerciaConnectError):
    """The local Connect runtime did not answer.

    This is the expected failure when the user simply has not started it. It
    is a degradation, not a defect: the caller reports the capability as
    unavailable and leaves the rest of Command untouched.
    """


class SolerciaConnectAuthError(SolerciaConnectError):
    """Connect rejected the API key, or its own provider session is invalid."""


class SolerciaConnectAccountMismatchError(SolerciaConnectError):
    """Connect answered for an account other than the one requested.

    The platform record (§4.1-4.3) requires one canonical observed identity
    before any data is read, and provenance that never substitutes a requested
    identity for a verified one. A mismatch yields zero records.
    """


class SolerciaConnectProtocolError(SolerciaConnectError):
    """Connect answered in a shape this adapter does not recognize.

    Raised when the envelope is missing its schema, its records, or carries a
    schema version this adapter was not written against.
    """
