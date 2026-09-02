import pytest

from aiops.triage.gate import decide_tier
from aiops.triage.schema import Verdict


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
