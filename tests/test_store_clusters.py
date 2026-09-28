from aiops.envelope import Event
from aiops.store import Store


def make_event(i):
    return Event(id=f"e{i}", source="s", type="dev.aiops.log.line",
                 title=f"line {i}")


def test_assign_clusters_updates_events_and_upserts_clusters(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1), make_event(2), make_event(3)])
    store.assign_clusters(
        {"e1": "log-1", "e2": "log-1", "e3": "log-2"},
        {"log-1": ("Connection timeout to <*>", "log"),
         "log-2": ("Disk full on <*>", "log")})
    assert store.get_event("e1").clusterid == "log-1"
    assert store.get_event("e3").clusterid == "log-2"
    clusters = {c["id"]: c for c in store.list_clusters()}
    assert clusters["log-1"]["size"] == 2
    assert clusters["log-1"]["label"] == "Connection timeout to <*>"
    assert clusters["log-1"]["tier"] == "log"
    assert clusters["log-2"]["size"] == 1


def test_unclustered_events_returns_only_events_without_cluster(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1), make_event(2)])
    store.assign_clusters({"e1": "log-1"}, {"log-1": ("t", "log")})
    pending = store.unclustered_events()
    assert [e.id for e in pending] == ["e2"]


def test_reassigning_updates_size_and_label(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1), make_event(2)])
    store.assign_clusters({"e1": "log-1"}, {"log-1": ("old", "log")})
    store.assign_clusters({"e2": "log-1"}, {"log-1": ("new", "log")})
    [cluster] = store.list_clusters()
    assert cluster["size"] == 2
    assert cluster["label"] == "new"


def test_routed_map_returns_every_clusters_sinks_in_one_query(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1), make_event(2)])
    store.assign_clusters({"e1": "log-1", "e2": "log-2"},
                          {"log-1": ("t1", "log"), "log-2": ("t2", "log")})
    store.record_routed("log-1", "tickets", "AIOPS-7")
    store.record_routed("log-1", "chat", None)
    assert store.routed_map() == {"log-1": {"tickets": "AIOPS-7", "chat": ""}}
