"""RED tests for the Jira adapter's self-registration (change
18-adapter-jira, specs/jira-import/spec.md "Registro del adaptador Jira en
el núcleo"). Mirrors ``test_adapter_glpi.py``'s registry precedent —
importing the package is what registers the adapter, the core (``ports.py``/
``registry.py``) is NEVER edited to know about ``jira`` (IP-R2).
"""


class TestJiraAdapterRegistration:
    def test_get_adapter_returns_the_jira_instance_after_import(self) -> None:
        import app.integrations.adapters.jira  # noqa: F401 - registers the adapter
        from app.integrations.adapters.jira.adapter import JiraAdapter
        from app.integrations.registry import get_adapter

        adapter = get_adapter("jira")

        assert adapter is not None
        assert isinstance(adapter, JiraAdapter)
        assert adapter.provider == "jira"

    def test_credential_kind_is_api_token(self) -> None:
        import app.integrations.adapters.jira  # noqa: F401
        from app.integrations.ports import CredentialKind
        from app.integrations.registry import get_adapter

        adapter = get_adapter("jira")

        assert adapter is not None
        assert adapter.credential_kind == CredentialKind.api_token
        assert adapter.oauth is None
        assert adapter.api_token is not None

    def test_supports_the_tickets_capability(self) -> None:
        import app.integrations.adapters.jira  # noqa: F401
        from app.integrations.ports import Capability
        from app.integrations.registry import get_adapter

        adapter = get_adapter("jira")

        assert adapter is not None
        assert Capability.tickets in adapter.capabilities
        assert adapter.port_for(Capability.tickets) is not None

    def test_excluded_from_ports_it_does_not_support(self) -> None:
        """The adapter only declares `tickets` — every other capability's
        port resolves to `None` without any `if provider == ...` branching
        anywhere in the core."""

        import app.integrations.adapters.jira  # noqa: F401
        from app.integrations.ports import Capability
        from app.integrations.registry import get_adapter

        adapter = get_adapter("jira")

        assert adapter is not None
        assert adapter.port_for(Capability.mail) is None
        assert adapter.port_for(Capability.calendar) is None
        assert adapter.port_for(Capability.meeting_notes) is None
        assert adapter.port_for(Capability.external_tasks) is None
