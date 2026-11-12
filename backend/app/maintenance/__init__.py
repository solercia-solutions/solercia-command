"""Operational data-maintenance package (change 42-purga-datos-demo).

Backs ``backend/scripts/purge_demo_data.py`` — never exposed over HTTP. A
single SQLAlchemy adapter (``repository.py``) backs every use case here; no
repository ever calls ``commit()`` or ``rollback()``.
"""
