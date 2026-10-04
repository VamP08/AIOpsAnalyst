import textwrap

from aiops.pipeline import Pipeline


def make_pipeline(tmp_path):
    config = tmp_path / "pipeline.yaml"
    config.write_text(textwrap.dedent(f"""
        store: {(tmp_path / "db.sqlite").as_posix()}
        sources: []
    """), encoding="utf-8")
    return Pipeline.from_yaml(str(config))


def fake_encoder(texts):
    return [[1.0, 0.0] if "crash" in t.lower() else [0.0, 1.0] for t in texts]


def seed(store):
    from aiops.envelope import Event
    store.insert_events([
        Event(id="l1", source="s", type="dev.aiops.log.line",
              title="Connection timeout to 10.0.0.5 after 30s"),
        Event(id="l2", source="s", type="dev.aiops.log.line",
              title="Connection timeout to 10.0.0.9 after 12s"),
        Event(id="i1", source="g", type="com.github.issue",
              title="Crash when config is empty"),
        Event(id="i2", source="g", type="com.github.issue",
              title="Crash if the config file is empty"),
        Event(id="i3", source="g", type="com.github.issue",
              title="Add dark mode please"),
    ])


def test_cluster_stage_dispatches_by_type_and_persists(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    counts = pipe.cluster(prose_encoder=fake_encoder)
    assert counts == {"log": 2, "prose": 3}

    logs = [pipe.store.get_event(i) for i in ("l1", "l2")]
    assert logs[0].clusterid == logs[1].clusterid
    assert logs[0].clusterid.startswith("log-")

    issues = [pipe.store.get_event(i) for i in ("i1", "i2", "i3")]
    assert issues[0].clusterid == issues[1].clusterid
    assert issues[2].clusterid != issues[0].clusterid

    tiers = {c["tier"] for c in pipe.store.list_clusters()}
    assert tiers == {"log", "prose"}


def test_recluster_is_idempotent(tmp_path):
    # the stage reclusters the whole corpus each run: stateless and
    # deterministic, so a rerun changes nothing
    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    first = pipe.cluster(prose_encoder=fake_encoder)
    before = {e: pipe.store.get_event(e).clusterid
              for e in ("l1", "l2", "i1", "i2", "i3")}
    second = pipe.cluster(prose_encoder=fake_encoder)
    after = {e: pipe.store.get_event(e).clusterid
             for e in ("l1", "l2", "i1", "i2", "i3")}
    assert first == second
    assert before == after


def test_every_non_log_event_type_is_clustered_as_prose(tmp_path):
    from aiops.envelope import Event
    pipe = make_pipeline(tmp_path)
    pipe.store.insert_events([
        Event(id="s1", source="statuspage://x", type="com.statuspage.incident",
              title="Elevated error rates in Europe"),
        Event(id="r1", source="github://a/b/actions",
              type="com.github.workflow_run", title="CI failed on main: test"),
    ])
    assert pipe.cluster(prose_encoder=fake_encoder) == {"prose": 2}
    assert all(pipe.store.get_event(i).clusterid for i in ("s1", "r1"))


def test_recluster_drops_clusters_left_without_events(tmp_path):
    pipe = make_pipeline(tmp_path)
    seed(pipe.store)
    pipe.cluster(prose_encoder=fake_encoder)
    dark_mode = pipe.store.get_event("i3").clusterid
    pipe.store.upsert_verdict(dark_mode, {
        "category": "feature_request", "severity": "low", "summary": "s",
        "confidence": 0.9, "evidence": [], "tier": "auto", "model": "m",
        "promptversion": "1.1"})
    pipe.store.db.execute("DELETE FROM events WHERE id = 'i3'")
    pipe.store.db.commit()

    pipe.cluster(prose_encoder=fake_encoder)
    assert dark_mode not in {c["id"] for c in pipe.store.list_clusters()}
    assert pipe.store.get_verdict(dark_mode) is None
