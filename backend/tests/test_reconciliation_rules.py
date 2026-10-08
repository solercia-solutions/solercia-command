"""E03: versioned classification rules per organization (pure, no DB).

The rules file follows the schema of the methodology's ``reglas.json``
(noise lists, exceptions, mass-mail condition, identifier regexes, matching
order, taxonomy). Every fixture here is SYNTHETIC.
"""

import json
from pathlib import Path

import pytest

from app.modules.reconciliation.rules import (
    EXAMPLE_RULES_PATH,
    RulesError,
    compile_rules,
    load_rules_file,
    load_rules_for_org,
    resolve_rules_path,
)


def _raw(**overrides):
    raw = {
        "version": "1.0.0",
        "buzon": "yo@ejemplo.gov.co",
        "resultados": {"Cierra": {}, "Avanza": {}, "Descartado": {}},
        "ruido": {
            "remitentes_a": {"valores": ["boletin@", "no-reply"]},
            "remitentes_b": {"valores": ["notificaciones@"], "fuente": "x"},
            "asunto_regex_x": "webinar|convocatoria",
            "asunto_regex_x_fuente": "no es una regex",
            "lista_masiva": {"valor": "todos@", "campo": "to"},
            "excepciones": {
                "asunto_seguridad_regex": "phishing|incidente",
                "no_descartar_remitentes": ["avisos@ejemplo.gov.co (comentario)"],
            },
        },
        "identificadores": {
            "tarea": {"regex": "\\bT-\\d{1,3}\\b"},
            "caso": {"regex": "\\bcaso\\s*#?\\s*0*(\\d{5})\\b"},
            "riesgo": {"regex": "\\bR\\d{1,2}\\b", "requiere_contexto": "riesgo|control"},
        },
        "orden_de_cruce": [{"paso": 1, "criterio": "ID explícito"}],
    }
    raw.update(overrides)
    return raw


def test_compiles_noise_lists_from_every_sender_group():
    rules = compile_rules(_raw())
    assert rules.version == "1.0.0"
    assert rules.owner == "yo@ejemplo.gov.co"
    assert set(rules.sender_noise) == {"boletin@", "no-reply", "notificaciones@"}
    assert rules.mass_lists == ("todos@",)
    assert rules.never_discard_senders == ("avisos@ejemplo.gov.co",)
    assert rules.subject_noise.search("Invitación al WEBINAR")
    assert not rules.subject_noise.search("no es una regex")
    assert rules.security_subject.search("Alerta de phishing")
    assert rules.subject_filter_mass_only is True


def test_identifiers_normalize_tokens_and_require_context():
    rules = compile_rules(_raw())
    assert rules.task_keys("Ver t-007 y T-12, no T-1234") == {"T-7", "T-12"}
    caso = next(i for i in rules.identifiers if i.name == "caso")
    assert caso.tokens("respuesta al caso #012345") == {"12345"}
    riesgo = next(i for i in rules.identifiers if i.name == "riesgo")
    assert riesgo.tokens("ajustar R3 del mapa") == set()
    assert riesgo.tokens("control del riesgo R3") == {"R3"}


def test_digest_changes_with_content_and_is_stable():
    first = compile_rules(_raw())
    assert first.digest == compile_rules(_raw()).digest
    assert first.digest != compile_rules(_raw(version="1.0.1")).digest


@pytest.mark.parametrize(
    "broken",
    [
        {"version": "uno"},
        {"identificadores": {"caso": {"regex": "\\d{5}"}}},
        {"identificadores": {"tarea": {"regex": "("}}},
        {"ruido": {"asunto_regex_x": "(sin cerrar"}},
    ],
)
def test_invalid_rules_are_rejected(broken):
    with pytest.raises(RulesError):
        compile_rules(_raw(**broken))


def test_unknown_keys_are_kept_for_forward_compatible_versions():
    rules = compile_rules(_raw(version="2.0.0", seccion_nueva={"a": 1}))
    assert rules.version == "2.0.0"


def test_resolves_a_file_or_a_directory_per_organization(tmp_path: Path):
    single = tmp_path / "reglas.json"
    single.write_text(json.dumps(_raw()), encoding="utf-8")
    assert resolve_rules_path(str(single), "acme") == single

    folder = tmp_path / "orgs"
    folder.mkdir()
    (folder / "acme.json").write_text(json.dumps(_raw(version="3.1.0")), encoding="utf-8")
    assert load_rules_for_org(str(folder), "acme").version == "3.1.0"
    with pytest.raises(RulesError):
        load_rules_for_org(str(folder), "otra")


def test_empty_path_falls_back_to_the_bundled_synthetic_example():
    assert resolve_rules_path("", "acme") == EXAMPLE_RULES_PATH
    rules = load_rules_file(EXAMPLE_RULES_PATH)
    assert rules.owner and rules.owner.endswith("@ejemplo.gov.co")
    assert rules.task_keys("T-05") == {"T-5"}


def test_unreadable_file_is_a_rules_error(tmp_path: Path):
    bad = tmp_path / "x.json"
    bad.write_text("{no json", encoding="utf-8")
    with pytest.raises(RulesError):
        load_rules_file(bad)


def test_taxonomy_maps_methodology_labels_to_the_eight_class_tokens():
    from app.modules.reconciliation.classes import CLASSES, class_token, relation_for

    assert len(CLASSES) == 8
    assert class_token("Solo bitácora") == "solo_bitacora"
    assert class_token("No concluyente") == "no_concluyente"
    assert class_token("Tarea nueva") == "tarea_nueva"
    assert class_token("otra cosa") is None
    rules = compile_rules(_raw())
    assert rules.taxonomy == ("cierra", "avanza", "descartado")
    assert relation_for("avanza", "t1") == "tarea_existente"
    assert relation_for("no_concluyente", None) == "irrelevante"
    assert relation_for("tarea_nueva", None) == "tarea_nueva"
    assert relation_for("informativo", "t1") == "irrelevante"


def test_loads_the_real_methodology_rules_when_available():
    real = Path.home() / "Proyectos/SOLERCIA/evaluaciones/reglas.json"
    if not real.exists():
        pytest.skip("reglas.json de la metodología no disponible en este equipo")
    rules = load_rules_file(real)
    assert rules.sender_noise and rules.mass_lists and rules.task_identifier
