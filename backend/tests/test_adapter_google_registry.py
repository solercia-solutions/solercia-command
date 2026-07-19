"""RED tests for `app/integrations/adapters/google/adapter.py` +
`__init__.py` registration (change 16-adapter-google,
specs/google-adapter/spec.md GA-R1/GA-R8/GA-R10).
"""


class TestGoogleAdapterRegistration:
    def test_get_adapter_returns_google_instance_without_editing_the_core(
        self,
    ) -> None:
        """Scenario: El adaptador aparece por su provider — the core's
        registry resolves ``provider="google"`` to this adapter's instance
        purely because the adapter's OWN module ran
        ``register_adapter(...)`` at import time (IP-R2, "sin tocar el
        núcleo")."""

        import app.integrations.adapters.google  # noqa: F401
        from app.integrations.adapters.google.adapter import GoogleAdapter
        from app.integrations.registry import get_adapter

        resolved = get_adapter("google")

        assert resolved is not None
        assert isinstance(resolved, GoogleAdapter)
        assert resolved.provider == "google"

    def test_external_tasks_capability_is_not_declared(self) -> None:
        """Scenario: Capacidad no declarada queda excluida — Google Tasks
        queda explícitamente fuera de este cambio (GA-R10)."""

        from app.integrations.adapters.google.adapter import GoogleAdapter
        from app.integrations.ports import Capability

        adapter = GoogleAdapter()

        assert Capability.external_tasks not in adapter.capabilities
        assert Capability.tickets not in adapter.capabilities
        assert adapter.port_for(Capability.external_tasks) is None

    def test_declared_capabilities_are_exactly_mail_calendar_and_meeting_notes(
        self,
    ) -> None:
        """Triangulation: las TRES capacidades que sí declara son
        exactamente `mail`/`calendar`/`meeting_notes` — ni más ni menos."""

        from app.integrations.adapters.google.adapter import GoogleAdapter
        from app.integrations.ports import Capability

        adapter = GoogleAdapter()

        assert adapter.capabilities == frozenset(
            {Capability.mail, Capability.calendar, Capability.meeting_notes}
        )

    def test_every_declared_capability_resolves_to_a_real_port(self) -> None:
        """Cada capacidad declarada tiene un puerto REAL detrás, no
        `None`."""

        from app.integrations.adapters.google.adapter import GoogleAdapter
        from app.integrations.adapters.google.calendar import GoogleCalendarReader
        from app.integrations.adapters.google.mail import GmailMailReader
        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )
        from app.integrations.ports import Capability

        adapter = GoogleAdapter()

        assert isinstance(adapter.port_for(Capability.mail), GmailMailReader)
        assert isinstance(
            adapter.port_for(Capability.calendar), GoogleCalendarReader
        )
        assert isinstance(
            adapter.port_for(Capability.meeting_notes), DriveMeetingNotesReader
        )

    def test_adapter_oauth_methods_delegate_to_the_oauth_module(self) -> None:
        """`authorize_url`/`exchange_code`/`refresh` on the adapter itself
        are thin delegations to `oauth.py` — proven here by checking
        `authorize_url` produces the SAME URL shape the module-level
        function does."""

        from app.config import Settings
        from app.integrations.adapters.google import oauth
        from app.integrations.adapters.google.adapter import GoogleAdapter

        settings = Settings(GOOGLE_OAUTH_CLIENT_ID="client-xyz")
        adapter = GoogleAdapter(settings=settings)

        url = adapter.authorize_url("state-1", "https://app.test/callback", [])

        assert url == oauth.authorize_url(
            "state-1", "https://app.test/callback", [], settings=settings
        )


def _called_http_verbs(module) -> set[str]:
    """Return every `.get`/`.post`/`.put`/`.patch`/`.delete` METHOD CALL
    name found in `module`'s own source (AST-based — never matches text
    inside a comment/docstring, unlike a plain substring search)."""

    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(inspect.getsource(module))
    tree = ast.parse(source)
    verbs = {"get", "post", "put", "patch", "delete"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in verbs
        ):
            found.add(node.func.attr)
    return found


class TestReadOnlyBoundary:
    def test_client_and_every_port_never_call_a_write_http_verb(self) -> None:
        """Scenario: Sin método de escritura en el adaptador — `client.py`
        (the ONLY module that ever talks to a Google API) and every port
        module (mail/calendar/meeting_notes) never call a write HTTP verb;
        every Google API call is a `GET` (GA-R8)."""

        from app.integrations.adapters.google import (
            calendar as calendar_module,
        )
        from app.integrations.adapters.google import client as client_module
        from app.integrations.adapters.google import mail as mail_module
        from app.integrations.adapters.google import (
            meeting_notes as meeting_notes_module,
        )

        for module in (client_module, mail_module, calendar_module, meeting_notes_module):
            verbs = _called_http_verbs(module)
            assert verbs <= {"get"}, f"{module.__name__} calls write verb(s): {verbs}"

    def test_oauth_module_posts_only_to_the_token_endpoint_never_to_a_data_api(
        self,
    ) -> None:
        """The package's ONE write HTTP verb — `oauth.py`'s `.post(...)`
        for the token exchange/refresh — targets ONLY
        `GOOGLE_TOKEN_BASE_URL` (Google's own token endpoint), never
        `GOOGLE_GMAIL_BASE_URL`/`GOOGLE_CALENDAR_BASE_URL`/
        `GOOGLE_DRIVE_BASE_URL` (the OAuth handshake itself is not a
        "write toward Google data", spec.md's scope is explicitly the
        Gmail/Calendar/Drive write endpoints — send mail, create event,
        edit file)."""

        import inspect

        from app.integrations.adapters.google import oauth as oauth_module

        source = inspect.getsource(oauth_module)
        verbs = _called_http_verbs(oauth_module)

        # `.get(...)` also appears as plain `dict.get(...)` calls (e.g.
        # `payload.get("scope")`), not an HTTP verb — only the WRITE verbs
        # matter for this guard, and `post` (the token endpoint) is the
        # sole one this module ever calls.
        assert "post" in verbs
        assert not {"put", "patch", "delete"} & verbs
        assert "GOOGLE_GMAIL_BASE_URL" not in source
        assert "GOOGLE_CALENDAR_BASE_URL" not in source
        assert "GOOGLE_DRIVE_BASE_URL" not in source
        assert "GOOGLE_TOKEN_BASE_URL" in source

    def test_no_port_declares_more_than_its_one_read_method(self) -> None:
        """Regression guard: no port implements a write capability BY
        DESIGN — every `*Reader` only ever exposes its ONE
        `list_*`/read method as a public method."""

        from app.integrations.adapters.google.calendar import GoogleCalendarReader
        from app.integrations.adapters.google.mail import GmailMailReader
        from app.integrations.adapters.google.meeting_notes import (
            DriveMeetingNotesReader,
        )

        for port_cls in (GmailMailReader, GoogleCalendarReader, DriveMeetingNotesReader):
            public_methods = {
                name
                for name in vars(port_cls)
                if not name.startswith("_") and callable(vars(port_cls)[name])
            }
            assert len(public_methods) == 1, (
                f"{port_cls.__name__} declares more than its ONE read method: "
                f"{public_methods}"
            )
