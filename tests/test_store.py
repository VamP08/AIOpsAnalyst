from aiops.envelope import Event
from aiops.store import Store


def make_event(i=1, **overrides):
    fields = dict(
        id=f"evt-{i}",
        source="syslog://web-1/nginx",
        type="dev.aiops.log.line",
        time="2026-09-02T10:00:00Z",
        severitynumber=17,
        title=f"GET /api {i}",
        attributes={"host": "web-1"},
        raw=f"raw line {i}",
    )
    fields.update(overrides)
    return Event(**fields)


def test_insert_returns_count_and_events_are_stored(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    assert store.insert_events([make_event(1), make_event(2)]) == 2
    assert store.count_events() == 2


def test_reinsert_of_same_ids_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1), make_event(2)])
    assert store.insert_events([make_event(1), make_event(2)]) == 0
    assert store.count_events() == 2


def test_event_fields_survive_roundtrip(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1, body="details", url="http://x/1")])
    e = store.get_event("evt-1")
    assert e.title == "GET /api 1"
    assert e.severitynumber == 17
    assert e.attributes == {"host": "web-1"}
    assert e.body == "details"
    assert e.url == "http://x/1"
    assert e.raw == "raw line 1"


def test_missing_event_returns_none(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    assert store.get_event("nope") is None


def test_source_cursor_persists(tmp_path):
    path = str(tmp_path / "t.sqlite")
    store = Store(path)
    assert store.get_cursor("github_issues:acme/widget") is None
    store.set_cursor("github_issues:acme/widget", "2026-09-02T09:30:00Z")
    assert Store(path).get_cursor("github_issues:acme/widget") == \
        "2026-09-02T09:30:00Z"


def test_set_cursor_overwrites(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    store.set_cursor("s", "1")
    store.set_cursor("s", "2")
    assert store.get_cursor("s") == "2"


def test_store_is_readable_from_another_thread(tmp_path):
    # FastAPI runs sync endpoints in a threadpool: a connection pinned to the
    # creating thread turns every dashboard request into a 500.
    import threading

    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(1)])
    result = {}

    def read():
        try:
            result["count"] = store.count_events()
        except Exception as e:                       # noqa: BLE001
            result["error"] = e

    thread = threading.Thread(target=read)
    thread.start()
    thread.join()
    assert result == {"count": 1}


def test_store_uses_wal_so_a_reader_is_not_blocked_by_a_writer(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    mode = store.db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_concurrent_readers_do_not_corrupt_the_connection(tmp_path):
    # The dashboard asks for /api/stats and /api/clusters at the same time and
    # FastAPI runs both in its threadpool. Sharing one sqlite connection across
    # those threads raises InterfaceError: bad parameter or other API misuse.
    import threading

    store = Store(str(tmp_path / "t.sqlite"))
    store.insert_events([make_event(i) for i in range(50)])
    errors = []

    def hammer():
        try:
            for _ in range(40):
                store.count_events()
                store.get_event("evt-7")
                store.list_clusters()
        except Exception as e:                       # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def clustered(store, cluster_id, label, titles, times):
    events = [Event(id=f"{cluster_id}-{i}", source="s",
                    type="dev.aiops.log.line", title=t, time=when)
              for i, (t, when) in enumerate(zip(titles, times))]
    store.insert_events(events)
    store.assign_clusters({e.id: cluster_id for e in events},
                          {cluster_id: (label, "log")})
    return events


def test_search_finds_clusters_by_words_in_the_template(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    clustered(store, "log-a", "Failed password for <*> from <*>",
              ["Failed password for root"], ["2026-09-01T10:00:00"])
    clustered(store, "log-b", "Disk full on <*>",
              ["Disk full on /dev/sda1"], ["2026-09-01T11:00:00"])
    hits = store.search_clusters("password")
    assert [h["id"] for h in hits] == ["log-a"]


def test_search_also_matches_the_verdict_summary(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    clustered(store, "log-a", "Failed password for <*>", ["x"],
              ["2026-09-01T10:00:00"])
    store.upsert_verdict("log-a", {
        "category": "error", "severity": "medium",
        "summary": "Repeated SSH brute force attempts against root",
        "confidence": 0.9, "evidence": [], "tier": "auto",
        "model": "m", "promptversion": "1.1"})
    assert [h["id"] for h in store.search_clusters("brute force")] == ["log-a"]


def test_search_survives_punctuation_that_would_break_fts_syntax(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    clustered(store, "log-a", "Failed password for <*>", ["x"],
              ["2026-09-01T10:00:00"])
    assert store.search_clusters('when did "password" errors start?') != []
    assert store.search_clusters("AND OR NOT") == []


def test_timespan_reports_first_last_and_count(tmp_path):
    store = Store(str(tmp_path / "t.sqlite"))
    clustered(store, "log-a", "Failed password for <*>",
              ["a", "b", "c"],
              ["2026-09-01T10:00:00", "2026-09-03T08:00:00",
               "2026-09-02T12:00:00"])
    span = store.timespan("log-a")
    assert span["first"] == "2026-09-01T10:00:00"
    assert span["last"] == "2026-09-03T08:00:00"
    assert span["events"] == 3


def test_events_are_indexed_by_cluster(tmp_path):
    store = Store(str(tmp_path / "s.sqlite"))
    names = [r[1] for r in store.db.execute("PRAGMA index_list(events)")]
    assert "events_clusterid" in names
