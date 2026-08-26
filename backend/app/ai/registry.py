"""Selects the single active `LlmPort` adapter for the process (change
48-puerto-llm, design.md "Registro"). `settings.LLM_PROVIDER` is read AT
CALL TIME, never cached (D3) — mirrors `get_email_sender()`.

`_ADAPTERS` registers `"fake"`, `"openai_compatible"` and `"anthropic"`.
`_build_anthropic` reaches the last one through a lazy
`importlib.import_module` so importing THIS module never imports the
`anthropic` SDK — only selecting `LLM_PROVIDER="anthropic"` at call time
does (spec `llm-port` R5 "Aislamiento de dependencia").
"""

import importlib
from collections.abc import Callable

from app.ai.adapters.fake import get_fake_adapter
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter
from app.ai.errors import LlmConfigInvalid
from app.ai.ports import LlmPort
from app.config import Settings
from app.config import settings as default_settings


def _build_fake(_settings: Settings) -> LlmPort:
    return get_fake_adapter()


def _build_openai_compatible(active: Settings) -> LlmPort:
    return OpenAiCompatibleAdapter(settings=active)


def _build_anthropic(active: Settings) -> LlmPort:
    module = importlib.import_module("app.ai.adapters.anthropic")
    adapter: LlmPort = module.AnthropicAdapter(settings=active)
    return adapter


_ADAPTERS: dict[str, Callable[[Settings], LlmPort]] = {
    "fake": _build_fake,
    "openai_compatible": _build_openai_compatible,
    "anthropic": _build_anthropic,
}


def get_llm_port(settings: Settings | None = None) -> LlmPort:
    """Unknown `LLM_PROVIDER` raises `LlmConfigInvalid` (422), never a
    bare `KeyError`; the invalid value is never named."""
    active = settings or default_settings
    builder = _ADAPTERS.get(active.LLM_PROVIDER)
    if builder is None:
        raise LlmConfigInvalid()
    return builder(active)
