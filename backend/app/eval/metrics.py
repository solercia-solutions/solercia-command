"""Metrics of one evaluation (E04). Pure: predictions in, numbers out.

Class metrics use run 1 (the reference run); ``accuracy_by_run`` and the
determinism block compare every run. Task metrics only count labels whose
expected tasks existed in the checklist before the cut.
"""

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from app.modules.reconciliation.channel_v2 import UNIT_ERRORS
from app.modules.reconciliation.classes import CLASSES, TASK_CLASSES

NO_CLASS = "sin_clase"


@dataclass(frozen=True)
class Prediction:
    cut: str
    kind: str
    key: str
    run: int
    expected: str
    predicted: str | None
    task_ref: str | None
    #: Expected tasks that existed in the checklist before the cut.
    expected_tasks: tuple[str, ...]
    candidate_refs: tuple[str, ...]
    confidence: float | None
    stage: str
    reason: str | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    output_hash: str | None
    #: Prompt version that produced it (rules-decided units carry it too).
    prompt_version: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear interpolation (same as ``numpy.percentile`` default)."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def _per_class(pairs: list[tuple[str, str]]) -> dict[str, dict]:
    labels = sorted(
        {e for e, _ in pairs} | {p for _, p in pairs if p != NO_CLASS},
        key=lambda c: CLASSES.index(c) if c in CLASSES else len(CLASSES),
    )
    result = {}
    for label in labels:
        tp = sum(1 for e, p in pairs if e == label and p == label)
        predicted = sum(1 for _, p in pairs if p == label)
        support = sum(1 for e, _ in pairs if e == label)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        result[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
        }
    return result


def _key(p: Prediction) -> tuple[str, str, str]:
    return (p.cut, p.kind, p.key)


def compute_metrics(predictions: Sequence[Prediction], *, runs: int) -> dict:
    by_run: dict[int, list[Prediction]] = defaultdict(list)
    for prediction in predictions:
        by_run[prediction.run].append(prediction)
    first = sorted(by_run.get(1, []), key=_key)
    pairs = [(p.expected, p.predicted or NO_CLASS) for p in first]
    per_class = _per_class(pairs)

    confusion = {e: dict.fromkeys((*CLASSES, NO_CLASS), 0) for e in CLASSES}
    for expected, predicted in pairs:
        confusion.setdefault(expected, dict.fromkeys((*CLASSES, NO_CLASS), 0))
        confusion[expected][predicted] = confusion[expected].get(predicted, 0) + 1

    task_labels = [p for p in first if p.expected in TASK_CLASSES and p.expected_tasks]
    with_tasks = [p for p in first if p.expected_tasks]

    hashes: dict[tuple, set] = defaultdict(set)
    for prediction in predictions:
        hashes[_key(prediction)].add(prediction.output_hash)
    run_hashes = {
        str(run): hashlib.sha256(
            "|".join(f"{_key(p)}={p.output_hash}" for p in sorted(items, key=_key)).encode()
        ).hexdigest()[:16]
        for run, items in sorted(by_run.items())
    }
    identical = sum(1 for values in hashes.values() if len(values) == 1)

    latencies = [p.latency_ms for p in predictions]
    llm_latencies = [p.latency_ms for p in predictions if p.stage in ("llm", "error_llm")]

    def pr(label: str) -> dict:
        return {k: per_class.get(label, {}).get(k, 0.0) for k in ("precision", "recall")}

    return {
        "n": len(first),
        "runs": runs,
        "class_accuracy": _ratio(sum(1 for e, p in pairs if e == p), len(pairs)),
        "accuracy_by_run": [
            _ratio(sum(1 for p in items if p.expected == p.predicted), len(items))
            for _, items in sorted(by_run.items())
        ],
        "macro_f1": (
            round(sum(c["f1"] for c in per_class.values()) / len(per_class), 4)
            if per_class
            else None
        ),
        "per_class": per_class,
        "confusion": confusion,
        "support": dict(Counter(p.expected for p in first)),
        "predicted": dict(Counter(p.predicted or NO_CLASS for p in first)),
        "task_top1": _ratio(
            sum(1 for p in task_labels if p.task_ref == p.expected_tasks[0]), len(task_labels)
        ),
        "task_any_expected": _ratio(
            sum(1 for p in task_labels if p.task_ref in p.expected_tasks), len(task_labels)
        ),
        "task_in_candidates": _ratio(
            sum(1 for p in task_labels if set(p.expected_tasks) & set(p.candidate_refs)),
            len(task_labels),
        ),
        "task_labels": len(task_labels),
        "candidate_coverage": _ratio(
            sum(1 for p in with_tasks if set(p.expected_tasks) & set(p.candidate_refs)),
            len(with_tasks),
        ),
        "descartado": pr("descartado"),
        "tarea_nueva": pr("tarea_nueva"),
        "no_concluyente_rate": _ratio(
            sum(1 for p in first if p.predicted == "no_concluyente"), len(first)
        ),
        "stages": dict(Counter(p.stage for p in first)),
        "determinism": {
            "identical_units": identical,
            "units": len(hashes),
            "rate": _ratio(identical, len(hashes)),
            "run_hashes": run_hashes,
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "llm_p50": percentile(llm_latencies, 0.5),
            "llm_p95": percentile(llm_latencies, 0.95),
        },
        "tokens": {
            "input": sum(p.input_tokens or 0 for p in predictions),
            "output": sum(p.output_tokens or 0 for p in predictions),
            "llm_calls": sum(1 for p in predictions if p.stage in ("llm", "error_llm")),
        },
        "json_errors": sum(1 for p in predictions if p.error in UNIT_ERRORS),
    }
