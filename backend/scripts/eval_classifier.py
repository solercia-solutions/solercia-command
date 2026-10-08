"""CLI: evalúa el clasificador (canal v2) contra el conjunto dorado, en simulación.

Ejecución en el host, desde ``backend/``::

    .venv/bin/python -m scripts.eval_classifier \\
        --golden-dir ~/Proyectos/SOLERCIA/evaluaciones/golden \\
        --rules ~/Proyectos/SOLERCIA/evaluaciones/reglas.json \\
        --cortes 2026-09-18 --model qwen3.5:9b-q4_K_M --runs 2 --profile mac --limit 15

No usa base de datos: el estado del checklist sale de ``checklist_before.csv``
en memoria. Los embeddings salen SIEMPRE del modelo local de embeddings y se
cachean en disco por (modelo, hash del texto). Los resultados van por defecto
a ``<evaluaciones>/resultados/<fecha>_<modelo>_<perfil>/`` (fuera del repo):
``metrics.json``, ``predictions.jsonl`` y ``report.md``.

Un preset externo se rechaza salvo con ``--allow-external <preset>`` Y la
variable ``SOLERCIA_EVAL_EXTERNAL_CONFIRM=<preset>``: el conjunto dorado
contiene correos reales.

Códigos de salida: 0 éxito · 1 uso · 2 proveedor externo rechazado · 3 datos o
reglas no válidos · 4 el proveedor no respondió.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from app.ai.determinism import DEFAULT_SERVER_THREADS, PROFILES
from app.ai.presets import PRESETS
from app.eval.golden import GoldenError
from app.eval.report import pct
from app.eval.runner import EvalOptions, ExternalProviderRefused, run_evaluation
from app.modules.reconciliation.channel_v2 import ProviderDown
from app.modules.reconciliation.prompt_versions import DEFAULT_PROMPT_VERSION_V2, PROMPTS_V2
from app.modules.reconciliation.rules import RulesError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--golden-dir", type=Path, required=True)
    parser.add_argument("--cortes", required=True, help="Cortes separados por coma.")
    parser.add_argument("--rules", type=Path, required=True, help="Archivo de reglas JSON.")
    parser.add_argument("--preset", default="ollama_local", choices=sorted(PRESETS))
    parser.add_argument("--model", default="qwen3.5:9b-q4_K_M")
    parser.add_argument("--embedding-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--profile", default="mac", choices=PROFILES)
    parser.add_argument("--num-thread", type=int, default=DEFAULT_SERVER_THREADS)
    parser.add_argument("--limit", type=int, default=None, help="Registros por corte.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--allow-external", default=None, metavar="PRESET")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--embedding-url", default="http://127.0.0.1:11434")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=6000)
    parser.add_argument("--max-tokens", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument(
        "--prompt-version", default=DEFAULT_PROMPT_VERSION_V2, choices=sorted(PROMPTS_V2)
    )
    parser.add_argument(
        "--subject-match",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Asunto literal en el texto de la tarea → candidata forzada.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.runs < 1:
        print("--runs debe ser al menos 1.", file=sys.stderr)
        return 1
    options = EvalOptions(
        golden_dir=args.golden_dir.expanduser(),
        cuts=[c.strip() for c in args.cortes.split(",") if c.strip()],
        rules_path=args.rules.expanduser(),
        preset=args.preset,
        model=args.model,
        embedding_model=args.embedding_model,
        runs=args.runs,
        profile=args.profile,
        num_thread=args.num_thread,
        limit=args.limit,
        out_dir=args.out_dir.expanduser() if args.out_dir else None,
        cache_dir=args.cache_dir.expanduser() if args.cache_dir else None,
        allow_external=args.allow_external,
        base_url=args.base_url,
        embedding_url=args.embedding_url,
        top_k=args.top_k,
        max_chars=args.max_chars,
        max_tokens=args.max_tokens,
        seed=args.seed,
        num_ctx=args.num_ctx,
        prompt_version=args.prompt_version,
        subject_match=args.subject_match,
    )
    try:
        metrics = asyncio.run(run_evaluation(options))
    except ExternalProviderRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (GoldenError, RulesError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except ProviderDown as exc:
        print(f"El proveedor no respondió ({exc.code}).", file=sys.stderr)
        return 4
    latency = metrics["latency_ms"]
    print(
        f"n={metrics['n']} exactitud={pct(metrics['class_accuracy'])} "
        f"macroF1={metrics['macro_f1']} tarea_top1={pct(metrics['task_top1'])} "
        f"cobertura={pct(metrics['candidate_coverage'])} "
        f"determinismo={pct(metrics['determinism']['rate'])} "
        f"p50={latency['p50']}ms p95={latency['p95']}ms errores_json={metrics['json_errors']}"
    )
    print(f"Prompt: {options.prompt_version} · resultados: {metrics['out_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
