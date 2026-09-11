"""Tier-2 clustering: Drain3 template mining over log lines.

Drain recovers the printf behind the output: tokens that vary across lines of
one template become <*>. Deterministic for a given corpus order, no training.

Cluster ids hash the earliest event that landed in the cluster rather than
Drain's own counter: a recluster after new events arrive must not renumber
existing clusters, or every stored verdict reattaches to the wrong cluster.
"""
import hashlib
import logging

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from aiops.envelope import Event

logging.getLogger("drain3").setLevel(logging.WARNING)


def cluster_id(prefix: str, first_event_id: str) -> str:
    digest = hashlib.sha256(first_event_id.encode()).hexdigest()[:12]
    return f"{prefix}-{digest}"


class LogClusterer:
    def __init__(self):
        config = TemplateMinerConfig()
        config.profiling_enabled = False
        self.miner = TemplateMiner(config=config)
        self.first_event: dict[int, str] = {}   # drain id -> earliest event id
        self.sizes: dict[str, int] = {}

    def _id(self, drain_id: int) -> str:
        return cluster_id("log", self.first_event[drain_id])

    def assign(self, events: list[Event]) -> dict[str, str]:
        assignment = {}
        for event in events:
            drain_id = self.miner.add_log_message(event.title)["cluster_id"]
            self.first_event.setdefault(drain_id, event.id)
            cid = self._id(drain_id)
            assignment[event.id] = cid
            self.sizes[cid] = self.sizes.get(cid, 0) + 1
        return assignment

    def clusters(self) -> list[tuple[str, str, int]]:
        return [(self._id(c.cluster_id), c.get_template(),
                 self.sizes.get(self._id(c.cluster_id), 0))
                for c in self.miner.drain.clusters
                if c.cluster_id in self.first_event]
