"""Prompt, output schema and output validation of the classifier (C05).

The LLM PROPOSES: it never changes a task. Its answer is validated twice —
by Pydantic (JSON schema) in the adapter and here against the candidates it
was shown: a ``task_ref`` outside them degrades to ``tarea_nueva`` with low
confidence, so a hallucinated reference can never point at a real task.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .candidates import Candidate
from .threads import MailThread, new_content

PROMPT_VERSION = "reconciliation-thread-v1"
DEGRADED_CONFIDENCE = 0.3
_FIELD_CHARS = {"accion": 300, "solicitante": 200, "resumen": 600, "motivo": 400}

Relation = Literal["tarea_existente", "tarea_nueva", "irrelevante"]

SYSTEM_PROMPT = """Eres el asistente de una persona que gestiona tareas en una entidad pública.
Recibes un hilo de correo (entrante = lo recibió; saliente = lo envió ella) y una lista de
tareas candidatas. Decide:
- relacion: "tarea_existente" si el hilo trata de una candidata; "tarea_nueva" si contiene una
  petición o compromiso que no está en las candidatas; "irrelevante" si es informativo,
  masivo, publicitario o no exige acción.
- task_ref: la referencia EXACTA de una candidata (solo con tarea_existente); si no, null.
- confianza: de 0 a 1.
- atendida: "si" si la petición quedó resuelta según lo escrito en el hilo, "parcial" si hubo
  avance sin cierre, "no" si sigue pendiente.
- accion: la acción concreta que queda (infinitivo, una línea) o null.
- solicitante: quién pide la acción o null.
- fecha_limite: fecha límite explícita en formato AAAA-MM-DD o null; no la inventes.
- resumen: una o dos frases.
- motivo: por qué elegiste la relación.
Responde solo con el JSON pedido, en español."""


class ThreadClassification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    relacion: Relation
    task_ref: str | None = None
    confianza: float = Field(ge=0, le=1)
    atendida: Literal["si", "no", "parcial"]
    accion: str | None = None
    solicitante: str | None = None
    fecha_limite: str | None = None
    resumen: str
    motivo: str


@dataclass(frozen=True)
class Decision:
    relation: Relation
    task_id: object | None
    confidence: float
    payload: dict


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value[:limit] or None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10]).isoformat()
    except ValueError:
        return None


def validate_classification(
    output: ThreadClassification, candidates: Sequence[Candidate]
) -> Decision:
    by_ref = {candidate.ref.upper(): candidate for candidate in candidates}
    relation: Relation = output.relacion
    confidence = float(output.confianza)
    chosen = None
    degraded = False
    if relation == "tarea_existente":
        chosen = by_ref.get((output.task_ref or "").strip().upper())
        if chosen is None:
            relation, degraded = "tarea_nueva", True
            confidence = min(confidence, DEGRADED_CONFIDENCE)
    payload = {
        "relacion": relation,
        "task_ref": chosen.ref if chosen else None,
        "confianza": confidence,
        "atendida": output.atendida,
        "fecha_limite": _iso_date(output.fecha_limite),
        "degradada": degraded,
        "task_ref_original": output.task_ref if degraded else None,
        **{name: _clip(getattr(output, name), limit) for name, limit in _FIELD_CHARS.items()},
    }
    return Decision(relation, chosen.task_id if chosen else None, confidence, payload)


def _direction_label(outbound: bool) -> str:
    return "SALIENTE" if outbound else "ENTRANTE"


def thread_messages_text(thread: MailThread, max_chars: int) -> str:
    """Newest messages first until the budget, then shown oldest first."""

    blocks: list[str] = []
    budget = max_chars
    for message in reversed(thread.messages):
        if budget <= 0:
            break
        header = (
            f"[{message.occurred_at:%Y-%m-%d %H:%M} UTC] {_direction_label(message.is_outbound)} "
            f"de {message.sender} para {', '.join(message.recipients) or '—'}"
        )
        body = new_content(message.body)[: max(budget - len(header) - 1, 0)]
        block = f"{header}\n{body}".strip()
        blocks.append(block)
        budget -= len(block) + 2
    omitted = len(thread.messages) - len(blocks)
    text = "\n\n".join(reversed(blocks))
    if omitted:
        text = f"({omitted} mensajes anteriores omitidos)\n\n{text}"
    return text


def thread_embedding_text(thread: MailThread, max_chars: int) -> str:
    return f"{thread.subject}\n{thread_messages_text(thread, max_chars)}"[:max_chars]


def build_user_message(thread: MailThread, candidates: Sequence[Candidate], max_chars: int) -> str:
    lines = [
        f"Fecha del último mensaje: {thread.last_message_at:%Y-%m-%d}",
        f"Estado determinista del hilo: {thread.state}",
        f"Asunto: {thread.subject}",
        "",
        "Mensajes:",
        thread_messages_text(thread, max_chars),
        "",
        "Tareas candidatas:",
    ]
    if candidates:
        lines += [f"- {c.ref}: {c.title}" for c in candidates]
    else:
        lines.append("(ninguna)")
    return "\n".join(lines)
