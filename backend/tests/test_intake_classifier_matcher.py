"""RED tests for the pure ``RuleBasedClassifier`` matcher (change
22-intake-classifier, tasks.md T3.7) — NO database, NO HTTP: every
``IntakeItem``/``IntakeRule`` here is an unpersisted Python object.
"""

import uuid

from app.modules.intake.classifier import RuleBasedClassifier
from app.modules.intake.models import IntakeItem, IntakeRule


def _item(**overrides) -> IntakeItem:
    defaults = dict(
        organization_id=uuid.uuid4(),
        source_provider="microsoft365",
        connector_id=uuid.uuid4(),
        item_type="email",
        external_id="ext-1",
        title="Incidente de seguridad detectado",
        snippet="Se detectó un acceso no autorizado.",
        origin_actor="alertas@Proveedor-X.com",
        raw_payload={},
    )
    defaults.update(overrides)
    return IntakeItem(**defaults)


def _rule(**overrides) -> IntakeRule:
    defaults = dict(
        organization_id=uuid.uuid4(),
        name="Regla de prueba",
        criteria=[{"field": "origin_actor", "operator": "contains", "value": "proveedor-x.com"}],
        convert_to_task=True,
        task_priority="medium",
        rule_order=1,
        is_active=True,
    )
    defaults.update(overrides)
    return IntakeRule(**defaults)


def test_matcher_folds_accents_and_case() -> None:
    """Folding sin tildes + case-insensitive: 'PROVEEDOR-X.COM' casa contra
    'proveedor-x.com' aunque el ítem tenga mayúsculas."""

    item = _item(origin_actor="Contacto@PROVEEDOR-X.com")
    rule = _rule(
        criteria=[{"field": "domain", "operator": "equals", "value": "proveedor-x.com"}]
    )

    result = RuleBasedClassifier().classify(item, [rule])

    assert result is rule


def test_matcher_folds_accents_in_title() -> None:
    """Un criterio con tilde casa contra un título sin tilde y viceversa."""

    item = _item(title="Cronograma de migración")
    rule = _rule(
        criteria=[{"field": "title", "operator": "contains", "value": "migracion"}]
    )

    result = RuleBasedClassifier().classify(item, [rule])

    assert result is rule


def test_two_matching_rules_lower_rule_order_wins() -> None:
    """Dos reglas casan → gana la de menor `rule_order` (intake-rules spec,
    'Precedencia determinista por orden de regla')."""

    item = _item()
    rule_order_2 = _rule(
        name="Regla orden 2",
        rule_order=2,
        criteria=[{"field": "source_provider", "operator": "equals", "value": "microsoft365"}],
    )
    rule_order_1 = _rule(
        name="Regla orden 1",
        rule_order=1,
        criteria=[{"field": "source_provider", "operator": "equals", "value": "microsoft365"}],
    )

    # Caller passes rules ORDERED by rule_order ascending (design.md contract).
    result = RuleBasedClassifier().classify(item, [rule_order_1, rule_order_2])

    assert result is rule_order_1


def test_inactive_rule_never_competes_even_if_it_would_match() -> None:
    """Regla inactiva no compite aunque casaría (intake-rules spec, 'Reglas
    inactivas excluidas de la evaluación') — la siguiente activa gana."""

    item = _item()
    inactive_rule = _rule(
        name="Regla inactiva",
        rule_order=1,
        is_active=False,
        criteria=[{"field": "source_provider", "operator": "equals", "value": "microsoft365"}],
    )
    active_rule = _rule(
        name="Regla activa",
        rule_order=2,
        is_active=True,
        criteria=[{"field": "source_provider", "operator": "equals", "value": "microsoft365"}],
    )

    result = RuleBasedClassifier().classify(item, [inactive_rule, active_rule])

    assert result is active_rule


def test_rule_without_target_project_id_still_matches_default_contract() -> None:
    """Una regla activa con `target_project_id=None` que casa se retorna
    igual — el contrato "usar el proyecto por defecto" lo interpreta el
    caller (Fase 4), el matcher no exige el campo."""

    item = _item()
    rule = _rule(target_project_id=None)

    result = RuleBasedClassifier().classify(item, [rule])

    assert result is rule
    assert result.target_project_id is None


def test_rule_with_two_and_conditions_requires_both_to_match() -> None:
    """Dos condiciones AND: solo casa si AMBAS se cumplen (intake-rules
    spec, 'Regla con dos condiciones — solo casa si ambas se cumplen')."""

    item = _item(source_provider="microsoft365", title="Incidente de red")
    rule = _rule(
        criteria=[
            {"field": "source_provider", "operator": "equals", "value": "microsoft365"},
            {"field": "title", "operator": "contains", "value": "incidente"},
        ]
    )

    assert RuleBasedClassifier().classify(item, [rule]) is rule

    # Only ONE of the two conditions holds now -> the rule must NOT match.
    partial_item = _item(source_provider="google", title="Incidente de red")
    assert RuleBasedClassifier().classify(partial_item, [rule]) is None


def test_no_rule_matches_returns_none() -> None:
    """Sin regla coincidente, `classify` retorna `None` (triage)."""

    item = _item(source_provider="google")
    rule = _rule(
        criteria=[{"field": "source_provider", "operator": "equals", "value": "microsoft365"}]
    )

    assert RuleBasedClassifier().classify(item, [rule]) is None
