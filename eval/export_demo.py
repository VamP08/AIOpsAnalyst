"""Freeze the store into the JSON the site reads.

The site is static on purpose: a free web service that sleeps takes
about a minute to wake, and a minute of blank page is the whole visit. So the
page ships precomputed results and loads instantly, and the live API is a
progressive enhancement the first impression never depends on.

Writes into demo/public/data/:
  stats.json       headline counters
  clusters.json    every cluster with its verdict and any ticket it produced
  scorecards.json  both published evaluations, verbatim
  specimens.json   a few real events followed from input to what happened
  policy.json      the gate's rules and the routes, as the code runs them

Usage: python eval/export_demo.py eval/labeling.sqlite demo/public/data [pipeline.yaml]
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store

# Chosen by hand after triage, one per kind of source and chosen so that they
# end differently: a ticket, a person told, a deliberate abstention.
SPECIMENS = [
    "prose-6d0df478cbdd",   # pytorch issue, torch.compile crash -> ticket
    "prose-9b77d6d34138",   # vscode CI, 17 failed runs of one step -> ticket
    "prose-8fef10e7acc9",   # Cloudflare incident, Durable Objects -> ticket
    "log-128241b27e0d",     # Linux OOM killer, critical -> a person
    "prose-4f2e9cb03091",   # vscode issue titled "NA" -> abstain
]


_KIND = {"com.github.issue": "issue", "com.github.workflow_run": "ci",
         "com.statuspage.incident": "status"}


def kind(event_type: str, source: str) -> str:
    """What a reader would call the source, not what the envelope calls it."""
    if event_type in _KIND:
        return _KIND[event_type]
    return "supercomputer" if source.startswith("bgl://") else "log"


_TIER_OUTCOME = {"escalate": "person", "suggest": "draft", "abstain": "unsure"}


def events_by_kind(store: Store) -> dict[str, int]:
    """How many events arrived from each kind of source, before any grouping."""
    counts: Counter = Counter()
    for event_type, source, n in store.db.execute(
            "SELECT type, source, COUNT(*) FROM events GROUP BY type, source"):
        counts[kind(event_type, source)] += n
    return dict(counts)


def outcome(row: dict, policy) -> str:
    """Which of the five bins a cluster ends in. Only auto-tier verdicts are
    routed, so the tier decides everything except ticket versus dropped."""
    if row["tier"] in _TIER_OUTCOME:
        return _TIER_OUTCOME[row["tier"]]
    return "ticket" if policy._sinks_for(row) else "dropped"


def clip(text: str, limit: int = 300) -> str:
    """At most `limit` characters, cut at a word and marked as cut, so a page never stops mid-word."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(None, 1)[0].rstrip(" ,;:.") + "\u2026"


def specimen(store: Store, cluster_id: str) -> dict:
    """One real event, followed through: what came in, what it was grouped
    with, what the model said, which rule decided, and what that caused."""
    from aiops.sinks.jira import ISSUE_TYPES, summary_line
    from aiops.textclean import strip_boilerplate
    from aiops.triage.gate import explain, matching_rule
    from aiops.triage.schema import Verdict

    cluster = next(c for c in store.list_clusters() if c["id"] == cluster_id)
    first, *siblings = store.events_in_cluster(cluster_id, 4)
    v = store.get_verdict(cluster_id)
    verdict = Verdict(category=v["category"], severity=v["severity"],
                      summary=v["summary"], confidence=v["confidence"],
                      evidence=[])
    key = store.routed(cluster_id).get("tickets") or None
    return {
        "input": {"source": first.source, "type": first.type,
                  "kind": kind(first.type, first.source),
                  "subject": first.subject, "time": first.time,
                  "title": first.title, "url": first.url,
                  "body": clip(strip_boilerplate(first.body or first.raw or ""))},
        "cluster": {"id": cluster_id, "label": cluster["label"],
                    "size": cluster["size"],
                    "siblings": [e.title for e in siblings]},
        "verdict": {"category": v["category"], "severity": v["severity"],
                    "confidence": v["confidence"], "summary": v["summary"]},
        "route": {"tier": v["tier"], "rule": matching_rule(verdict),
                  "why": explain(verdict),
                  "ticket": key and {
                      "key": key,
                      "type": ISSUE_TYPES.get(v["category"], "Task"),
                      "summary": summary_line(v["category"], v["summary"])}},
    }


def policy_export(routes: list[dict]) -> dict:
    from aiops.triage.gate import Thresholds, policy

    t = Thresholds()
    return {"thresholds": {"auto": t.auto, "suggest": t.suggest},
            "gate": policy(), "routes": routes}


def cluster_rows(store: Store, samples: int = 5) -> list[dict]:
    """Everything the dashboard needs without a server behind it: the verdict,
    the timing SQL would have computed, and enough sample events to show what a
    cluster is made of."""
    routed = store.routed_map()
    rows = []
    for cluster in store.list_clusters():
        verdict = store.get_verdict(cluster["id"]) or {}
        span = store.timespan(cluster["id"])
        events = store.events_in_cluster(cluster["id"], samples)
        rows.append({
            "first": span["first"],
            "last": span["last"],
            "samples": [{"title": e.title, "url": e.url, "time": e.time}
                        for e in events],
            "id": cluster["id"],
            "label": cluster["label"],
            "source": cluster["tier"],
            "kind": kind(events[0].type, events[0].source) if events else None,
            "size": cluster["size"],
            "category": verdict.get("category"),
            "severity": verdict.get("severity"),
            "summary": verdict.get("summary"),
            "confidence": verdict.get("confidence"),
            "tier": verdict.get("tier"),
            "model": verdict.get("model"),
            "prompt_version": verdict.get("promptversion"),
            "ticket": routed.get(cluster["id"], {}).get("tickets") or None,
        })
    return rows


def escalations(store: Store, rows: list[dict]) -> list[dict]:
    """The clusters the gate refused to act on alone, each with the rule that
    sent it to a person. This is the part of the pipeline worth showing: the
    model supplies labels and confidence, and a table nobody can argue with
    decides the consequence."""
    from aiops.triage.gate import explain
    from aiops.triage.schema import Verdict

    out = []
    for row in rows:
        if row["tier"] != "escalate":
            continue
        verdict = Verdict(category=row["category"], severity=row["severity"],
                          summary=row["summary"] or "",
                          confidence=row["confidence"] or 0.0, evidence=[])
        out.append({
            "id": row["id"], "label": row["label"], "size": row["size"],
            "category": row["category"], "severity": row["severity"],
            "summary": row["summary"], "confidence": row["confidence"],
            "why": explain(verdict),
            "evidence": [{"title": e.title, "url": e.url}
                         for e in store.events_in_cluster(row["id"], 2)],
        })
    return sorted(out, key=lambda e: e["size"], reverse=True)


def stats_from(rows: list[dict], events: int,
               routes: list[dict] | None = None) -> dict:
    """`tickets` counts what was actually filed; `route_matched` counts what
    the policy would file. They differ because the demo tracker holds a sample,
    and a page that shows one as the other is overclaiming."""
    from aiops.pipeline import Pipeline

    policy = Pipeline(store=None, sources=[], routes=routes or [])
    triaged = [r for r in rows if r["category"]]
    tiers = Counter(r["tier"] for r in triaged)
    bins = Counter(outcome(r, policy) for r in rows if r["tier"])
    return {
        "events": events,
        "clusters": len(rows),
        "triaged": len(triaged),
        "compression": round(events / len(rows), 1) if rows else 0,
        "by_tier": dict(tiers),
        "by_category": dict(Counter(r["category"] for r in triaged)),
        "outcomes": {b: bins.get(b, 0) for b in
                     ("ticket", "person", "draft", "dropped", "unsure")},
        "by_kind": dict(Counter(r["kind"] for r in rows)),
        "by_source": dict(Counter(r["source"] for r in rows)),
        "tickets": len([r for r in rows if r["ticket"]]),
        "route_matched": len([r for r in triaged if policy._sinks_for(r)]),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M UTC%z") or
        datetime.now().isoformat(timespec="minutes"),
    }


def scorecards() -> dict:
    out = {}
    for name, path in (("maintainer_labels", "eval/scorecard-external.json"),
                       ("operator_labels", "eval/scorecard-bgl.json"),
                       ("ask", "eval/scorecard-ask.json"),
                       ("runs", "eval/scorecard-runs.json")):
        file = Path(path)
        if file.exists():
            out[name] = json.loads(file.read_text(encoding="utf-8"))
    return out


def main(db_path: str, out_dir: str = "demo/public/data",
         config: str = "pipeline.yaml") -> None:
    import yaml

    store = Store(db_path)
    with open(config, encoding="utf-8") as f:
        routes = yaml.safe_load(f).get("routes", [])
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    from aiops.pipeline import Pipeline

    policy = Pipeline(store=None, sources=[], routes=routes)
    rows = cluster_rows(store)
    for row in rows:
        row["outcome"] = outcome(row, policy) if row["tier"] else None
    specimens = [specimen(store, c) for c in SPECIMENS]
    for s in specimens:
        s["outcome"] = outcome({"tier": s["route"]["tier"],
                                "category": s["verdict"]["category"]}, policy)
    written = {
        "clusters.json": rows,
        "escalations.json": escalations(store, rows),
        "stats.json": {**stats_from(rows, store.count_events(), routes),
                       "events_by_kind": events_by_kind(store)},
        "scorecards.json": scorecards(),
        "specimens.json": specimens,
        "policy.json": policy_export(routes),
    }
    for name, payload in written.items():
        target = out / name
        target.write_text(json.dumps(payload, separators=(",", ":")),
                          encoding="utf-8")
        print(f"{name:18} {target.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main(*sys.argv[1:4])
