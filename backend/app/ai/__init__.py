"""Neutral `LlmPort` core (change 48-puerto-llm) — knows nothing about
FastAPI, SQLAlchemy or any concrete provider (design.md "Enfoque técnico").

Empty on purpose: never imports its own submodules (precedent
`app/integrations/adapters/__init__.py`); callers import `app.ai.ports`,
`app.ai.errors` or `app.ai.registry` explicitly.
"""
