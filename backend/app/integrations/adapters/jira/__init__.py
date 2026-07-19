"""Jira adapter package (change 18-adapter-jira, specs/jira-import/spec.md).

Read-only issue import over Jira Cloud's REST API v3 and CSV/XLSX export;
``credential_kind=api_token`` (email + API token, HTTP Basic). Registers
itself in import-time (specs/jira-import/spec.md "El adaptador se registra
sin editar el núcleo" — precedent ``adapters/fake.py``/``adapters/glpi``):
the core never imports this module directly, ``app/db_init.py`` does.
"""

from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.registry import register_adapter

register_adapter(JiraAdapter())
