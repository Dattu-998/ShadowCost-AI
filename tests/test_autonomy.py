import pytest

from shadowcost.autonomy import PromotionPolicy, Stage, evaluate, wilson_lower_bound


def test_wilson_lower_bound_is_conservative():
    assert wilson_lower_bound(0, 0) == 0.0
    # A perfect 10/10 is far less convincing than a perfect 100/100.
    assert wilson_lower_bound(10, 10) < 0.75
    assert wilson_lower_bound(100, 100) > 0.96
    assert wilson_lower_bound(30, 30) == pytest.approx(0.886, abs=1e-3)


def test_holds_until_enough_cases():
    decision = evaluate(Stage.SHADOW, [True] * 29)
    assert decision.action == "hold"
    assert decision.next == Stage.SHADOW
    assert "1 more case" in decision.reason


def test_promotes_one_stage_with_strong_evidence():
    decision = evaluate(Stage.SHADOW, [True] * 30)
    assert decision.action == "promote"
    assert decision.next == Stage.DRAFT


def test_holds_when_agreement_is_good_but_not_convincing():
    # 26/30 = 87% agreement, but the lower bound is only ~0.70.
    decision = evaluate(Stage.DRAFT, [True] * 26 + [False] * 4)
    assert decision.action == "hold"
    assert decision.next == Stage.DRAFT


def test_demotes_one_stage_when_recent_agreement_drops():
    decision = evaluate(Stage.APPROVAL, [True] * 6 + [False] * 4)
    assert decision.action == "demote"
    assert decision.next == Stage.DRAFT


def test_does_not_demote_on_too_few_cases():
    decision = evaluate(Stage.APPROVAL, [False] * 3)
    assert decision.action == "hold"


def test_critical_failure_returns_to_shadow():
    decision = evaluate(Stage.AUTONOMOUS, [True] * 50, critical_failure=True)
    assert decision.action == "demote"
    assert decision.next == Stage.SHADOW


def test_autonomous_is_the_top_stage():
    decision = evaluate(Stage.AUTONOMOUS, [True] * 50)
    assert decision.action == "hold"
    assert decision.next == Stage.AUTONOMOUS


def test_only_recent_window_counts():
    # Early failures fall outside the window once enough good cases accumulate.
    policy = PromotionPolicy(window=40)
    decision = evaluate(Stage.SHADOW, [False] * 20 + [True] * 40, policy)
    assert decision.n == 40
    assert decision.action == "promote"
