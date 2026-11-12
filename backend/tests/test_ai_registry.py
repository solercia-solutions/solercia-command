"""`get_llm_port()` provider selection (design.md "Registro"). Requirement
`llm-port` R2, the isolation scenario of R5, and R8. `_ADAPTERS` registers
`"fake"` and `"openai_compatible"` as of this slice; `"anthropic"` joins
in slice 3.
"""

import builtins
import sys
from pathlib import Path

import pytest

from app.ai.adapters.fake import FakeLlmAdapter
from app.ai.errors import LlmConfigInvalid
from app.ai.registry import get_llm_port
from app.config import Settings, settings


def test_returns_the_fake_adapter_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    assert isinstance(get_llm_port(), FakeLlmAdapter)


def test_selects_the_adapter_named_by_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    assert isinstance(get_llm_port(), FakeLlmAdapter)


def test_unknown_provider_raises_llm_config_invalid_not_key_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama-legacy")
    with pytest.raises(LlmConfigInvalid) as excinfo:
        get_llm_port()
    assert excinfo.value.status_code == 422
    assert "ollama-legacy" not in excinfo.value.detail


def test_reads_the_setting_at_call_time_not_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """A module-level constant captured at import would never observe
    either flip below; reading live does."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", "unregistered-provider")
    with pytest.raises(LlmConfigInvalid):
        get_llm_port()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    assert isinstance(get_llm_port(), FakeLlmAdapter)


def test_does_not_import_the_anthropic_package_for_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    real_import = builtins.__import__

    def _guarded_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "anthropic" or name.startswith("anthropic."):
            raise AssertionError("the anthropic package must never be imported here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    get_llm_port()
    assert "anthropic" not in sys.modules
    assert "app.ai.adapters.anthropic" not in sys.modules


def test_fake_adapter_is_a_process_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER", "fake")
    assert get_llm_port() is get_llm_port()


def test_settings_llm_defaults_are_safe() -> None:
    defaults = Settings()
    assert defaults.LLM_PROVIDER == "fake"
    assert defaults.LLM_MAX_RETRIES == 2
    assert defaults.LLM_ANTHROPIC_FALLBACKS is False


def test_docker_compose_backend_environment_pins_llm_provider_fake() -> None:
    """No `yaml` parser is declared in `requirements.txt` (out of scope
    here), so this reads the `backend:`/`frontend:`-bounded text block."""
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose_text = compose_path.read_text()
    backend_start = compose_text.index("\n  backend:\n")
    frontend_start = compose_text.index("\n  frontend:\n", backend_start)
    assert 'LLM_PROVIDER: "fake"' in compose_text[backend_start:frontend_start]
