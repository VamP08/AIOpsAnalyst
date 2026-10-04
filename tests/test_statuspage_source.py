import httpx

from aiops.sources.statuspage import StatuspageSource

INCIDENT = {
    "id": "32sg73xwyq89",
    "name": "Network Performance Issues in Eastern North America",
    "status": "resolved",
    "impact": "minor",
    "created_at": "2026-09-28T20:36:00.150Z",
    "updated_at": "2026-09-28T21:10:00.239Z",
    "shortlink": "https://stspg.io/abc",
    "incident_updates": [   # the API lists newest first
        {"status": "resolved", "body": "This incident has been resolved.",
         "created_at": "2026-09-28T21:10:00.000Z"},
        {"status": "investigating",
         "body": "Customers may observe elevated error rates in Eastern North America.",
         "created_at": "2026-09-28T20:36:00.227Z"},
    ],
    "components": [{"name": "Network"}, {"name": "CDN/Cache"}],
}


def make_source(incidents, captured=None):
    def handler(request):
        if captured is not None:
            captured.append(request)
        return httpx.Response(200, json={"page": {}, "incidents": incidents})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return StatuspageSource(page="www.cloudflarestatus.com", client=client)


def test_incident_becomes_event_with_first_report_as_body():
    [e] = list(make_source([INCIDENT]).fetch())
    assert e.source == "statuspage://www.cloudflarestatus.com"
    assert e.type == "com.statuspage.incident"
    assert e.subject == "32sg73xwyq89"
    assert e.title == "Network Performance Issues in Eastern North America"
    # what was known when it was raised, not the resolution note
    assert e.body.startswith("Customers may observe elevated error rates")
    assert e.time == "2026-09-28T21:10:00.239Z"
    assert e.url == "https://www.cloudflarestatus.com/incidents/32sg73xwyq89"
    assert e.attributes["impact"] == "minor"
    assert e.attributes["components"] == "Network,CDN/Cache"
    assert e.severitynumber == 13  # minor impact -> WARN


def test_requests_the_public_incidents_endpoint():
    captured = []
    list(make_source([INCIDENT], captured).fetch())
    assert str(captured[0].url) == \
        "https://www.cloudflarestatus.com/api/v2/incidents.json"


def test_cursor_skips_incidents_not_updated_since():
    older = {**INCIDENT, "id": "old", "updated_at": "2026-09-01T00:00:00.000Z"}
    src = make_source([INCIDENT, older])
    events = list(src.fetch(cursor="2026-09-10T00:00:00.000Z"))
    assert [e.subject for e in events] == ["32sg73xwyq89"]
    assert src.cursor == "2026-09-28T21:10:00.239Z"


def test_event_id_changes_only_when_the_incident_does():
    a = list(make_source([INCIDENT]).fetch())[0].id
    b = list(make_source([INCIDENT]).fetch())[0].id
    assert a == b
    edited = {**INCIDENT, "updated_at": "2026-09-29T00:00:00.000Z"}
    assert list(make_source([edited]).fetch())[0].id != a


def test_incident_without_updates_still_becomes_an_event():
    bare = {**INCIDENT, "incident_updates": [], "components": []}
    [e] = list(make_source([bare]).fetch())
    assert e.body is None
    assert e.attributes["components"] == ""
