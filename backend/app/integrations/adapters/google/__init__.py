"""Registers the ``google`` adapter with the core's registry at import
time (change 16-adapter-google) — same precedent as
``app/integrations/adapters/fake.py``/``adapters/microsoft365/__init__.py``
(IP-R2, "sin tocar el núcleo"): this module registers ITSELF,
``registry.py`` is never edited.
"""

from app.integrations.adapters.google.adapter import GoogleAdapter
from app.integrations.registry import register_adapter

register_adapter(GoogleAdapter())
