"""`AssistantHealthService.describe()` — reads `settings` for every field
(so the endpoint answers 200 even with a badly configured provider) and
touches `LlmPort` ONLY when `probe=True` (design.md "Endpoint de salud",
D4). No SQLAlchemy: the `LlmPort` configuration is global per process, not
per organization (design.md "Aislamiento por organización" — RBAC alone
protects access, there is no per-tenant state to leak).
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from app.ai.ports import LlmPort, Reachability
from app.ai.registry import get_llm_port
from app.config import settings
from app.modules.assistant.schemas import AssistantHealthData
from app.shared.exceptions import AppException


def _base_url_host(base_url: str) -> str:
    """`hostname[:port]` derived explicitly from `urlsplit(...)`, NEVER
    `parts.netloc` — `netloc` carries `userinfo`
    (`usuario:secreto@host`), which would leak a credential through a
    health endpoint. `port` is only appended when the URL actually wrote
    one, so `"api.anthropic.com"` never becomes `"api.anthropic.com:None"`
    (design.md "Redacción de secretos")."""

    parts = urlsplit(base_url)
    if not parts.hostname:
        return ""
    return f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname


class AssistantHealthService:
    def __init__(self, *, port_factory: Callable[[], LlmPort] | None = None) -> None:
        self._port_factory = port_factory

    async def describe(self, *, probe: bool) -> AssistantHealthData:
        reachability: Reachability = "not_probed"
        reachability_reason: str | None = None

        if probe:
            # Resolved HERE, not in `__init__`: a test's `monkeypatch` of
            # this module's `get_llm_port` attribute only takes effect if
            # the lookup happens at call time (design.md "Inyección para
            # pruebas").
            build_port = self._port_factory or get_llm_port
            try:
                port = build_port()
            except AppException as exc:
                # The provider is misconfigured (e.g. `LLM_BASE_URL`
                # outside the allowlist, empty model/key) — reported as a
                # readable reason, never a 500 (design.md, table).
                reachability = "unreachable"
                reachability_reason = exc.detail
            else:
                probed = await port.probe()
                reachability = probed.reachability
                reachability_reason = probed.reason

        return AssistantHealthData(
            provider=settings.LLM_PROVIDER,
            model=settings.LLM_MODEL,
            base_url_host=_base_url_host(settings.LLM_BASE_URL),
            api_key_configured=bool(settings.LLM_API_KEY.strip()),
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            max_tokens=settings.LLM_MAX_TOKENS,
            structured_output_mode=settings.LLM_JSON_MODE,
            reachability=reachability,
            reachability_reason=reachability_reason,
        )
