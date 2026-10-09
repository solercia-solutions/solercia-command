"""Evaluation run (E04): golden cuts → channel v2 in dry-run → metrics.

- The checklist state is built in memory from ``checklist_before.csv``;
  nothing is written to any database (this module never imports one).
- Embeddings ALWAYS come from the local embedding model (independent of the
  chat model) and are cached on disk by (model, text hash): every chat model
  sees exactly the same candidates.
- A non-local chat preset is refused unless ``allow_external`` names that
  preset AND the environment variable ``CONFIRM_ENV`` names it too: golden
  data is real mail and must not leave the machine by accident.
"""

import json
import os
import re
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.ai.adapters.ollama_native import OllamaNativeAdapter, OllamaNativeConfig
from app.ai.adapters.openai_compatible import OpenAiCompatibleAdapter, OpenAiCompatibleConfig
from app.ai.determinism import Determinism, determinism_profile
from app.ai.ports import LlmDispatchContext, LlmPort
from app.ai.presets import ProviderPreset, get_preset
from app.modules.reconciliation.channel_v2 import ChannelV2, ChannelV2Config
from app.modules.reconciliation.prompt_versions import DEFAULT_PROMPT_VERSION_V2
from app.modules.reconciliation.rules import load_rules_file
from app.modules.reconciliation.stages import build_units

from .golden import load_cut
from .metrics import Prediction, compute_metrics
from .report import render_report

CONFIRM_ENV = "SOLERCIA_EVAL_EXTERNAL_CONFIRM"
API_KEY_ENV = "SOLERCIA_EVAL_API_KEY"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


class ExternalProviderRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class EvalOptions:
    golden_dir: Path
    cuts: list[str]
    rules_path: Path
    preset: str = "ollama_local"
    model: str = "qwen3.5:9b-q4_K_M"
    embedding_model: str = "qwen3-embedding:0.6b"
    runs: int = 3
    profile: str = "mac"
    num_thread: int = 8
    num_batch: int | None = None
    #: Seconds per chat call (E08: emulated amd64 needs more than 300 s per 9B call).
    timeout: float = 300.0
    limit: int | None = None
    out_dir: Path | None = None
    cache_dir: Path | None = None
    allow_external: str | None = None
    base_url: str | None = None
    embedding_url: str = DEFAULT_OLLAMA_URL
    top_k: int = ChannelV2Config.top_k
    max_chars: int = 6000
    max_tokens: int = 600
    seed: int = 42
    num_ctx: int = 8192
    prompt_version: str = DEFAULT_PROMPT_VERSION_V2
    subject_match: bool = ChannelV2Config.subject_match
    object_match: str = ChannelV2Config.object_match
    task_text: str = ChannelV2Config.task_text
    ranking: str = ChannelV2Config.ranking
    #: E07b: only retrieval (no chat model, one run) — candidate coverage in seconds.
    candidates_only: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def check_external(preset_key: str, allow_external: str | None, env: Mapping[str, str]) -> None:
    preset = get_preset(preset_key)
    if preset.locality == "local":
        return
    if allow_external != preset_key or env.get(CONFIRM_ENV) != preset_key:
        raise ExternalProviderRefused(
            f"El preset «{preset_key}» es externo: el conjunto dorado contiene correos reales y "
            f"saldría de este equipo. Para continuar usa --allow-external {preset_key} y define "
            f"{CONFIRM_ENV}={preset_key}."
        )


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")


def default_out_dir(golden_dir: Path, model: str, profile: str, today: date) -> Path:
    return Path(golden_dir).parent / "resultados" / f"{today:%Y-%m-%d}_{_safe(model)}_{profile}"


class DiskEmbeddingCache:
    """JSONL per embedding model: ``{"h": <sha256 of text>, "v": [...]}``."""

    def __init__(self, folder: Path) -> None:
        self._folder = Path(folder)
        self._loaded: dict[str, dict[str, list[float]]] = {}

    def _path(self, model: str) -> Path:
        return self._folder / f"{_safe(model)}.jsonl"

    def _table(self, model: str) -> dict[str, list[float]]:
        if model not in self._loaded:
            table: dict[str, list[float]] = {}
            path = self._path(model)
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        row = json.loads(line)
                        table[row["h"]] = row["v"]
            self._loaded[model] = table
        return self._loaded[model]

    def get(self, model: str, digest: str) -> list[float] | None:
        return self._table(model).get(digest)

    def put(self, model: str, digest: str, vector: list[float]) -> None:
        self._table(model)[digest] = list(vector)
        self._folder.mkdir(parents=True, exist_ok=True)
        with self._path(model).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"h": digest, "v": list(vector)}) + "\n")


def _context() -> LlmDispatchContext:
    return LlmDispatchContext(organization_id=uuid.UUID(int=0), source="offline_evaluation")


def determinism_for(options: EvalOptions) -> Determinism:
    return determinism_profile(
        options.profile,
        num_thread=options.num_thread,
        seed=options.seed,
        num_ctx=options.num_ctx,
        num_batch=options.num_batch,
    )


def uses_ollama_native(preset: ProviderPreset) -> bool:
    """Local Ollama presets go through ``/api/chat``: ``/v1`` ignores ``options``.

    Without it ``num_ctx``, ``seed``, ``top_k``, ``num_gpu`` and ``num_thread``
    never reach the runner and a measurement would not be reproducible.
    """

    return preset.locality == "local" and preset.supports_num_ctx


def build_chat(options: EvalOptions) -> LlmPort:
    preset = get_preset(options.preset)
    determinism = determinism_for(options)
    if uses_ollama_native(preset):
        return OllamaNativeAdapter(
            config=OllamaNativeConfig(
                base_url=options.base_url or preset.base_url or DEFAULT_OLLAMA_URL,
                chat_model=options.model,
                determinism=determinism,
                max_tokens=options.max_tokens,
                timeout_seconds=options.timeout,
            ),
            dispatch_context=_context(),
        )
    extra: dict[str, Any] = {"seed": determinism.seed, "top_p": determinism.top_p}
    if preset.locality == "local":
        extra["top_k"] = determinism.top_k
    return OpenAiCompatibleAdapter(
        config=OpenAiCompatibleConfig(
            base_url=options.base_url or preset.base_url or "",
            chat_model=options.model,
            api_key=os.environ.get(API_KEY_ENV, ""),
            timeout_seconds=options.timeout,
            max_tokens=options.max_tokens,
            temperature=determinism.temperature,
            reasoning_effort="none" if preset.sends_reasoning_effort else None,
            json_mode=preset.json_mode,
            extra_body=extra,
            provider_label=preset.key,
        ),
        dispatch_context=_context(),
    )


def build_embedder(options: EvalOptions) -> LlmPort:
    """Always the LOCAL Ollama embedding model, whatever the chat preset."""

    return OllamaNativeAdapter(
        config=OllamaNativeConfig(
            base_url=options.embedding_url,
            chat_model=options.embedding_model,
            embedding_model=options.embedding_model,
        ),
        dispatch_context=_context(),
    )


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


async def _memory(embedder: LlmPort, model: str) -> int | None:
    loaded = getattr(embedder, "loaded_models", None)
    if loaded is None:
        return None
    try:
        models = await loaded()
    except Exception:  # noqa: BLE001 — RAM is informative, never fatal
        return None
    entry = models.get(model) or models.get(f"{model}:latest")
    return entry["size"] if entry else None


async def run_evaluation(
    options: EvalOptions,
    *,
    chat_factory: Callable[[EvalOptions], LlmPort] | None = None,
    embedder_factory: Callable[[EvalOptions], LlmPort] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    env: Mapping[str, str] | None = None,
) -> dict:
    check_external(options.preset, options.allow_external, os.environ if env is None else env)
    started = clock()
    rules = load_rules_file(options.rules_path)
    cuts = [load_cut(options.golden_dir, cut) for cut in options.cuts]
    out_dir = options.out_dir or default_out_dir(
        options.golden_dir, options.model, options.profile, started.date()
    )
    cache = DiskEmbeddingCache(
        options.cache_dir
        or Path(options.golden_dir).parent / "resultados" / "_cache" / "embeddings"
    )
    runs = 1 if options.candidates_only else options.runs
    chat = None if options.candidates_only else (chat_factory or build_chat)(options)
    embedder = (embedder_factory or build_embedder)(options)
    determinism = determinism_for(options)
    config = ChannelV2Config(
        top_k=options.top_k,
        max_chars=options.max_chars,
        max_tokens=options.max_tokens,
        prompt_version=options.prompt_version,
        subject_match=options.subject_match,
        object_match=options.object_match,  # type: ignore[arg-type]
        task_text=options.task_text,  # type: ignore[arg-type]
        ranking=options.ranking,  # type: ignore[arg-type]
    )

    plan = []  # (cut, unit, label, existing tasks)
    for cut in cuts:
        labels = {(lb.kind, lb.key): lb for lb in cut.labels}
        existing = {t.ref for t in cut.tasks}
        units = [u for u in build_units(cut.records) if (u.kind, u.key) in labels]
        if options.limit:
            units = units[: options.limit]
        plan += [(cut, u, labels[(u.kind, u.key)], existing) for u in units]

    predictions: list[Prediction] = []
    ram_bytes: int | None = None
    for run in range(1, runs + 1):
        vectors_by_cut = {}
        for cut in cuts:
            channel = ChannelV2(
                rules,
                chat=chat,
                embedder=embedder,
                embedding_model=options.embedding_model,
                cache=cache,
                config=config,
            )
            vectors_by_cut[cut.name] = (channel, await channel.task_vectors(cut.tasks))
        for cut, unit, label, existing in plan:
            channel, vectors = vectors_by_cut[cut.name]
            begin = time.perf_counter()
            result = await channel.classify(unit, cut.tasks, vectors)
            elapsed = int((time.perf_counter() - begin) * 1000)
            predictions.append(
                Prediction(
                    cut=cut.name,
                    kind=unit.kind,
                    key=unit.key,
                    run=run,
                    expected=label.expected,
                    predicted=result.clase,
                    task_ref=result.task_ref,
                    expected_tasks=tuple(t for t in label.expected_tasks if t in existing),
                    candidate_refs=tuple(c.ref for c in result.candidates),
                    confidence=result.confidence,
                    stage=result.stage,
                    reason=result.reason,
                    latency_ms=elapsed,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    error=result.error,
                    output_hash=result.output_hash,
                    prompt_version=options.prompt_version,
                )
            )
        if run == 1 and chat is not None:
            ram_bytes = await _memory(embedder, options.model)

    metrics = compute_metrics(predictions, runs=runs)
    metrics["manual_needed_excluded"] = sum(c.manual_needed for c in cuts)
    metrics["ram_bytes"] = ram_bytes
    metrics["config"] = {
        "preset": options.preset,
        "model": options.model,
        "embedding_model": options.embedding_model,
        "profile": options.profile,
        "runs": runs,
        "candidates_only": options.candidates_only,
        "cuts": options.cuts,
        "limit": options.limit,
        "top_k": options.top_k,
        "max_chars": options.max_chars,
        "max_tokens": options.max_tokens,
        "prompt_version": options.prompt_version,
        "subject_match": options.subject_match,
        "object_match": options.object_match,
        "task_text": options.task_text,
        "ranking": options.ranking,
        "rules": {"version": rules.version, "digest": rules.digest},
        "determinism": determinism.as_dict(),
        "git_commit": _git_commit(),
        "started_at": started.isoformat(),
        "finished_at": clock().isoformat(),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(json.dumps(prediction.as_dict(), ensure_ascii=False) + "\n")
    (out_dir / "report.md").write_text(render_report(metrics), encoding="utf-8")
    metrics["out_dir"] = str(out_dir)
    return metrics
