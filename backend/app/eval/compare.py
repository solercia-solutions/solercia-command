"""Comparison table across evaluations (E04): model × profile × metrics."""

import json
from collections.abc import Sequence
from pathlib import Path

from .report import gigabytes, num, pct

HEADER = (
    "| Modelo | Perfil | Preset | Corridas | n | Exactitud | Macro-F1 | Tarea top-1 | "
    "Cobertura | Desc. P / R | T. nueva P / R | No concl. | Determinismo | p50 ms | p95 ms | "
    "RAM GB | Errores JSON |"
)


def _row(metrics: dict) -> str:
    config = metrics.get("config", {})
    per_class = metrics.get("per_class", {})

    def pr(name: str) -> str:
        values = metrics.get(name) or per_class.get(name) or {}
        return f"{pct(values.get('precision'))} / {pct(values.get('recall'))}"

    latency = metrics.get("latency_ms", {})
    cells = [
        config.get("model"),
        config.get("profile"),
        config.get("preset"),
        config.get("runs"),
        metrics.get("n"),
        pct(metrics.get("class_accuracy")),
        num(metrics.get("macro_f1"), 3),
        pct(metrics.get("task_top1")),
        pct(metrics.get("candidate_coverage")),
        pr("descartado"),
        pr("tarea_nueva"),
        pct(metrics.get("no_concluyente_rate")),
        pct(metrics.get("determinism", {}).get("rate")),
        num(latency.get("p50")),
        num(latency.get("p95")),
        gigabytes(metrics.get("ram_bytes")),
        metrics.get("json_errors"),
    ]
    return "| " + " | ".join("—" if c is None else str(c) for c in cells) + " |"


def compare_markdown(folders: Sequence[Path]) -> str:
    rows = []
    for folder in folders:
        metrics = json.loads((Path(folder) / "metrics.json").read_text(encoding="utf-8"))
        rows.append(_row(metrics))
    separator = "|" + "---|" * (HEADER.count("|") - 1)
    return "\n".join([HEADER, separator, *rows]) + "\n"
