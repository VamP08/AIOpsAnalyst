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
