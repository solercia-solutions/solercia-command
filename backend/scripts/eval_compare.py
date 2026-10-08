"""CLI: tabla comparativa (modelo × perfil × métricas) de varias evaluaciones.

Desde ``backend/``::

    .venv/bin/python -m scripts.eval_compare <out-dir> [<out-dir> ...] [--out tabla.md]

Lee ``metrics.json`` de cada carpeta y escribe la tabla en Markdown (en la
salida estándar o en ``--out``). Solo números: nunca contenido de correos.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.eval.compare import compare_markdown


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    missing = [str(f) for f in args.folders if not (f / "metrics.json").exists()]
    if missing:
        print(f"Sin metrics.json en: {', '.join(missing)}", file=sys.stderr)
        return 1
    table = compare_markdown(args.folders)
    if args.out:
        args.out.write_text(table, encoding="utf-8")
    else:
        print(table, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
