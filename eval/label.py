"""Blind hand-labeling CLI for the agreement gate.

Shows each cluster's template and sample events — never the model's verdict, so
labels stay unbiased. Samples carry the same text the model was given, so the
comparison is fair. Appends to the CSV after every keypress: stop whenever,
resume by rerunning. Order is shuffled with a fixed seed so effort spreads
across sources instead of front-loading one.

Usage: python eval/label.py eval/labeling.sqlite eval/labels.csv
Keys:  1-6 category, s skip, q quit
"""
import csv
import random
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.triage.schema import CATEGORIES

TARGET = 100  # the gate wants at least this many paired labels
RULE = "-" * 72


def already_labeled(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {row["clusterid"] for row in csv.DictReader(f)}


def show(store: Store, cluster: dict, done: int, total: int) -> None:
    print(f"\n{RULE}\n {done}/{total} labeled"
          f"{'' if done >= TARGET else f' (gate needs {TARGET})'}"
          f"  ·  {cluster['tier']} cluster, {cluster['size']} event"
          f"{'s' if cluster['size'] != 1 else ''}\n")
    for line in textwrap.wrap(cluster["label"], 70):
        print(f"  {line}")
    for event in store.events_in_cluster(cluster["id"], 3):
        print()
        if event.title != cluster["label"]:
            for line in textwrap.wrap(event.title, 68):
                print(f"    {line}")
        if event.body:
            body = " ".join(event.body.split())[:280]
            for line in textwrap.wrap(body, 66):
                print(f"      {line}")
        if event.url:
            print(f"      {event.url}")
    print(f"\n  [1] crash   [2] error    [3] performance")
    print(f"  [4] feature_request   [5] question   [6] noise"
          f"        s=skip  q=quit")


def main(db_path: str, out_path: str) -> None:
    store = Store(db_path)
    out = Path(out_path)
    done = already_labeled(out)
    clusters = store.list_clusters()
    total = len(clusters)
    pending = [c for c in clusters if c["id"] not in done]
    random.Random(7).shuffle(pending)
    if not pending:
        print(f"all {total} clusters labeled — run eval/agreement_report.py")
        return

    new_file = not out.exists()
    with open(out, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["clusterid", "category"])
        for cluster in pending:
            show(store, cluster, len(done), total)
            try:
                answer = input("  > ").strip().lower()
            except EOFError:
                break
            if answer == "q":
                break
            if not answer.isdigit() or not 1 <= int(answer) <= len(CATEGORIES):
                continue  # skip: ambiguity is rubric feedback, not a label
            writer.writerow([cluster["id"], CATEGORIES[int(answer) - 1]])
            f.flush()
            done.add(cluster["id"])
    print(f"\n{len(done)} labeled of {total}. "
          f"{'Gate satisfied.' if len(done) >= TARGET else f'{TARGET - len(done)} to go.'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
