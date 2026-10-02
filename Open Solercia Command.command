#!/bin/bash
# Finder puede ejecutar este archivo desde cualquier directorio, incluso con espacios.
# Solo abre una instancia existente; no instala ni inicia servicios.
set -eu
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$SCRIPT_DIR/scripts/local-status.sh" --open
