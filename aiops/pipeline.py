"""Wires configured adapters to the store.

pipeline.yaml names adapter instances; each instance id keys its own cursor in
the store, so any number of runs — cron, CLI, tests — resume where the last one
stopped. Import of aiops.sources/aiops.sinks populates the registries.
"""
import yaml

import aiops.sources.github_issues  # noqa: F401  (registers adapter)
import aiops.sources.log_file  # noqa: F401
from aiops.registry import create
from aiops.store import Store


class Pipeline:
    def __init__(self, store: Store, sources: list[dict]):
        self.store = store
        self.sources = sources

    @classmethod
    def from_yaml(cls, path: str) -> "Pipeline":
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(Store(config["store"]), config.get("sources", []))

    def ingest(self) -> dict[str, int]:
        inserted = {}
        for entry in self.sources:
            instance = entry["id"]
            adapter = create(entry["adapter"], entry.get("config", {}))
            events = adapter.fetch(cursor=self.store.get_cursor(instance))
            inserted[instance] = self.store.insert_events(events)
            if adapter.cursor is not None:
                self.store.set_cursor(instance, adapter.cursor)
        return inserted
