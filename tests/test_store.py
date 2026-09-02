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
