"""Blind hand-labeling CLI for the M3 agreement gate.

Shows each cluster's label and sample events — never the LLM's verdict, so
labels stay unbiased. Appends to the CSV so a session can stop and resume.
Order is shuffled with a fixed seed: labeling effort spreads across tiers
instead of front-loading one source.

Usage: python eval/label.py <db.sqlite> <labels.csv>
Keys: 1-6 category, s skip, q quit.
"""
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.triage.schema import CATEGORIES


def main(db_path: str, out_path: str) -> None:
    store = Store(db_path)
    done = set()
    out = Path(out_path)
    if out.exists():
        with open(out, encoding="utf-8", newline="") as f:
            done = {row["clusterid"] for row in csv.DictReader(f)}

    clusters = [c for c in store.list_clusters() if c["id"] not in done]
    random.Random(7).shuffle(clusters)
    if not clusters:
        print("nothing left to label")
        return

    menu = "  ".join(f"[{i + 1}] {c}" for i, c in enumerate(CATEGORIES))
    new_file = not out.exists()
    with open(out, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["clusterid", "category"])
        for n, cluster in enumerate(clusters, 1):
            print(f"\n--- {n}/{len(clusters)}  {cluster['id']} "
                  f"({cluster['tier']}, {cluster['size']} events)")
            print(f"    {cluster['label'][:120]}")
            for event in store.events_in_cluster(cluster["id"], 3):
                print(f"    · {event.title[:110]}")
            answer = input(f"{menu}  [s]kip [q]uit > ").strip().lower()
            if answer == "q":
                break
            if answer == "s" or not answer.isdigit() \
                    or not 1 <= int(answer) <= len(CATEGORIES):
                continue
            writer.writerow([cluster["id"], CATEGORIES[int(answer) - 1]])
            f.flush()
    print(f"\nlabels in {out}: {sum(1 for _ in open(out)) - 1}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
