import pytest

from aiops.triage.agreement import cohens_kappa


def test_perfect_agreement_is_one():
    a = ["crash", "error", "noise", "crash"]
    b = ["crash", "error", "noise", "crash"]
    assert cohens_kappa(a, b) == 1.0


def test_no_agreement_beyond_chance_is_zero():
    # observed agreement equals chance agreement exactly
    a = ["x", "x", "y", "y"]
    b = ["x", "y", "x", "y"]
    assert cohens_kappa(a, b) == pytest.approx(0.0)


def test_known_hand_computed_value():
    # 2x2: po=(25+45)/100=0.70, marginals 40/60 both raters,
    # pe=0.4*0.4+0.6*0.6=0.52, kappa=(0.70-0.52)/0.48=0.375
    a = ["yes"] * 25 + ["yes"] * 15 + ["no"] * 15 + ["no"] * 45
    b = ["yes"] * 25 + ["no"] * 15 + ["yes"] * 15 + ["no"] * 45
    assert cohens_kappa(a, b) == pytest.approx(0.375)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        cohens_kappa(["a"], ["a", "b"])


def test_all_one_category_by_both_raters_is_one():
    # degenerate case: pe=1, po=1 -> define as 1.0 agreement, not 0/0
    assert cohens_kappa(["x", "x"], ["x", "x"]) == 1.0


def test_bootstrap_ci_brackets_the_point_estimate():
    from aiops.triage.agreement import kappa_ci
    human = ["defect"] * 20 + ["feature_request"] * 10
    model = ["defect"] * 18 + ["feature_request"] * 2 + \
            ["feature_request"] * 8 + ["defect"] * 2
    point = cohens_kappa(human, model)
    low, high = kappa_ci(human, model, seed=7)
    assert low < point < high
    assert 0.0 <= low and high <= 1.0


def test_bootstrap_ci_is_reproducible_from_the_seed():
    human = ["defect"] * 15 + ["question"] * 5
    model = ["defect"] * 14 + ["question"] * 6
    assert kappa_ci_call(human, model) == kappa_ci_call(human, model)


def kappa_ci_call(human, model):
    from aiops.triage.agreement import kappa_ci
    return kappa_ci(human, model, seed=11)


def test_wider_interval_for_fewer_pairs():
    from aiops.triage.agreement import kappa_ci
    human_small = ["defect"] * 6 + ["question"] * 4
    model_small = ["defect"] * 5 + ["question"] * 5
    human_big = human_small * 10
    model_big = model_small * 10
    small = kappa_ci(human_small, model_small, seed=3)
    big = kappa_ci(human_big, model_big, seed=3)
    assert (small[1] - small[0]) > (big[1] - big[0])
