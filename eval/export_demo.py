"""Freeze the store into the JSON the demo page reads.

The demo front door is static on purpose: a free web service that sleeps takes
about a minute to wake, and a minute of blank page is the whole visit. So the
page ships precomputed results and loads instantly, and the live API is a
progressive enhancement the first impression never depends on.

Writes into demo/data/:
  stats.json       headline counters
  clusters.json    every cluster with its verdict and any ticket it produced
  scorecards.json  both published evaluations, verbatim
  replay.json      one real incident, event by event, for the replay player

Usage: python eval/export_demo.py eval/labeling.sqlite demo/data
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.envelope import Event
from aiops.store import Store

# A three minute burst on the Blue Gene/L machine: 4,096 lines and 76 of them
# flagged by the operators. Real timestamps, replayed at speed.
REPLAY_SOURCE = "bgl://llnl/bluegene"
REPLAY_FROM = "2005-06-05T00:00"
REPLAY_TO = "2005-06-05T02:00"


def replay_window(events: list[Event], start: str, end: str) -> list[Event]:
    inside = [e for e in events if e.time and start <= e.time < end]
    return sorted(inside, key=lambda e: e.time)


def offsets_ms(events: list[Event]) -> list[int]:
    if not events:
        return []
    stamps = [datetime.fromisoformat(e.time) for e in events]
    return [int((s - stamps[0]).total_seconds() * 1000) for s in stamps]


def compact(stream: list[dict], samples: int = 3) -> list[dict]:
    """Drop repeated line text, keep every event.

    A two hour window is sixteen thousand lines and most of them are the same
    sentence with different numbers. The first few of each cluster and every
    operator-flagged line keep their text; the rest are counted and timed
    exactly as before, and the player shows the cluster template for them. No
    event is sampled away, because the counter racing past sixteen thousand is
    the point of the replay.
    """
    seen: Counter = Counter()
    out = []
    for event in stream:
        seen[event["cluster"]] += 1
        keep = event["alert"] or seen[event["cluster"]] <= samples
        out.append(event if keep else {k: v for k, v in event.items()
                                       if k != "line"})
    return out


def cluster_rows(store: Store) -> list[dict]:
    routed = store.routed_map()
    rows = []
    for cluster in store.list_clusters():
        verdict = store.get_verdict(cluster["id"]) or {}
        rows.append({
            "id": cluster["id"],
            "label": cluster["label"],
            "source": cluster["tier"],
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


def stats_from(rows: list[dict], events: int) -> dict:
    triaged = [r for r in rows if r["category"]]
    tiers = Counter(r["tier"] for r in triaged)
    return {
        "events": events,
        "clusters": len(rows),
        "triaged": len(triaged),
        "compression": round(events / len(rows), 1) if rows else 0,
        "by_tier": dict(tiers),
        "by_category": dict(Counter(r["category"] for r in triaged)),
        "by_source": dict(Counter(r["source"] for r in rows)),
        "tickets": len([r for r in rows if r["ticket"]]),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M UTC%z") or
        datetime.now().isoformat(timespec="minutes"),
    }


def replay_from(store: Store) -> dict:
    events = [e for e in store.all_events() if e.source == REPLAY_SOURCE]
    window = replay_window(events, REPLAY_FROM, REPLAY_TO)
    return {
        "source": REPLAY_SOURCE,
        "from": REPLAY_FROM,
        "to": REPLAY_TO,
        "note": "Blue Gene/L supercomputer log, replayed from its own timestamps",
        "events": compact([{"ms": ms, "cluster": e.clusterid,
                            "line": e.title[:110],
                            "alert": e.attributes.get("bgl_label", "-") != "-"}
                           for ms, e in zip(offsets_ms(window), window)]),
    }


def scorecards() -> dict:
    out = {}
    for name, path in (("maintainer_labels", "eval/scorecard-external.json"),
                       ("operator_labels", "eval/scorecard-bgl.json")):
        file = Path(path)
        if file.exists():
            out[name] = json.loads(file.read_text(encoding="utf-8"))
    return out


def main(db_path: str, out_dir: str) -> None:
    store = Store(db_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows = cluster_rows(store)
    written = {
        "clusters.json": rows,
        "stats.json": stats_from(rows, store.count_events()),
        "scorecards.json": scorecards(),
        "replay.json": replay_from(store),
    }
    for name, payload in written.items():
        target = out / name
        target.write_text(json.dumps(payload, separators=(",", ":")),
                          encoding="utf-8")
        print(f"{name:18} {target.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "demo/data")
