"""Harvest external ground truth from the labels maintainers already applied.

Issues arrive carrying their project's own labels. Where those labels name a
class unambiguously, that is ground truth nobody on this project chose and
anyone can verify by opening the issue. Maintainer vocabularies do not separate
a crash from a failed operation, so both sides of the comparison collapse into
one space (see eval/CODEBOOK.md).

A cluster whose issues carry labels from two different classes is excluded
rather than guessed at.

Usage: python eval/harvest_maintainer_labels.py eval/labeling.sqlite eval/external_labels.csv
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store

SIGNAL = {
    "defect": {"bug", "kind/bug", "type/bug", "c-bug", "bug report",
               "type: bug", "bug/fix"},
    "feature_request": {"feature request", "kind/feature", "enhancement",
                        "feature", "type/feature", "kind/enhancement",
                        "type: feature", "feature-request"},
    "question": {"question", "kind/support", "support", "kind/question",
                 "type: question"},
    "performance": {"performance", "kind/performance", "perf",
                    "type: performance"},
}

# crash and error are one class to a maintainer: both are "bug"
COLLAPSE = {"crash": "defect", "error": "defect"}


def map_labels(labels: set[str]) -> str | None:
    lowered = {label.strip().lower() for label in labels}
    matched = {cls for cls, names in SIGNAL.items() if lowered & names}
    return matched.pop() if len(matched) == 1 else None


def collapse_model(category: str) -> str:
    return COLLAPSE.get(category, category)


def harvest(store: Store) -> list[dict]:
    clusters: dict[str, dict] = {}
    for cluster in store.list_clusters():
        if cluster["tier"] != "prose":
            continue
        labels: set[str] = set()
        url = None
        for event in store.events_in_cluster(cluster["id"], 50):
            labels |= {l for l in event.attributes.get("labels", "").split(",")
                       if l}
            url = url or event.url
        category = map_labels(labels)
        if category:
            clusters[cluster["id"]] = {
                "clusterid": cluster["id"], "category": category,
                "source_labels": ";".join(sorted(labels)), "url": url or "",
                "size": cluster["size"],
            }
    return list(clusters.values())


def main(db_path: str, out_path: str) -> None:
    rows = harvest(Store(db_path))
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, ["clusterid", "category", "source_labels", "url", "size"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["clusterid"]))
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    print(f"{len(rows)} clusters with maintainer ground truth -> {out_path}")
    for category, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {category}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
