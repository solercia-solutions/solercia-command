"""User-homologation module for GLPI assignees (change 17-adapter-glpi).

``router -> service -> repository``, same layering as ``assets``/
``connectors``. Owns the tenant-scoped ORM state (``glpi_user_links``,
``glpi_unmatched_assignees``/``glpi_unmatched_cases``) and the matching
cascade (correo -> documento -> nombre); NEVER speaks the GLPI HTTP
protocol directly — that stays isolated in
``app.integrations.adapters.glpi`` (design.md, "adaptador + módulo").
"""
