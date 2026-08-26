"""Selects the single active `LlmPort` adapter for the process (change
48-puerto-llm, design.md "Registro"). `settings.LLM_PROVIDER` is read AT
CALL TIME, never cached (D3) — mirrors `get_email_sender()`.

`_ADAPTERS` only registers `"fake"` in this slice; `"openai_compatible"`
and `"anthropic"` join in slices 2/3 without changing this module's shape.
Importing this module never imports the `anthropic` SDK.
"""

from collections.abc import Callable

from app.ai.adapters.fake import get_fake_adapter
from app.ai.errors import LlmConfigInvalid
from app.ai.ports import LlmPort
from app.config import Settings
from app.config import settings as default_settings


def _build_fake(_settings: Settings) -> LlmPort:
    return get_fake_adapter()


_ADAPTERS: dict[str, Callable[[Settings], LlmPort]] = {
    "fake": _build_fake,
}


def get_llm_port(settings: Settings | None = None) -> LlmPort:
    """Unknown `LLM_PROVIDER` raises `LlmConfigInvalid` (422), never a
    bare `KeyError`; the invalid value is never named."""
    active = settings or default_settings
    builder = _ADAPTERS.get(active.LLM_PROVIDER)
    if builder is None:
        raise LlmConfigInvalid()
    return builder(active)
