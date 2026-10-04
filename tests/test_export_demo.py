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


def _triaged_store(tmp_path, tier="auto", severity="high", confidence=0.95,
                   category="crash", ticket="AIOPS-7"):
    from aiops.store import Store

    store = Store(str(tmp_path / "db.sqlite"))
    events = [Event(id=f"i{i}", source="github://acme/widget",
                    type="com.github.issue", subject=str(40 + i),
                    title=f"App crashes on start {i}", body="Traceback " * 80,
                    url=f"https://github.com/acme/widget/issues/{40 + i}",
                    time=f"2026-09-0{i + 1}T10:00:00Z")
              for i in range(5)]
    store.insert_events(events)
    store.assign_clusters({e.id: "prose-a" for e in events},
                          {"prose-a": ("App crashes on start 0", "prose")})
    store.upsert_verdict("prose-a", {
        "category": category, "severity": severity, "summary": "It crashes.",
        "confidence": confidence, "evidence": [], "tier": tier, "model": "m",
        "promptversion": "1.1"})
    if ticket:
        store.record_routed("prose-a", "tickets", ticket)
    return store


def test_specimen_follows_one_event_from_input_to_ticket(tmp_path):
    from export_demo import specimen

    s = specimen(_triaged_store(tmp_path), "prose-a")
    assert s["input"]["title"] == "App crashes on start 0"
    assert s["input"]["url"] == "https://github.com/acme/widget/issues/40"
    assert s["input"]["type"] == "com.github.issue"
    assert len(s["input"]["body"]) <= 300
    assert s["cluster"]["size"] == 5
    assert s["cluster"]["siblings"] == ["App crashes on start 1",
                                        "App crashes on start 2",
                                        "App crashes on start 3"]
    assert s["verdict"] == {"category": "crash", "severity": "high",
                            "confidence": 0.95, "summary": "It crashes."}
    assert s["route"]["tier"] == "auto"
    assert s["route"]["rule"] == 1          # row of policy.json that matched
    assert "0.95" in s["route"]["why"]
    assert s["route"]["ticket"] == {"key": "AIOPS-7", "type": "Bug",
                                    "summary": "[crash] It crashes."}


def test_specimen_that_escalates_has_no_ticket(tmp_path):
    from export_demo import specimen

    store = _triaged_store(tmp_path, tier="escalate", severity="critical",
                           ticket=None)
    s = specimen(store, "prose-a")
    assert s["route"]["tier"] == "escalate"
    assert s["route"]["rule"] == 0
    assert s["route"]["ticket"] is None


def test_policy_export_carries_gate_rules_and_routes():
    from export_demo import policy_export

    routes = [{"tiers": ["auto"], "categories": ["crash"], "sink": "tickets"}]
    p = policy_export(routes)
    assert p["gate"][0] == {"condition": "severity is critical",
                            "tier": "escalate"}
    assert p["routes"] == routes
    assert p["thresholds"] == {"auto": 0.9, "suggest": 0.7}


def test_stats_separate_what_the_policy_matched_from_tickets_filed():
    from export_demo import stats_from

    routes = [{"tiers": ["auto"], "categories": ["crash"], "sink": "tickets"}]
    rows = [
        {"category": "crash", "tier": "auto", "ticket": "AIOPS-1", "source": "prose", "kind": "issue"},
        {"category": "crash", "tier": "auto", "ticket": None, "source": "prose", "kind": "issue"},
        {"category": "crash", "tier": "suggest", "ticket": None, "source": "log", "kind": "issue"},
    ]
    stats = stats_from(rows, events=10, routes=routes)
    assert stats["route_matched"] == 2
    assert stats["tickets"] == 1


def test_kind_names_the_source_a_reader_would_recognise():
    from export_demo import kind

    assert kind("com.github.issue", "github://a/b") == "issue"
    assert kind("com.github.workflow_run", "github://a/b/actions") == "ci"
    assert kind("com.statuspage.incident", "statuspage://x") == "status"
    assert kind("dev.aiops.log.line", "bgl://llnl/bluegene") == "supercomputer"
    assert kind("dev.aiops.log.line", "syslog://combo") == "log"


def test_outcome_partitions_every_tier():
    from export_demo import outcome
    from aiops.pipeline import Pipeline

    policy = Pipeline(store=None, sources=[], routes=[
        {"tiers": ["auto"], "categories": ["crash"], "sink": "tickets"}])
    assert outcome({"tier": "auto", "category": "crash"}, policy) == "ticket"
    assert outcome({"tier": "auto", "category": "noise"}, policy) == "dropped"
    assert outcome({"tier": "escalate", "category": "crash"}, policy) == "person"
    assert outcome({"tier": "suggest", "category": "crash"}, policy) == "draft"
    assert outcome({"tier": "abstain", "category": "crash"}, policy) == "unsure"


def test_stats_outcomes_sum_to_the_clusters():
    from export_demo import stats_from

    routes = [{"tiers": ["auto"], "categories": ["crash"], "sink": "tickets"}]
    rows = [
        {"category": "crash", "tier": "auto", "ticket": None, "source": "prose", "kind": "issue"},
        {"category": "noise", "tier": "auto", "ticket": None, "source": "log", "kind": "log"},
        {"category": "crash", "tier": "escalate", "ticket": None, "source": "log", "kind": "log"},
        {"category": "error", "tier": "suggest", "ticket": None, "source": "prose", "kind": "ci"},
        {"category": "error", "tier": "abstain", "ticket": None, "source": "prose", "kind": "status"},
    ]
    stats = stats_from(rows, events=50, routes=routes)
    assert stats["outcomes"] == {"ticket": 1, "dropped": 1, "person": 1,
                                 "draft": 1, "unsure": 1}
    assert sum(stats["outcomes"].values()) == stats["clusters"]
    assert stats["by_kind"] == {"issue": 1, "log": 2, "ci": 1, "status": 1}


def test_events_by_kind_counts_arrivals_per_source_kind(tmp_path):
    from export_demo import events_by_kind

    from aiops.store import Store

    store = Store(str(tmp_path / "db.sqlite"))
    store.insert_events([
        Event(id="i1", source="github://a/b", type="com.github.issue", title="x"),
        Event(id="l1", source="syslog://h", type="dev.aiops.log.line", title="y"),
        Event(id="l2", source="syslog://h", type="dev.aiops.log.line", title="z"),
        Event(id="b1", source="bgl://llnl/bluegene", type="dev.aiops.log.line", title="w"),
    ])
    assert events_by_kind(store) == {"issue": 1, "log": 2, "supercomputer": 1}
