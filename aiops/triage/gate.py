"""Confidence gate: the model classifies, these rules act (Zendesk lesson).

Deterministic and config-owned — no LLM output reaches a sink without passing
through this table. Critical severity always goes to a human regardless of
confidence: paging is cheap, a wrong auto-action on an outage is not.
"""
from dataclasses import dataclass

from aiops.triage.schema import Verdict


@dataclass(frozen=True)
class Thresholds:
    auto: float = 0.9
    suggest: float = 0.7


def explain(verdict: Verdict, thresholds: Thresholds = Thresholds()) -> str:
    """Why this verdict landed in its tier, in the words of the rule that
    decided it. The gate is the part a reader is entitled to audit, so it says
    what it did rather than leaving the reader to infer it from two numbers."""
    if verdict.severity == "critical":
        return "critical severity escalates whatever the confidence"
    if verdict.confidence >= thresholds.auto:
        return (f"confidence {verdict.confidence:.2f} is at or above the "
                f"{thresholds.auto} auto threshold")
    if verdict.confidence >= thresholds.suggest:
        return (f"confidence {verdict.confidence:.2f} is below the "
                f"{thresholds.auto} auto threshold")
    if verdict.severity == "high":
        return (f"confidence {verdict.confidence:.2f} is below "
                f"{thresholds.suggest} and the severity is high")
    return (f"confidence {verdict.confidence:.2f} is below "
            f"{thresholds.suggest} and nothing forces a human to look")


def _rules(t: Thresholds) -> list[tuple[str, object, str]]:
    """First match wins. Held as a table so the demo can print the rules the
    gate actually runs rather than a hand-copied description of them."""
    return [
        ("severity is critical", lambda v: v.severity == "critical",
         "escalate"),
        (f"confidence at or above {t.auto}", lambda v: v.confidence >= t.auto,
         "auto"),
        (f"confidence at or above {t.suggest}",
         lambda v: v.confidence >= t.suggest, "suggest"),
        ("severity is high", lambda v: v.severity == "high", "escalate"),
        ("anything else", lambda v: True, "abstain"),
    ]


def policy(thresholds: Thresholds = Thresholds()) -> list[dict]:
    return [{"condition": condition, "tier": tier}
            for condition, _, tier in _rules(thresholds)]


def matching_rule(verdict: Verdict, thresholds: Thresholds = Thresholds()) -> int:
    return next(i for i, (_, when, _) in enumerate(_rules(thresholds))
                if when(verdict))


def decide_tier(verdict: Verdict, thresholds: Thresholds = Thresholds()) -> str:
    return _rules(thresholds)[matching_rule(verdict, thresholds)][2]
