from aiops.cluster.drain import LogClusterer
from aiops.cluster.prose import ProseClusterer
from aiops.envelope import Event

DISK = "Disk full on /dev/sda1"
TIMEOUT = "Connection timeout to 10.0.0.5 after 30s"


def log_event(event_id, line):
    return Event(id=event_id, source="s", type="dev.aiops.log.line",
                 title=line, raw=line)


def test_log_cluster_id_survives_a_new_cluster_appearing_before_it():
    # same event, different corpus position: the id must not move with it,
    # or every stored verdict reattaches to the wrong cluster on a recluster
    first = LogClusterer().assign([log_event("x1", DISK)])
    second = LogClusterer().assign([log_event("y1", TIMEOUT),
                                    log_event("x1", DISK)])
    assert first["x1"] == second["x1"]
    assert second["y1"] != second["x1"]


def test_log_cluster_id_is_not_a_counter():
    assignment = LogClusterer().assign([log_event("x1", DISK)])
    assert assignment["x1"] != "log-1"
    assert assignment["x1"].startswith("log-")


def test_log_clusters_listing_uses_the_same_ids():
    clusterer = LogClusterer()
    assignment = clusterer.assign([log_event("x1", DISK),
                                   log_event("x2", DISK)])
    listed = {cid for cid, _, _ in clusterer.clusters()}
    assert listed == {assignment["x1"]}


def issue_event(event_id, title):
    return Event(id=event_id, source="g", type="com.github.issue", title=title)


def fake_encoder(texts):
    return [[1.0, 0.0] if "crash" in t.lower() else [0.0, 1.0] for t in texts]


def test_prose_cluster_id_survives_another_cluster_appearing_before_it():
    crash = "Crash on startup when config is empty"
    feature = "Please add dark mode"
    first = ProseClusterer(encoder=fake_encoder).assign(
        [issue_event("i9", crash)])
    second = ProseClusterer(encoder=fake_encoder).assign(
        [issue_event("i1", feature), issue_event("i9", crash)])
    assert first["i9"] == second["i9"]
    assert second["i9"].startswith("prose-")
    assert second["i9"] != "prose-1"
