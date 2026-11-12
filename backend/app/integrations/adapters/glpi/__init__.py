"""GLPI adapter package (change 17-adapter-glpi, specs/glpi-adapter/spec.md).

Read-only I/O over GLPI's ``apirest.php``; ``credential_kind=api_token``.
Registers itself in import-time (GA-R1, "sin tocar el núcleo" — precedent
``adapters/fake.py``): the core never imports this module directly,
``app/db_init.py`` does (mirrors ``import app.integrations.adapters.
microsoft365``/``google``).
"""

from app.integrations.adapters.glpi.adapter import GlpiAdapter
from app.integrations.registry import register_adapter

register_adapter(GlpiAdapter())
