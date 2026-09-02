import textwrap

from aiops.envelope import Event
from aiops.pipeline import Pipeline
from aiops.triage.llm import Reply

GOOD = ('{"category": "error", "severity": "medium", '
        '"summary": "Auth failures against sshd", '
        '"confidence": 0.92, "evidence": ["l1"]}')


def make_pipeline(tmp_path):
    config = tmp_path / "pipeline.yaml"
    config.write_text(textwrap.dedent(f"""
        store: {(tmp_path / "db.sqlite").as_posix()}
        sources: []
    """), encoding="utf-8")
    return Pipeline.from_yaml(str(config))


def seed_clustered(store):
    store.insert_events([
        Event(id="l1", source="s", type="dev.aiops.log.line",
              title="Failed password for root from 10.0.0.5"),
        Event(id="l2", source="s", type="dev.aiops.log.line",
              title="Failed password for root from 10.0.0.9"),
        Event(id="l3", source="s", type="dev.aiops.log.line",
              title="Disk full on /dev/sda1"),
    ])
    store.assign_clusters(
        {"l1": "log-1", "l2": "log-1", "l3": "log-2"},
        {"log-1": ("Failed password for <*> from <*>", "log"),
         "log-2": ("Disk full on <*>", "log")})


def test_triage_stores_validated_verdicts_with_provenance(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed_clustered(pipe.store)
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(messages)
        return Reply(GOOD, "test-model")

    counts = pipe.triage(chat=fake_chat)
    assert counts == {"triaged": 2, "failed": 0}
    verdict = pipe.store.get_verdict("log-1")
    assert verdict["category"] == "error"
    assert verdict["tier"] == "auto"          # 0.92 >= 0.9, severity medium
    assert verdict["model"] == "test-model"
    assert verdict["promptversion"] == "1.0"
    assert verdict["evidence"] == ["l1"]
    # cluster label and sample event titles reached the model
    user_turn = calls[0][1]["content"]
    assert "Failed password for <*> from <*>" in user_turn
    assert "l1" in user_turn


def test_triaged_clusters_are_not_reprocessed(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed_clustered(pipe.store)
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(1)
        return Reply(GOOD, "m")

    pipe.triage(chat=fake_chat)
    assert pipe.triage(chat=fake_chat) == {"triaged": 0, "failed": 0}
    assert len(calls) == 2  # one per cluster, not four


def test_pause_sleeps_between_llm_calls(tmp_path, monkeypatch):
    naps = []
    monkeypatch.setattr("time.sleep", lambda s: naps.append(s))
    pipe = make_pipeline(tmp_path)
    seed_clustered(pipe.store)
    pipe.triage(chat=lambda m, **kw: Reply(GOOD, "m"), pause=2.5)
    assert naps == [2.5]  # between calls: 2 clusters, 1 nap


def test_no_pause_by_default(tmp_path, monkeypatch):
    naps = []
    monkeypatch.setattr("time.sleep", lambda s: naps.append(s))
    pipe = make_pipeline(tmp_path)
    seed_clustered(pipe.store)
    pipe.triage(chat=lambda m, **kw: Reply(GOOD, "m"))
    assert naps == []


def test_invalid_or_missing_reply_leaves_cluster_untriaged(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed_clustered(pipe.store)

    replies = iter([Reply("not json at all", "m"), None])
    counts = pipe.triage(chat=lambda messages, **kw: next(replies))
    assert counts == {"triaged": 0, "failed": 2}
    assert pipe.store.get_verdict("log-1") is None
    # untriaged clusters are retried on the next run
    counts = pipe.triage(chat=lambda messages, **kw: Reply(GOOD, "m"))
    assert counts == {"triaged": 2, "failed": 0}
