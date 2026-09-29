"""Prompt for cluster-level triage. Version-stamped: every stored verdict
records PROMPT_VERSION, so an eval number is always tied to the exact rubric
that produced it. The system turn is identical for every cluster (cacheable
prefix); everything cluster-specific goes in the user turn.
"""
from aiops.envelope import Event
from aiops.textclean import strip_boilerplate
from aiops.triage.schema import CATEGORIES, SEVERITIES

# 1.1: issue-template boilerplate stripped from bodies. In use.
# 1.2: three boundary rules written against the dev half of the labelled set.
#      It won its held-out half (0.604-0.764 across three runs, against
#      0.565-0.584 for 1.1) and was still rejected: it cost alert recall on
#      logs, dropped ask hit@1 from 0.90 to 0.80, and stopped using the
#      critical severity altogether, which silences the one gate rule that
#      ignores confidence. Kept here so both numbers can be reproduced.
PROMPT_VERSION = "1.1"
CANDIDATE_VERSION = "1.2"

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


# 1.2 adds three boundary rules, each written against a disagreement in the dev
# half of the labelled set and none from the test half. They clarify the rubric
# rather than push a number: an issue a person filed is never routine chatter,
# a question that reports broken behaviour is still that broken behaviour, and
# "it does not do X today" is a fault even when it is phrased as a wish.
_BOUNDARIES = """
Boundary rules, in this order:
1. An issue a person filed is never noise. Use noise only for machine chatter in logs that no one would act on.
2. A report that behaviour differs from what is documented or promised is a crash or an error, even when it is worded as a question. Use question only when nothing is claimed to be broken and the writer only wants information.
3. "X does not work", "X is missing", "X should already do Y" describe a fault in what exists, so they are crash or error even when phrased as a wish. Use feature_request only for capability that plainly does not exist yet and is being asked for.
"""

_SYSTEM_12 = _SYSTEM.replace(
    "Do not guess high confidence:",
    _BOUNDARIES.strip() + chr(10) + "Do not guess high confidence:")

SYSTEMS = {"1.1": _SYSTEM, "1.2": _SYSTEM_12}


def build_messages(label: str, tier: str, samples: list[Event],
                   version: str = PROMPT_VERSION) -> list[dict]:
    lines = [f"Cluster tier: {tier}", f"Cluster label: {label}",
             f"Sample events ({len(samples)}):"]
    for event in samples:
        lines.append(f"- id={event.id} | {event.title}")
        if event.body:
            lines.append(f"  {strip_boilerplate(event.body)[:400]}")
    return [{"role": "system", "content": SYSTEMS[version]},
            {"role": "user", "content": "\n".join(lines)}]
