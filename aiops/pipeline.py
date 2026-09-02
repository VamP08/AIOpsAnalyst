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

    def cluster(self, prose_encoder=None) -> dict[str, int]:
        """Recluster the whole corpus. Stateless and deterministic — a rerun
        assigns identical ids, so this is safe to call after every ingest.
        # ponytail: O(corpus) per run; switch to drain3 persistence + inference
        # mode if the corpus outgrows a laptop
        """
        from aiops.cluster.drain import LogClusterer
        from aiops.cluster.prose import ProseClusterer

        events = self.store.all_events()
        log_events = [e for e in events if e.type == "dev.aiops.log.line"]
        prose_events = [e for e in events if e.type == "com.github.issue"]

        counts: dict[str, int] = {}
        assignment: dict[str, str] = {}
        clusters: dict[str, tuple[str, str]] = {}

        if log_events:
            clusterer = LogClusterer()
            assignment.update(clusterer.assign(log_events))
            for cid, template, _ in clusterer.clusters():
                clusters[cid] = (template, "log")
            counts["log"] = len(log_events)

        if prose_events:
            prose_assignment = ProseClusterer(
                encoder=prose_encoder).assign(prose_events)
            assignment.update(prose_assignment)
            for event in prose_events:  # first title labels the cluster
                clusters.setdefault(prose_assignment[event.id],
                                    (event.title, "prose"))
            counts["prose"] = len(prose_events)

        self.store.assign_clusters(assignment, clusters)
        return counts

    def triage(self, chat=None, samples_per_cluster: int = 5) -> dict[str, int]:
        """One LLM call per un-triaged cluster, never per event. Malformed or
        missing replies leave the cluster untriaged — retried next run, never
        stored as a guess.
        """
        from aiops.triage.gate import decide_tier
        from aiops.triage.prompts import PROMPT_VERSION, build_messages
        from aiops.triage.schema import parse_verdict

        if chat is None:
            from aiops.envfile import load_env
            from aiops.triage.llm import chat
            load_env()

        triaged = failed = 0
        for cluster in self.store.clusters_without_verdict():
            events = self.store.events_in_cluster(cluster["id"],
                                                  samples_per_cluster)
            reply = chat(build_messages(cluster["label"], cluster["tier"],
                                        events))
            verdict = parse_verdict(reply.text) if reply else None
            if verdict is None:
                failed += 1
                continue
            self.store.upsert_verdict(cluster["id"], {
                **verdict.model_dump(),
                "tier": decide_tier(verdict),
                "model": reply.model,
                "promptversion": PROMPT_VERSION,
            })
            triaged += 1
        return {"triaged": triaged, "failed": failed}
