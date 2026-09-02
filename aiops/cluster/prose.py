"""Tier-3 clustering: human text (issues, tickets) in two stages.

Stage 1, MinHash LSH: collapses lexical near-duplicates in O(n) — cheap, but
"fast car" and "quick automobile" look unrelated to it. Stage 2, sentence
embeddings over one representative per group: cosine edges above a threshold,
connected components. Deliberately no UMAP/HDBSCAN — they cluster prettier but
non-deterministically, and the M2 gate requires two identical runs.
"""
import re
from itertools import combinations
from math import sqrt

from datasketch import MinHash, MinHashLSH

from aiops.envelope import Event

_WORD = re.compile(r"[a-z0-9]+")
_NUM_PERM = 128
_model = None


def _default_encoder(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model.encode(texts, show_progress_bar=False).tolist()


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class _UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, i):
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


class ProseClusterer:
    def __init__(self, encoder=None, threshold: float = 0.8,
                 lsh_threshold: float = 0.7):
        self.encoder = encoder or _default_encoder
        self.threshold = threshold
        self.lsh_threshold = lsh_threshold

    def assign(self, events: list[Event]) -> dict[str, str]:
        texts = {e.id: f"{e.title}\n{e.body or ''}".strip() for e in events}
        uf = _UnionFind(texts)

        lsh = MinHashLSH(threshold=self.lsh_threshold, num_perm=_NUM_PERM)
        for e in events:
            mh = MinHash(num_perm=_NUM_PERM)
            for token in set(_WORD.findall(texts[e.id].lower())):
                mh.update(token.encode())
            for candidate in lsh.query(mh):
                uf.union(e.id, candidate)
            lsh.insert(e.id, mh)

        representatives = []
        seen_roots = set()
        for e in events:
            root = uf.find(e.id)
            if root not in seen_roots:
                seen_roots.add(root)
                representatives.append(e.id)
        vectors = dict(zip(representatives,
                           self.encoder([texts[r] for r in representatives])))
        # ponytail: O(n^2) over group representatives; ANN index if reps exceed ~5k
        for a, b in combinations(representatives, 2):
            if _cosine(vectors[a], vectors[b]) >= self.threshold:
                uf.union(a, b)

        cluster_ids: dict[str, str] = {}
        assignment = {}
        for e in events:
            root = uf.find(e.id)
            if root not in cluster_ids:
                cluster_ids[root] = f"prose-{len(cluster_ids) + 1}"
            assignment[e.id] = cluster_ids[root]
        return assignment
