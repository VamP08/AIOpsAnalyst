"""Agreement between hand labels and model verdicts - the M3 gate report.

Prints raw agreement, Cohen's kappa, per-category precision and recall, and
the confusion pairs, together with the provenance that makes the number
meaningful: which prompt version and which models produced the verdicts. With
--json it also writes the scorecard for the repo to cite.

Kappa bands in common use: >0.80 strong, 0.60-0.80 substantial, <0.60 means the
rubric needs work. Report whatever comes out, before any tuning.

With --collapse the model's categories are mapped into the maintainer-label
space (crash and error both become defect) so verdicts can be compared against
eval/external_labels.csv. See eval/CODEBOOK.md.

Usage:
  python eval/agreement_report.py eval/labeling.sqlite eval/labels.csv
  python eval/agreement_report.py eval/labeling.sqlite eval/external_labels.csv --collapse --json eval/scorecard-external.json
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harvest_maintainer_labels import collapse_model

from aiops.store import Store
from aiops.triage.agreement import cohens_kappa, kappa_ci
from aiops.triage.schema import CATEGORIES

COLLAPSED = ("defect", "performance", "feature_request", "question", "noise")


def pairs(store: Store, labels_path: str, collapse: bool = False):
    human, model, provenance = [], [], []
    with open(labels_path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            verdict = store.get_verdict(row["clusterid"])
            if verdict:
                human.append(row["category"])
                category = verdict["category"]
                model.append(collapse_model(category) if collapse else category)
                provenance.append((verdict["promptversion"], verdict["model"]))
    return human, model, provenance


def scorecard(human, model, provenance, categories=CATEGORIES) -> dict:
    n = len(human)
    agree = sum(h == m for h, m in zip(human, model))
    per_category = {}
    for category in categories:
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
        "kappa_ci95": list(kappa_ci(human, model, seed=7)),
        "per_category": per_category,
        "confusions": {f"{h} -> {m}": c for (h, m), c in
                       Counter((h, m) for h, m in zip(human, model)
                               if h != m).most_common()},
        "taxonomy": list(categories),
        "prompt_versions": sorted({p for p, _ in provenance}),
        "models": dict(Counter(m for _, m in provenance)),
    }


def main(db_path: str, labels_path: str, json_out: str | None,
         collapse: bool = False) -> None:
    store = Store(db_path)
    human, model, provenance = pairs(store, labels_path, collapse)
    if not human:
        print("no labeled cluster has a verdict yet")
        return
    card = scorecard(human, model, provenance,
                     COLLAPSED if collapse else CATEGORIES)
    card["reference"] = ("maintainer labels (collapsed taxonomy)" if collapse
                         else "author labels (six-class taxonomy)")

    print(f"reference       : {card['reference']}")
    print(f"paired clusters : {card['pairs']}")
    print(f"raw agreement   : {card['raw_agreement']}")
    print(f"cohen's kappa   : {card['cohens_kappa']} "
          f"(95% CI {card['kappa_ci95'][0]} to {card['kappa_ci95'][1]})")
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
    main(argv[0], argv[1], out, "--collapse" in argv)
