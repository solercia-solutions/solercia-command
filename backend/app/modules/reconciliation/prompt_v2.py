"""Prompt v2 of the classifier (E03): 8 classes, methodology criteria.

The LLM only CHOOSES among candidates the deterministic stages produced.
Its answer is checked by ``apply_post_rules``:

- a ``task_ref`` outside the candidates → ``no_concluyente`` (a hallucinated
  reference can never point at a real task);
- ``cierra``/``avanza``/``confirma`` without a task → ``no_concluyente``;
- other classes carry no task;
- confidence is CALIBRATED by evidence — how the task was reached (explicit
  ID 0.9 > object identifier 0.75 > similarity only 0.5) times 0.6 when the
  quoted evidence is not literally in the record. The model's own number is
  never asked for.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, ConfigDict

from .classes import TASK_CLASSES, ResultClass
from .rules import CompiledRules, normalize_task_ref
from .stages import CandidateV2, Unit, clean_body

PROMPT_VERSION_V2 = "reconciliation-v2.0"
_EVIDENCE_MISSING_FACTOR = 0.6
_MIN_EVIDENCE_CHARS = 8
_FIELD_CHARS = {"accion": 300, "solicitante": 200, "resumen": 600, "evidencia": 400}
_VIA_CONFIDENCE = {"id_explicito": 0.9, "identificador": 0.75, "asunto": 0.75, "similitud": 0.5}
_CLASS_CONFIDENCE = {
    "tarea_nueva": 0.55,
    "solo_bitacora": 0.6,
    "informativo": 0.6,
    "descartado": 0.5,
    "no_concluyente": 0.2,
}

SYSTEM_PROMPT_V2 = """Eres el asistente que hace el corte de correo contra el checklist de tareas
de una persona (el dueño del buzón) en una entidad pública. Recibes UN registro (un hilo de
correo, un correo enviado por el dueño o un evento de su calendario) y una lista cerrada de
tareas candidatas con su estado. Asigna exactamente una clase:

- cierra: el registro acredita que quedó hecho lo que dependía del dueño, con evidencia válida,
  aunque falte que un tercero responda o apruebe.
- avanza: hay una acción con evidencia sobre una candidata y queda algo pendiente del dueño;
  también una reapertura (devolvieron el entregable con observaciones).
- confirma: ratifica lo ya registrado en una candidata (abierta o cerrada) sin cambiar su estado.
- tarea_nueva: un pedido o compromiso con objeto propio, solicitante identificable y acción del
  dueño que no corresponde a ninguna candidata. Si es un paso más de una candidata, NO es nueva.
- solo_bitacora: actividad ejecutada que no es un pendiente (aceptación de reunión, acuse breve,
  notificación de compartición, envío duplicado).
- informativo: se lee, pero no pide acción ni mueve ninguna tarea.
- descartado: ruido (publicidad, boletines, avisos automáticos sin relación con tareas).
- no_concluyente: el registro no permite afirmar el hecho (por ejemplo, una reunión sin
  evidencia de asistencia). Ante la duda, no_concluyente.

Evidencia válida para cerrar: correo enviado, evento con asistencia acreditada, radicado,
caso de mesa de ayuda, commit o archivo entregado. Un borrador, un correo sin enviar o una
vista previa NO bastan. Usa solo lo escrito en el registro; no inventes fechas ni hechos.

Campos:
- clase: una de las ocho clases.
- task_ref: la referencia EXACTA de una candidata (solo con cierra, avanza, confirma o
  no_concluyente); en otro caso null.
- evidencia: cita textual breve copiada del registro que sostiene la clase, o null.
- accion: lo que queda por hacer (infinitivo, una línea) o null.
- solicitante: quién pide la acción o null.
- fecha_limite: fecha límite explícita AAAA-MM-DD o null.
- resumen: una o dos frases.
Responde solo con el JSON pedido, en español."""


class ClassificationV2(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clase: ResultClass
    task_ref: str | None = None
    evidencia: str | None = None
    accion: str | None = None
    solicitante: str | None = None
    fecha_limite: str | None = None
    resumen: str


@dataclass(frozen=True)
class Verdict:
    clase: str
    task_id: str | None
    task_ref: str | None
    confidence: float
    via: str | None
    payload: dict = field(default_factory=dict)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return " ".join(plain.split())


def evidence_is_valid(evidence: str | None, record_text: str) -> bool:
    quote = _fold(evidence or "").strip(" .\"'«»")
    return len(quote) >= _MIN_EVIDENCE_CHARS and quote in _fold(record_text)


def calibrated_confidence(clase: str, via: str | None, evidence_ok: bool) -> float:
    if clase in TASK_CLASSES:
        base = _VIA_CONFIDENCE.get((via or "similitud").split(":")[0], 0.5)
    else:
        base = _CLASS_CONFIDENCE.get(clase, 0.5)
    if clase != "no_concluyente" and not evidence_ok:
        base *= _EVIDENCE_MISSING_FACTOR
    return round(base, 2)


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return " ".join(value.split())[:limit] or None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError:
        return None


def apply_post_rules(
    output: ClassificationV2, candidates: Sequence[CandidateV2], record_text: str
) -> Verdict:
    by_ref = {normalize_task_ref(c.ref): c for c in candidates}
    clase: str = output.clase
    raw_ref = (output.task_ref or "").strip()
    chosen = by_ref.get(normalize_task_ref(raw_ref)) if raw_ref else None
    adjustments: list[str] = []
    if raw_ref and chosen is None and (clase in TASK_CLASSES or clase == "no_concluyente"):
        clase = "no_concluyente"
        adjustments.append("task_ref_fuera_de_candidatas")
    elif clase in TASK_CLASSES and chosen is None:
        clase = "no_concluyente"
        adjustments.append("clase_sin_tarea")
    if clase not in TASK_CLASSES and clase != "no_concluyente":
        chosen = None
    evidence_ok = evidence_is_valid(output.evidencia, record_text)
    via = chosen.via if chosen else None
    confidence = calibrated_confidence(clase, via, evidence_ok)
    payload = {
        "clase": clase,
        "clase_modelo": output.clase,
        "task_ref": chosen.ref if chosen else None,
        "via": via,
        "confianza": confidence,
        "evidencia_valida": evidence_ok,
        "ajustes": adjustments,
        "task_ref_original": (raw_ref or None) if adjustments else None,
        "fecha_limite": _iso_date(output.fecha_limite),
        **{name: _clip(getattr(output, name), limit) for name, limit in _FIELD_CHARS.items()},
    }
    return Verdict(
        clase=clase,
        task_id=chosen.task_id if chosen else None,
        task_ref=chosen.ref if chosen else None,
        confidence=confidence,
        via=via,
        payload=payload,
    )


_KIND_LABEL = {
    "thread": "Hilo de correo (frente B)",
    "sent": "Correo enviado por el dueño (frente A)",
    "event": "Evento del calendario del dueño (frente A)",
}


def _record_block(record, rules: CompiledRules | None, budget: int) -> str:
    if record.kind == "event":
        header = (
            f"[{record.occurred_at:%Y-%m-%d %H:%M} UTC] EVENTO organizado por {record.sender}; "
            f"respuesta del dueño: {record.response_status or 'desconocida'}"
            f"{'; CANCELADO' if record.is_cancelled else ''}"
        )
    else:
        direction = "SALIENTE" if record.kind == "out" else "ENTRANTE"
        header = (
            f"[{record.occurred_at:%Y-%m-%d %H:%M} UTC] {direction} de {record.sender} "
            f"para {', '.join(record.to) or '—'}"
            f"{' (cc ' + ', '.join(record.cc) + ')' if record.cc else ''}"
        )
    if record.attachments:
        header += f"\nAdjuntos: {', '.join(record.attachments)}"
    body = clean_body(record.body, rules)[: max(budget - len(header) - 1, 0)]
    return f"{header}\n{body}".strip()


def unit_messages_text(unit: Unit, max_chars: int, rules: CompiledRules | None = None) -> str:
    """Newest records first until the budget, then shown oldest first."""

    blocks: list[str] = []
    budget = max_chars
    for record in reversed(unit.records):
        if budget <= 0:
            break
        block = _record_block(record, rules, budget)
        blocks.append(block)
        budget -= len(block) + 2
    omitted = len(unit.records) - len(blocks)
    text = "\n\n".join(reversed(blocks))
    return f"({omitted} mensajes anteriores omitidos)\n\n{text}" if omitted else text


def build_user_message_v2(
    unit: Unit,
    candidates: Sequence[CandidateV2],
    *,
    max_chars: int,
    rules: CompiledRules | None = None,
) -> str:
    lines = [
        f"Tipo de registro: {_KIND_LABEL[unit.kind]}",
        f"Fecha del último mensaje: {unit.last_at:%Y-%m-%d}",
    ]
    if unit.state:
        lines.append(f"Estado determinista del hilo: {unit.state}")
    lines += [
        f"Asunto: {unit.subject}",
        "",
        "Registro:",
        unit_messages_text(unit, max_chars, rules),
        "",
        "Tareas candidatas (referencia [estado] (vía): título):",
    ]
    if candidates:
        lines += [f"- {c.ref} [{c.status or '?'}] ({c.via}): {c.title}" for c in candidates]
    else:
        lines.append("(ninguna)")
    return "\n".join(lines)
