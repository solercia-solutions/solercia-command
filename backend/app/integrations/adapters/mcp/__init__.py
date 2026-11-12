"""``mcp`` adapter package (change 19-mcp-connector, mcp-connector/spec.md
MC-R2 "Registro en import-time sin editar el núcleo"). Registers itself in
import-time (precedent ``adapters/fake.py``/``adapters/glpi``/
``adapters/jira``): the core never imports this module directly,
``app/db_init.py`` does (mirrors ``import app.integrations.adapters.glpi``).
"""

from app.integrations.adapters.mcp.adapter import McpAdapter
from app.integrations.registry import register_adapter

register_adapter(McpAdapter())
