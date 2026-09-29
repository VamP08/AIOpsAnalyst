"""Split the labelled clusters into a half to tune on and a half to report.

The baseline (kappa 0.610 on all 109) was recorded before any tuning, which
makes it honest but also spent: once a prompt is revised in response to the
mistakes it made, the same clusters can no longer measure it. So the set is cut
in two, stratified by class, with a fixed seed. The prompt may be changed in
response to the dev half only. The test half is scored once per prompt version
and never inspected for ideas.

Usage: python eval/split.py eval/external_labels.csv eval/split
"""
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path


def split_labels(rows: list[dict], seed: int = 7,
                 dev_share: float = 0.5) -> tuple[list[dict], list[dict]]:
    """Stratified by category, so a rare class cannot land entirely on one side
    and make both halves measure different things."""
    by_class = defaultdict(list)
    for row in rows:
        by_class[row["category"]].append(row)

    dev, test = [], []
    rng = random.Random(seed)
    for category in sorted(by_class):
        members = sorted(by_class[category], key=lambda r: r["clusterid"])
        rng.shuffle(members)
        cut = round(len(members) * dev_share)
        dev += members[:cut]
        test += members[cut:]
    return dev, test


def main(labels_path: str, out_prefix: str) -> None:
    with open(labels_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    dev, test = split_labels(rows)

    for name, part in (("dev", dev), ("test", test)):
        path = Path(f"{out_prefix}-{name}.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(part)
        counts = {}
        for row in part:
            counts[row["category"]] = counts.get(row["category"], 0) + 1
        print(f"{name:4} {len(part):4} clusters  {counts}  -> {path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "eval/split")
