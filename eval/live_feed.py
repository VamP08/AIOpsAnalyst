"""Triage whatever the watched repositories have posted lately.

The corpus behind the published numbers is frozen on purpose: a scorecard that
moves whenever a stranger opens an issue is not a measurement. This is the
other half - a small rolling feed that shows the pipeline still runs, written to
demo/data/live.json and committed by the scheduled workflow, so the page can say
when it last saw something and the commit history shows it was not staged.

Each run works in a throwaway store: fetch recent issues, cluster them, triage
the clusters, and merge the results into the feed. Nothing here touches the
evaluation corpus.

Usage: python eval/live_feed.py demo/data/live.json [--repos a/b,c/d] [--per-repo 8]
"""
import itertools
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiops.envfile import load_env
from aiops.pipeline import Pipeline
from aiops.sources.github_issues import GitHubIssuesSource
from aiops.store import Store

REPOS = ["huggingface/transformers", "vercel/next.js", "langchain-ai/langchain"]
PER_REPO = 8
CAP = 60


def lexical_encoder(texts: list[str]) -> list[list[float]]:
    """Stand-in for sentence embeddings when they are not installed.

    The scheduled run clusters a couple of dozen issues, which does not justify
    pulling PyTorch into the job. Hashing each text to a fixed unit vector keeps
    the embedding stage honest in the only way that still holds without a model:
    identical text matches itself, different text does not collapse together,
    and near-duplicate wording is left to the MinHash stage that runs first.
    """
    import hashlib
    import math

    vectors = []
    for text in texts:
        digest = hashlib.sha256(text.encode()).digest()
        raw = [b - 127.5 for b in digest[:16]]
        length = math.sqrt(sum(v * v for v in raw)) or 1.0
        vectors.append([v / length for v in raw])
    return vectors


def encoder():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        print("sentence-transformers not installed: clustering this feed "
              "lexically", file=sys.stderr)
        return lexical_encoder
    return None                                  # the default MiniLM encoder


def merge(existing: list[dict], fresh: list[dict], cap: int = CAP) -> list[dict]:
    """Newest first, one entry per cluster, capped. A cluster seen again
    replaces its earlier entry instead of appearing twice."""
    by_id = {entry["id"]: entry for entry in existing}
    for entry in fresh:
        by_id[entry["id"]] = entry
    ordered = sorted(by_id.values(), key=lambda e: e["seen"], reverse=True)
    return ordered[:cap]


def collect(repos: list[str], per_repo: int, hours: int = 24) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    store = Store(str(Path(tempfile.mkdtemp()) / "live.sqlite"))
    for repo in repos:
        try:
            source = GitHubIssuesSource(repo=repo, max_pages=1)
            store.insert_events(
                itertools.islice(source.fetch(cursor=since), per_repo))
        except Exception as e:                       # one repo must not stop the run
            print(f"{repo}: {type(e).__name__}: {e}", file=sys.stderr)
    if not store.count_events():
        return []

    pipeline = Pipeline(store, sources=[], routes=[])
    pipeline.cluster(prose_encoder=encoder())
    pipeline.triage(pause=3)

    seen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    feed = []
    for cluster in store.list_clusters():
        verdict = store.get_verdict(cluster["id"])
        if not verdict:
            continue
        events = store.events_in_cluster(cluster["id"], 1)
        feed.append({
            "id": cluster["id"],
            "seen": seen,
            "repo": events[0].source.removeprefix("github://") if events else "",
            "url": events[0].url if events else None,
            "title": cluster["label"],
            "summary": verdict["summary"],
            "category": verdict["category"],
            "severity": verdict["severity"],
            "confidence": verdict["confidence"],
            "tier": verdict["tier"],
            "model": verdict["model"],
            "size": cluster["size"],
        })
    return feed


def main(out_path: str, repos: list[str], per_repo: int) -> None:
    load_env()
    out = Path(out_path)
    existing = json.loads(out.read_text(encoding="utf-8")).get("entries", []) \
        if out.exists() else []
    fresh = collect(repos, per_repo)
    entries = merge(existing, fresh)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repos": repos,
        "entries": entries,
    }, separators=(",", ":")), encoding="utf-8")
    print(f"{len(fresh)} triaged this run, {len(entries)} in the feed -> {out}")


if __name__ == "__main__":
    argv = sys.argv[1:]
    repos = (argv[argv.index("--repos") + 1].split(",")
             if "--repos" in argv else REPOS)
    per_repo = (int(argv[argv.index("--per-repo") + 1])
                if "--per-repo" in argv else PER_REPO)
    main(argv[0] if argv else "demo/data/live.json", repos, per_repo)
