"""Golden set loader (E04): ``<golden>/<cut>/input/{records.jsonl,
checklist_before.csv}`` and ``<golden>/<cut>/labels.jsonl``.

Records become ``MailRecord`` (direction ``in``/``out``/``event``), the
checklist BEFORE the cut becomes ``TaskEntry`` (open and closed tasks: a
``confirma`` needs the closed ones) and labels map the methodology's class
names to the 8 tokens; ``manual_needed`` (null class) is excluded and
counted. Nothing is copied anywhere: the data stays in memory.
"""

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.modules.reconciliation.classes import class_token
from app.modules.reconciliation.rules import normalize_task_ref
from app.modules.reconciliation.stages import MailRecord, TaskEntry


class GoldenError(ValueError):
    """The golden cut is missing or malformed (message has no mail content)."""


@dataclass(frozen=True)
class GoldenLabel:
    cut: str
    kind: str
    key: str
    expected: str
    expected_tasks: tuple[str, ...]
    label_confidence: str | None


@dataclass(frozen=True)
class GoldenCut:
    name: str
    records: list[MailRecord]
    tasks: list[TaskEntry]
    labels: list[GoldenLabel]
    manual_needed: int


def _when(raw: dict) -> datetime:
    for field in ("dt", "sent_at", "received_at", "start"):
        value = raw.get(field)
        if value:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    raise GoldenError("Registro sin fecha.")


def _attachments(raw: dict) -> tuple[str, ...]:
    names = []
    for item in raw.get("attachments") or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
    return tuple(names)


def _record(raw: dict) -> MailRecord:
    direction = raw.get("direction")
    if direction not in ("in", "out", "event"):
        raise GoldenError("Registro con dirección desconocida.")
    return MailRecord(
        id=str(raw["id"]),
        kind=direction,
        conversation_id=raw.get("conversation_id") or None,
        subject=raw.get("subject") or "",
        sender=(raw.get("sender") or "").strip().lower(),
        to=tuple(str(a).strip().lower() for a in raw.get("to") or []),
        cc=tuple(str(a).strip().lower() for a in raw.get("cc") or []),
        occurred_at=_when(raw),
        body=raw.get("body_text") or "",
        attachments=_attachments(raw),
        response_status=raw.get("response_status"),
        is_cancelled=bool(raw.get("is_cancelled")),
    )


def _tasks(path: Path) -> list[TaskEntry]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    tasks = []
    for row in rows:
        ref = normalize_task_ref(row.get("ID") or "")
        if not ref:
            continue
        tasks.append(
            TaskEntry(
                id=ref,
                ref=ref,
                title=(row.get("Tarea") or "").strip(),
                detail=(row.get("Detalle") or "").strip(),
                status=(row.get("Estado") or "").strip(),
                observations=(row.get("Observaciones") or "").strip(),
            )
        )
    return tasks


def load_cut(golden_dir: Path, cut: str) -> GoldenCut:
    base = Path(golden_dir) / cut
    try:
        with (base / "input" / "records.jsonl").open(encoding="utf-8") as handle:
            records = [_record(json.loads(line)) for line in handle if line.strip()]
        tasks = _tasks(base / "input" / "checklist_before.csv")
        with (base / "labels.jsonl").open(encoding="utf-8") as handle:
            raw_labels = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError, KeyError) as exc:
        raise GoldenError(f"No fue posible leer el corte {cut}.") from exc

    labels: list[GoldenLabel] = []
    manual = 0
    for raw in raw_labels:
        expected = class_token(raw.get("expected_result"))
        if expected is None:
            manual += 1
            continue
        labels.append(
            GoldenLabel(
                cut=cut,
                kind=raw["record_kind"],
                key=str(raw["record_key"]),
                expected=expected,
                expected_tasks=tuple(
                    normalize_task_ref(t) for t in raw.get("expected_task_ids") or []
                ),
                label_confidence=raw.get("confidence_of_label"),
            )
        )
    return GoldenCut(cut, records, tasks, labels, manual)
