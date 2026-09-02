"""Tier-2 clustering: Drain3 template mining over log lines.

Drain recovers the printf behind the output: tokens that vary across lines of
one template become <*>. Deterministic for a given corpus order, no training.
Cluster ids are the miner's own numeric ids prefixed "log-", stable across
fresh runs on the same corpus.
"""
import logging

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from aiops.envelope import Event

logging.getLogger("drain3").setLevel(logging.WARNING)


class LogClusterer:
    def __init__(self):
        config = TemplateMinerConfig()
        config.profiling_enabled = False
        self.miner = TemplateMiner(config=config)
        self.sizes: dict[str, int] = {}

    def assign(self, events: list[Event]) -> dict[str, str]:
        assignment = {}
        for event in events:
            result = self.miner.add_log_message(event.title)
            cluster_id = f"log-{result['cluster_id']}"
            assignment[event.id] = cluster_id
            self.sizes[cluster_id] = self.sizes.get(cluster_id, 0) + 1
        return assignment

    def clusters(self) -> list[tuple[str, str, int]]:
        return [(f"log-{c.cluster_id}", c.get_template(),
                 self.sizes.get(f"log-{c.cluster_id}", 0))
                for c in self.miner.drain.clusters]
