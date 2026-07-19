"""GLPI adapter package (change 17-adapter-glpi, specs/glpi-adapter/spec.md).

Read-only I/O over GLPI's ``apirest.php``; ``credential_kind=api_token``.
The adapter registers itself (``register_adapter(GlpiAdapter())``) at
import time once ``adapter.py`` exists (Lote 6) — this module intentionally
does nothing yet in earlier lotes (4/5) so ``client.py``/``session.py`` can
be developed and tested standalone without a half-registered adapter.
"""
