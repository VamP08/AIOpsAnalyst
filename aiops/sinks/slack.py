"""Slack incoming webhook. Free on every plan, one message per second."""
import os

import httpx

from aiops.decision import Decision
from aiops.registry import Sink, register


@register("slack")
class SlackSink(Sink):
    def __init__(self, webhook: str | None = None,
                 client: httpx.Client | None = None):
        self.webhook = webhook or os.environ.get("SLACK_WEBHOOK_URL", "")
        self.client = client or httpx.Client(timeout=30)

    def check(self) -> bool:
        return bool(self.webhook)

    def emit(self, decision: Decision) -> str | None:
        text = "\n".join([
            f"*{decision.category}* / {decision.severity} "
            f"— {decision.summary}",
            f"cluster `{decision.cluster_id}` · {decision.size} events · "
            f"confidence {decision.confidence:.2f} · tier {decision.tier}",
            f"```{decision.label}```",
            *decision.evidence_lines(),
        ])
        r = self.client.post(self.webhook, json={"text": text})
        r.raise_for_status()
        return None
