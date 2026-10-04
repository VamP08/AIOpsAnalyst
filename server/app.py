"""Read API over a triaged store, plus the one interactive endpoint.

The public site is static (Astro, in demo/); everything dynamic it needs is
here. /api/triage is the "paste your own event" box: it classifies one pasted
event through the same prompt and gate as the pipeline, and stores nothing —
visitors must not be able to write into the corpus the numbers are measured on.
"""
import os
from collections import Counter

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator

from aiops.ask import answer
from aiops.envelope import Event
from aiops.envfile import load_env
from aiops.store import Store
from aiops.triage.gate import decide_tier
from aiops.triage.prompts import PROMPT_VERSION, build_messages
from aiops.triage.schema import parse_verdict


class PastedEvent(BaseModel):
    text: str
    title: str | None = None

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


def create_app(store: Store, chat=None) -> FastAPI:
    app = FastAPI(title="AIOpsAnalyst", docs_url="/api/docs")

    def _chat():
        if chat is not None:
            return chat
        from aiops.envfile import load_env
        from aiops.triage.llm import chat as live_chat
        load_env()
        return live_chat

    def _rows() -> list[dict]:
        routed = store.routed_map()
        return [{**cluster, **{f: None for f in
                               ("category", "severity", "summary",
                                "confidence", "verdict_tier", "model")},
                 **_verdict_fields(store.get_verdict(cluster["id"])),
                 "routed": routed.get(cluster["id"], {})}
                for cluster in store.list_clusters()]

    def _verdict_fields(verdict: dict | None) -> dict:
        if not verdict:
            return {}
        return {"category": verdict["category"], "severity": verdict["severity"],
                "summary": verdict["summary"],
                "confidence": verdict["confidence"],
                "verdict_tier": verdict["tier"], "model": verdict["model"]}

    @app.get("/api/stats")
    def stats() -> dict:
        rows = _rows()
        triaged = [r for r in rows if r["category"]]
        events = store.count_events()
        return {
            "events": events,
            "clusters": len(rows),
            "triaged": len(triaged),
            "compression": round(events / len(rows), 2) if rows else 0.0,
            "by_tier": dict(Counter(r["verdict_tier"] for r in triaged)),
            "by_category": dict(Counter(r["category"] for r in triaged)),
            "by_source_tier": dict(Counter(r["tier"] for r in rows)),
            "prompt_version": PROMPT_VERSION,
            # the page turns a ticket reference into a link with this; the
            # credentials behind it never leave the server
            "jira_base": os.environ.get("JIRA_BASE_URL", "").rstrip("/"),
        }

    @app.get("/api/clusters")
    def clusters(category: str | None = None, tier: str | None = None,
                 limit: int = 500) -> list[dict]:
        rows = _rows()
        if category:
            rows = [r for r in rows if r["category"] == category]
        if tier:
            rows = [r for r in rows if r["verdict_tier"] == tier]
        return rows[:limit]

    @app.get("/api/clusters/{cluster_id}")
    def cluster(cluster_id: str) -> dict:
        match = next((c for c in store.list_clusters()
                      if c["id"] == cluster_id), None)
        if match is None:
            raise HTTPException(404, f"no cluster {cluster_id}")
        return {**match, "verdict": store.get_verdict(cluster_id),
                "routed": store.routed(cluster_id),
                "events": [e.to_dict() | {"title": e.title}
                           for e in store.events_in_cluster(cluster_id, 10)]}

    @app.get("/api/ask")
    def ask(q: str = Query(min_length=1), limit: int = 5) -> dict:
        """Counting and timing questions are answered from SQL, and every
        answer names the clusters and events behind it. No model is called
        here: triage already classified these clusters, and asking one to
        re-read the result would only add a way to be wrong."""
        if not q.strip():
            raise HTTPException(422, "ask something")
        return answer(store, q, limit=limit)

    @app.post("/api/triage")
    def triage_text(pasted: PastedEvent) -> dict:
        event = Event(id="pasted", source="paste://demo",
                      type="dev.aiops.log.line",
                      title=pasted.title or pasted.text[:200],
                      body=pasted.text if pasted.title else None)
        reply = _chat()(build_messages(event.title, "pasted", [event]))
        verdict = parse_verdict(reply.text) if reply else None
        if verdict is None:
            raise HTTPException(
                503, "triage unavailable: no provider returned a usable verdict")
        return {**verdict.model_dump(), "tier": decide_tier(verdict),
                "model": reply.model, "prompt_version": PROMPT_VERSION}

    return app


# uvicorn server.app:app should work from a clean shell: credentials and the
# tracker URL come from .env, and a real environment variable still wins.
load_env()
app = create_app(Store(os.environ.get("AIOPS_DB", "aiops.sqlite")))
