"""Provider adapters for the integrations core.

Each adapter module registers ITSELF in ``app.integrations.registry`` at
import time (precedent ``app/email/outbox.py``); this package never imports
its submodules — the caller (``app/db_init.py``, change 14-integration-ports
Lote 2) decides which adapters to activate by importing them explicitly.
"""
