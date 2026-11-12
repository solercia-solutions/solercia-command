"""Activity <-> activity links stated by the sources (45a D6, D14).

Only the PTR states cross-references (column «Actividad Plan Seguridad»,
e.g. ``4.5 (OM-03)``, ``1.1, 1.2, 1.3``). Policy, never resolved silently:

1. With an ``OM-xx`` code the link goes to the PSPI activity carrying that
   code: ``exact`` when the cited number matches it too, ``conflict`` when it
   does not (R17/R19/R20 cite 4.5 but OM-03 is 4.4). A conflict IS persisted,
   with the literal text, and never counts as confirmed.
2. Without a code the number is taken literally (``exact``) unless the action
   shares no ISO 27001 control with the cited activities: then NO link is
   created and the reference goes to review (R26 -> 4.4, R32 -> 4.3). An
   invented link is worse than a missing one.

``by_external_code`` is reserved for a reference that carries only a code and
no number; none of the current sources does it, but the rule is the same.
"""

import re
from dataclasses import dataclass

from app.modules.plans.importers.common import ParsedPlan

LINK_TYPE = "contributes_to"
_REFERENCE = re.compile(r"(?P<number>\d+\.\d+)?\s*(?:\((?P<om>OM-\d{2})\))?")


@dataclass(frozen=True)
class LinkDraft:
    from_plan: str
    from_code: str
    to_plan: str
    to_code: str
    resolution: str
    source_reference: str
    note: str | None = None

    @property
    def from_key(self) -> str:
        return f"{self.from_plan}/{self.from_code}"

    @property
    def to_key(self) -> str:
        return f"{self.to_plan}/{self.to_code}"


@dataclass(frozen=True)
class ReviewItem:
    from_key: str
    source_reference: str
    reason: str


def _tokens(reference: str) -> list[tuple[str, str | None, str | None]]:
    """``"2.5 (OM-09), 5.3"`` -> ``[("2.5 (OM-09)", "2.5", "OM-09"), ("5.3", "5.3", None)]``."""

    tokens = []
    for match in _REFERENCE.finditer(reference):
        literal = match.group(0).strip()
        if literal and (match.group("number") or match.group("om")):
            tokens.append((literal, match.group("number"), match.group("om")))
    return tokens


def resolve_cross_references(
    source: ParsedPlan, target: ParsedPlan
) -> tuple[list[LinkDraft], list[ReviewItem]]:
    """Resolve ``source.cross_refs`` (PTR) against ``target`` activities (PSPI)."""

    by_code = {activity.code: activity for activity in target.activities}
    by_om = {
        om: activity for activity in target.activities for om in (activity.external_codes or [])
    }
    actions = {activity.code: activity for activity in source.activities}
    links: list[LinkDraft] = []
    review: list[ReviewItem] = []
    seen: set[tuple[str, str]] = set()
    for code, reference in source.cross_refs.items():
        from_key = f"{source.plan.code}/{code}"
        tokens = _tokens(reference)
        if not tokens:
            review.append(ReviewItem(from_key, reference, "Referencia sin actividad reconocible."))
            continue
        cited = [by_code[n] for _, n, om in tokens if n and not om and n in by_code]
        cited_controls = {c for activity in cited for c in (activity.iso_controls or [])}
        action_controls = set(actions[code].iso_controls or [])
        for literal, number, om in tokens:
            if om:
                owner = by_om.get(om)
                if owner is None:
                    review.append(
                        ReviewItem(
                            from_key,
                            literal,
                            f"Ninguna actividad del {target.plan.code} lleva {om}.",
                        )
                    )
                    continue
                if number is None:
                    draft = LinkDraft(
                        source.plan.code,
                        code,
                        target.plan.code,
                        owner.code,
                        "by_external_code",
                        literal,
                    )
                elif number == owner.code:
                    draft = LinkDraft(
                        source.plan.code, code, target.plan.code, owner.code, "exact", literal
                    )
                else:
                    draft = LinkDraft(
                        source.plan.code,
                        code,
                        target.plan.code,
                        owner.code,
                        "conflict",
                        literal,
                        note=f"El texto cita {number}, pero {om} pertenece a {owner.code}.",
                    )
            else:
                if number not in by_code:
                    review.append(
                        ReviewItem(
                            from_key,
                            literal,
                            f"La actividad {number} no existe en el {target.plan.code}.",
                        )
                    )
                    continue
                if action_controls and cited_controls and not action_controls & cited_controls:
                    review.append(
                        ReviewItem(
                            from_key,
                            literal,
                            "Sin código OM y sin control ISO en común "
                            f"(acción {', '.join(sorted(action_controls))}; actividad "
                            f"{number}: {', '.join(by_code[number].iso_controls or [])}). "
                            "No se crea el enlace.",
                        )
                    )
                    continue
                draft = LinkDraft(
                    source.plan.code, code, target.plan.code, number, "exact", literal
                )
            if (draft.from_key, draft.to_key) in seen:
                continue
            seen.add((draft.from_key, draft.to_key))
            links.append(draft)
    return links, review
