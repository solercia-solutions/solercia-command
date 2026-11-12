"""RED tests for the adapter registry (IP-R1/IP-R2,
specs/integration-ports/spec.md "Registro de adaptadores extensible en
import-time").
"""

from app.integrations.ports import Capability
from app.integrations.registry import get_adapter, register_adapter


class _OutlookLikeAdapter:
    provider = "test-outlook"
    capabilities = frozenset({Capability.mail})

    def authorize_url(self, state, redirect_uri, scopes):
        return f"https://outlook.test/authorize?state={state}"

    async def exchange_code(self, code, redirect_uri):
        raise NotImplementedError

    async def refresh(self, refresh_token):
        raise NotImplementedError

    def port_for(self, capability):
        return self if capability == Capability.mail else None

    async def list_messages(self, ctx, *, since=None, limit=50):
        return []


class _GmailLikeAdapter:
    provider = "test-gmail"
    capabilities = frozenset({Capability.mail})

    def authorize_url(self, state, redirect_uri, scopes):
        return f"https://gmail.test/authorize?state={state}"

    async def exchange_code(self, code, redirect_uri):
        raise NotImplementedError

    async def refresh(self, refresh_token):
        raise NotImplementedError

    def port_for(self, capability):
        return self if capability == Capability.mail else None

    async def list_messages(self, ctx, *, since=None, limit=50):
        return []


def test_new_adapter_registers_without_editing_registry_module() -> None:
    """Scenario: Adaptador nuevo se registra sin tocar el núcleo — calling
    `register_adapter` from OUTSIDE registry.py (standing in for a real
    adapter's import-time self-registration) makes it resolvable by
    provider, with zero edits to registry.py."""

    adapter = _OutlookLikeAdapter()
    register_adapter(adapter)

    resolved = get_adapter("test-outlook")
    assert resolved is adapter


def test_get_adapter_resolves_by_provider_without_conditionals() -> None:
    """Scenario: Consulta del registro por proveedor — two adapters with
    distinct `provider` values each resolve to their OWN instance."""

    outlook = _OutlookLikeAdapter()
    gmail = _GmailLikeAdapter()
    register_adapter(outlook)
    register_adapter(gmail)

    assert get_adapter("test-outlook") is outlook
    assert get_adapter("test-gmail") is gmail
    assert get_adapter("unknown-provider") is None


def test_two_mail_providers_expose_the_same_port_contract() -> None:
    """Scenario: Un puerto sirve a varios proveedores de correo — Outlook-
    and Gmail-like adapters both implement `MailReaderPort` (`list_messages`)
    rather than provider-specific methods."""

    outlook = _OutlookLikeAdapter()
    gmail = _GmailLikeAdapter()

    outlook_port = outlook.port_for(Capability.mail)
    gmail_port = gmail.port_for(Capability.mail)

    assert hasattr(outlook_port, "list_messages")
    assert hasattr(gmail_port, "list_messages")
