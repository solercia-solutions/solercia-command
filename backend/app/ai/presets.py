"""Provider presets (C04) — the «llanta» catalogue lives in code, not in the
database: adding a provider is a code change reviewed like any other.

Every preset speaks the OpenAI-compatible protocol (`/chat/completions`,
`/embeddings`, `/models`). Model names are editable suggestions; base URLs
of external presets are fixed (the anti-SSRF guard enforces it). `locality`
tells the UI whether mail content leaves the machine.
"""

from dataclasses import dataclass
from typing import Literal

from app.ai.errors import LlmPresetUnknown

Locality = Literal["local", "external"]
JsonMode = Literal["json_object", "json_schema_openai", "json_schema_llamacpp"]


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    label: str
    locality: Locality
    #: ``None`` only for ``custom`` (the admin must supply one).
    base_url: str | None
    chat_model: str
    embedding_model: str | None
    requires_api_key: bool
    #: Local presets accept another loopback/Docker-host URL (other port).
    base_url_editable: bool
    json_mode: JsonMode
    #: Some providers reject an unknown ``reasoning_effort`` with a 400.
    sends_reasoning_effort: bool
    #: Ollama reads ``options.num_ctx``; others would reject/ignore it.
    supports_num_ctx: bool = False


DEFAULT_PRESET_KEY = "ollama_local"

PRESETS: dict[str, ProviderPreset] = {
    preset.key: preset
    for preset in (
        ProviderPreset(
            key="ollama_local",
            label="Ollama (local)",
            locality="local",
            base_url="http://127.0.0.1:11434/v1",
            chat_model="qwen3.5:9b-q4_K_M",
            embedding_model="qwen3-embedding:0.6b",
            requires_api_key=False,
            base_url_editable=True,
            json_mode="json_schema_openai",
            sends_reasoning_effort=True,
            supports_num_ctx=True,
        ),
        ProviderPreset(
            key="llamacpp_local",
            label="llama.cpp (local)",
            locality="local",
            base_url="http://127.0.0.1:8080/v1",
            chat_model="local-model",
            embedding_model=None,
            requires_api_key=False,
            base_url_editable=True,
            json_mode="json_schema_llamacpp",
            sends_reasoning_effort=False,
        ),
        ProviderPreset(
            key="openai",
            label="OpenAI",
            locality="external",
            base_url="https://api.openai.com/v1",
            chat_model="gpt-5-mini",
            embedding_model="text-embedding-3-small",
            requires_api_key=True,
            base_url_editable=False,
            json_mode="json_schema_openai",
            sends_reasoning_effort=True,
        ),
        ProviderPreset(
            key="openrouter",
            label="OpenRouter",
            locality="external",
            base_url="https://openrouter.ai/api/v1",
            chat_model="openai/gpt-5-mini",
            embedding_model=None,
            requires_api_key=True,
            base_url_editable=False,
            json_mode="json_schema_openai",
            sends_reasoning_effort=False,
        ),
        ProviderPreset(
            key="groq",
            label="Groq",
            locality="external",
            base_url="https://api.groq.com/openai/v1",
            chat_model="llama-3.1-8b-instant",
            embedding_model=None,
            requires_api_key=True,
            base_url_editable=False,
            json_mode="json_object",
            sends_reasoning_effort=False,
        ),
        ProviderPreset(
            key="deepseek",
            label="DeepSeek",
            locality="external",
            base_url="https://api.deepseek.com",
            chat_model="deepseek-chat",
            embedding_model=None,
            requires_api_key=True,
            base_url_editable=False,
            json_mode="json_object",
            sends_reasoning_effort=False,
        ),
        ProviderPreset(
            key="mistral",
            label="Mistral",
            locality="external",
            base_url="https://api.mistral.ai/v1",
            chat_model="mistral-small-latest",
            embedding_model="mistral-embed",
            requires_api_key=True,
            base_url_editable=False,
            json_mode="json_object",
            sends_reasoning_effort=False,
        ),
        ProviderPreset(
            key="custom",
            label="URL propia (compatible con OpenAI)",
            locality="external",
            base_url=None,
            chat_model="",
            embedding_model=None,
            requires_api_key=False,
            base_url_editable=True,
            json_mode="json_object",
            sends_reasoning_effort=True,
        ),
    )
}


def get_preset(key: str) -> ProviderPreset:
    """Unknown keys raise `LlmPresetUnknown` without naming the value."""

    preset = PRESETS.get(key)
    if preset is None:
        raise LlmPresetUnknown()
    return preset


def preset_base_urls() -> set[str]:
    """Fixed preset URLs, admitted by the global `LLM_*` allowlist too."""

    return {p.base_url for p in PRESETS.values() if p.base_url}
