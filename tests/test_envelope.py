from aiops.envelope import Event, severity_number


def make_event(**overrides):
    fields = dict(
        id="evt-1",
        source="syslog://web-1/nginx",
        type="dev.aiops.log.line",
        time="2026-09-02T10:00:00Z",
        title="GET /api/checkout 500",
    )
    fields.update(overrides)
    return Event(**fields)


def test_minimal_event_serializes_cloudevents_shape():
    d = make_event().to_dict()
    assert d["specversion"] == "1.0"
    assert d["id"] == "evt-1"
    assert d["source"] == "syslog://web-1/nginx"
    assert d["type"] == "dev.aiops.log.line"
    assert d["data"]["title"] == "GET /api/checkout 500"


def test_unset_optional_fields_are_omitted_from_dict():
    d = make_event().to_dict()
    assert "subject" not in d
    assert "severitytext" not in d
    assert "clusterid" not in d


def test_extension_attribute_names_follow_cloudevents_rule():
    # CE spec: context attribute names are lowercase a-z0-9, max 20 chars.
    d = make_event(
        subject="issue-42",
        severitytext="ERROR",
        severitynumber=17,
        fingerprint="abc123",
        clusterid="c-7",
    ).to_dict()
    for key in set(d) - {"data"}:
        assert key == key.lower() and key.isalnum() and len(key) <= 20


def test_body_attributes_and_url_live_under_data():
    d = make_event(
        body="upstream timed out",
        attributes={"host": "web-1", "service": "nginx"},
        url="https://example.com/log/1",
    ).to_dict()
    assert d["data"]["body"] == "upstream timed out"
    assert d["data"]["attributes"]["host"] == "web-1"
    assert d["data"]["url"] == "https://example.com/log/1"


def test_events_are_immutable():
    e = make_event()
    try:
        e.id = "changed"
        assert False, "Event must be frozen"
    except AttributeError:
        pass


def test_severity_number_maps_common_level_strings():
    assert severity_number("ERROR") == 17
    assert severity_number("error") == 17
    assert severity_number("WARN") == 13
    assert severity_number("warning") == 13
    assert severity_number("INFO") == 9
    assert severity_number("DEBUG") == 5
    assert severity_number("FATAL") == 21
    assert severity_number("critical") == 21
    assert severity_number("TRACE") == 1


def test_severity_number_unknown_level_is_zero():
    assert severity_number("verbose-custom") == 0
    assert severity_number("") == 0
