"""Questions about the corpus, answered from the store rather than by a model.

Three kinds of question arrive at a triage system, and only one of them wants
prose:

  "when did X start"     -> a timestamp. SQL knows it exactly; a model would
                            approximate it from whatever text it was shown.
  "how many X"           -> a count. Same argument, more so.
  "what is failing"      -> a ranked list of clusters, each already carrying
                            its verdict and its evidence.

So retrieval finds the clusters and SQL answers the question, and every answer
names the clusters and sample events it came from. Nothing here calls an LLM:
the triage stage already did that, per cluster, and asking a model to re-read
the answer would only add a way to be wrong.

Retrieval is lexical and semantic together. Full-text search is exact and free
and handles most questions, but it cannot connect "Tomcat connector" to a
template that only ever says mod_jk. Running the semantic pass only when the
lexical one came back short does not help either: a bag of common words like
"what is failing on the web server" fills every slot with weak matches and
hides the gap. So both passes run, lexical hits keep their position, and
semantic hits fill in behind them. Cluster vectors are computed once per store
and reused.
"""
import re
from math import sqrt

WHEN = re.compile(r"\b(when|since when|what time|how long|start(ed)?|begin|"
                  r"began|first|last seen)\b", re.I)
COUNT = re.compile(r"\b(how many|how much|count|number of|total)\b", re.I)


def classify(question: str) -> str:
    if COUNT.search(question):
        return "count"
    if WHEN.search(question):
        return "when"
    return "what"


_model = None


def _default_encoder(texts: list[str]) -> list[list[float]]:
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model.encode(texts, show_progress_bar=False).tolist()


def _cosine(a, b) -> float:
    na, nb = sqrt(sum(x * x for x in a)), sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


# out of five results, two are held for the semantic pass
RESERVED_FOR_SEMANTIC = 2

_vector_cache: dict[int, tuple[list[dict], list[list[float]]]] = {}


def _cluster_vectors(store, encoder):
    """Embed every cluster once per store; the corpus changes between runs,
    not between questions."""
    key = id(store)
    if key not in _vector_cache:
        rows, texts = [], []
        for cluster in store.list_clusters():
            verdict = store.get_verdict(cluster["id"]) or {}
            rows.append(cluster)
            texts.append(f"{cluster['label']} {verdict.get('summary') or ''}")
        _vector_cache[key] = (rows, encoder(texts) if texts else [])
    return _vector_cache[key]


def _semantic(store, question: str, encoder, wanted: int,
              threshold: float = 0.3) -> list[dict]:
    """Rank clusters by similarity to the question, for the wording the corpus
    never uses."""
    rows, vectors = _cluster_vectors(store, encoder)
    if not rows:
        return []
    query = encoder([question])[0]
    rest = vectors
    scored = [(( _cosine(query, vector)), row)
              for vector, row in zip(rest, rows)]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [{"id": row["id"], "label": row["label"], "tier": row["tier"],
             "rank": -score, "how": "semantic"}
            for score, row in scored[:wanted] if score >= threshold]


def _match(store, question: str, limit: int, encoder=None) -> list[dict]:
    hits = [{**h, "how": "lexical"}
            for h in store.search_clusters(question, limit=limit)]
    if encoder is not False:
        seen = {h["id"] for h in hits}
        try:
            semantic = [h for h in _semantic(store, question,
                                             encoder or _default_encoder, limit)
                        if h["id"] not in seen]
        except ImportError:
            # a minimal install has no embeddings; lexical search is the whole
            # answer then, which is worse for unusual wording and fine for the
            # rest, so it degrades rather than failing
            semantic = []
        # reserve seats rather than appending: a question full of common words
        # fills every lexical slot with weak matches, and appending after them
        # means the semantic pass can never be seen
        reserved = min(RESERVED_FOR_SEMANTIC, len(semantic), limit)
        hits = hits[:limit - reserved] + semantic[:reserved]
    out = []
    for hit in hits:
        verdict = store.get_verdict(hit["id"]) or {}
        span = store.timespan(hit["id"])
        out.append({**hit, **span,
                    "category": verdict.get("category"),
                    "severity": verdict.get("severity"),
                    "summary": verdict.get("summary"),
                    "confidence": verdict.get("confidence"),
                    "tier": verdict.get("tier")})
    return out


def _evidence(store, cluster_id: str, limit: int = 3) -> list[dict]:
    return [{"id": e.id, "title": e.title, "url": e.url, "time": e.time}
            for e in store.events_in_cluster(cluster_id, limit)]


def answer(store, question: str, limit: int = 5, encoder=None) -> dict:
    """encoder=False disables the semantic pass, which is how the lexical-only
    number in the scorecard is reproduced."""
    kind = classify(question)
    matches = _match(store, question, limit, encoder)
    if not matches:
        return {"question": question, "kind": "none", "matches": [],
                "evidence": [],
                "answer": "Nothing in the corpus matches that."}

    top = matches[0]
    evidence = _evidence(store, top["id"])
    base = {"question": question, "matches": matches, "evidence": evidence}

    if kind == "count":
        events = sum(m["events"] for m in matches)
        return {**base, "kind": "count", "events": events,
                "clusters": len(matches),
                "answer": f"{events:,} events in {len(matches)} cluster"
                          f"{'' if len(matches) == 1 else 's'}."}

    if kind == "when":
        return {**base, "kind": "when", "cluster": top,
                "first": top["first"], "last": top["last"],
                "answer": f"First seen {top['first']}, last seen {top['last']}, "
                          f"{top['events']:,} events."}

    return {**base, "kind": "what",
            "answer": f"{len(matches)} matching cluster"
                      f"{'' if len(matches) == 1 else 's'}, "
                      f"strongest: {top.get('summary') or top['label']}"}
