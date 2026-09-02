"""Clustering benchmark against a Loghub-2.0 dataset.

Reads the dataset's structured CSV (per-line ground-truth EventId), runs the
Drain tier over the raw Content twice, and reports: compression ratio,
determinism across the two runs, and LogPai Grouping Accuracy. Numbers go into
PROGRESS.md unedited.

Usage: python eval/bench_loghub.py corpus/data/OpenSSH/OpenSSH_full.log_structured.csv
"""
import csv
import sys
import time

from aiops.cluster.drain import LogClusterer
from aiops.cluster.metrics import grouping_accuracy
from aiops.envelope import Event


def load(path):
    lines, truth = [], {}
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            line_id = str(i)
            lines.append(Event(id=line_id, source="bench", type="dev.aiops.log.line",
                               title=row["Content"]))
            truth[line_id] = row["EventId"]
    return lines, truth


def main(path):
    events, truth = load(path)
    print(f"lines: {len(events):,}")

    t0 = time.time()
    run_a = LogClusterer().assign(events)
    t1 = time.time()
    run_b = LogClusterer().assign(events)

    clusters = len(set(run_a.values()))
    print(f"clusters: {clusters:,}")
    print(f"ground-truth templates: {len(set(truth.values())):,}")
    print(f"compression: {len(events) / clusters:,.0f}x "
          f"({len(events):,} lines -> {clusters:,} clusters)")
    print(f"deterministic across runs: {run_a == run_b}")
    print(f"grouping accuracy (LogPai GA): {grouping_accuracy(run_a, truth):.4f}")
    print(f"cluster time: {t1 - t0:.1f}s "
          f"({len(events) / (t1 - t0):,.0f} lines/s)")


if __name__ == "__main__":
    main(sys.argv[1])
