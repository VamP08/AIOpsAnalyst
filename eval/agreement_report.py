"""M3 gate report: agreement between hand labels and LLM verdicts.

Prints overall Cohen's kappa, raw agreement, per-category precision/recall,
and the confusion pairs. Run it once labels.csv has >=100 rows; numbers go
into PROGRESS.md unedited, before any prompt tuning.

Usage: python eval/agreement_report.py <db.sqlite> <labels.csv>
"""
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.triage.agreement import cohens_kappa
from aiops.triage.schema import CATEGORIES


def main(db_path: str, labels_path: str) -> None:
    store = Store(db_path)
    human, model = [], []
    with open(labels_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            verdict = store.get_verdict(row["clusterid"])
            if verdict:
                human.append(row["category"])
                model.append(verdict["category"])

    n = len(human)
    if n == 0:
        print("no labeled clusters have verdicts yet")
        return
    agree = sum(h == m for h, m in zip(human, model))
    print(f"paired clusters: {n}")
    print(f"raw agreement: {agree}/{n} = {agree / n:.3f}")
    print(f"cohen's kappa: {cohens_kappa(human, model):.3f}")

    print(f"\n{'category':15} {'n':>4} {'precision':>9} {'recall':>7}")
    for cat in CATEGORIES:
        support = sum(h == cat for h in human)
        predicted = sum(m == cat for m in model)
        hits = sum(h == m == cat for h, m in zip(human, model))
        precision = hits / predicted if predicted else float("nan")
        recall = hits / support if support else float("nan")
        print(f"{cat:15} {support:4d} {precision:9.2f} {recall:7.2f}")

    confusion = Counter((h, m) for h, m in zip(human, model) if h != m)
    if confusion:
        print("\ntop confusions (human -> model):")
        for (h, m), count in confusion.most_common(8):
            print(f"  {h} -> {m}: {count}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
