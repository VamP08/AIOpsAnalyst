"""Score a candidate prompt against the one in use, without touching the corpus.

The rule this enforces: a prompt is revised in response to the dev half, and
the test half decides whether the revision was real. Both halves are scored for
both versions so the comparison is visible, and the candidate is only promoted
if the test number moves - the dev number moving is expected and proves nothing.

Re-triage happens in a copy of the store, so the published corpus keeps the
verdicts its scorecard was computed from until a promotion is deliberate.

Usage: python eval/prompt_experiment.py eval/labeling.sqlite 1.2
"""
import csv
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agreement_report import pairs, scorecard
from harvest_maintainer_labels import COLLAPSE  # noqa: F401  (documents the map)

from aiops.envfile import load_env
from aiops.store import Store
from aiops.triage.gate import decide_tier
from aiops.triage.prompts import build_messages
from aiops.triage.schema import parse_verdict

COLLAPSED = ("defect", "performance", "feature_request", "question", "noise")


def labelled_ids(*paths: str) -> list[str]:
    ids = []
    for path in paths:
        with open(path, encoding="utf-8", newline="") as f:
            ids += [row["clusterid"] for row in csv.DictReader(f)]
    return ids


def retriage(store: Store, cluster_ids: list[str], version: str,
             chat=None, pause: float = 3.0) -> dict[str, int]:
    if chat is None:
        from aiops.triage.llm import chat
    done = failed = 0
    for n, cluster_id in enumerate(cluster_ids):
        if pause and n:
            time.sleep(pause)
        cluster = next((c for c in store.list_clusters()
                        if c["id"] == cluster_id), None)
        if cluster is None:
            continue
        events = store.events_in_cluster(cluster_id, 5)
        reply = chat(build_messages(cluster["label"], cluster["tier"], events,
                                    version=version))
        verdict = parse_verdict(reply.text) if reply else None
        if verdict is None:
            failed += 1
            continue
        store.upsert_verdict(cluster_id, {
            **verdict.model_dump(), "tier": decide_tier(verdict),
            "model": reply.model, "promptversion": version})
        done += 1
    return {"retriaged": done, "failed": failed}


def score_half(store_path: str, labels: str) -> dict:
    human, model, provenance = pairs(Store(store_path), labels, collapse=True)
    return scorecard(human, model, provenance, COLLAPSED) if human else {}


def main(db_path: str, version: str) -> None:
    load_env()
    dev, test = "eval/split-dev.csv", "eval/split-test.csv"

    before = {half: score_half(db_path, path)
              for half, path in (("dev", dev), ("test", test))}

    work = Path(tempfile.mkdtemp()) / "candidate.sqlite"
    shutil.copy(db_path, work)
    print(f"re-triaging {len(labelled_ids(dev, test))} labelled clusters "
          f"with prompt {version} in a copy\n", flush=True)
    result = retriage(Store(str(work)), labelled_ids(dev, test), version)
    print(result, "\n", flush=True)

    after = {half: score_half(str(work), path)
             for half, path in (("dev", dev), ("test", test))}

    print(f"{'half':6} {'n':>4}  {'kappa 1.1':>10} {'kappa ' + version:>10}"
          f"  {'change':>8}")
    for half in ("dev", "test"):
        old, new = before[half].get("cohens_kappa"), after[half].get("cohens_kappa")
        if old is None or new is None:
            continue
        print(f"{half:6} {before[half]['pairs']:4}  {old:10.3f} {new:10.3f}"
              f"  {new - old:+8.3f}")
    print("\ndev moving is expected; only the test column decides.")
    print(f"candidate store kept at {work}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "1.2")
