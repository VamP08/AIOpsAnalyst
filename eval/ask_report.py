"""The M5 gate: how often does a question reach the right cluster.

Runs eval/questions.yaml against the ask layer and reports hit@1, hit@3 and
routing accuracy. Retrieval and routing are scored separately on purpose - a
question can reach the right cluster and still be answered as the wrong kind of
question, and averaging the two would hide both.

The set was written before this was ever run, and the number goes into the docs
whatever it says.

Usage: python eval/ask_report.py eval/labeling.sqlite [--json eval/scorecard-ask.json]
"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.ask import answer
from aiops.store import Store


def hit_rank(matches: list[dict], marker: str) -> int | None:
    """1-based position of the first cluster whose label or summary contains
    the marker, or None when the retriever never found it."""
    needle = marker.lower()
    for position, match in enumerate(matches, start=1):
        haystack = f"{match.get('label', '')} {match.get('summary') or ''}".lower()
        if needle in haystack:
            return position
    return None


def score(results: list[dict]) -> dict:
    n = len(results)
    if not n:
        return {"questions": 0}
    at = lambda k: round(sum(1 for r in results
                             if r["rank"] is not None and r["rank"] <= k) / n, 3)
    return {
        "questions": n,
        "hit_at_1": at(1),
        "hit_at_3": at(3),
        "hit_at_5": at(5),
        "routing_accuracy": round(
            sum(1 for r in results if r["kind"] == r["expected_kind"]) / n, 3),
        "misses": [r["q"] for r in results if r["rank"] is None and "q" in r],
    }


def run(store: Store, questions: list[dict], encoder=None) -> list[dict]:
    results = []
    for item in questions:
        result = answer(store, item["q"], limit=5, encoder=encoder)
        results.append({
            "q": item["q"],
            "expected_kind": item["kind"],
            "kind": result["kind"] if result["kind"] != "none" else "what",
            "rank": hit_rank(result["matches"], item["marker"]),
            "answer": result["answer"],
        })
    return results


def main(db_path: str, json_out: str | None) -> None:
    questions = yaml.safe_load(
        Path("eval/questions.yaml").read_text(encoding="utf-8"))
    store = Store(db_path)
    lexical = score(run(store, questions, encoder=False))
    results = run(store, questions)
    card = score(results)

    # The set was written and run lexically before the semantic pass existed;
    # that pass was added after seeing which two questions missed, so the
    # hybrid number is a post-hoc improvement, not a held-out result. Both are
    # reported, labelled as what they are.
    card["lexical_only"] = lexical

    print(f"questions        : {card['questions']}")
    print(f"hit@1            : {card['hit_at_1']}"
          f"   (lexical only {lexical['hit_at_1']})")
    print(f"hit@3            : {card['hit_at_3']}"
          f"   (lexical only {lexical['hit_at_3']})")
    print(f"hit@5            : {card['hit_at_5']}"
          f"   (lexical only {lexical['hit_at_5']})")
    print(f"routing accuracy : {card['routing_accuracy']}")
    print()
    for r in results:
        mark = "-" if r["rank"] is None else str(r["rank"])
        route = "" if r["kind"] == r["expected_kind"] else \
            f"  [routed {r['kind']}, expected {r['expected_kind']}]"
        print(f"  rank {mark:>2}  {r['q'][:58]:58}{route}")
    if json_out:
        Path(json_out).write_text(
            json.dumps({**card, "results": results}, indent=1), encoding="utf-8")
        print(f"\nwrote {json_out}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    main(argv[0], out)
