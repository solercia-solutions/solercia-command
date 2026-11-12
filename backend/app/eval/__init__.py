"""Offline evaluation of the mail classifier (E04).

Reads a golden set from OUTSIDE the repository at run time (it contains real
mail), runs channel v2 in dry-run (no database) and writes metrics. Never
imports database modules.
"""
