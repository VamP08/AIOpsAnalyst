import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from export_demo import offsets_ms, replay_window

from aiops.envelope import Event


def event(eid, time, cluster="log-a", title="a line"):
    e = Event(id=eid, source="bgl://llnl/bluegene", type="dev.aiops.log.line",
              time=time, title=title)
    return Event(**{**e.__dict__, "clusterid": cluster})


EVENTS = [
    event("e1", "2005-06-05T00:07:59.000000"),
    event("e2", "2005-06-05T00:08:13.410695"),
    event("e3", "2005-06-05T00:08:14.410695"),
    event("e4", "2005-06-05T00:11:00.000000"),
]


def test_window_keeps_only_events_inside_the_range():
    picked = replay_window(EVENTS, "2005-06-05T00:08", "2005-06-05T00:10")
    assert [e.id for e in picked] == ["e2", "e3"]


def test_window_returns_events_in_time_order():
    shuffled = [EVENTS[2], EVENTS[1]]
    picked = replay_window(shuffled, "2005-06-05T00:08", "2005-06-05T00:10")
    assert [e.id for e in picked] == ["e2", "e3"]


def test_offsets_are_milliseconds_from_the_first_event():
    picked = replay_window(EVENTS, "2005-06-05T00:08", "2005-06-05T00:10")
    assert offsets_ms(picked) == [0, 1000]


def test_offsets_of_nothing_is_nothing():
    assert offsets_ms([]) == []


def test_compact_keeps_text_for_first_samples_and_every_alert():
    from export_demo import compact

    stream = [
        {"ms": 0, "cluster": "a", "line": "first a", "alert": False},
        {"ms": 1, "cluster": "a", "line": "second a", "alert": False},
        {"ms": 2, "cluster": "a", "line": "third a", "alert": False},
        {"ms": 3, "cluster": "a", "line": "fourth a", "alert": False},
        {"ms": 4, "cluster": "a", "line": "alerting a", "alert": True},
        {"ms": 5, "cluster": "b", "line": "first b", "alert": False},
    ]
    out = compact(stream, samples=3)
    assert [e.get("line") for e in out] == [
        "first a", "second a", "third a", None, "alerting a", "first b"]
    # counts and timing are untouched: only text is dropped
    assert [e["ms"] for e in out] == [0, 1, 2, 3, 4, 5]
    assert sum(e["alert"] for e in out) == 1


def test_cluster_rows_carry_timing_and_samples_for_a_static_dashboard(tmp_path):
    from export_demo import cluster_rows

    from aiops.store import Store

    store = Store(str(tmp_path / "db.sqlite"))
    events = [Event(id=f"e{i}", source="s", type="dev.aiops.log.line",
                    title=f"Failed password {i}", time=f"2026-09-0{i + 1}T10:00:00")
              for i in range(3)]
    store.insert_events(events)
    store.assign_clusters({e.id: "log-a" for e in events},
                          {"log-a": ("Failed password <*>", "log")})

    [row] = cluster_rows(store)
    assert row["first"] == "2026-09-01T10:00:00"
    assert row["last"] == "2026-09-03T10:00:00"
    assert len(row["samples"]) == 3
    assert row["samples"][0]["title"] == "Failed password 0"
