"""Sink that records instead of sending. Used by tests and by the demo, where
a live Jira write would be noise."""
from aiops.decision import Decision
from aiops.registry import Sink, register


@register("dryrun")
class DryRunSink(Sink):
    def __init__(self):
        self.sent: list[Decision] = []

    def emit(self, decision: Decision) -> str | None:
        self.sent.append(decision)
        return None
