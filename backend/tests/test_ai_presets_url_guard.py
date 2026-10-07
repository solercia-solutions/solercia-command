"""C04: provider presets (code, not DB) and the anti-SSRF base URL guard.

The guard is pure: DNS resolution is injected, so no test touches the
network. Rejections never echo the offending URL.
"""

import pytest

from app.ai.errors import LlmBaseUrlRejected, LlmPresetUnknown
from app.ai.presets import DEFAULT_PRESET_KEY, PRESETS, get_preset
from app.ai.url_guard import is_loopback_url, validate_provider_base_url


def _no_dns(host: str) -> list[str]:
    raise AssertionError(f"DNS must not be resolved for {host}")


def _dns(mapping: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        if host not in mapping:
            raise OSError("unknown host")
        return mapping[host]

    return resolve


# --- presets -----------------------------------------------------------------


def test_default_preset_is_local_ollama_with_qwen_models():
    preset = get_preset(DEFAULT_PRESET_KEY)
    assert DEFAULT_PRESET_KEY == "ollama_local"
    assert preset.base_url == "http://127.0.0.1:11434/v1"
    assert preset.chat_model == "qwen3.5:9b-q4_K_M"
    assert preset.embedding_model == "qwen3-embedding:0.6b"
    assert preset.requires_api_key is False
    assert preset.locality == "local"


@pytest.mark.parametrize(
    ("key", "base_url", "locality"),
    [
        ("ollama_local", "http://127.0.0.1:11434/v1", "local"),
        ("llamacpp_local", "http://127.0.0.1:8080/v1", "local"),
        ("openai", "https://api.openai.com/v1", "external"),
        ("openrouter", "https://openrouter.ai/api/v1", "external"),
        ("groq", "https://api.groq.com/openai/v1", "external"),
        ("deepseek", "https://api.deepseek.com", "external"),
        ("mistral", "https://api.mistral.ai/v1", "external"),
        ("custom", None, "external"),
    ],
)
def test_every_requested_preset_exists_with_url_and_locality(key, base_url, locality):
    preset = PRESETS[key]
    assert preset.key == key
    assert preset.base_url == base_url
    assert preset.locality == locality
    assert preset.label


def test_external_presets_require_a_key_and_local_ones_do_not():
    for preset in PRESETS.values():
        if preset.key in ("ollama_local", "llamacpp_local", "custom"):
            assert preset.requires_api_key is False
        else:
            assert preset.requires_api_key is True


def test_unknown_preset_raises_a_typed_error_without_echoing_it():
    with pytest.raises(LlmPresetUnknown) as caught:
        get_preset("evil-preset")
    assert caught.value.status_code == 422
    assert caught.value.code == "llm_preset_unknown"
    assert "evil-preset" not in caught.value.detail


# --- guard: fixed external presets ------------------------------------------


@pytest.mark.parametrize("key", ["openai", "openrouter", "groq", "deepseek", "mistral"])
def test_external_preset_uses_its_fixed_url_without_dns(key):
    preset = get_preset(key)
    assert validate_provider_base_url(preset, None, resolver=_no_dns) == preset.base_url
    assert validate_provider_base_url(preset, preset.base_url + "/", resolver=_no_dns) == (
        preset.base_url
    )


def test_external_preset_rejects_a_different_url():
    with pytest.raises(LlmBaseUrlRejected) as caught:
        validate_provider_base_url(
            get_preset("openai"), "https://attacker.example/v1", resolver=_no_dns
        )
    assert "attacker" not in caught.value.detail
    assert caught.value.code == "llm_base_url_rejected"


# --- guard: local presets ---------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/v1",
        "http://localhost:11434/v1",
        "http://[::1]:11434/v1",
        "http://host.docker.internal:11434/v1",
        "http://127.0.0.1:9999/v1",
    ],
)
def test_local_preset_accepts_loopback_or_docker_host(url):
    assert validate_provider_base_url(get_preset("ollama_local"), url, resolver=_no_dns) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10:11434/v1",
        "http://ollama.example.com:11434/v1",
        "http://169.254.169.254/latest",
    ],
)
def test_local_preset_rejects_non_loopback_hosts(url):
    with pytest.raises(LlmBaseUrlRejected):
        validate_provider_base_url(get_preset("llamacpp_local"), url, resolver=_no_dns)


# --- guard: custom ----------------------------------------------------------


def test_custom_https_public_host_is_accepted():
    url = "https://llm.example.com/v1"
    resolver = _dns({"llm.example.com": ["93.184.216.34"]})
    assert validate_provider_base_url(get_preset("custom"), url, resolver=resolver) == url


def test_custom_plain_http_to_public_host_is_rejected():
    resolver = _dns({"llm.example.com": ["93.184.216.34"]})
    with pytest.raises(LlmBaseUrlRejected):
        validate_provider_base_url(
            get_preset("custom"), "http://llm.example.com/v1", resolver=resolver
        )


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8000/v1", "http://localhost:1234/v1", "http://[::1]:1234/v1"],
)
def test_custom_allows_explicit_loopback_over_http(url):
    assert validate_provider_base_url(get_preset("custom"), url, resolver=_no_dns) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.5/v1",
        "https://172.16.3.4/v1",
        "https://192.168.0.1/v1",
        "https://169.254.169.254/v1",
        "https://100.64.0.1/v1",
        "https://0.0.0.0/v1",
        "https://[fe80::1]/v1",
        "https://[fd00::1]/v1",
        "https://[::ffff:10.0.0.1]/v1",
        "https://224.0.0.1/v1",
    ],
)
def test_custom_blocks_private_link_local_and_reserved_ip_literals(url):
    with pytest.raises(LlmBaseUrlRejected) as caught:
        validate_provider_base_url(get_preset("custom"), url, resolver=_no_dns)
    assert url not in caught.value.detail


def test_custom_blocks_a_hostname_that_resolves_to_a_private_address():
    resolver = _dns({"internal.example.com": ["93.184.216.34", "10.1.2.3"]})
    with pytest.raises(LlmBaseUrlRejected):
        validate_provider_base_url(
            get_preset("custom"), "https://internal.example.com/v1", resolver=resolver
        )


def test_custom_blocks_metadata_hostnames_and_unresolvable_hosts():
    resolver = _dns({"metadata.google.internal": ["169.254.169.254"]})
    for url in ("https://metadata.google.internal/v1", "https://nowhere.invalid/v1"):
        with pytest.raises(LlmBaseUrlRejected):
            validate_provider_base_url(get_preset("custom"), url, resolver=resolver)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "ftp://llm.example.com/v1",
        "https://user:secret@llm.example.com/v1",
        "https://llm.example.com/v1?x=1",
        "https://llm.example.com/v1#frag",
        "https:///v1",
        "llm.example.com/v1",
    ],
)
def test_custom_rejects_malformed_urls_without_echoing_secrets(url):
    resolver = _dns({"llm.example.com": ["93.184.216.34"]})
    with pytest.raises(LlmBaseUrlRejected) as caught:
        validate_provider_base_url(get_preset("custom"), url, resolver=resolver)
    assert "secret" not in caught.value.detail


def test_custom_requires_an_explicit_url():
    with pytest.raises(LlmBaseUrlRejected):
        validate_provider_base_url(get_preset("custom"), None, resolver=_no_dns)


def test_is_loopback_url():
    assert is_loopback_url("http://127.0.0.1:11434/v1")
    assert is_loopback_url("http://localhost:8080/v1")
    assert is_loopback_url("http://[::1]:8080/v1")
    assert not is_loopback_url("https://api.openai.com/v1")
    assert not is_loopback_url("http://host.docker.internal:11434/v1")
