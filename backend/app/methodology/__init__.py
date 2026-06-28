"""Methodology Strategy package.

Each methodology encapsulates its board columns, allowed statuses and feature
flags behind a common :class:`MethodologyStrategy` interface, resolved through
:func:`app.methodology.factory.get_strategy`.
"""
