"""Solercia Connect adapter package.

Reads mail, calendar and meeting notes through a local Solercia Connect
runtime over its loopback contract. ``credential_kind=api_token``: the key is
the runtime's, never a provider's.

Registers itself at import time, following the GLPI and Microsoft 365
precedent — the core never imports this module; ``app/db_init.py`` does.
"""

from app.integrations.adapters.solercia_connect.adapter import SolerciaConnectAdapter
from app.integrations.registry import register_adapter

register_adapter(SolerciaConnectAdapter())
