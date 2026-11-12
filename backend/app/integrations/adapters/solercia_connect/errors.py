"""Typed failures for the Solercia Connect adapter.

Every failure here is deliberately distinguishable, because the platform
decision record (``docs/decisions/2026-08-23-solercia-platform-decisions.md``,
§2.3) requires that a Connect outage degrade only the capabilities Connect
backs — never the Command core. A caller that cannot tell "Connect is not
running" from "Connect answered that the account is wrong" cannot honour that.

``code`` carries Connect's own ``error.code`` when the failure was mapped from
an envelope (``browser_login_required``, ``action_required``...) and each
class's ``default_code`` otherwise. Command's connector facade needs it to
tell "the person must log in again" apart from "the runtime broke", which the
exception class alone cannot express.
"""


class SolerciaConnectError(Exception):
    """Base class for every Solercia Connect adapter failure."""

    default_code: str | None = None

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class SolerciaConnectConfigError(SolerciaConnectError):
    """The connector's stored settings are unusable.

    Raised before any network call — a base URL outside the allowlist, a
    missing API key, a malformed access context.
    """

    default_code = "solercia_connect_not_configured"


class SolerciaConnectUnavailableError(SolerciaConnectError):
    """The local Connect runtime did not answer.

    This is the expected failure when the user simply has not started it. It
    is a degradation, not a defect: the caller reports the capability as
    unavailable and leaves the rest of Command untouched.
    """

    default_code = "solercia_connect_unavailable"


class SolerciaConnectNotConfiguredError(SolerciaConnectUnavailableError):
    """Connect is running but answered HTTP 503: it is not configured to
    serve this request (no API key on its side, feature disabled...).

    Still an ``Unavailable`` for every caller that only cares whether the
    read can proceed; distinguishable for the connector facade, which
    reports it as a misconfiguration rather than a stopped runtime.
    """

    default_code = "solercia_connect_misconfigured"


class SolerciaConnectAuthError(SolerciaConnectError):
    """Connect rejected the API key, or its own provider session is invalid."""

    default_code = "solercia_connect_unauthorized"


class SolerciaConnectAccountMismatchError(SolerciaConnectError):
    """Connect answered for an account other than the one requested.

    The platform record (§4.1-4.3) requires one canonical observed identity
    before any data is read, and provenance that never substitutes a requested
    identity for a verified one. A mismatch yields zero records.
    """

    default_code = "browser_account_mismatch"


class SolerciaConnectProtocolError(SolerciaConnectError):
    """Connect answered in a shape this adapter does not recognize.

    Raised when the envelope is missing its schema, its records, or carries a
    schema version this adapter was not written against.
    """

    default_code = "solercia_connect_protocol_error"
