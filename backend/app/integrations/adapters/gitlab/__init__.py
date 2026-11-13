"""GitLab adapter package — read-only REST v4, ``credential_kind=api_token``.

Registers itself at import time (precedent ``adapters/glpi``/``adapters/jira``):
the core never imports this module directly, ``app/db_init.py`` does.
"""

from app.integrations.adapters.gitlab.adapter import GitlabAdapter
from app.integrations.registry import register_adapter

register_adapter(GitlabAdapter())
