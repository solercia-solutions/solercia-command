"""C05: pure thread building — grouping, fallback key, deterministic state,
quote stripping and task-key extraction. No database, no LLM."""

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.reconciliation.threads import (
    MailItem,
    extract_task_keys,
    group_threads,
    new_content,
    normalize_subject,
    thread_state,
)

_T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_ME = "yo@entidad.gov.co"


def _mail(
    minutes: int,
    *,
    direction: str | None = "inbound",
    conversation_id: str | None = "conv-1",
    subject: str = "Solicitud de acceso",
    sender: str = "ana@entidad.gov.co",
    recipients: tuple[str, ...] = (_ME,),
    cc: tuple[str, ...] = (),
    body: str = "Hola, necesito acceso.",
) -> MailItem:
    return MailItem(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        subject=subject,
        sender=sender,
        recipients=recipients,
        cc=cc,
        direction=direction,
        occurred_at=_T0 + timedelta(minutes=minutes),
        body=body,
        mailbox=_ME,
    )


def _reply(minutes: int, **kwargs) -> MailItem:
    kwargs.setdefault("sender", _ME)
    kwargs.setdefault("recipients", ("ana@entidad.gov.co",))
    return _mail(minutes, direction="outbound", **kwargs)


# --- grouping --------------------------------------------------------------


def test_groups_by_conversation_id_and_orders_messages():
    a1, b1, a2 = _mail(0), _mail(5, conversation_id="conv-2"), _reply(10)
    threads = group_threads([a2, b1, a1])
    assert len(threads) == 2
    by_key = {t.key: t for t in threads}
    assert [m.id for m in by_key["conv:conv-1"].messages] == [a1.id, a2.id]
    # Most recent thread first.
    assert threads[0].key == "conv:conv-1"


def test_fallback_groups_by_normalized_subject_and_participants():
    first = _mail(0, conversation_id=None, subject="Informe mensual")
    reply = _reply(30, conversation_id=None, subject="RE: Informe mensual")
    forward = _mail(40, conversation_id=None, subject="RV: FW: Fwd: TR: informe  MENSUAL")
    other_person = _mail(
        50, conversation_id=None, subject="Informe mensual", sender="luis@otra.gov.co"
    )
    threads = group_threads([first, reply, forward, other_person])
    sizes = sorted(len(t.messages) for t in threads)
    assert sizes == [1, 3]
    assert all(t.key.startswith("subj:") for t in threads)


def test_fallback_separates_counterparts_even_without_replies():
    ana = _mail(0, conversation_id=None, subject="Informe")
    luis = _mail(5, conversation_id=None, subject="Informe", sender="luis@otra.gov.co")
    assert len(group_threads([ana, luis])) == 2


def test_fallback_key_is_stable_when_the_thread_grows():
    first = _mail(0, conversation_id=None, subject="Backup semanal")
    key_before = group_threads([first])[0].key
    later = _mail(
        60,
        conversation_id=None,
        subject="RE: Backup semanal",
        cc=("jefa@entidad.gov.co",),
    )
    reply = _reply(30, conversation_id=None, subject="RE: Backup semanal")
    assert group_threads([first, reply, later])[0].key == key_before


def test_normalize_subject_strips_prefixes_accents_and_case():
    assert normalize_subject("RE: RV: Fwd:  Revisión de Políticas ") == "revision de politicas"
    assert normalize_subject("TR: tr: fw: x") == "x"
    assert normalize_subject("") == ""


# --- deterministic state ----------------------------------------------------


def test_state_answered_when_outbound_after_last_inbound():
    assert thread_state([_mail(0), _reply(10)]) == "respondido"


def test_state_pending_when_last_message_is_inbound():
    assert thread_state([_mail(0), _reply(10), _mail(20)]) == "pendiente_respuesta"


def test_state_only_outbound_is_own_follow_up():
    assert thread_state([_reply(0), _reply(5)]) == "solo_saliente"


def test_unknown_direction_counts_as_inbound():
    assert thread_state([_mail(0, direction=None)]) == "pendiente_respuesta"


# --- content ------------------------------------------------------------------


def test_new_content_cuts_quoted_history_and_html():
    body = (
        "<p>Ya quedó el ajuste.</p><br>Saludos\n"
        "De: Ana <ana@entidad.gov.co>\nEnviado: lunes\nTexto viejo T-999"
    )
    assert new_content(body) == "Ya quedó el ajuste.\nSaludos"
    assert "T-999" not in new_content(body)
    assert new_content("El lun, 1 oct 2026 a las 9:00, Ana escribió:\nviejo") != ""


def test_extract_task_keys_normalizes_and_ignores_embedded_tokens():
    text = "Sobre la t-07 y SGSI-12; ver CP-13. No es ABC-12X ni T-5a ni 9T-4"
    assert extract_task_keys(text) == {"T-7", "SGSI-12", "CP-13"}
