"""Prompt scaffolding for change 49 (`clasificador-llm`), which persists
`PROMPT_VERSION` alongside every `assistant_suggestions` row. Bump it
whenever a template change is MATERIAL (could plausibly change the
model's output); a purely cosmetic edit does not require it.
"""

from typing import Final

PROMPT_VERSION: Final[str] = "v1"
