"""Registers the ``microsoft365`` adapter with the core's registry at
import time (change 15-adapter-microsoft365) — same precedent as
``app/integrations/adapters/fake.py`` (IP-R2, "sin tocar el núcleo"): this
module registers ITSELF, ``registry.py`` is never edited.
"""

from app.integrations.adapters.microsoft365.adapter import Microsoft365Adapter
from app.integrations.registry import register_adapter

register_adapter(Microsoft365Adapter())
