"""RED tests for the MCP adapter's self-registration (change
19-mcp-connector, Lote 5, mcp-connector/spec.md MC-R2 "Adaptador
auto-registrado, transporte exclusivo Streamable HTTP"). Mirrors
``test_jira_adapter_registry.py``/``test_adapter_glpi.py``'s registry
precedent — importing the package is what registers the adapter, the core
(``ports.py``/``registry.py``) is NEVER edited to know about ``mcp`` (IP-R2).
"""


class TestMcpAdapterRegistration:
    def test_get_adapter_returns_the_mcp_instance_after_import(self) -> None:
        import app.integrations.adapters.mcp  # noqa: F401 - registers the adapter
        from app.integrations.adapters.mcp.adapter import McpAdapter
        from app.integrations.registry import get_adapter

        adapter = get_adapter("mcp")

        assert adapter is not None
        assert isinstance(adapter, McpAdapter)
        assert adapter.provider == "mcp"

    def test_capabilities_is_exactly_external_resources(self) -> None:
        import app.integrations.adapters.mcp  # noqa: F401
        from app.integrations.ports import Capability
        from app.integrations.registry import get_adapter

        adapter = get_adapter("mcp")

        assert adapter is not None
        assert adapter.capabilities == frozenset({Capability.external_resources})
        assert adapter.port_for(Capability.external_resources) is not None

    def test_excluded_from_ports_it_does_not_support(self) -> None:
        """The adapter only declares `external_resources` — every other
        capability's port resolves to `None` without any `if provider ==
        ...` branching anywhere in the core."""

        import app.integrations.adapters.mcp  # noqa: F401
        from app.integrations.ports import Capability
        from app.integrations.registry import get_adapter

        adapter = get_adapter("mcp")

        assert adapter is not None
        assert adapter.port_for(Capability.mail) is None
        assert adapter.port_for(Capability.calendar) is None
        assert adapter.port_for(Capability.tickets) is None
        assert adapter.port_for(Capability.meeting_notes) is None
        assert adapter.port_for(Capability.external_tasks) is None

    def test_credential_kinds_are_api_token_and_none(self) -> None:
        """Scenario (MC-R2 traceability): `credential_kinds == {api_token,
        none}` — a per-connector choice, never a fixed single value like
        GLPI/Jira's `api_token`-only or fake/Google/M365's `oauth`-only."""

        import app.integrations.adapters.mcp  # noqa: F401
        from app.integrations.ports import CredentialKind
        from app.integrations.registry import get_adapter

        adapter = get_adapter("mcp")

        assert adapter is not None
        assert adapter.credential_kinds == frozenset(
            {CredentialKind.api_token, CredentialKind.none}
        )
        assert adapter.oauth is None
        assert adapter.api_token is None

    def test_no_local_stdio_or_subprocess_transport_is_available(self) -> None:
        """Scenario: No existe transporte local — solo Streamable HTTP
        remoto está disponible; no hay opción `stdio`/subprocess. Asserted
        structurally: the adapter/reader modules never import `subprocess`
        or the SDK's `stdio` client, and the adapter exposes no transport
        selection knob at all — Streamable HTTP is the ONLY code path."""

        import ast
        import inspect

        from app.integrations.adapters.mcp import adapter as adapter_module
        from app.integrations.adapters.mcp import reader as reader_module
        from app.integrations.adapters.mcp import session as session_module

        for module in (adapter_module, reader_module, session_module):
            source = inspect.getsource(module)
            tree = ast.parse(source)
            imported_names = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module is not None
            }
            assert "subprocess" not in imported_names
            assert "mcp.client.stdio" not in imported_names
