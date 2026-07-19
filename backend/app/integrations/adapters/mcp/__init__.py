"""``mcp`` adapter package (change 19-mcp-connector) — registers the
``McpAdapter`` at import time (Lote 5), mirroring ``adapters/glpi/__init__.py``
/``adapters/jira/__init__.py``. Populated once ``adapter.py`` exists (Lote 5);
until then this package only hosts the SSRF guard (``ssrf.py``, Lote 3),
session/reader/mapping modules (Lote 4) and domain errors (``errors.py``).
"""
