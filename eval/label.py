"""Blind hand-labeling CLI for the agreement gate.

Shows each cluster's template and sample events - never the model's verdict, so
labels stay unbiased. Samples carry the same text the model was given, so the
comparison is fair. Appends to the CSV after every keypress: stop whenever,
resume by rerunning. Order is shuffled with a fixed seed so effort spreads
across sources instead of front-loading one.

--tier log restricts the session to log clusters, the half no maintainer can
label; eval/CODEBOOK.md explains every template in that set.

Usage: python eval/label.py eval/labeling.sqlite eval/labels.csv [--tier log]
Keys:  1-6 category, s skip, q quit
"""
import csv
import random
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.textclean import strip_boilerplate
from aiops.triage.schema import CATEGORIES

TARGET = 100  # the gate wants at least this many paired labels
RULE = "-" * 72


def already_labeled(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {row["clusterid"] for row in csv.DictReader(f)}


def show(store: Store, cluster: dict, done: int, total: int,
         note: str = "") -> None:
    print(f"\n{RULE}\n {done}/{total} labeled"
          f"{note}"
          f"  |  {cluster['tier']} cluster, {cluster['size']} event"
          f"{'s' if cluster['size'] != 1 else ''}\n")
    for line in textwrap.wrap(cluster["label"], 70):
        print(f"  {line}")
    for event in store.events_in_cluster(cluster["id"], 3):
        block = []
        if event.title != cluster["label"]:
            block += [f"    {line}" for line in textwrap.wrap(event.title, 68)]
        if event.body:
            body = " ".join(strip_boilerplate(event.body).split())[:280]
            block += [f"      {line}" for line in textwrap.wrap(body, 66)]
        if event.url:
            block.append(f"      {event.url}")
        if block:                  # a template identical to its lines adds nothing
            print()
            for line in block:
                print(line)
    print("\n  [1] crash   [2] error    [3] performance")
    print("  [4] feature_request   [5] question   [6] noise"
          "        s=skip  q=quit")


def main(db_path: str, out_path: str, tier: str | None = None) -> None:
    store = Store(db_path)
    out = Path(out_path)
    done = already_labeled(out)
    clusters = [c for c in store.list_clusters()
                if tier is None or c["tier"] == tier]
    total = len(clusters)
    pending = [c for c in clusters if c["id"] not in done]
    random.Random(7).shuffle(pending)
    if not pending:
        print(f"all {total} clusters labeled - run eval/agreement_report.py")
        return

    note = "" if tier or len(done) >= TARGET else f" (gate wants {TARGET})"
    new_file = not out.exists()
    with open(out, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["clusterid", "category"])
        for cluster in pending:
            show(store, cluster, len(done), total, note)
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
    here = len([c for c in clusters if c["id"] in done])
    scope = f" {tier}" if tier else ""
    print()
    print(f"{here}/{total}{scope} clusters labeled. "
          f"Run eval/agreement_report.py when you are done.")


if __name__ == "__main__":
    argv = sys.argv[1:]
    tier = argv[argv.index("--tier") + 1] if "--tier" in argv else None
    main(argv[0], argv[1], tier)
