"""`LlmPort` adapter implementations. Empty on purpose: `registry.py`
imports each adapter it needs; the `anthropic` adapter is imported lazily
so its SDK never loads for another provider (design.md D5).
"""
