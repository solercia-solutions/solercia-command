"""``google`` adapter package (change 16-adapter-google).

Registration (``register_adapter(GoogleAdapter())``) lands here in Lote 6
once ``adapter.py`` exists — mirrors ``adapters/microsoft365/__init__.py``.
Left without a top-level import in earlier lotes so
``app.integrations.adapters.google.errors``/``client``/``oauth``/... stay
independently importable while the package is being built module by
module.
"""
