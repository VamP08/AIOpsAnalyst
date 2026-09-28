"""Line-level evaluation against the operator labels shipped with BGL.

Every line of the Blue Gene/L log carries an alert label applied by the
operations staff who ran the machine and published with the dataset
(Oliner and Stearley, DSN 2007): "-" for routine, otherwise an alert tag such
as KERNDTLB. Those labels are ground truth nobody on this project chose.

The pipeline never sees them - the parser keeps the label in attributes and the
prompt is built from title and body only, which tests/test_prompts.py asserts.

What this measures is the decision the category exists to make: would this line
have been surfaced to a human, or suppressed as routine? A cluster triaged as
noise suppresses every line in it; any other category surfaces them. That is
alert fatigue expressed as two numbers - how many real alerts survive, and how
much routine chatter is kept off the screen.

Usage: python eval/bgl_report.py eval/labeling.sqlite [--json eval/scorecard-bgl.json]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.triage.agreement import cohens_kappa, kappa_ci

BGL_SOURCE = "bgl://llnl/bluegene"


def is_alert(label: str) -> bool:
    return label.strip() != "-"


def surfaced(category: str | None) -> bool:
    return category is not None and category != "noise"


def tally(lines: list[tuple[str, str | None]]) -> dict[str, int]:
    counts = {"alert_surfaced": 0, "alert_missed": 0,
              "routine_surfaced": 0, "routine_suppressed": 0}
    for label, category in lines:
        alert, shown = is_alert(label), surfaced(category)
        if alert and shown:
            counts["alert_surfaced"] += 1
        elif alert:
            counts["alert_missed"] += 1
        elif shown:
            counts["routine_surfaced"] += 1
        else:
            counts["routine_suppressed"] += 1
    return counts


def cluster_view(clusters: list[dict]) -> dict:
    """What a responder actually reads. Line counts flatter or punish a system
    depending on how large its clusters are; the screen shows clusters."""
    shown = [c for c in clusters if surfaced(c["category"])]
    bearing = [c for c in clusters if c["alerts"] > 0]
    return {
        "clusters": len(clusters),
        "surfaced": len(shown),
        "alert_bearing": len(bearing),
        "alert_bearing_surfaced": len([c for c in bearing
                                       if surfaced(c["category"])]),
    }


def collect_clusters(store: Store) -> list[dict]:
    out = []
    for cluster in store.list_clusters():
        events = [e for e in store.events_in_cluster(cluster["id"], 10_000)
                  if e.source == BGL_SOURCE]
        if not events:
            continue
        verdict = store.get_verdict(cluster["id"]) or {}
        out.append({
            "label": cluster["label"],
            "category": verdict.get("category"),
            "lines": len(events),
            "alerts": sum(is_alert(e.attributes.get("bgl_label", "-"))
                          for e in events),
        })
    return out


def collect(store: Store) -> list[tuple[str, str | None]]:
    category_of = {c["id"]: (store.get_verdict(c["id"]) or {}).get("category")
                   for c in store.list_clusters()}
    return [(event.attributes.get("bgl_label", "-"), category_of.get(event.clusterid))
            for event in store.all_events() if event.source == BGL_SOURCE]


def report(lines: list[tuple[str, str | None]]) -> dict:
    counts = tally(lines)
    alerts = counts["alert_surfaced"] + counts["alert_missed"]
    routine = counts["routine_surfaced"] + counts["routine_suppressed"]
    shown = counts["alert_surfaced"] + counts["routine_surfaced"]
    truth = ["alert" if is_alert(l) else "routine" for l, _ in lines]
    called = ["alert" if surfaced(c) else "routine" for _, c in lines]
    return {
        "lines": len(lines),
        "operator_alerts": alerts,
        "operator_routine": routine,
        **counts,
        "alert_recall": round(counts["alert_surfaced"] / alerts, 4) if alerts else None,
        "alert_precision": round(counts["alert_surfaced"] / shown, 4) if shown else None,
        "noise_suppression": round(counts["routine_suppressed"] / routine, 4)
        if routine else None,
        "cohens_kappa": round(cohens_kappa(truth, called), 4) if lines else None,
        "kappa_ci95": list(kappa_ci(truth, called, resamples=500, seed=7))
        if lines else None,
    }


def main(db_path: str, json_out: str | None) -> None:
    store = Store(db_path)
    card = report(collect(store))
    card["by_cluster"] = cluster_view(collect_clusters(store))
    if not card["lines"]:
        print("no BGL events in this store")
        return
    print(f"lines                : {card['lines']:,}")
    print(f"operator alerts      : {card['operator_alerts']:,}")
    print(f"operator routine     : {card['operator_routine']:,}")
    print()
    print(f"alerts surfaced      : {card['alert_surfaced']:,} "
          f"(recall {card['alert_recall']})")
    print(f"alerts missed        : {card['alert_missed']:,}")
    print(f"routine suppressed   : {card['routine_suppressed']:,} "
          f"(suppression {card['noise_suppression']})")
    print(f"routine surfaced     : {card['routine_surfaced']:,}")
    print(f"precision on surfaced: {card['alert_precision']}")
    print(f"cohen's kappa        : {card['cohens_kappa']} "
          f"(95% CI {card['kappa_ci95'][0]} to {card['kappa_ci95'][1]})")
    view = card["by_cluster"]
    print()
    print(f"clusters             : {view['clusters']} "
          f"({view['surfaced']} surfaced, the rest suppressed as noise)")
    print(f"incident types found : {view['alert_bearing_surfaced']}"
          f"/{view['alert_bearing']} clusters carrying operator alerts "
          f"are surfaced")
    if json_out:
        Path(json_out).write_text(json.dumps(card, indent=1), encoding="utf-8")
        print(f"\nwrote {json_out}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    main(argv[0], out)
