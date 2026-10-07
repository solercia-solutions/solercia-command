"""AI provider per organization (C04) — BYOK, swappable «like a tyre».

Precedence when building an `LlmPort` for an organization
(`get_llm_port_for_org`):

1. **Organization row** (`ai_provider_settings`). If it exists it wins, and
   `enabled=false` STOPS (`LlmProviderDisabled`) — never a silent fallback
   to another provider that would receive the organization's mail.
2. **Global `LLM_*`** of the process, when `LLM_PROVIDER` is not ``"fake"``:
   ``openai_compatible`` builds the adapter from `LLM_BASE_URL`/`LLM_MODEL`/
   `LLM_API_KEY` (allowlist + preset URLs); ``anthropic`` is delegated to
   `get_llm_port()` (its barrier still applies).
3. **Default preset** ``ollama_local`` (local Ollama, Qwen 3.5 9B, no key).

`LLM_PROVIDER="fake"` is the shipped default, so it counts as "the operator
configured nothing". Tests inject fakes instead of relying on it.

The service owns transaction completion (`commit`); the repository only
flushes. API keys are Fernet tokens at rest and never leave this module in
clear except inside the adapter's `Authorization` header.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter, OpenAiCompatibleConfig
from app.ai.errors import LlmProviderDisabled
from app.ai.ports import LlmDispatchContext, LlmMessage, LlmPort, LlmRequest
from app.ai.presets import DEFAULT_PRESET_KEY, PRESETS, ProviderPreset, get_preset
from app.ai.registry import get_llm_port
from app.ai.url_guard import Resolver, default_resolver, is_loopback_url, validate_provider_base_url
from app.config import Settings
from app.config import settings as default_settings
from app.integrations import crypto
from app.shared.exceptions import AppException

from .models import AiProviderSettings
from .repository import AiProviderSettingsRepository, SqlAiProviderSettingsRepository
from .schemas import (
    AiConnectionError,
    AiConnectionTestResult,
    AiSettingsRead,
    AiSettingsUpdate,
    SettingsSource,
)

_SOURCE_TO_DISPATCH = {
    "organization": "organization_settings",
    "global": "global_settings",
    "default": "default_preset",
}
_TEST_PROMPT_VERSION = "ai-settings-connection-test-v1"
_TEST_EMBED_TEXT = "Prueba de conexión de Solercia Command."


class AiSettingsError(AppException):
    def __init__(self, detail: str, *, code: str, status_code: int = 422) -> None:
        super().__init__(detail, code=code, status_code=status_code)


@dataclass(frozen=True)
class ResolvedProvider:
    source: SettingsSource
    enabled: bool
    #: ``None`` only for a global non-OpenAI provider (``anthropic``).
    config: OpenAiCompatibleConfig | None
    preset: str
    locality: Literal["local", "external"]
    global_settings: Settings | None = None


@dataclass(frozen=True)
class _Candidate:
    preset: ProviderPreset
    base_url: str
    chat_model: str
    embedding_model: str | None
    api_key: str | None
    timeout_seconds: float
    max_tokens: int
    temperature: float
    reasoning_effort: str | None
    num_ctx: int | None
    enabled: bool


def _locality(preset: ProviderPreset, base_url: str) -> Literal["local", "external"]:
    if preset.key == "custom":
        return "local" if is_loopback_url(base_url) else "external"
    return preset.locality


def _safe_url(url: str) -> str:
    """scheme://host[:port]/path — never userinfo, query nor fragment."""

    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return ""
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme}://{host}{port}{parts.path}" if host else ""


def _config_from_candidate(candidate: _Candidate) -> OpenAiCompatibleConfig:
    preset = candidate.preset
    extra: dict = {}
    if preset.supports_num_ctx and candidate.num_ctx:
        extra["options"] = {"num_ctx": candidate.num_ctx}
    return OpenAiCompatibleConfig(
        base_url=candidate.base_url,
        chat_model=candidate.chat_model,
        embedding_model=candidate.embedding_model,
        api_key=candidate.api_key or "",
        timeout_seconds=candidate.timeout_seconds,
        max_tokens=candidate.max_tokens,
        temperature=candidate.temperature,
        reasoning_effort=candidate.reasoning_effort if preset.sends_reasoning_effort else None,
        json_mode=preset.json_mode,
        extra_body=extra,
        provider_label=preset.key,
    )


def build_llm_port(
    resolved: ResolvedProvider,
    organization_id: uuid.UUID,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LlmPort:
    """Turn a resolution into a port. The `LlmDispatchContext` is created
    HERE and only here: the organization comes from the server (JWT
    membership or the scheduler loop), never from a payload."""

    if not resolved.enabled:
        raise LlmProviderDisabled()
    if resolved.config is None:
        return get_llm_port(resolved.global_settings)
    return OpenAiCompatibleAdapter(
        config=resolved.config,
        dispatch_context=LlmDispatchContext(
            organization_id=organization_id,
            source=_SOURCE_TO_DISPATCH[resolved.source],  # type: ignore[arg-type]
        ),
        transport=transport,
    )


class AiSettingsService:
    def __init__(
        self,
        repository: AiProviderSettingsRepository,
        *,
        commit: Callable[[], Awaitable[None]],
        global_settings: Settings = default_settings,
        resolver: Resolver = default_resolver,
    ) -> None:
        self._repository = repository
        self._commit = commit
        self._global = global_settings
        self._resolver = resolver

    # --- resolution -----------------------------------------------------------

    def _global_configured(self) -> bool:
        return self._global.LLM_PROVIDER != "fake"

    def _row_candidate(self, row: AiProviderSettings) -> _Candidate:
        preset = get_preset(row.preset)
        return _Candidate(
            preset=preset,
            base_url=validate_provider_base_url(preset, row.base_url, resolver=self._resolver),
            chat_model=row.chat_model,
            embedding_model=row.embedding_model,
            api_key=self._decrypt(row.api_key_ciphertext),
            timeout_seconds=row.timeout_seconds,
            max_tokens=row.max_tokens,
            temperature=row.temperature,
            reasoning_effort=row.reasoning_effort,
            num_ctx=(row.options or {}).get("num_ctx"),
            enabled=row.enabled,
        )

    def _default_candidate(self) -> _Candidate:
        preset = PRESETS[DEFAULT_PRESET_KEY]
        return _Candidate(
            preset=preset,
            base_url=preset.base_url or "",
            chat_model=preset.chat_model,
            embedding_model=preset.embedding_model,
            api_key=None,
            timeout_seconds=60.0,
            max_tokens=1024,
            temperature=0.0,
            reasoning_effort="none",
            # C05: reduced context window for the local default (RAM).
            num_ctx=getattr(self._global, "AI_DEFAULT_NUM_CTX", None) or None,
            enabled=True,
        )

    async def resolve(self, organization_id: uuid.UUID) -> ResolvedProvider:
        """Apply the precedence documented in the module docstring."""

        row = await self._repository.find_for_organization(organization_id)
        if row is not None:
            candidate = self._row_candidate(row)
            return ResolvedProvider(
                source="organization",
                enabled=candidate.enabled,
                config=_config_from_candidate(candidate),
                preset=candidate.preset.key,
                locality=_locality(candidate.preset, candidate.base_url),
            )
        if self._global_configured():
            config = None
            if self._global.LLM_PROVIDER == "openai_compatible":
                config = OpenAiCompatibleConfig.from_settings(self._global)
            return ResolvedProvider(
                source="global",
                enabled=True,
                config=config,
                preset="global",
                locality=self._global_locality(),
                global_settings=self._global,
            )
        candidate = self._default_candidate()
        return ResolvedProvider(
            source="default",
            enabled=True,
            config=_config_from_candidate(candidate),
            preset=candidate.preset.key,
            locality=candidate.preset.locality,
        )

    def _global_locality(self) -> Literal["local", "external"]:
        url = self._global.LLM_BASE_URL
        host = (urlsplit(url).hostname or "").lower() if url else ""
        if is_loopback_url(url) or host == "host.docker.internal":
            return "local"
        return "external"

    # --- read -------------------------------------------------------------------

    async def get_settings(self, organization_id: uuid.UUID) -> AiSettingsRead:
        row = await self._repository.find_for_organization(organization_id)
        if row is not None:
            return self._view(row)
        if self._global_configured():
            gs = self._global
            return AiSettingsRead(
                preset="global",
                preset_label="Variables de entorno del servidor (LLM_*)",
                locality=self._global_locality(),
                base_url=_safe_url(gs.LLM_BASE_URL),
                chat_model=gs.LLM_MODEL,
                embedding_model=None,
                has_api_key=bool(gs.LLM_API_KEY.strip()),
                api_key_last4=None,
                timeout_seconds=gs.LLM_TIMEOUT_SECONDS,
                max_tokens=gs.LLM_MAX_TOKENS,
                temperature=0.0,
                reasoning_effort=None,
                num_ctx=None,
                enabled=True,
                source="global",
            )
        candidate = self._default_candidate()
        return self._candidate_view(candidate, source="default", last4=None)

    @staticmethod
    def _candidate_view(
        candidate: _Candidate, *, source: SettingsSource, last4: str | None
    ) -> AiSettingsRead:
        return AiSettingsRead(
            preset=candidate.preset.key,
            preset_label=candidate.preset.label,
            locality=_locality(candidate.preset, candidate.base_url),
            base_url=_safe_url(candidate.base_url),
            chat_model=candidate.chat_model,
            embedding_model=candidate.embedding_model,
            has_api_key=bool(candidate.api_key),
            api_key_last4=last4,
            timeout_seconds=candidate.timeout_seconds,
            max_tokens=candidate.max_tokens,
            temperature=candidate.temperature,
            reasoning_effort=candidate.reasoning_effort,  # type: ignore[arg-type]
            num_ctx=candidate.num_ctx,
            enabled=candidate.enabled,
            source=source,
        )

    def _view(self, row: AiProviderSettings) -> AiSettingsRead:
        preset = PRESETS.get(row.preset)
        base_url = row.base_url or (preset.base_url if preset else "") or ""
        return AiSettingsRead(
            preset=row.preset,
            preset_label=preset.label if preset else row.preset,
            locality=_locality(preset, base_url) if preset else "external",
            base_url=_safe_url(base_url),
            chat_model=row.chat_model,
            embedding_model=row.embedding_model,
            has_api_key=row.api_key_ciphertext is not None,
            api_key_last4=row.api_key_last4,
            timeout_seconds=row.timeout_seconds,
            max_tokens=row.max_tokens,
            temperature=row.temperature,
            reasoning_effort=row.reasoning_effort,  # type: ignore[arg-type]
            num_ctx=(row.options or {}).get("num_ctx"),
            enabled=row.enabled,
            source="organization",
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )

    # --- write --------------------------------------------------------------------

    @staticmethod
    def _decrypt(ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        try:
            return crypto.decrypt(ciphertext)
        except InvalidToken as exc:
            raise AiSettingsError(
                "No fue posible leer la llave guardada del proveedor de IA; vuelve a ingresarla.",
                code="AI_API_KEY_UNREADABLE",
                status_code=409,
            ) from exc

    def _candidate_from_update(
        self, payload: AiSettingsUpdate, stored: AiProviderSettings | None
    ) -> _Candidate:
        preset = get_preset(payload.preset)
        base_url = validate_provider_base_url(preset, payload.base_url, resolver=self._resolver)
        chat_model = (payload.chat_model or "").strip() or preset.chat_model
        if not chat_model:
            raise AiSettingsError(
                "Indica el modelo de chat del proveedor.", code="AI_CHAT_MODEL_REQUIRED"
            )
        embedding_model = (payload.embedding_model or "").strip() or preset.embedding_model

        if "api_key" in payload.model_fields_set and payload.api_key is None:
            api_key = None
        elif payload.api_key and payload.api_key.strip():
            api_key = payload.api_key.strip()
        else:
            api_key = self._kept_key(stored, base_url)

        if preset.requires_api_key and not api_key:
            raise AiSettingsError(
                "Este proveedor necesita una llave de API.", code="AI_API_KEY_REQUIRED"
            )
        return _Candidate(
            preset=preset,
            base_url=base_url,
            chat_model=chat_model,
            embedding_model=embedding_model,
            api_key=api_key,
            timeout_seconds=payload.timeout_seconds,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
            reasoning_effort=payload.reasoning_effort,
            num_ctx=payload.num_ctx,
            enabled=payload.enabled,
        )

    def _kept_key(self, stored: AiProviderSettings | None, base_url: str) -> str | None:
        """A stored key is reused ONLY for the same destination URL: switching
        provider must never hand one vendor's key to another."""

        if stored is None or not stored.api_key_ciphertext:
            return None
        stored_preset = PRESETS.get(stored.preset)
        stored_url = stored.base_url or (stored_preset.base_url if stored_preset else "") or ""
        if stored_url.rstrip("/") != base_url:
            return None
        return self._decrypt(stored.api_key_ciphertext)

    async def update_settings(
        self,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        payload: AiSettingsUpdate,
    ) -> AiSettingsRead:
        row = await self._repository.find_for_organization(organization_id)
        candidate = self._candidate_from_update(payload, row)
        now = datetime.now(UTC)
        is_new = row is None
        if row is None:
            row = AiProviderSettings(
                id=uuid.uuid4(),
                organization_id=organization_id,
                created_by=actor_id,
                created_at=now,
            )
        row.preset = candidate.preset.key
        row.base_url = candidate.base_url
        row.chat_model = candidate.chat_model
        row.embedding_model = candidate.embedding_model
        if candidate.api_key:
            row.api_key_ciphertext = crypto.encrypt(candidate.api_key)
            row.api_key_last4 = candidate.api_key[-4:]
        else:
            row.api_key_ciphertext = None
            row.api_key_last4 = None
        row.timeout_seconds = candidate.timeout_seconds
        row.max_tokens = candidate.max_tokens
        row.temperature = candidate.temperature
        row.reasoning_effort = candidate.reasoning_effort
        row.options = {"num_ctx": candidate.num_ctx} if candidate.num_ctx else {}
        row.enabled = candidate.enabled
        row.updated_by = actor_id
        row.updated_at = now
        if is_new:
            await self._repository.add(row)
        await self._commit()
        return self._view(row)

    # --- connection test ----------------------------------------------------------

    async def test_connection(
        self,
        organization_id: uuid.UUID,
        proposal: AiSettingsUpdate | None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> AiConnectionTestResult:
        """Short chat + one embedding against the proposal (never persisted)
        or the effective configuration. Provider failures come back as
        ``ok=false`` with a stable code; the key never appears."""

        if proposal is not None:
            stored = await self._repository.find_for_organization(organization_id)
            candidate = self._candidate_from_update(proposal, stored)
            resolved = ResolvedProvider(
                source="organization",
                enabled=True,
                config=_config_from_candidate(candidate),
                preset=candidate.preset.key,
                locality=_locality(candidate.preset, candidate.base_url),
            )
        else:
            resolved = await self.resolve(organization_id)
            if resolved.config is None:
                raise AiSettingsError(
                    "La prueba de conexión solo aplica a proveedores compatibles con OpenAI.",
                    code="AI_TEST_UNSUPPORTED",
                    status_code=409,
                )
            resolved = ResolvedProvider(
                source=resolved.source,
                enabled=True,
                config=resolved.config,
                preset=resolved.preset,
                locality=resolved.locality,
            )

        config = resolved.config
        assert config is not None
        port = build_llm_port(resolved, organization_id, transport=transport)
        result = AiConnectionTestResult(
            ok=False,
            preset=resolved.preset,
            locality=resolved.locality,
            chat_model=config.chat_model,
            embedding_model=config.embedding_model,
        )
        try:
            response = await port.complete(
                LlmRequest(
                    system="Prueba de conexión. Responde únicamente: ok",
                    messages=(LlmMessage(role="user", content="ping"),),
                    max_tokens=32,
                    temperature=0.0,
                    prompt_version=_TEST_PROMPT_VERSION,
                )
            )
        except AppException as exc:
            result.error = AiConnectionError(stage="chat", code=exc.code, detail=exc.detail)
            return result
        result.chat_latency_ms = response.latency_ms

        if config.embedding_model:
            started = time.perf_counter()
            try:
                vectors = await port.embed([_TEST_EMBED_TEXT])
            except AppException as exc:
                result.error = AiConnectionError(
                    stage="embeddings", code=exc.code, detail=exc.detail
                )
                return result
            result.embedding_latency_ms = int((time.perf_counter() - started) * 1000)
            result.embedding_dimensions = len(vectors[0])

        result.ok = True
        return result


async def get_llm_for_org(
    organization_id: uuid.UUID,
    db: AsyncSession,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = default_resolver,
) -> tuple[LlmPort, ResolvedProvider]:
    """Port plus the resolution it came from (the classifier, C05, needs
    the embedding model name to key its vector cache). Read-only."""

    service = AiSettingsService(
        SqlAiProviderSettingsRepository(db),
        commit=db.commit,
        resolver=resolver,
    )
    resolved = await service.resolve(organization_id)
    return build_llm_port(resolved, organization_id, transport=transport), resolved


async def get_llm_port_for_org(
    organization_id: uuid.UUID,
    db: AsyncSession,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = default_resolver,
) -> LlmPort:
    """The `LlmPort` an organization's domain flows (classifier, C05) use.
    Read-only: never commits. See the module docstring for precedence."""

    port, _ = await get_llm_for_org(organization_id, db, transport=transport, resolver=resolver)
    return port
