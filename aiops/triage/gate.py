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


def decide_tier(verdict: Verdict, thresholds: Thresholds = Thresholds()) -> str:
    if verdict.severity == "critical":
        return "escalate"
    if verdict.confidence >= thresholds.auto:
        return "auto"
    if verdict.confidence >= thresholds.suggest:
        return "suggest"
    if verdict.severity == "high":
        return "escalate"
    return "abstain"
