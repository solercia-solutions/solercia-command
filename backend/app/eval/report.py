"""Readable report of one evaluation (E04). Numbers only, never mail content."""

from app.modules.reconciliation.classes import CLASSES

from .metrics import NO_CLASS


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f} %".replace(".", ",")


def num(value: float | int | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",")


def gigabytes(value: int | None) -> str:
    return "—" if not value else f"{value / 1e9:.1f}".replace(".", ",")


def render_report(metrics: dict) -> str:
    config = metrics.get("config", {})
    determinism = metrics.get("determinism", {})
    latency = metrics.get("latency_ms", {})
    by_run = ", ".join(pct(v) for v in metrics.get("accuracy_by_run", []))
    lines = [
        f"# Evaluación del clasificador — {config.get('model')} ({config.get('profile')})",
        "",
        f"- Preset: `{config.get('preset')}` · embeddings: `{config.get('embedding_model')}`",
        f"- Cortes: {', '.join(config.get('cuts', []))} · límite: {config.get('limit') or '—'}"
        f" · corridas: {config.get('runs')}",
        f"- Prompt: `{config.get('prompt_version')}` · reglas "
        f"{config.get('rules', {}).get('version')} (`{config.get('rules', {}).get('digest')}`)",
        f"- Determinismo: `{config.get('determinism')}`",
        f"- Commit: `{config.get('git_commit')}` · inicio {config.get('started_at')}",
        "",
        "## Resumen",
        "",
        "| Métrica | Valor |",
        "|---|---|",
        f"| Registros evaluados (sin manual_needed) | {metrics.get('n')} |",
        f"| manual_needed excluidos | {metrics.get('manual_needed_excluded')} |",
        f"| Exactitud de clase | {pct(metrics.get('class_accuracy'))} |",
        f"| Exactitud por corrida | {by_run} |",
        f"| Macro-F1 | {num(metrics.get('macro_f1'), 3)} |",
        f"| Tarea top-1 ({metrics.get('task_labels')} con tarea) | {pct(metrics.get('task_top1'))}"
        " |",
        f"| Tarea correcta entre candidatas | {pct(metrics.get('task_in_candidates'))} |",
        f"| Cobertura de candidatas | {pct(metrics.get('candidate_coverage'))} |",
        f"| Descartado P / R | {pct(metrics.get('descartado', {}).get('precision'))} / "
        f"{pct(metrics.get('descartado', {}).get('recall'))} |",
        f"| Tarea nueva P / R | {pct(metrics.get('tarea_nueva', {}).get('precision'))} / "
        f"{pct(metrics.get('tarea_nueva', {}).get('recall'))} |",
        f"| Tasa de no concluyente | {pct(metrics.get('no_concluyente_rate'))} |",
        f"| Determinismo (salida idéntica en todas las corridas) | {pct(determinism.get('rate'))}"
        f" ({determinism.get('identical_units')}/{determinism.get('units')}) |",
        f"| Latencia p50 / p95 por registro (ms) | {num(latency.get('p50'))} / "
        f"{num(latency.get('p95'))} |",
        f"| Latencia LLM p50 / p95 (ms) | {num(latency.get('llm_p50'))} / "
        f"{num(latency.get('llm_p95'))} |",
        f"| Tokens entrada / salida | {num(metrics.get('tokens', {}).get('input'))} / "
        f"{num(metrics.get('tokens', {}).get('output'))} |",
        f"| RAM del modelo (GB, ollama ps) | {gigabytes(metrics.get('ram_bytes'))} |",
        f"| Errores de JSON | {metrics.get('json_errors')} |",
        f"| Etapas (corrida 1) | {metrics.get('stages')} |",
        "",
        "## Por clase (corrida 1)",
        "",
        "| Clase | Precisión | Recall | F1 | Soporte |",
        "|---|---|---|---|---|",
    ]
    for name, values in metrics.get("per_class", {}).items():
        lines.append(
            f"| {name} | {pct(values['precision'])} | {pct(values['recall'])} | "
            f"{num(values['f1'], 3)} | {values['support']} |"
        )
    columns = (*CLASSES, NO_CLASS)
    lines += [
        "",
        "## Matriz de confusión (filas = esperado, columnas = predicho)",
        "",
        "| esperado \\ predicho | " + " | ".join(columns) + " |",
        "|---" * (len(columns) + 1) + "|",
    ]
    for expected in CLASSES:
        row = metrics.get("confusion", {}).get(expected, {})
        lines.append(f"| {expected} | " + " | ".join(str(row.get(c, 0)) for c in columns) + " |")
    lines += ["", f"Hash por corrida: `{determinism.get('run_hashes')}`", ""]
    return "\n".join(lines)
