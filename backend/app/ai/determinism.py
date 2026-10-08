"""Decoding parameters that make a classifier reproducible (E03).

Same input, same model, same output: temperature 0, ``top_k`` 1, ``top_p``
1, a fixed seed and a fixed context window, without reasoning. The
``server`` profile runs on CPU only (``num_gpu`` 0, ``num_thread`` N), like a
conventional server without a GPU.
"""

from dataclasses import dataclass, replace
from typing import Any

PROFILES = ("mac", "server")
DEFAULT_SERVER_THREADS = 8


@dataclass(frozen=True)
class Determinism:
    temperature: float = 0.0
    top_k: int = 1
    top_p: float = 1.0
    seed: int = 42
    num_ctx: int = 8192
    #: ``False`` sends ``think: false`` (Ollama) / ``reasoning_effort: none``.
    think: bool = False
    num_gpu: int | None = None
    num_thread: int | None = None

    def ollama_options(self, *, max_tokens: int) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": float(self.temperature),
            "top_k": self.top_k,
            "top_p": float(self.top_p),
            "seed": self.seed,
            "num_ctx": self.num_ctx,
            "num_predict": max_tokens,
        }
        if self.num_gpu is not None:
            options["num_gpu"] = self.num_gpu
        if self.num_thread is not None:
            options["num_thread"] = self.num_thread
        return options

    def as_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "seed": self.seed,
            "num_ctx": self.num_ctx,
            "think": self.think,
            "num_gpu": self.num_gpu,
            "num_thread": self.num_thread,
        }


def determinism_profile(
    name: str, *, num_thread: int = DEFAULT_SERVER_THREADS, **overrides: Any
) -> Determinism:
    if name not in PROFILES:
        raise ValueError(f"Perfil desconocido: {name}. Usa uno de {', '.join(PROFILES)}.")
    base = Determinism() if name == "mac" else Determinism(num_gpu=0, num_thread=num_thread)
    return replace(base, **overrides) if overrides else base
