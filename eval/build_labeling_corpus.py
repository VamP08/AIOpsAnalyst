"""Build the fixed corpus the agreement gate is labeled against.

Three log formats plus live GitHub issues, so the golden set exercises the
whole pipeline rather than one source: OpenSSH auth logs (Loghub-2.0), Apache
error logs (Loghub-2.0), and recent issues from four busy public repos.

Lines are sampled with a stride instead of taken from the head — the first
thousand lines of a log are startup chatter and would yield a corpus of five
templates. Clusters are then triaged in passes: free-tier limits are per model
per minute, so a pass that hits them is retried after the window resets.

Writes eval/labeling.sqlite (the labeling target) and
eval/labeling_corpus.json (a committed snapshot, so the labels stay meaningful
even if the database is lost). Refuses to overwrite an existing database:
rebuilding would renumber nothing, but it would change membership, and labels
are only as good as the corpus they were made against.

Usage: python eval/build_labeling_corpus.py [--rebuild]
"""
import itertools
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aiops.envfile import load_env
from aiops.pipeline import Pipeline
from aiops.sources.github_issues import GitHubIssuesSource
from aiops.sources.log_file import LogFileSource
from aiops.store import Store

DB = ROOT / "eval" / "labeling.sqlite"
SNAPSHOT = ROOT / "eval" / "labeling_corpus.json"

LOGS = [
    ("corpus/data/OpenSSH/OpenSSH_full.log", "syslog", "syslog://labsz/sshd",
     7, 2500),
    ("corpus/data/Apache/Apache_full.log", "apache_error", "apache://web-1",
     11, 3000),
]
REPOS = ["huggingface/transformers", "vercel/next.js", "pytorch/pytorch",
         "langchain-ai/langchain"]
ISSUES_PER_REPO = 15
DAYS_BACK = 4


def sample_log(path: str, stride: int, keep: int) -> Path:
    """Stride-sample a big log into a temp file the source can read."""
    out = ROOT / "eval" / f"_sample_{Path(path).stem}.log"
    with open(ROOT / path, encoding="utf-8", errors="replace") as src, \
            open(out, "w", encoding="utf-8") as dst:
        dst.writelines(itertools.islice(
            (line for n, line in enumerate(src) if n % stride == 0), keep))
    return out


def ingest(store: Store) -> None:
    for path, fmt, source, stride, keep in LOGS:
        sample = sample_log(path, stride, keep)
        events = list(LogFileSource(path=str(sample), format=fmt,
                                    source=source).fetch())
        print(f"  {Path(path).name}: {store.insert_events(events)} events")

    since = (datetime.now(timezone.utc)
             - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for repo in REPOS:
        events = list(itertools.islice(
            GitHubIssuesSource(repo=repo, max_pages=1).fetch(cursor=since),
            ISSUES_PER_REPO))
        print(f"  {repo}: {store.insert_events(events)} issues")


def triage_until_done(pipe: Pipeline, max_passes: int = 6) -> None:
    for attempt in range(1, max_passes + 1):
        result = pipe.triage(pause=5)
        print(f"  pass {attempt}: {result}", flush=True)
        if not result["failed"]:
            return
        if attempt < max_passes:
            time.sleep(70)  # per-model token windows reset on the minute


def write_snapshot(store: Store) -> None:
    clusters = []
    for cluster in store.list_clusters():
        clusters.append({
            **cluster,
            "samples": [{"id": e.id, "title": e.title, "url": e.url}
                        for e in store.events_in_cluster(cluster["id"], 3)],
        })
    SNAPSHOT.write_text(json.dumps(
        {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
         "events": store.count_events(), "clusters": clusters},
        indent=1), encoding="utf-8")


def main(rebuild: bool) -> None:
    if DB.exists() and not rebuild:
        sys.exit(f"{DB.name} already exists — labels are tied to it. "
                 f"Pass --rebuild only if you mean to discard them.")
    if DB.exists():
        DB.unlink()
    load_env(str(ROOT / ".env"))

    store = Store(str(DB))
    print("ingest:")
    ingest(store)
    pipe = Pipeline(store, sources=[])
    print(f"cluster: {pipe.cluster()}", flush=True)
    print(f"clusters: {len(store.list_clusters())}")
    print("triage:")
    triage_until_done(pipe)
    write_snapshot(store)

    triaged = sum(1 for c in store.list_clusters()
                  if store.get_verdict(c["id"]))
    print(f"\nready: {store.count_events()} events, "
          f"{len(store.list_clusters())} clusters, {triaged} with verdicts")
    print(f"label with: python eval/label.py {DB.relative_to(ROOT)} "
          f"eval/labels.csv")


if __name__ == "__main__":
    main("--rebuild" in sys.argv)
