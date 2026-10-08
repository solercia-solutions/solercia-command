"""Registered prompt versions of channel v2 (E05a).

Each iteration of the prompt is a NEW version and older ones are never
removed: a stored proposal or an evaluation prediction names the version
that produced it, and that text must stay reproducible. All versions share
the output schema (``ClassificationV2``) and the post-rules; the user
message differs only when a version shows the candidates' latest notes.

``DEFAULT_PROMPT_VERSION_V2`` is the version the evaluation chose (by
macro-F1 on the TEST cuts, never on the development cut).
"""

from dataclasses import dataclass

from . import prompt_v2_1, prompt_v2_2, prompt_v2_3, prompt_v2_4
from .prompt_v2 import PROMPT_VERSION_V2, SYSTEM_PROMPT_V2


@dataclass(frozen=True)
class PromptSpec:
    version: str
    system: str
    #: Show each candidate's newest observation (what is already registered).
    candidate_notes: bool = False


PROMPTS_V2: dict[str, PromptSpec] = {
    spec.version: spec
    for spec in (
        PromptSpec(PROMPT_VERSION_V2, SYSTEM_PROMPT_V2),
        *(
            PromptSpec(m.PROMPT_VERSION, m.SYSTEM_PROMPT, getattr(m, "CANDIDATE_NOTES", False))
            for m in (prompt_v2_1, prompt_v2_2, prompt_v2_3, prompt_v2_4)
        ),
    )
}

DEFAULT_PROMPT_VERSION_V2 = prompt_v2_2.PROMPT_VERSION


def get_prompt_v2(version: str) -> PromptSpec:
    spec = PROMPTS_V2.get(version)
    if spec is None:
        raise ValueError(f"Versión de prompt desconocida: {version}.")
    return spec
