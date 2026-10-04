"""Wires configured adapters to the store.

pipeline.yaml names adapter instances; each instance id keys its own cursor in
the store, so any number of runs — cron, CLI, tests — resume where the last one
stopped. Import of aiops.sources/aiops.sinks populates the registries.
"""
import yaml

import aiops.sinks.dryrun  # noqa: F401
import aiops.sinks.jira  # noqa: F401
import aiops.sinks.slack  # noqa: F401
import aiops.sources.github_actions  # noqa: F401
import aiops.sources.github_issues  # noqa: F401  (registers adapter)
import aiops.sources.log_file  # noqa: F401
import aiops.sources.statuspage  # noqa: F401
from aiops.registry import create
from aiops.store import Store


class Pipeline:
    def __init__(self, store: Store, sources: list[dict],
                 sinks: list[dict] | None = None,
                 routes: list[dict] | None = None):
        self.store = store
        self.sources = sources
        self.sink_configs = sinks or []
        self.routes = routes or []

    @classmethod
    def from_yaml(cls, path: str) -> "Pipeline":
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return cls(Store(config["store"]), config.get("sources", []),
                   config.get("sinks"), config.get("routes"))

    def ingest(self) -> dict[str, int | str]:
        """One flaky source must not block the rest. A failed source inserts
        nothing and keeps no cursor, so its next run is a clean full retry."""
        result: dict[str, int | str] = {}
        for entry in self.sources:
            instance = entry["id"]
            try:
                adapter = create(entry["adapter"], entry.get("config", {}))
                events = adapter.fetch(cursor=self.store.get_cursor(instance))
                result[instance] = self.store.insert_events(events)
                if adapter.cursor is not None:
                    self.store.set_cursor(instance, adapter.cursor)
            except Exception as e:
                result[instance] = f"{type(e).__name__}: {e}"
        return result

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
        # anything a person or a status page wrote, rather than a program
        prose_events = [e for e in events if e.type != "dev.aiops.log.line"]

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
        self.store.prune_clusters(clusters)
        return counts

    def triage(self, chat=None, samples_per_cluster: int = 5,
               pause: float = 0.0) -> dict[str, int]:
        """One LLM call per un-triaged cluster, never per event. Malformed or
        missing replies leave the cluster untriaged — retried next run, never
        stored as a guess. `pause` sleeps between calls so a batch stays under
        free-tier tokens-per-minute limits; calling triage again is the retry.
        """
        import time
        from aiops.triage.gate import decide_tier
        from aiops.triage.prompts import PROMPT_VERSION, build_messages
        from aiops.triage.schema import parse_verdict

        if chat is None:
            from aiops.envfile import load_env
            from aiops.triage.llm import chat
            load_env()

        triaged = failed = 0
        for n, cluster in enumerate(self.store.clusters_without_verdict()):
            if pause and n:
                time.sleep(pause)
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

    def _build_sinks(self) -> dict:
        return {entry["id"]: create(entry["adapter"], entry.get("config", {}))
                for entry in self.sink_configs}

    def _sinks_for(self, verdict: dict) -> list[str]:
        """Deterministic policy: the model supplied the labels, these rules
        decide what happens. A route with no categories matches any."""
        return [route["sink"] for route in self.routes
                if verdict["tier"] in route["tiers"]
                and verdict["category"] in route.get("categories",
                                                     [verdict["category"]])]

    def route(self, sinks: dict | None = None, samples_per_cluster: int = 3,
              limit: int | None = None,
              only: set[str] | None = None) -> dict[str, int | str]:
        """Emit every verdict that a route matches and that has not already
        been emitted to that sink. Side effects are recorded only on success,
        so a sink that is down costs a retry rather than a duplicate ticket.

        limit caps how many emits one run may perform - blast radius for a
        first run against a real tracker, and what stops a backfill of a large
        corpus from opening hundreds of tickets at once. The rest follow on the
        next run, because what was sent is recorded.

        only restricts the run to the named clusters - the policy still
        decides whether each of them is emitted at all.
        """
        from aiops.decision import Decision

        sinks = sinks if sinks is not None else self._build_sinks()
        sent: dict[str, int] = {}
        failed: dict[str, int] = {}
        for cluster in self.store.list_clusters():
            if only is not None and cluster["id"] not in only:
                continue
            verdict = self.store.get_verdict(cluster["id"])
            if not verdict:
                continue
            already = self.store.routed(cluster["id"])
            for name in self._sinks_for(verdict):
                if name in already or name not in sinks:
                    continue
                decision = Decision(
                    cluster_id=cluster["id"], label=cluster["label"],
                    tier=verdict["tier"], category=verdict["category"],
                    severity=verdict["severity"], summary=verdict["summary"],
                    confidence=verdict["confidence"], size=cluster["size"],
                    evidence=self.store.events_in_cluster(
                        cluster["id"], samples_per_cluster))
                try:
                    ref = sinks[name].emit(decision)
                except Exception:
                    failed[name] = failed.get(name, 0) + 1
                    continue
                self.store.record_routed(cluster["id"], name, ref)
                sent[name] = sent.get(name, 0) + 1
                if limit is not None and sum(sent.values()) >= limit:
                    return {**sent, **{n: f"{c} failed"
                                       for n, c in failed.items()}}
        return {**sent, **{name: f"{n} failed" for name, n in failed.items()}}
