"""E03: deterministic stages of channel v2, in the methodology's order.

Noise (with exceptions and the mass-mail condition) → explicit identifiers
(forced candidates) → thread state → fronts A (sent mail and calendar
events as their own records) and B (threads). Pure; SYNTHETIC data only.
"""

from datetime import UTC, datetime, timedelta

from app.modules.reconciliation.rules import compile_rules
from app.modules.reconciliation.stages import (
    MailRecord,
    TaskEntry,
    build_units,
    forced_candidates,
    message_noise,
    precheck,
    rank_candidates,
    unit_identifiers,
)

ME = "yo@ejemplo.gov.co"
T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

RULES = compile_rules(
    {
        "version": "1.0.0",
        "buzon": ME,
        "ruido": {
            "remitentes": {"valores": ["boletin@", "no-reply"]},
            "asunto_regex": "convocatoria|jornada",
            "lista_masiva": {"valor": "todos@"},
            "excepciones": {
                "asunto_seguridad_regex": "phishing|incidente",
                "no_descartar_remitentes": ["avisos-sistema@ejemplo.gov.co"],
            },
        },
        "identificadores": {
            "tarea": {"regex": "\\bT-\\d{1,3}\\b"},
            "caso": {"regex": "\\bcaso\\s*#?\\s*0*(\\d{5})\\b"},
        },
    }
)


def _mail(
    rid,
    *,
    kind="in",
    subject="Asunto",
    sender="ana@otra.gov.co",
    to=(ME,),
    cc=(),
    minutes=0,
    body="",
    conversation="c1",
    attachments=(),
    status=None,
    cancelled=False,
):
    return MailRecord(
        id=rid,
        kind=kind,
        conversation_id=conversation,
        subject=subject,
        sender=sender,
        to=tuple(to),
        cc=tuple(cc),
        occurred_at=T0 + timedelta(minutes=minutes),
        body=body,
        attachments=tuple(attachments),
        response_status=status,
        is_cancelled=cancelled,
    )


# --- noise ---------------------------------------------------------------------------


def test_outbound_and_security_subjects_are_never_noise():
    assert message_noise(_mail("1", kind="out", sender=ME, to=("todos@x",)), RULES) is None
    alert = _mail("2", sender="no-reply@x.com", to=("todos@ejemplo.gov.co",), subject="Phishing")
    assert message_noise(alert, RULES) is None


def test_mass_list_is_noise_even_for_never_discard_senders():
    mass = _mail("1", sender="avisos-sistema@ejemplo.gov.co", to=("todos@ejemplo.gov.co",))
    assert message_noise(mass, RULES) == "lista_masiva"
    direct = _mail("2", sender="avisos-sistema@ejemplo.gov.co", to=("otro@x",))
    assert message_noise(direct, RULES) is None


def test_noise_sender_is_kept_when_addressed_to_the_owner():
    assert message_noise(_mail("1", sender="boletin@x.com", to=("lista@x",)), RULES) == (
        "remitente"
    )
    assert message_noise(_mail("2", sender="boletin@x.com", cc=(ME,), to=("x@x",)), RULES) is None


def test_subject_filter_only_applies_to_mass_mail():
    mass = _mail("1", subject="Convocatoria abierta", to=("grupo@x",))
    assert message_noise(mass, RULES) == "asunto"
    directed = _mail("2", subject="Convocatoria abierta", to=(ME,))
    assert message_noise(directed, RULES) is None


# --- units (fronts A and B) and thread state ----------------------------------------------


def test_builds_threads_sent_records_and_events():
    records = [
        _mail("a", minutes=0),
        _mail("b", kind="out", sender=ME, to=("ana@otra.gov.co",), minutes=5),
        _mail("c", conversation="c2", minutes=1),
        _mail("e", kind="event", conversation=None, subject="Comité", status="Accepted"),
    ]
    units = build_units(records)
    by_kind = {(u.kind, u.key) for u in units}
    assert ("thread", "c1") in by_kind and ("thread", "c2") in by_kind
    assert ("sent", "b") in by_kind and ("event", "e") in by_kind
    states = {u.key: u.state for u in units if u.kind == "thread"}
    assert states == {"c1": "respondido", "c2": "pendiente_respuesta"}
    sent = next(u for u in units if u.kind == "sent")
    assert sent.state == "respondido" and sent.thread_key == "c1"


def test_thread_without_conversation_uses_normalized_subject():
    units = build_units(
        [
            _mail("a", conversation=None, subject="RE: Informe"),
            _mail("b", conversation=None, subject="Informe", minutes=3),
        ]
    )
    threads = [u for u in units if u.kind == "thread"]
    assert [u.key for u in threads] == ["subj:informe"]
    assert threads[0].state == "pendiente_respuesta"


def test_only_outbound_thread_is_solo_saliente():
    (thread,) = [u for u in build_units([_mail("a", kind="out", sender=ME)]) if u.kind == "thread"]
    assert thread.state == "solo_saliente"


def test_unit_order_is_stable():
    records = [_mail(str(i), conversation=f"c{i % 3}", minutes=i) for i in range(9)]
    assert [u.key for u in build_units(records)] == [
        u.key for u in build_units(list(reversed(records)))
    ]


# --- prechecks ---------------------------------------------------------------------------


def test_thread_is_discarded_only_when_every_inbound_message_is_noise():
    noisy = build_units([_mail("a", sender="boletin@x.com", to=("lista@x",))])
    assert precheck(noisy[0], RULES) == ("descartado", "ruido:remitente")
    mixed = build_units(
        [
            _mail("a", sender="boletin@x.com", to=("lista@x",)),
            _mail("b", sender="ana@otra.gov.co", minutes=2),
        ]
    )
    assert precheck(mixed[0], RULES) is None


def test_event_without_attendance_evidence_is_not_conclusive():
    (pending,) = build_units([_mail("e", kind="event", status="NotResponded")])
    assert precheck(pending, RULES) == ("no_concluyente", "evento_sin_asistencia")
    (cancelled,) = build_units([_mail("e", kind="event", status="Accepted", cancelled=True)])
    assert precheck(cancelled, RULES) == ("no_concluyente", "evento_cancelado")
    (accepted,) = build_units([_mail("e", kind="event", status="Organizer")])
    assert precheck(accepted, RULES) is None


# --- identifiers and candidates -------------------------------------------------------------


TASKS = [
    TaskEntry(id="T-3", ref="T-3", title="Renovar antivirus", detail="", status="PENDIENTE"),
    TaskEntry(id="T-7", ref="T-7", title="VPN", detail="caso #04567 abierto", status="EN CURSO"),
    TaskEntry(id="T-9", ref="T-9", title="Informe", detail="", status="COMPLETADA"),
]


def test_explicit_ids_and_object_identifiers_force_candidates():
    (unit,) = [
        u
        for u in build_units(
            [_mail("a", subject="Sobre T-09", body="Ver caso 04567", attachments=("T-3.pdf",))]
        )
        if u.kind == "thread"
    ]
    found = unit_identifiers(unit, RULES)
    assert found.task_keys == {"T-9", "T-3"}
    assert found.objects == {"caso": {"4567"}}
    forced = forced_candidates(found, TASKS, RULES)
    assert [(c.ref, c.via) for c in forced] == [
        ("T-3", "id_explicito"),
        ("T-9", "id_explicito"),
        ("T-7", "identificador:caso"),
    ]


def test_unknown_task_id_is_not_a_candidate():
    (unit,) = [u for u in build_units([_mail("a", subject="T-99")]) if u.kind == "thread"]
    assert forced_candidates(unit_identifiers(unit, RULES), TASKS, RULES) == []


def test_ranking_has_fixed_k_and_breaks_ties_by_task_id():
    vectors = {"T-3": [1.0, 0.0], "T-7": [1.0, 0.0], "T-9": [0.0, 1.0]}
    ranked = rank_candidates([], [1.0, 0.0], vectors, TASKS, k=2)
    assert [(c.ref, c.via) for c in ranked] == [("T-3", "similitud"), ("T-7", "similitud")]
    forced = forced_candidates(
        unit_identifiers(build_units([_mail("a", subject="T-9")])[0], RULES), TASKS, RULES
    )
    ranked = rank_candidates(forced, [1.0, 0.0], vectors, TASKS, k=2)
    assert [c.ref for c in ranked] == ["T-9", "T-3"]
    assert rank_candidates(forced, None, {}, TASKS, k=2)[0].via == "id_explicito"


RULES_V2 = compile_rules(
    {
        "version": "2.0.0",
        "buzon": ME,
        "clases": {"cierra": {}, "informativo": {}},
        "ruido": {
            "listas_masivas": {"valores": ["todos@"], "campos": ["to", "cc"]},
            "asunto_seguridad_regex": "phishing",
            "excepciones": {
                "reglas": [
                    {"nombre": "sistema", "remitente": ["avisos-sistema@"]},
                    {"nombre": "resumen", "asunto_regex": "\\bresumen semanal\\b"},
                ]
            },
            "remitentes_automaticos": {"valores": ["reportes@", "microsoft"]},
            "remitentes_lista": {"valores": ["boletin@", "microsoft"]},
            "asunto_masivo_regex": "convocatoria",
        },
        "identificadores": {"tarea": {"regex": "\\bT-\\d{1,3}\\b"}},
    }
)


def test_rules_v2_shape_follows_the_v2_evaluation_order():
    assert RULES_V2.taxonomy == ("cierra", "informativo")
    automatic = _mail("1", sender="reportes@x.com", to=(ME,))
    assert message_noise(automatic, RULES_V2) == "remitente_automatico"
    summary = _mail("2", sender="no-reply@microsoft.com", subject="Resumen semanal", to=(ME,))
    assert message_noise(summary, RULES_V2) is None
    mass_cc = _mail("3", sender="avisos-sistema@x", to=(ME,), cc=("todos@ejemplo.gov.co",))
    assert message_noise(mass_cc, RULES_V2) == "lista_masiva"
    listed = _mail("4", sender="boletin@x", to=("grupo@x",))
    assert message_noise(listed, RULES_V2) == "remitente"
    assert message_noise(_mail("5", sender="boletin@x", to=(ME,)), RULES_V2) is None


# --- E05a: literal subject against the task text (methodology b.4, step 2) ------------------


def test_literal_subject_in_task_text_forces_a_candidate():
    from app.modules.reconciliation.stages import subject_candidates

    tasks = [
        TaskEntry(id="a", ref="T-20", title="Plan de continuidad", observations=""),
        TaskEntry(
            id="b",
            ref="T-21",
            title="Mesa de soporte",
            observations="[Corte 1-sep] Se respondió «Solicitud de acceso a la VPN» | previa",
        ),
        TaskEntry(id="c", ref="T-22", title="Otra", detail="Ver solicitud de acceso a la vpn."),
    ]
    (unit,) = [
        u
        for u in build_units([_mail("a", subject="RE: Solicitud de acceso a la VPN")])
        if u.kind == "thread"
    ]
    found = subject_candidates(unit, tasks, exclude=set(), limit=5)
    assert [(c.ref, c.via) for c in found] == [("T-21", "asunto"), ("T-22", "asunto")]
    assert subject_candidates(unit, tasks, exclude={"b"}, limit=5)[0].ref == "T-22"
    assert len(subject_candidates(unit, tasks, exclude=set(), limit=1)) == 1


def test_short_or_generic_subject_forces_nothing():
    from app.modules.reconciliation.stages import subject_candidates

    tasks = [TaskEntry(id="a", ref="T-1", title="Informe", observations="informe mensual")]
    (unit,) = [u for u in build_units([_mail("a", subject="RV: Informe")]) if u.kind == "thread"]
    assert subject_candidates(unit, tasks, exclude=set(), limit=5) == []
