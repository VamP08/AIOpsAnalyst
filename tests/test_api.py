from fastapi.testclient import TestClient

from aiops.envelope import Event
from aiops.store import Store
from aiops.triage.llm import Reply
from server.app import create_app


def seeded_store(tmp_path):
    store = Store(str(tmp_path / "db.sqlite"))
    log_events = [Event(id=f"l{i}", source="syslog://web-1/nginx",
                        type="dev.aiops.log.line",
                        title=f"Failed password for root from 10.0.0.{i}")
                  for i in range(3)]
    issue = Event(id="i1", source="github://acme/widget",
                  type="com.github.issue", title="Crash on empty config",
                  body="Traceback follows",
                  url="https://github.com/acme/widget/issues/42")
    store.insert_events([*log_events, issue])
    store.assign_clusters(
        {**{e.id: "log-aaa" for e in log_events}, "i1": "prose-bbb"},
        {"log-aaa": ("Failed password for <*> from <*>", "log"),
         "prose-bbb": ("Crash on empty config", "prose")})
    store.upsert_verdict("log-aaa", {
        "category": "error", "severity": "medium", "summary": "auth failures",
        "confidence": 0.92, "evidence": ["l0"], "tier": "auto",
        "model": "m", "promptversion": "1.1"})
    return store


def client(tmp_path, chat=None):
    return TestClient(create_app(seeded_store(tmp_path), chat=chat))


def test_stats_reports_corpus_shape_and_compression(tmp_path):
    body = client(tmp_path).get("/api/stats").json()
    assert body["events"] == 4
    assert body["clusters"] == 2
    assert body["triaged"] == 1
    assert body["compression"] == 2.0
    assert body["by_tier"] == {"auto": 1}
    assert body["by_category"] == {"error": 1}


def test_clusters_listing_joins_verdicts_and_sorts_by_size(tmp_path):
    rows = client(tmp_path).get("/api/clusters").json()
    assert [r["id"] for r in rows] == ["log-aaa", "prose-bbb"]
    assert rows[0]["size"] == 3
    assert rows[0]["category"] == "error"
    assert rows[0]["confidence"] == 0.92
    assert rows[1]["category"] is None


def test_clusters_can_be_filtered_by_category(tmp_path):
    rows = client(tmp_path).get("/api/clusters?category=error").json()
    assert [r["id"] for r in rows] == ["log-aaa"]


def test_cluster_detail_carries_evidence_events(tmp_path):
    body = client(tmp_path).get("/api/clusters/log-aaa").json()
    assert body["label"] == "Failed password for <*> from <*>"
    assert body["verdict"]["model"] == "m"
    assert len(body["events"]) == 3
    assert body["events"][0]["title"].startswith("Failed password")


def test_unknown_cluster_is_404(tmp_path):
    assert client(tmp_path).get("/api/clusters/nope").status_code == 404


def test_triage_text_classifies_a_pasted_event_without_storing_it(tmp_path):
    seen = {}

    def fake_chat(messages, **kwargs):
        seen["user"] = messages[1]["content"]
        return Reply('{"category": "performance", "severity": "high", '
                     '"summary": "checkout is slow", "confidence": 0.64, '
                     '"evidence": ["pasted"]}', "test-model")

    c = client(tmp_path, chat=fake_chat)
    body = c.post("/api/triage", json={"text": "checkout p99 2400ms"}).json()
    assert body["category"] == "performance"
    # 0.64 is below the suggest threshold and severity is high: a human gets it
    assert body["tier"] == "escalate"
    assert body["model"] == "test-model"
    assert "checkout p99 2400ms" in seen["user"]
    assert c.get("/api/stats").json()["events"] == 4


def test_triage_text_reports_unavailable_when_no_provider_answers(tmp_path):
    c = client(tmp_path, chat=lambda messages, **kw: None)
    r = c.post("/api/triage", json={"text": "anything"})
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()


def test_triage_text_rejects_empty_input(tmp_path):
    r = client(tmp_path).post("/api/triage", json={"text": "   "})
    assert r.status_code == 422
