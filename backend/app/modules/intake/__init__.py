"""Intake classifier module (change 22-intake-classifier).

Storage + rules engine over the 14's read-only ports: ``IntakeItem`` persists
every insumo read from a connected account, ``IntakeRule`` configures
tema→respondiente routing, ``IntakeRun`` logs each ``POST /intake/pull``
execution, and ``IntakeSettings`` holds the organization's lazy default
project. ``classifier.py`` is a pure ``ClassifierPort``/``RuleBasedClassifier``
strategy — no DB, no HTTP — evaluated by ``service.py`` after every pull.
"""
