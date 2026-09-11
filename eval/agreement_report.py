"""Agreement between hand labels and model verdicts - the M3 gate report.

Prints raw agreement, Cohen's kappa, per-category precision and recall, and
the confusion pairs, together with the provenance that makes the number
meaningful: which prompt version and which models produced the verdicts. With
--json it also writes the scorecard for the repo to cite.

Kappa bands in common use: >0.80 strong, 0.60-0.80 substantial, <0.60 means the
rubric needs work. Report whatever comes out, before any tuning.

Usage: python eval/agreement_report.py eval/labeling.sqlite eval/labels.csv [--json eval/scorecard.json]
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.store import Store
from aiops.triage.agreement import cohens_kappa
from aiops.triage.schema import CATEGORIES


def pairs(store: Store, labels_path: str):
    human, model, provenance = [], [], []
    with open(labels_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            verdict = store.get_verdict(row["clusterid"])
            if verdict:
                human.append(row["category"])
                model.append(verdict["category"])
                provenance.append((verdict["promptversion"], verdict["model"]))
    return human, model, provenance


def scorecard(human, model, provenance) -> dict:
    n = len(human)
    agree = sum(h == m for h, m in zip(human, model))
    per_category = {}
    for category in CATEGORIES:
        support = sum(h == category for h in human)
        predicted = sum(m == category for m in model)
        hits = sum(h == m == category for h, m in zip(human, model))
        per_category[category] = {
            "support": support,
            "precision": round(hits / predicted, 3) if predicted else None,
            "recall": round(hits / support, 3) if support else None,
        }
    return {
        "pairs": n,
        "raw_agreement": round(agree / n, 3),
        "cohens_kappa": round(cohens_kappa(human, model), 3),
        "per_category": per_category,
        "confusions": {f"{h} -> {m}": c for (h, m), c in
                       Counter((h, m) for h, m in zip(human, model)
                               if h != m).most_common()},
        "prompt_versions": sorted({p for p, _ in provenance}),
        "models": dict(Counter(m for _, m in provenance)),
    }


def main(db_path: str, labels_path: str, json_out: str | None) -> None:
    store = Store(db_path)
    human, model, provenance = pairs(store, labels_path)
    if not human:
        print("no labeled cluster has a verdict yet")
        return
    card = scorecard(human, model, provenance)

    print(f"paired clusters : {card['pairs']}")
    print(f"raw agreement   : {card['raw_agreement']}")
    print(f"cohen's kappa   : {card['cohens_kappa']}")
    print(f"prompt version  : {', '.join(card['prompt_versions'])}")
    print(f"models          : {card['models']}")
    print()
    print(f"{'category':16} {'n':>4} {'precision':>10} {'recall':>8}")
    for category, row in card["per_category"].items():
        precision = "-" if row["precision"] is None else f"{row['precision']:.2f}"
        recall = "-" if row["recall"] is None else f"{row['recall']:.2f}"
        print(f"{category:16} {row['support']:4d} {precision:>10} {recall:>8}")
    if card["confusions"]:
        print("\nconfusions (human -> model):")
        for pair, count in list(card["confusions"].items())[:8]:
            print(f"  {pair}: {count}")
    if json_out:
        Path(json_out).write_text(json.dumps(card, indent=1), encoding="utf-8")
        print(f"\nwrote {json_out}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    main(argv[0], argv[1], out)
