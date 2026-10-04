"""Build the fixed corpus the agreement gate is labeled against.

Seven log corpora plus three live feeds, so the golden set exercises the
whole pipeline rather than one source. Logs, all Loghub: OpenSSH auth, Apache
errors, OpenStack, ZooKeeper, Linux syslog, and Blue Gene/L (kept small, for
its operator labels). Feeds: recent issues from six busy public repos, recent
incidents from four public status pages, and failed CI runs on the main
branches of three repos.

Lines are sampled with a stride instead of taken from the head — the first
thousand lines of a log are startup chatter and would yield a corpus of five
templates. Clusters are then triaged in passes: free-tier limits are per model
per minute, so a pass that hits them is retried after the window resets.

Writes eval/labeling.sqlite (the labeling target) and
eval/labeling_corpus.json (a committed snapshot, so the labels stay meaningful
even if the database is lost). Refuses to overwrite an existing database:
rebuilding would renumber nothing, but it would change membership, and labels
are only as good as the corpus they were made against.

Cluster ids are content-derived, so the corpus can be grown later without
invalidating labels already made: --extend adds sources to an existing database
and triages only what has no verdict yet.

Usage:
  python eval/build_labeling_corpus.py
  python eval/build_labeling_corpus.py --extend --repos microsoft/vscode,rust-lang/rust
  python eval/build_labeling_corpus.py --extend --feeds  # status pages + CI
  python eval/build_labeling_corpus.py --extend --drop-source bgl://llnl/bluegene
  python eval/build_labeling_corpus.py --rebuild        # discards labels' basis
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
from aiops.sources.github_actions import GitHubActionsSource
from aiops.sources.github_issues import GitHubIssuesSource
from aiops.sources.log_file import LogFileSource
from aiops.sources.statuspage import StatuspageSource
from aiops.store import Store

DB = ROOT / "eval" / "labeling.sqlite"
SNAPSHOT = ROOT / "eval" / "labeling_corpus.json"

LOGS = [
    ("corpus/data/OpenSSH/OpenSSH_full.log", "syslog", "syslog://labsz/sshd",
     7, 2500),
    ("corpus/data/Apache/Apache_full.log", "apache_error", "apache://web-1",
     11, 3000),
    ("corpus/data/OpenStack/OpenStack_full.log", "openstack",
     "openstack://cloud", 40, 5000),
    ("corpus/data/Zookeeper/Zookeeper_full.log", "zookeeper",
     "zookeeper://quorum", 14, 5000),
    ("corpus/data/Linux/Linux_full.log", "syslog", "syslog://combo", 4, 5000),
    # the first 80,000 lines of Loghub's BGL.log; every line carries the label
    # its operators applied, which is what eval/bgl_report.py scores against
    ("corpus/data/BGL/BGL_slice.log", "bgl", "bgl://llnl/bluegene", 8, 10000),
]
REPOS = ["huggingface/transformers", "vercel/next.js", "pytorch/pytorch",
         "langchain-ai/langchain", "microsoft/vscode", "kubernetes/kubernetes"]
STATUS_PAGES = ["www.cloudflarestatus.com", "www.githubstatus.com",
                "status.openai.com", "status.datadoghq.com"]
CI_BRANCHES = [("pytorch/pytorch", "main"), ("microsoft/vscode", "main"),
               ("huggingface/transformers", "main")]
CI_RUNS_PER_REPO = 50
CI_DAYS_BACK = 14
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


def ingest_feeds(store: Store) -> None:
    for page in STATUS_PAGES:
        events = list(StatuspageSource(page=page).fetch())
        print(f"  {page}: {store.insert_events(events)} incidents")
    since = (datetime.now(timezone.utc)
             - timedelta(days=CI_DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for repo, branch in CI_BRANCHES:
        events = list(GitHubActionsSource(
            repo=repo, branch=branch,
            per_page=CI_RUNS_PER_REPO).fetch(cursor=since))
        print(f"  {repo} CI: {store.insert_events(events)} failed runs")


def drop_source(store: Store, source: str) -> None:
    """Remove one source's events. Cluster ids hash each cluster's earliest
    event, so the next recluster gives surviving clusters their old ids and
    prunes the ones left empty."""
    n = store.db.execute("DELETE FROM events WHERE source = ?",
                         (source,)).rowcount
    store.db.commit()
    print(f"  dropped {n} events from {source}")


def ingest(store: Store, repos: list[str], logs=LOGS) -> None:
    for path, fmt, source, stride, keep in logs:
        sample = sample_log(path, stride, keep)
        events = list(LogFileSource(path=str(sample), format=fmt,
                                    source=source).fetch())
        print(f"  {Path(path).name}: {store.insert_events(events)} events")

    since = (datetime.now(timezone.utc)
             - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for repo in repos:
        events = list(itertools.islice(
            GitHubIssuesSource(repo=repo, max_pages=4).fetch(cursor=since),
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


def main(argv: list[str]) -> None:
    rebuild, extend = "--rebuild" in argv, "--extend" in argv
    # extending re-reads every log sample (ids are deterministic, so what is
    # already stored is ignored) but fetches issues only when asked: new issues
    # would be unlabelled additions to a labelled set
    repos = [] if extend else REPOS
    if "--repos" in argv:
        repos = argv[argv.index("--repos") + 1].split(",")
    global ISSUES_PER_REPO, DAYS_BACK
    if "--per-repo" in argv:
        ISSUES_PER_REPO = int(argv[argv.index("--per-repo") + 1])
    if "--days" in argv:
        DAYS_BACK = int(argv[argv.index("--days") + 1])
    if DB.exists() and not (rebuild or extend):
        sys.exit(f"{DB.name} already exists - labels are tied to it. "
                 f"Use --extend to add sources, or --rebuild to discard.")
    labels = ROOT / "eval" / "labels.csv"
    if rebuild and labels.exists():
        sys.exit(f"refusing to rebuild: {labels.name} exists and its labels are "
                 f"tied to this corpus. Move it aside first if you mean it.")
    if DB.exists() and rebuild:
        DB.unlink()
    load_env(str(ROOT / ".env"))

    store = Store(str(DB))
    if "--drop-source" in argv:
        drop_source(store, argv[argv.index("--drop-source") + 1])
    print("ingest:")
    ingest(store, repos)
    if "--feeds" in argv or not extend:
        ingest_feeds(store)
    pipe = Pipeline(store, sources=[])
    print(f"cluster: {pipe.cluster()}", flush=True)
    print(f"clusters: {len(store.list_clusters())}")
    print("triage:")
    triage_until_done(pipe)
    write_snapshot(store)

    triaged = sum(1 for c in store.list_clusters()
                  if store.get_verdict(c["id"]))
    print()
    print(f"ready: {store.count_events()} events, "
          f"{len(store.list_clusters())} clusters, {triaged} with verdicts")
    print(f"label with: python eval/label.py {DB.relative_to(ROOT)} "
          f"eval/labels.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
