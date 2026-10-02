"""Readers of the institutional plan source documents (change 45b).

Pure parsing: no session, no I/O besides reading the given file. The parsers
produce the 45a write-seam payloads (``PlanUpsert``/``PlanActivityUpsert``);
persisting them is the job of :mod:`app.modules.plans.importers.apply`.
"""
