import pytest

from aiops.triage.gate import decide_tier, explain
from aiops.triage.schema import SEVERITIES, Verdict


def verdict(category="error", severity="medium", confidence=0.8):
    return Verdict(category=category, severity=severity,
                   summary="s", confidence=confidence, evidence=[])


@pytest.mark.parametrize("confidence,severity,expected", [
    (0.95, "medium", "auto"),
    (0.90, "low", "auto"),
    (0.80, "medium", "suggest"),
    (0.70, "low", "suggest"),
    (0.50, "high", "escalate"),
    (0.30, "low", "abstain"),
])
def test_tiers_from_confidence_and_severity(confidence, severity, expected):
    assert decide_tier(verdict(severity=severity,
                               confidence=confidence)) == expected


def test_critical_always_escalates_even_at_high_confidence():
    assert decide_tier(verdict(severity="critical", confidence=0.99)) == "escalate"


def test_rules_are_deterministic_config_not_model_output():
    v = verdict(confidence=0.90)
    assert decide_tier(v) == decide_tier(v) == "auto"


def test_explain_names_the_rule_that_decided_the_tier():
    assert explain(verdict(severity="critical", confidence=0.99)) == (
        "critical severity escalates whatever the confidence")
    assert explain(verdict(confidence=0.95)) == (
        "confidence 0.95 is at or above the 0.9 auto threshold")
    assert explain(verdict(confidence=0.78)) == (
        "confidence 0.78 is below the 0.9 auto threshold")
    assert explain(verdict(severity="high", confidence=0.4)) == (
        "confidence 0.40 is below 0.7 and the severity is high")
    assert explain(verdict(severity="low", confidence=0.4)) == (
        "confidence 0.40 is below 0.7 and nothing forces a human to look")


def test_every_tier_has_an_explanation():
    for severity in SEVERITIES:
        for confidence in (0.99, 0.8, 0.5):
            reason = explain(verdict(severity=severity, confidence=confidence))
            assert reason and isinstance(reason, str)


def test_policy_lists_the_rules_in_the_order_the_gate_applies_them():
    from aiops.triage.gate import policy
    rows = policy()
    assert [r["tier"] for r in rows] == [
        "escalate", "auto", "suggest", "escalate", "abstain"]
    assert rows[0]["condition"] == "severity is critical"
    assert rows[1]["condition"] == "confidence at or above 0.9"


def test_policy_row_that_matches_first_is_the_tier_decided():
    from aiops.triage.gate import matching_rule, policy
    rows = policy()
    for severity in SEVERITIES:
        for confidence in (0.99, 0.9, 0.8, 0.7, 0.5):
            v = verdict(severity=severity, confidence=confidence)
            assert rows[matching_rule(v)]["tier"] == decide_tier(v)
