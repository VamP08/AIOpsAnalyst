"""Prompt for cluster-level triage. Version-stamped: every stored verdict
records PROMPT_VERSION, so an eval number is always tied to the exact rubric
that produced it. The system turn is identical for every cluster (cacheable
prefix); everything cluster-specific goes in the user turn.
"""
from aiops.envelope import Event
from aiops.triage.schema import CATEGORIES, SEVERITIES

PROMPT_VERSION = "1.0"

_SYSTEM = f"""You are a triage analyst. You are given one CLUSTER of similar \
events from a production system (log template, GitHub issues, or alerts) with \
a few representative samples. Classify the cluster.

Reply with ONLY a JSON object:
{{"category": one of {list(CATEGORIES)},
 "severity": one of {list(SEVERITIES)},
 "summary": one sentence, plain language, max 200 chars,
 "confidence": 0.0-1.0, your honest probability that category is right,
 "evidence": list of the sample event ids that best support your call}}

Category guide: crash = process/service dies or fails to start; error = \
operation fails but service lives; performance = slow, timeout, resource \
exhaustion; feature_request = ask for new behavior; question = ask for help \
or information; noise = routine chatter, no action needed.
Severity guide: critical = outage or data loss now; high = user-facing \
failure; medium = degraded or risky; low = cosmetic or informational.
Do not guess high confidence: if samples are ambiguous, say so with a lower \
number."""


def build_messages(label: str, tier: str, samples: list[Event]) -> list[dict]:
    lines = [f"Cluster tier: {tier}", f"Cluster label: {label}",
             f"Sample events ({len(samples)}):"]
    for event in samples:
        lines.append(f"- id={event.id} | {event.title}")
        if event.body:
            lines.append(f"  {event.body[:400]}")
    return [{"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n".join(lines)}]
